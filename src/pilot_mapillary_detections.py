"""Imagery-phase pilot: are Mapillary's PRECOMPUTED detections usable?

Decides the imagery phase's build-vs-harvest question. Mapillary runs its own
vision models server-side and exposes per-image "detections" (segmentation
polygons with taxonomy labels). If those cover Houston's imagery and the
classes needed (person, vehicle, sidewalk, vegetation), feature extraction
becomes API harvesting and no local GPU work is required. If not, plan B is
running our own models (piloted separately, full run on the RTX 3070).

Method: sample images along three street archetypes (a HIN corridor, an
overlooked high-design-risk corridor, a covered local street), pull each
image's detections, tally availability by class and capture year, and render
overlay galleries for visual quality review.

Outputs:
  reports/mapillary_pilot_report.md
  reports/mapillary_pilot/<site>_<n>.jpg   (detection overlays)
"""

import base64
import io
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
import requests

import config as cfg

REPORTS = cfg.REPORTS
GALLERY = REPORTS / "mapillary_pilot"
API = "https://graph.mapillary.com"

SITES = {  # street name -> how many sample points along it
    "Westheimer Road": 4,        # HIN corridor (dense harm, dense imagery)
    "Bay Area Boulevard": 4,     # the overlooked archetype (high design risk, low history)
    "Vassar Street": 3,          # quiet covered local street (Montrose area)
}
PER_POINT = 25                   # images requested per sample point
MAX_DETCALLS = 320               # cap on detection lookups (politeness)
BUCKETS = {"person": "human", "vehicle": "object--vehicle", "sidewalk": "construction--flat--sidewalk",
           "road": "construction--flat--road", "vegetation": "nature--vegetation",
           "marking": "marking", "sign": "object--sign"}
COLORS = {"person": (215, 48, 31), "vehicle": (49, 99, 206), "sidewalk": (200, 162, 75),
          "vegetation": (46, 125, 79), "road": (130, 130, 130)}


def token():
    import os
    return os.environ.get("MAPILLARY_TOKEN") or \
        (cfg.EXTERNAL / ".mapillary_token").read_text().strip()


def get(url, **params):
    params["access_token"] = token()
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def sample_points(seg, name, n):
    g = seg[seg["name"] == name]
    if g.empty:
        return []
    g = g.sort_values("length_ft", ascending=False).head(n)
    mids = g.geometry.to_crs(cfg.CRS_FT).interpolate(0.5, normalized=True).to_crs(4326)
    return [(p.y, p.x) for p in mids]


def images_near(lat, lon, limit=PER_POINT):
    """Image ids near a point, from the z14 vector tiles (the Graph API's bbox
    search returns empty for areas the tiles prove are covered, so discovery
    uses tiles; the Graph API is used per-image for detections/thumbnails)."""
    import math
    import mapbox_vector_tile
    z = 14
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    yr = math.radians(lat)
    y = int((1 - math.log(math.tan(yr) + 1 / math.cos(yr)) / math.pi) / 2 * n)
    r = requests.get(f"https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}",
                     params={"access_token": token()}, timeout=30)
    if r.status_code != 200 or not r.content:
        return []
    layers = mapbox_vector_tile.decode(r.content)
    layer = layers.get("image")
    if not layer:
        return []
    ext = layer.get("extent", 4096)
    w = x / n * 360 - 180
    e = (x + 1) / n * 360 - 180
    s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    nn = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    d = 0.0013  # ~140 m
    out = []
    for f in layer["features"]:
        gx, gy = f["geometry"]["coordinates"]
        ilon = w + (gx / ext) * (e - w)
        ilat = s + (gy / ext) * (nn - s)
        if abs(ilon - lon) <= d and abs(ilat - lat) <= d and f["properties"].get("id"):
            out.append({"id": f["properties"]["id"],
                        "captured_at": f["properties"].get("captured_at")})
    out.sort(key=lambda im: im.get("captured_at") or 0, reverse=True)
    return out[:limit]


def thumb_url(image_id):
    try:
        return get(f"{API}/{image_id}", fields="thumb_1024_url").get("thumb_1024_url")
    except Exception:
        return None


def detections_for(image_id):
    js = get(f"{API}/{image_id}/detections", fields="value,geometry")
    return js.get("data", [])


def decode_polys(det):
    """Mapillary detection geometry: base64 vector tile -> [(cls, [(x01,y01)..])]."""
    import mapbox_vector_tile
    out = []
    try:
        layers = mapbox_vector_tile.decode(base64.b64decode(det["geometry"]))
        for layer in layers.values():
            ext = layer.get("extent", 4096)
            for f in layer["features"]:
                geom = f["geometry"]
                rings = geom["coordinates"] if geom["type"] == "Polygon" else \
                    [r for poly in geom["coordinates"] for r in poly]
                for ring in rings:
                    out.append([(x / ext, 1 - y / ext) for x, y in ring])
    except Exception:
        pass
    return out


