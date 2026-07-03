"""Size the imagery-extraction work: recent coverage + detection richness.

The pilot found Mapillary back-processed ALL vintages, but old imagery
(2012-13) carries only point features (poles, signs) while ~2019+ imagery
carries full-scene segmentation (vehicles, people, road, vegetation). This
scan sizes the two work buckets:

  A. RECENT COVERAGE (local, from the cached 4.79M image points): per-segment
     coverage using only images captured 2019+ (and 2022+), same rule as the
     audit (50 m sampling, image within 25 m, segment covered at >=50%).
  B. RICHNESS BY VINTAGE (API sample): stratified citywide sample of images
     across capture years; each image's detections classified as full-scene /
     points-only / none. Calibrates which vintages are harvestable.
  C. THE WORK PLAN: arterial+collector miles split into harvest (rich-vintage
     imagery nearby), own-CV on GPU (older imagery only), and no imagery.

Outputs:
  reports/mapillary_richness_scan.md
"""

import math
import time
from collections import Counter
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

import config as cfg

REPORTS, EXTERNAL, DOCS = cfg.REPORTS, cfg.EXTERNAL, cfg.DOCS
SAMPLE_FT, NEAR_FT, COVERED_FRAC = 164.0, 82.0, 0.5
MS2019 = datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
MS2022 = datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
N_TILES, PER_TILE_PER_ERA, MAX_DET = 30, 3, 400
ERAS = [(2012, 2014), (2015, 2017), (2018, 2020), (2021, 2023), (2024, 2027)]
FULL_PREFIX = ("construction--flat", "nature--", "human", "object--vehicle",
               "void--ego", "construction--structure")
POINT_PREFIX = ("object--support", "object--street-light", "object--sign",
                "object--traffic-sign", "marking--", "object--manhole",
                "object--fire-hydrant", "object--bench")


def token():
    import os
    return os.environ.get("MAPILLARY_TOKEN") or \
        (EXTERNAL / ".mapillary_token").read_text().strip()


# ---------------------------------------------------------------- part A ----
def coverage_since(pts, seg, cutoff_ms, label):
    sub = pts[pd.to_numeric(pts.captured_at, errors="coerce") >= cutoff_ms]
    if sub.empty:
        return None
    g = gpd.GeoDataFrame(sub, geometry=gpd.points_from_xy(sub.lon, sub.lat),
                         crs=4326).to_crs(cfg.CRS_FT)
    tree = cKDTree(np.c_[g.geometry.x, g.geometry.y])
    frac = []
    for geom in seg.geometry:
        n = max(int(geom.length // SAMPLE_FT), 1) + 1
        samples = [geom.interpolate(d) for d in np.linspace(0, geom.length, n + 1)]
        xy = np.array([[p.x, p.y] for p in samples])
        hits = [len(v) > 0 for v in tree.query_ball_point(xy, NEAR_FT)]
        frac.append(float(np.mean(hits)))
    out = pd.Series(frac, index=seg.index)
    print(f"[{label}] {len(sub):,} image points; "
          f"{100 * (out >= COVERED_FRAC).mean():.1f}% of segments covered")
    return out


# ---------------------------------------------------------------- part B ----
def tiles_over(boundary, k):
    from shapely.geometry import box
    z, n = 14, 2 ** 14
    minx, miny, maxx, maxy = boundary.total_bounds

    def tx(lon): return int((lon + 180) / 360 * n)
    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)

    cand = [(x, y) for x in range(tx(minx), tx(maxx) + 1)
            for y in range(ty(maxy), ty(miny) + 1)]

    def bounds(x, y):
        def lon(x_): return x_ / n * 360 - 180
        def lat(y_): return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y_ / n))))
        return box(lon(x), lat(y + 1), lon(x + 1), lat(y))

    keep = [t for t in cand if boundary.intersects(bounds(*t)).any()]
    rng = np.random.default_rng(42)
    return [keep[i] for i in rng.choice(len(keep), size=min(k, len(keep)), replace=False)]


def tile_images(x, y):
    import mapbox_vector_tile
    r = requests.get(f"https://tiles.mapillary.com/maps/vtp/mly1_public/2/14/{x}/{y}",
                     params={"access_token": token()}, timeout=30)
    if r.status_code != 200 or not r.content:
        return []
    layer = mapbox_vector_tile.decode(r.content).get("image")
    if not layer:
        return []
    return [(f["properties"]["id"], f["properties"].get("captured_at"))
            for f in layer["features"] if f["properties"].get("id")]


def classify(det_values):
    if not det_values:
        return "none"
    if any(v.startswith(FULL_PREFIX) for v in det_values):
        return "full"
    if any(v.startswith(POINT_PREFIX) for v in det_values):
        return "points_only"
    return "other"


