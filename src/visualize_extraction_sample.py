"""Visual audit of the street-view extraction: what did the models actually see?

Re-runs the EXACT inference code path from extract_streetview_features.py
(same pano slicing, same SegFormer processing, same detection threshold and
self-capture rule) on a small sample of already-downloaded images, but keeps
the pixel-level outputs and renders them:

  - segmentation overlay (Cityscapes classes colorized, per-class pixel shares)
  - detection boxes (counted detections, self-capture exclusions, and
    below-threshold detections the pipeline ignored)

For panoramas the original equirectangular frame is shown above its four
gnomonic views, so the slicing itself is visible.

Outputs one PNG per image plus an index.html in reports/extraction_gallery/.
Each image's recomputed features are printed next to the values stored by the
overnight run (small floating-point differences are expected, nothing else).

Run on the extraction PC (images live in data/imagery/):
  run_visualize_sample.bat            five representative images
  ... visualize_extraction_sample.py --n 8
  ... visualize_extraction_sample.py --ids 123,456
"""

import argparse
import math
import webbrowser
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from extract_streetview_features import (COCO, DET_THRESH, IMG_DIR, IMG_FEATS,
                                         MANIFEST, SELF_CAPTURE_AREA,
                                         equirect_views)
import config as cfg

GALLERY = cfg.REPORTS / "extraction_gallery"
LOW_THRESH = 0.25          # draw ignored detections scoring in [0.25, 0.5)

# standard Cityscapes class colors (what the segmenter was trained on)
PALETTE = {
    "road": (128, 64, 128), "sidewalk": (244, 35, 232), "building": (70, 70, 70),
    "wall": (102, 102, 156), "fence": (190, 153, 153), "pole": (153, 153, 153),
    "traffic light": (250, 170, 30), "traffic sign": (220, 220, 0),
    "vegetation": (107, 142, 35), "terrain": (152, 251, 152),
    "sky": (70, 130, 180), "person": (220, 20, 60), "rider": (255, 0, 0),
    "car": (0, 0, 142), "truck": (0, 0, 70), "bus": (0, 60, 100),
    "train": (0, 80, 100), "motorcycle": (0, 0, 230), "bicycle": (119, 11, 32),
}
DET_COLORS = {"person": (0, 200, 0), "bicycle": (0, 230, 230),
              "vehicle": (255, 140, 0), "traffic_light": (255, 230, 0),
              "self_capture": (255, 0, 0), "below threshold": (150, 150, 150)}