def bucket(value):
    for b, prefix in BUCKETS.items():
        if value.startswith(prefix) or prefix in value:
            return b
    return None


def overlay(img_bytes, dets, path):
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    dr = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    for det in dets:
        b = bucket(det["value"])
        if b not in COLORS:
            continue
        col = COLORS[b]
        for ring in decode_polys(det):
            pts = [(x * W, y * H) for x, y in ring]
            if len(pts) >= 3:
                dr.polygon(pts, outline=col + (255,), fill=col + (60,))
    im.save(path, quality=88)


def main():
    GALLERY.mkdir(exist_ok=True)
    seg = gpd.read_file(cfg.DOCS / "segments_vz.geojson")

    rows, det_calls = [], 0
    galleries = defaultdict(int)
    for site, npts in SITES.items():
        pts = sample_points(seg, site, npts)
        imgs = []
        for lat, lon in pts:
            imgs += images_near(lat, lon)
            time.sleep(0.15)
        # dedupe, spread across years
        imgs = list({im["id"]: im for im in imgs}.values())
        print(f"[{site}] {len(imgs)} images found")
        for im in imgs:
            if det_calls >= MAX_DETCALLS:
                break
            try:
                dets = detections_for(im["id"])
            except Exception as e:
                dets = None
            det_calls += 1
            time.sleep(0.12)
            year = None
            if im.get("captured_at"):
                year = datetime.fromtimestamp(im["captured_at"] / 1000, tz=timezone.utc).year
            counts = Counter(b for d in (dets or []) if (b := bucket(d["value"])))
            rows.append({"site": site, "id": im["id"], "year": year,
                         "api_ok": dets is not None, "n_det": len(dets or []),
                         **{f"n_{b}": counts.get(b, 0) for b in BUCKETS}})
            # gallery: first 8 per site with any detections
            if dets and galleries[site] < 8:
                url = thumb_url(im["id"])
                try:
                    jpg = requests.get(url, timeout=30).content if url else None
                    if not jpg:
                        raise ValueError("no thumbnail")
                    overlay(jpg, dets, GALLERY / f"{site.split()[0].lower()}_{galleries[site]+1}.jpg")
                    galleries[site] += 1
                except Exception:
                    pass

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No images sampled; tile discovery returned nothing.")
    df.to_csv(REPORTS / "mapillary_pilot_sample.csv", index=False)

    def blk(g):
        has = (g.n_det > 0).mean()
        return (f"{len(g)} images | {100*g.api_ok.mean():.0f}% API ok | {100*has:.0f}% with detections | "
                f"person on {100*(g.n_person>0).mean():.0f}% | vehicle {100*(g.n_vehicle>0).mean():.0f}% | "
                f"sidewalk {100*(g.n_sidewalk>0).mean():.0f}% | vegetation {100*(g.n_vegetation>0).mean():.0f}%")

    lines = [
        "# Mapillary Precomputed-Detections Pilot",
        "",
        f"Generated by `src/pilot_mapillary_detections.py`, {datetime.now().date()}. "
        f"{len(df)} images sampled across {len(SITES)} street archetypes; "
        f"{det_calls} detection lookups.",
        "",
        f"## Overall: {blk(df)}",
        "",
        "## By site",
        "",
    ]
    for site, g in df.groupby("site"):
        lines.append(f"- **{site}**: {blk(g)}")
    lines += ["", "## By capture year (the vintage question)", "",
              "| Year | images | % with detections | median detections/image |", "|---|---|---|---|"]
    for yr, g in df.groupby("year"):
        lines.append(f"| {int(yr)} | {len(g)} | {100*(g.n_det>0).mean():.0f}% | {g.n_det.median():.0f} |")
    lines += ["", "## Visual QA",
              f"Overlay gallery in `reports/mapillary_pilot/` ({sum(galleries.values())} images): "
              "red = person, blue = vehicle, gold = sidewalk, green = vegetation, grey = road.",
              "", "## Verdict criteria",
              "- Harvest path viable if detections exist on the large majority of images",
              "  (including the pre-2020 vintage) and person/vehicle/sidewalk classes are",
              "  present and visually sane.",
              "- Otherwise: plan B, own models (pilot ~100 images on the M1, full run on the RTX 3070).", ""]
    (REPORTS / "mapillary_pilot_report.md").write_text("\n".join(lines))
    print(f"\nWrote {REPORTS / 'mapillary_pilot_report.md'}")
    print("\n".join(lines[4:20]))


if __name__ == "__main__":
    main()