def richness_sample():
    boundary = gpd.read_file(DOCS / "boundary.geojson").to_crs(4326)
    rows, calls = [], 0
    for x, y in tiles_over(boundary, N_TILES):
        imgs = tile_images(x, y)
        time.sleep(0.05)
        by_era = {e: [] for e in ERAS}
        for iid, cap in imgs:
            if not cap:
                continue
            yr = datetime.fromtimestamp(cap / 1000, tz=timezone.utc).year
            for e in ERAS:
                if e[0] <= yr <= e[1] and len(by_era[e]) < PER_TILE_PER_ERA:
                    by_era[e].append((iid, yr))
        for e, lst in by_era.items():
            for iid, yr in lst:
                if calls >= MAX_DET:
                    break
                try:
                    js = requests.get(f"https://graph.mapillary.com/{iid}/detections",
                                      params={"access_token": token(), "fields": "value"},
                                      timeout=30).json()
                    vals = [d["value"] for d in js.get("data", [])]
                    rows.append({"year": yr, "n_det": len(vals),
                                 "cls": classify(vals),
                                 "has_vehicle": any("object--vehicle" in v for v in vals),
                                 "has_person": any(v.startswith("human") for v in vals)})
                except Exception:
                    rows.append({"year": yr, "n_det": -1, "cls": "api_error",
                                 "has_vehicle": False, "has_person": False})
                calls += 1
                time.sleep(0.1)
    print(f"richness sample: {len(rows)} images, {calls} calls")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def main():
    pts = pd.read_parquet(cfg.external("mapillary_points.parquet"))
    seg = gpd.read_file(DOCS / "segments_vz.geojson").to_crs(cfg.CRS_FT)
    art = seg[seg.road_class.isin(["Major arterial", "Arterial", "Collector"])]

    cov19 = coverage_since(pts, seg, MS2019, "2019+")
    cov22 = coverage_since(pts, seg, MS2022, "2022+")
    covall = coverage_since(pts, seg, 0, "all years")

    rich = richness_sample()
    era_tab = (rich[rich.cls != "api_error"]
               .assign(era=lambda d: pd.cut(d.year, [2011, 2014, 2017, 2020, 2023, 2027],
                                            labels=["2012-14", "2015-17", "2018-20",
                                                    "2021-23", "2024-26"]))
               .groupby("era", observed=True)
               .agg(n=("cls", "size"),
                    full=("cls", lambda s: (s == "full").mean()),
                    points_only=("cls", lambda s: (s == "points_only").mean()),
                    none=("cls", lambda s: (s == "none").mean()),
                    vehicle=("has_vehicle", "mean"), person=("has_person", "mean")))

    # ---- the work plan (arterials + collectors) ----------------------------
    a19 = cov19.loc[art.index] >= COVERED_FRAC
    aall = covall.loc[art.index] >= COVERED_FRAC
    mi = art.length_ft / 5280
    harvest = float(mi[a19].sum())
    own_cv = float(mi[aall & ~a19].sum())
    none = float(mi[~aall].sum())
    tot = float(mi.sum())

    def p(x): return f"{100 * x:.0f}%"

    lines = [
        "# Mapillary Richness Scan (extraction work plan)",
        "",
        f"Generated by `src/scan_mapillary_richness.py`, {datetime.now().date()}.",
        "",
        "## A. Spatial coverage by imagery vintage (all 66,922 segments)",
        "",
        "| Vintage | segments covered | arterials+collectors covered |",
        "|---|---|---|",
        f"| Any year | {p((covall >= COVERED_FRAC).mean())} | {p(aall.mean())} |",
        f"| 2019+ | {p((cov19 >= COVERED_FRAC).mean())} | {p(a19.mean())} |",
        f"| 2022+ | {p((cov22 >= COVERED_FRAC).mean())} | {p((cov22.loc[art.index] >= COVERED_FRAC).mean())} |",
        "",
        "## B. Detection richness by capture era (citywide sample)",
        "",
        era_tab.round(2).to_markdown(),
        "",
        "full = full-scene segmentation (road/vegetation/vehicles/people): harvestable.",
        "points_only = poles/signs only: needs own CV on the photos.",
        "",
        "## C. The work plan (arterial + collector miles)",
        "",
        f"| Bucket | miles | share |",
        f"|---|---|---|",
        f"| HARVEST (2019+ imagery nearby) | {harvest:,.0f} | {p(harvest / tot)} |",
        f"| OWN CV on RTX 3070 (older imagery only) | {own_cv:,.0f} | {p(own_cv / tot)} |",
        f"| NO imagery | {none:,.0f} | {p(none / tot)} |",
        "",
        "Bucket rule: a segment is harvestable when 2019+ images cover it (>=50%",
        "of 50 m sample points within 25 m); the richness table validates 2019+",
        "as the full-segmentation era. Own-CV mileage uses the same photos the",
        "audit verified exist; only the labels must be computed locally.",
        "",
    ]
    (REPORTS / "mapillary_richness_scan.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