def font(size=16):
    from PIL import ImageFont
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def load_models():
    import torch
    from torchvision.models.detection import (FasterRCNN_ResNet50_FPN_V2_Weights,
                                              fasterrcnn_resnet50_fpn_v2)
    from transformers import (SegformerForSemanticSegmentation,
                              SegformerImageProcessor)
    device = ("cuda" if torch.cuda.is_available()
              else "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"[viz] device: {device}")
    name = "nvidia/segformer-b2-finetuned-cityscapes-1024-1024"
    proc = SegformerImageProcessor.from_pretrained(name)
    seg = SegformerForSemanticSegmentation.from_pretrained(name).to(device).eval()
    det = fasterrcnn_resnet50_fpn_v2(
        weights=FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT).to(device).eval()
    id2label = {int(k): v for k, v in seg.config.id2label.items()}
    return device, proc, seg, det, id2label


def segment_view(im, device, proc, seg_model, id2label):
    """Same computation as the pipeline's seg_shares, plus the class map."""
    import torch
    from PIL import Image
    inputs = proc(images=[im], return_tensors="pt").to(device)
    with torch.no_grad(), torch.autocast(device, enabled=device == "cuda"):
        logits = seg_model(**inputs).logits
    pred = logits.argmax(1)[0].cpu().numpy()               # shares at this res,
    lab, cnt = np.unique(pred, return_counts=True)         # exactly as pipeline
    shares = {id2label[int(l)]: float(c) / float(cnt.sum())
              for l, c in zip(lab, cnt)}
    color = np.zeros((*pred.shape, 3), dtype=np.uint8)
    for l in lab:
        color[pred == l] = PALETTE.get(id2label[int(l)], (255, 255, 255))
    overlay = Image.blend(im, Image.fromarray(color).resize(im.size, Image.NEAREST), 0.45)
    return shares, overlay


def detect_view(im, device, det_model):
    """Same rules as the pipeline's det_counts, plus every box for drawing."""
    import torch
    tens = (torch.from_numpy(np.asarray(im)).permute(2, 0, 1)
            .float().div(255).to(device))
    with torch.no_grad():
        p = det_model([tens])[0]
    W, H = im.size
    counts = {"person": 0, "bicycle": 0, "vehicle": 0, "traffic_light": 0,
              "self_capture": 0}
    boxes = []                                   # (kind, name, score, box)
    for lb, sc, bx in zip(p["labels"].tolist(), p["scores"].tolist(),
                          p["boxes"].tolist()):
        if lb not in COCO or sc < LOW_THRESH:
            continue
        name = COCO[lb]
        if sc < DET_THRESH:
            boxes.append(("below threshold", name, sc, bx))
            continue
        if name == "person":
            area = (bx[2] - bx[0]) * (bx[3] - bx[1]) / (W * H)
            if area > SELF_CAPTURE_AREA:
                counts["self_capture"] += 1
                boxes.append(("self_capture", name, sc, bx))
                continue
        counts[name] += 1
        boxes.append(("counted", name, sc, bx))
    return counts, boxes


def draw_boxes(im, boxes):
    from PIL import ImageDraw
    out = im.copy()
    dr = ImageDraw.Draw(out)
    f = font(14)
    for kind, name, sc, bx in boxes:
        color = DET_COLORS["below threshold"] if kind == "below threshold" \
            else DET_COLORS["self_capture"] if kind == "self_capture" \
            else DET_COLORS[name]
        width = 1 if kind == "below threshold" else 3
        dr.rectangle(bx, outline=color, width=width)
        tag = f"{name} {sc:.2f}"
        if kind == "self_capture":
            tag += " excluded"
        elif kind == "below threshold":
            tag += " ignored"
        x, y = bx[0], max(bx[1] - 16, 0)
        tw = dr.textlength(tag, font=f)
        dr.rectangle([x, y, x + tw + 4, y + 16], fill=color)
        dr.text((x + 2, y + 1), tag, fill=(0, 0, 0), font=f)
    return out


def caption_strip(lines, width, size=16, pad=6):
    from PIL import Image, ImageDraw
    f = font(size)
    h = pad * 2 + len(lines) * (size + 6)
    im = Image.new("RGB", (width, h), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    y = pad
    for parts in lines:                          # [(text, color|None), ...]
        x = pad
        for text, color in parts:
            if color:
                dr.rectangle([x, y + 3, x + 12, y + 15], fill=color)
                x += 16
            dr.text((x, y), text, fill=(20, 20, 20), font=f)
            x += dr.textlength(text, font=f) + 14
        y += size + 6
    return im


def hstack(imgs, pad=6, bg=(255, 255, 255)):
    from PIL import Image
    h = max(i.height for i in imgs)
    w = sum(i.width for i in imgs) + pad * (len(imgs) - 1)
    out = Image.new("RGB", (w, h), bg)
    x = 0
    for i in imgs:
        out.paste(i, (x, 0))
        x += i.width + pad
    return out


def vstack(imgs, pad=6, bg=(255, 255, 255)):
    from PIL import Image
    w = max(i.width for i in imgs)
    h = sum(i.height for i in imgs) + pad * (len(imgs) - 1)
    out = Image.new("RGB", (w, h), bg)
    y = 0
    for i in imgs:
        out.paste(i, (0, y))
        y += i.height + pad
    return out


def pick_sample(n, ids):
    man = pd.read_parquet(MANIFEST)
    man = man[[(IMG_DIR / f"{i}.jpg").exists() for i in man.img_id]]
    if man.empty:
        raise SystemExit(f"No downloaded images found in {IMG_DIR}. "
                         "Run this on the PC that ran the extraction.")
    if ids:
        got = man[man.img_id.isin(ids)]
        missing = set(ids) - set(got.img_id)
        if missing:
            print(f"[viz] not on disk or not in manifest: {sorted(missing)}")
        return got
    stored = pd.read_parquet(IMG_FEATS) if IMG_FEATS.exists() else pd.DataFrame()
    m = man.merge(stored, on="img_id", how="left") if not stored.empty else man
    m = m.sort_values("img_id")                  # deterministic sample
    wanted = [
        ("pano with a counted person", (m.is_pano == 1) & (m.get("cnt_person", 0) >= 1)),
        ("pano with traffic", (m.is_pano == 1) & (m.get("cnt_vehicle", 0) >= 3)),
        ("pano with a self-capture exclusion",
         (m.is_pano == 1) & (m.get("cnt_self_capture", 0) >= 1)),
        ("flat image with traffic", (m.is_pano == 0) & (m.get("cnt_vehicle", 0) >= 2)),
        ("flat image with a traffic light",
         (m.is_pano == 0) & (m.get("cnt_traffic_light", 0) >= 1)),
    ]
    picks, seen = [], set()
    for why, mask in wanted:
        cand = m[mask & ~m.img_id.isin(seen)]
        if len(cand):
            row = cand.iloc[0]
            picks.append((row, why))
            seen.add(row.img_id)
        if len(picks) >= n:
            break
    for _, row in m[~m.img_id.isin(seen)].iterrows():   # top up if criteria thin
        if len(picks) >= n:
            break
        picks.append((row, "additional sample"))
        seen.add(row.img_id)
    return picks[:n]


def main():
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--ids", default="",
                    help="comma-separated Mapillary image ids to render instead")
    a = ap.parse_args()
    ids = [int(s) for s in a.ids.split(",") if s.strip()]

    picks = pick_sample(a.n, ids)
    if ids:
        picks = [(row, "requested id") for _, row in picks.iterrows()]
    device, proc, seg_model, det_model, id2label = load_models()
    stored = pd.read_parquet(IMG_FEATS) if IMG_FEATS.exists() else pd.DataFrame()
    GALLERY.mkdir(parents=True, exist_ok=True)
    sections = []

    for row, why in picks:
        iid = int(row.img_id)
        im = Image.open(IMG_DIR / f"{iid}.jpg").convert("RGB")
        pano = bool(row.is_pano)
        year = datetime.fromtimestamp(row.captured_at / 1000, tz=timezone.utc).year \
            if pd.notna(row.captured_at) else "?"
        views = ([("original equirectangular frame", None)] +
                 [(f"gnomonic view, yaw {y} deg", v)
                  for y, v in zip((0, 90, 180, 270), equirect_views(im))]) \
            if pano else [("single perspective image", im)]

        all_shares, total_counts, panels = [], None, []
        if pano:
            w = 640 * 3 + 12                     # match the trio panel width
            panels.append(vstack([caption_strip(
                [[(f"image {iid}  |  360 pano, captured {year}, "
                   f"segment {row.seg_id}  |  chosen as: {why}", None)]], w),
                im.resize((w, int(im.height * w / im.width)))]))
        for name, v in views:
            if v is None:
                continue
            shares, seg_overlay = segment_view(v, device, proc, seg_model, id2label)
            counts, boxes = detect_view(v, device, det_model)
            all_shares.append(shares)
            total_counts = counts if total_counts is None else \
                {k: total_counts[k] + counts[k] for k in counts}
            top = sorted(shares.items(), key=lambda kv: -kv[1])[:6]
            legend = [[(f"{name}", None)],
                      [(f"{k} {100*s:.0f}%", PALETTE.get(k, (255, 255, 255)))
                       for k, s in top]]
            det_line = [(f"{k.replace('_', ' ')}: {c}", DET_COLORS[k])
                        for k, c in counts.items() if c] or [("no detections at threshold 0.5", None)]
            legend.append(det_line)
            trio = hstack([v, seg_overlay, draw_boxes(v, boxes)])
            panels.append(vstack([caption_strip(legend, trio.width), trio]))
        if not pano:
            panels.insert(0, caption_strip(
                [[(f"image {iid}  |  flat, captured {year}, "
                   f"segment {row.seg_id}  |  chosen as: {why}", None)],
                 [("columns: original, segmentation overlay, detections "
                   "(thin gray boxes scored below 0.5 and were ignored)", None)]],
                panels[0].width if panels else im.width * 3))

        page = vstack(panels, pad=10)
        out_png = GALLERY / f"sample_{iid}.png"
        page.save(out_png)

        # recomputed per-image features, pipeline arithmetic: shares averaged
        # across views, counts summed
        keys = {k for s in all_shares for k in s}
        mean_sh = {k: float(np.mean([s.get(k, 0.0) for s in all_shares]))
                   for k in keys}
        srow = stored[stored.img_id == iid].iloc[0] if (
            not stored.empty and (stored.img_id == iid).any()) else None
        comp = []
        for k in ["road", "sidewalk", "building", "vegetation", "sky"]:
            stored_v = (f"{srow[f'share_{k}']:.3f}"
                        if srow is not None and f"share_{k}" in srow and
                        pd.notna(srow.get(f"share_{k}")) else "n/a")
            comp.append((f"share {k}", f"{mean_sh.get(k, 0):.3f}", stored_v))
        for k in ["person", "vehicle", "bicycle", "traffic_light", "self_capture"]:
            stored_v = (f"{srow[f'cnt_{k}']:.0f}"
                        if srow is not None and f"cnt_{k}" in srow and
                        pd.notna(srow.get(f"cnt_{k}")) else "n/a")
            comp.append((f"count {k}", f"{total_counts[k]:.0f}", stored_v))
        print(f"\n[viz] image {iid} ({'pano' if pano else 'flat'}, {year}) "
              f"-> {out_png.name}")
        for label, now, was in comp:
            print(f"    {label:<22} recomputed {now:>8}   stored {was:>8}")
        rows = "".join(f"<tr><td>{l}</td><td>{n}</td><td>{w}</td></tr>"
                       for l, n, w in comp)
        sections.append(
            f"<h2>Image {iid} ({'360 pano' if pano else 'flat'}, {year}) "
            f"&mdash; {why}</h2>"
            f"<img src='sample_{iid}.png' style='max-width:100%'>"
            f"<table border=1 cellpadding=4 style='border-collapse:collapse'>"
            f"<tr><th>feature</th><th>recomputed now</th>"
            f"<th>stored by the overnight run</th></tr>{rows}</table>")

    html = ("<html><head><title>Extraction visual audit</title></head><body>"
            "<h1>Street-view extraction: visual audit sample</h1>"
            "<p>Each figure shows the exact inference path of the overnight "
            "run: pano slicing, Cityscapes segmentation (middle column), and "
            "object detections (right column; thin gray boxes scored below "
            "the 0.5 threshold and were not counted; red boxes were excluded "
            "by the self-capture guard). The table under each figure compares "
            "features recomputed now against the values the overnight run "
            "stored; small floating-point differences are expected.</p>"
            + "".join(sections) + "</body></html>")
    index = GALLERY / "index.html"
    index.write_text(html, encoding="utf-8")
    print(f"\n[viz] gallery: {index}")
    try:
        webbrowser.open(index.as_uri())
    except Exception:
        pass


if __name__ == "__main__":
    main()
