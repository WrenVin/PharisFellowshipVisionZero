"""Street-imagery feature extraction (the imagery phase's main engine).

Designed to run unattended on a GPU PC via run_extraction.bat (clone, double
click). Four resumable stages; rerunning skips completed work, so an
interrupted overnight run continues where it stopped.

  plan       tile-fetch all Mapillary image locations (with ids), sample the
             target network every 50 m, assign each sample point its nearest
             image within 25 m -> data/external/houston_extraction_manifest.parquet
  download   fetch 1024 px thumbnails -> data/imagery/<id>.jpg (skips existing)
  infer      GPU: semantic segmentation (SegFormer-B2, Cityscapes classes:
             road/sidewalk/building/vegetation/sky/...) + object detection
             (torchvision Faster R-CNN, COCO: person/bicycle/vehicles/lights)
             -> per-image features, appended in chunks (resumable)
  aggregate  per-segment means -> data/processed/houston_streetview_features.parquet
             + reports/streetview_extraction_report.md

Scope: arterials + collectors by default (the evidence-backed scope; ~84% of
their miles have imagery). STREETVIEW_SCOPE=all widens to every street;
STREETVIEW_SCOPE=smoke runs ~30 segments end-to-end as a test.

Self-capture guard: person detections occupying >15% of the frame (the
photographer in walking panoramas) are excluded from person counts and
tallied separately.
"""

import argparse
import io
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config as cfg

EXTERNAL, PROCESSED, REPORTS, DOCS = cfg.EXTERNAL, cfg.PROCESSED, cfg.REPORTS, cfg.DOCS
IMG_DIR = cfg.ROOT / "data" / "imagery"
MANIFEST = cfg.external("extraction_manifest.parquet")
IMG_FEATS = cfg.external("sv_image_features.parquet")
OUT = PROCESSED / f"{cfg.AREA}_streetview_features.parquet"

SAMPLE_FT, NEAR_FT = 164.0, 82.0          # 50 m sampling, 25 m match radius
MAX_PER_SEG = 12                          # cap images per segment (spread along it)
COCO = {1: "person", 2: "bicycle", 3: "vehicle", 4: "vehicle", 6: "vehicle",
        8: "vehicle", 10: "traffic_light"}
DET_THRESH = 0.5
SELF_CAPTURE_AREA = 0.15                  # person box >15% of frame = photographer
SEG_BATCH = 6


def token():
    t = os.environ.get("MAPILLARY_TOKEN")
    f = EXTERNAL / ".mapillary_token"
    if not t and f.exists():
        t = f.read_text().strip()
    if not t:
        raise SystemExit("No Mapillary token: set MAPILLARY_TOKEN or create "
                         "data/external/.mapillary_token (run_extraction.bat "
                         "prompts for it on first run).")
    return t


# ------------------------------------------------------------------ plan ----
def stage_plan(scope):
    import geopandas as gpd
    import mapbox_vector_tile
    from scipy.spatial import cKDTree
    from shapely.geometry import box

    if MANIFEST.exists():
        print(f"[plan] manifest exists ({MANIFEST.name}); skipping (delete to redo)")
        return
    seg = gpd.read_file(DOCS / "segments_vz.geojson").to_crs(cfg.CRS_FT)
    if scope == "arterials":
        seg = seg[seg.road_class.isin(["Major arterial", "Arterial", "Collector"])]
    elif scope == "smoke":
        seg = seg[seg.road_class.isin(["Major arterial", "Arterial"])].head(30)
    print(f"[plan] target: {len(seg):,} segments ({seg.length_ft.sum()/5280:,.0f} mi)")

    # tiles covering the target (z14), keeping image ids this time
    boundary = gpd.read_file(DOCS / "boundary.geojson").to_crs(4326)
    z, n = 14, 2 ** 14
    minx, miny, maxx, maxy = (seg.to_crs(4326).total_bounds if scope == "smoke"
                              else boundary.total_bounds)
    tx = lambda lon: int((lon + 180) / 360 * n)
    ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) +
                                       1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    cand = [(x, y) for x in range(tx(minx), tx(maxx) + 1)
            for y in range(ty(maxy), ty(miny) + 1)]

    def tbounds(x, y):
        lon = lambda x_: x_ / n * 360 - 180
        lat = lambda y_: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y_ / n))))
        return lon(x), lat(y + 1), lon(x + 1), lat(y)

    if scope != "smoke":
        bnd = boundary.geometry
        cand = [(x, y) for x, y in cand if bnd.intersects(box(*tbounds(x, y))).any()]
    print(f"[plan] fetching {len(cand):,} tiles for image locations...")
    rows = []
    for i, (x, y) in enumerate(cand):
        try:
            r = requests.get(
                f"https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}",
                params={"access_token": token()}, timeout=30)
            layer = mapbox_vector_tile.decode(r.content).get("image") if r.content else None
            if layer:
                ext = layer.get("extent", 4096)
                w, s, e, nn_ = tbounds(x, y)
                for f in layer["features"]:
                    p = f["properties"]
                    if not p.get("id"):
                        continue
                    gx, gy = f["geometry"]["coordinates"]
                    rows.append((p["id"], w + gx / ext * (e - w), s + gy / ext * (nn_ - s),
                                 p.get("captured_at"), int(bool(p.get("is_pano")))))
        except Exception:
            pass
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(cand)} tiles, {len(rows):,} image points")
        time.sleep(0.04)
    pts = pd.DataFrame(rows, columns=["img_id", "lon", "lat", "captured_at", "is_pano"])
    pts = pts.drop_duplicates("img_id")
    print(f"[plan] {len(pts):,} unique images citywide")

    gpts = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat),
                            crs=4326).to_crs(cfg.CRS_FT)
    tree = cKDTree(np.c_[gpts.geometry.x, gpts.geometry.y])
    assign = {}                                    # image row idx -> seg_id (first claim)
    for seg_id, geom in zip(seg.seg_id, seg.geometry):
        k = max(int(geom.length // SAMPLE_FT), 1) + 1
        samples = [geom.interpolate(d) for d in np.linspace(0, geom.length, k + 1)]
        taken = 0
        for p in samples:                          # ordered along the street -> spread
            if taken >= MAX_PER_SEG:
                break
            d, idx = tree.query([p.x, p.y], k=1)
            if d <= NEAR_FT and idx not in assign:
                assign[idx] = seg_id
                taken += 1
    man = gpts.iloc[sorted(assign)].drop(columns="geometry").copy()
    man["seg_id"] = [assign[i] for i in sorted(assign)]
    man.to_parquet(MANIFEST)
    print(f"[plan] manifest: {len(man):,} images across "
          f"{man.seg_id.nunique():,} segments -> {MANIFEST.name}")


# -------------------------------------------------------------- download ----
def stage_download(workers=8):
    from concurrent.futures import ThreadPoolExecutor
    man = pd.read_parquet(MANIFEST)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    todo = [i for i in man.img_id if not (IMG_DIR / f"{i}.jpg").exists()]
    print(f"[download] {len(man):,} planned; {len(man)-len(todo):,} already on disk; "
          f"{len(todo):,} to fetch")
    tok = token()

    def fetch(img_id):
        try:
            js = requests.get(f"https://graph.mapillary.com/{img_id}",
                              params={"access_token": tok, "fields": "thumb_1024_url"},
                              timeout=30).json()
            url = js.get("thumb_1024_url")
            if url:
                jpg = requests.get(url, timeout=60).content
                (IMG_DIR / f"{img_id}.jpg").write_bytes(jpg)
                return len(jpg)
        except Exception:
            return 0
        return 0

    done = bytes_ = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for nb in ex.map(fetch, todo):
            done += 1
            bytes_ += nb or 0
            if done % 500 == 0:
                print(f"  {done:,}/{len(todo):,} downloaded ({bytes_/1e9:.1f} GB)")
    print(f"[download] complete: {done:,} fetched this run ({bytes_/1e9:.1f} GB)")


# ----------------------------------------------------------------- infer ----
def stage_infer():
    import torch
    from PIL import Image
    from torchvision.models.detection import (FasterRCNN_ResNet50_FPN_V2_Weights,
                                              fasterrcnn_resnet50_fpn_v2)
    from transformers import (SegformerForSemanticSegmentation,
                              SegformerImageProcessor)

    device = ("cuda" if torch.cuda.is_available()
              else "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"[infer] device: {device}"
          + ("" if device == "cuda" else "  (no CUDA GPU found: this will be slow; "
                                         "fine for smoke tests)"))

    man = pd.read_parquet(MANIFEST)
    done_ids = set()
    if IMG_FEATS.exists():
        done_ids = set(pd.read_parquet(IMG_FEATS).img_id)
    todo = [i for i in man.img_id
            if i not in done_ids and (IMG_DIR / f"{i}.jpg").exists()]
    print(f"[infer] {len(todo):,} images to process ({len(done_ids):,} already done)")
    if not todo:
        return

    seg_name = "nvidia/segformer-b2-finetuned-cityscapes-1024-1024"
    proc = SegformerImageProcessor.from_pretrained(seg_name)
    seg_model = SegformerForSemanticSegmentation.from_pretrained(seg_name).to(device).eval()
    id2label = {int(k): v for k, v in seg_model.config.id2label.items()}
    det_model = fasterrcnn_resnet50_fpn_v2(
        weights=FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT).to(device).eval()
    use_amp = device == "cuda"

    def seg_shares(batch_imgs):
        inputs = proc(images=batch_imgs, return_tensors="pt").to(device)
        with torch.no_grad(), torch.autocast(device, enabled=use_amp):
            logits = seg_model(**inputs).logits          # B,C,h,w
        pred = logits.argmax(1)
        out = []
        for b in range(pred.shape[0]):
            lab, cnt = torch.unique(pred[b], return_counts=True)
            tot = float(cnt.sum())
            out.append({id2label[int(l)]: float(c) / tot
                        for l, c in zip(lab.tolist(), cnt.tolist())})
        return out

    def det_counts(batch_imgs):
        tens = [torch.from_numpy(np.asarray(im)).permute(2, 0, 1).float().div(255).to(device)
                for im in batch_imgs]
        with torch.no_grad():
            preds = det_model(tens)
        out = []
        for im, p in zip(batch_imgs, preds):
            W, H = im.size
            c = {"person": 0, "bicycle": 0, "vehicle": 0, "traffic_light": 0,
                 "self_capture": 0}
            for lb, sc, bx in zip(p["labels"].tolist(), p["scores"].tolist(),
                                  p["boxes"].tolist()):
                if sc < DET_THRESH or lb not in COCO:
                    continue
                name = COCO[lb]
                if name == "person":
                    area = (bx[2] - bx[0]) * (bx[3] - bx[1]) / (W * H)
                    if area > SELF_CAPTURE_AREA:
                        c["self_capture"] += 1
                        continue
                c[name] += 1
            out.append(c)
        return out

    t0, buf = time.time(), []
    for i in range(0, len(todo), SEG_BATCH):
        ids = todo[i:i + SEG_BATCH]
        imgs = []
        for iid in ids:
            try:
                imgs.append(Image.open(IMG_DIR / f"{iid}.jpg").convert("RGB"))
            except Exception:
                imgs.append(None)
        pairs = [(iid, im) for iid, im in zip(ids, imgs) if im is not None]
        if not pairs:
            continue
        ids2, imgs2 = zip(*pairs)
        shares = seg_shares(list(imgs2))
        counts = det_counts(list(imgs2))
        for iid, sh, ct in zip(ids2, shares, counts):
            buf.append({"img_id": iid,
                        **{f"share_{k.replace(' ', '_')}": v for k, v in sh.items()},
                        **{f"cnt_{k}": v for k, v in ct.items()}})
        if len(buf) >= 240 or i + SEG_BATCH >= len(todo):
            new = pd.DataFrame(buf)
            if IMG_FEATS.exists():
                new = pd.concat([pd.read_parquet(IMG_FEATS), new], ignore_index=True)
            new.to_parquet(IMG_FEATS)
            buf = []
            rate = (i + SEG_BATCH) / max(time.time() - t0, 1)
            eta = (len(todo) - i - SEG_BATCH) / max(rate, .01) / 3600
            print(f"  {min(i+SEG_BATCH, len(todo)):,}/{len(todo):,} "
                  f"({rate:.1f} img/s, ~{eta:.1f} h left)")
    print("[infer] complete")


# ------------------------------------------------------------- aggregate ----
def stage_aggregate():
    man = pd.read_parquet(MANIFEST)
    feats = pd.read_parquet(IMG_FEATS).merge(
        man[["img_id", "seg_id", "captured_at", "is_pano"]], on="img_id")
    share_cols = [c for c in feats.columns if c.startswith("share_")]
    cnt_cols = [c for c in feats.columns if c.startswith("cnt_")]
    agg = feats.groupby("seg_id").agg(
        sv_n_img=("img_id", "size"), sv_pano_share=("is_pano", "mean"),
        sv_year_med=("captured_at",
                     lambda s: datetime.fromtimestamp(np.median(s) / 1000,
                                                      tz=timezone.utc).year),
        **{c.replace("share_", "sv_"): (c, "mean") for c in share_cols},
        **{c.replace("cnt_", "sv_n_"): (c, "mean") for c in cnt_cols})
    agg = agg.reset_index()
    agg.to_parquet(OUT)
    rep = (f"# Street-view extraction report\n\nGenerated {datetime.now()}.\n\n"
           f"- Images processed: {len(feats):,} across {len(agg):,} segments\n"
           f"- Median images/segment: {agg.sv_n_img.median():.0f}\n"
           f"- Segment-mean person count: {agg.get('sv_n_person', pd.Series([0])).mean():.2f} "
           f"| vehicle: {agg.get('sv_n_vehicle', pd.Series([0])).mean():.2f}\n"
           f"- Output: `{OUT}`\n\nNext: commit/copy the output parquet back for the "
           f"model refit (v2).\n")
    (REPORTS / "streetview_extraction_report.md").write_text(rep)
    print(rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "plan", "download", "infer", "aggregate"])
    ap.add_argument("--scope", default=os.environ.get("STREETVIEW_SCOPE", "arterials"),
                    choices=["arterials", "all", "smoke"])
    a = ap.parse_args()
    print(f"=== street-view extraction | stage={a.stage} scope={a.scope} ===")
    if a.stage in ("all", "plan"):
        stage_plan(a.scope)
    if a.stage in ("all", "download"):
        stage_download()
    if a.stage in ("all", "infer"):
        stage_infer()
    if a.stage in ("all", "aggregate"):
        stage_aggregate()
    print("=== done ===")


if __name__ == "__main__":
    main()
