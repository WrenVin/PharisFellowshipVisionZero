"""Audit Mapillary street-view coverage along the published street network.

Decision-support for the modeling phase's imagery question: before spending
GPU-weeks extracting streetscape features from Mapillary (per Yue 2025, AAP
210:107851), measure whether Houston even HAS usable crowdsourced imagery —
and whether its coverage is biased by road class or neighborhood income
(coverage that skips poor neighborhoods would bake an equity bias into any
imagery-derived feature).

Method (mirrors the paper's coverage rule):
  1. Fetch all Mapillary image locations over the study area from the public
     vector tiles (z14, layer "image"), cached to data/external/.
  2. Sample each published segment every 50 m (matching the paper's sampling
     interval); a sample point is "covered" when any Mapillary image lies
     within 25 m of it.
  3. A segment is "covered" when >=50% of its sample points are covered
     (the paper's retention threshold).
  4. Cross coverage against road class, neighborhood income tier, and
     council district; report image recency (share captured 2020+).

Needs a free Mapillary client token (mapillary.com -> Developers -> register
application): env MAPILLARY_TOKEN or data/external/.mapillary_token (gitignored).

Outputs:
  data/processed/houston_mapillary_coverage.csv   (per-segment coverage)
  reports/mapillary_coverage_audit.md
  reports/mapillary_coverage_map.png
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree
from shapely.geometry import box

import config as cfg

DOCS, EXTERNAL, PROCESSED, REPORTS = cfg.DOCS, cfg.EXTERNAL, cfg.PROCESSED, cfg.REPORTS

ZOOM = 14                    # mly1_public serves individual image points at z14
TILE_URL = "https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}"
SAMPLE_FT = 164.0            # 50 m sampling interval along each segment
NEAR_FT = 82.0               # 25 m: an image this close to a sample point covers it
COVERED_FRAC = 0.5           # segment "covered" when >=50% of samples are covered
RECENT_MS = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
INC_EDGES = [50000, 100000, 150000]
INC_LAB = ["Under $50k", "$50-100k", "$100-150k", "$150k+"]


def get_token():
    tok = os.environ.get("MAPILLARY_TOKEN")
    if not tok:
        f = EXTERNAL / ".mapillary_token"
        if f.exists():
            tok = f.read_text().strip()
    if not tok:
        raise SystemExit(
            "No Mapillary token. Create a free one at mapillary.com "
            "(Dashboard -> Developers -> register application -> Client Token) "
            "and either set MAPILLARY_TOKEN or save it to "
            "data/external/.mapillary_token"
        )
    return tok


def tiles_for(bounds_4326):
    """All z14 slippy tiles whose box intersects the study-area bbox."""
    minx, miny, maxx, maxy = bounds_4326
    n = 2 ** ZOOM

    def tx(lon):
        return int((lon + 180) / 360 * n)

    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)

    return [(x, y) for x in range(tx(minx), tx(maxx) + 1)
            for y in range(ty(maxy), ty(miny) + 1)]   # y grows southward


def tile_bounds(x, y):
    n = 2 ** ZOOM

    def lon(x_):
        return x_ / n * 360 - 180

    def lat(y_):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y_ / n))))

    return lon(x), lat(y + 1), lon(x + 1), lat(y)


def fetch_points(boundary_4326, token):
    """All Mapillary image points (lon, lat, captured_at) in the study area (cached)."""
    cache = cfg.external("mapillary_points.parquet")
    if cache.exists():
        pts = pd.read_parquet(cache)
        print(f"Using cached Mapillary points: {len(pts):,} ({cache.name})")
        return pts

    import mapbox_vector_tile

    cand = tiles_for(boundary_4326.total_bounds)
    keep = [(x, y) for x, y in cand
            if boundary_4326.intersects(box(*tile_bounds(x, y))).any()]
    print(f"Fetching {len(keep):,} z{ZOOM} tiles (of {len(cand):,} in bbox) ...")

    rows, empty, errors = [], 0, 0
    for i, (x, y) in enumerate(keep):
        url = TILE_URL.format(z=ZOOM, x=x, y=y)
        try:
            r = requests.get(url, params={"access_token": token}, timeout=30)
            if r.status_code != 200 or not r.content:
                empty += 1
                continue
            layers = mapbox_vector_tile.decode(r.content)
            layer = layers.get("image")
            if not layer:
                empty += 1
                continue
            extent = layer.get("extent", 4096)
            w, s, e, n_ = tile_bounds(x, y)
            for f in layer["features"]:
                gx, gy = f["geometry"]["coordinates"]
                lon = w + (gx / extent) * (e - w)
                lat = s + (gy / extent) * (n_ - s)
                rows.append((lon, lat, f["properties"].get("captured_at")))
        except Exception:
            errors += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(keep)} tiles, {len(rows):,} image points so far")
        time.sleep(0.05)   # polite pacing, well under rate limits

    print(f"Tiles: {len(keep):,} fetched, {empty:,} empty, {errors:,} errors")
    pts = pd.DataFrame(rows, columns=["lon", "lat", "captured_at"])
    pts.to_parquet(cache)
    print(f"Cached {len(pts):,} image points -> {cache}")
    return pts


def sample_points(geom):
    """Points every SAMPLE_FT along a projected line (always incl. both ends)."""
    n = max(int(geom.length // SAMPLE_FT), 1) + 1
    return [geom.interpolate(d) for d in np.linspace(0, geom.length, n + 1)]


def main():
    token = get_token()
    boundary = gpd.read_file(DOCS / "boundary.geojson").to_crs(4326)
    pts = fetch_points(boundary, token)

    seg = gpd.read_file(DOCS / "segments_vz.geojson").to_crs(cfg.CRS_FT)
    inc = pd.read_csv(PROCESSED / f"{cfg.AREA}_segments.csv",
                      usecols=["seg_id", "median_hh_income"], low_memory=False)
    seg = seg.merge(inc, on="seg_id", how="left")
    seg["inc_tier"] = pd.cut(seg["median_hh_income"],
                             bins=[-1] + INC_EDGES + [10**9], labels=INC_LAB)

    if len(pts):
        gpts = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.lon, pts.lat),
                                crs=4326).to_crs(cfg.CRS_FT)
        tree = cKDTree(np.c_[gpts.geometry.x, gpts.geometry.y])
        recent = pd.to_numeric(gpts["captured_at"], errors="coerce") >= RECENT_MS
    else:
        tree, recent = None, None

    frac, n_near, rec_share = [], [], []
    for geom in seg.geometry:
        samples = sample_points(geom)
        if tree is None:
            frac.append(0.0); n_near.append(0); rec_share.append(np.nan)
            continue
        xy = np.array([[p.x, p.y] for p in samples])
        near_lists = tree.query_ball_point(xy, NEAR_FT)
        hits = [len(v) > 0 for v in near_lists]
        frac.append(float(np.mean(hits)))
        idx = sorted({j for v in near_lists for j in v})
        n_near.append(len(idx))
        rec_share.append(float(recent.iloc[idx].mean()) if idx else np.nan)

    seg["cov_frac"] = frac
    seg["n_img"] = n_near
    seg["recent_share"] = rec_share
    seg["covered"] = seg["cov_frac"] >= COVERED_FRAC

    out_csv = PROCESSED / f"{cfg.AREA}_mapillary_coverage.csv"
    seg.drop(columns="geometry")[["seg_id", "road_class", "district", "inc_tier",
                                  "cov_frac", "n_img", "recent_share", "covered"]] \
        .to_csv(out_csv, index=False)
    print(f"Wrote {out_csv}")

    # --- report ---------------------------------------------------------------
    def block(g):
        return (f"{100*g['covered'].mean():.1f}% covered | "
                f"median cov_frac {g['cov_frac'].median():.2f} | n={len(g):,}")

    mi = seg.geometry.length.sum() / 5280
    lines = [
        "# Mapillary Coverage Audit",
        "",
        f"Generated by `src/audit_mapillary_coverage.py` on {datetime.now().date()}.",
        f"Universe: the published dashboard network ({len(seg):,} segments, {mi:,.0f} mi).",
        f"Rule (per Yue 2025): sample every 50 m; a point is covered when a Mapillary",
        f"image lies within 25 m; a segment is covered at >={int(COVERED_FRAC*100)}% of points.",
        "",
        f"**Image points in study area: {len(pts):,}**",
        "",
        f"## Overall: {block(seg)}",
        "",
        "## By road class",
        "",
        "| Road class | Coverage |",
        "|---|---|",
    ]
    for k, g in seg.groupby("road_class"):
        lines.append(f"| {k} | {block(g)} |")
    lines += ["", "## By neighborhood income (the equity-bias check)", "",
              "| Income tier | Coverage |", "|---|---|"]
    for k, g in seg.groupby("inc_tier", observed=True):
        lines.append(f"| {k} | {block(g)} |")
    unk = seg[seg["inc_tier"].isna()]
    if len(unk):
        lines.append(f"| Unknown income | {block(unk)} |")
    lines += ["", "## By council district", "", "| District | Coverage |", "|---|---|"]
    for k, g in seg.groupby("district", dropna=False):
        lines.append(f"| {k} | {block(g)} |")
    r = seg["recent_share"].dropna()
    if len(r):
        lines += ["", f"## Recency: median {100*r.median():.0f}% of nearby images captured 2020+ "
                      f"(across segments with imagery)"]
    lines += ["", "## Interpretation notes",
              "- Coverage is crowdsourced: expect arterial bias. The income table is the",
              "  key equity read — a large coverage gap between tiers means imagery-derived",
              "  features would systematically miss the very streets the equity analysis",
              "  cares about, and any Phase-B extraction must handle that (weighting,",
              "  targeted collection, or restricting claims to covered classes).",
              "- `cov_frac` is spatial coverage only; it says nothing about image quality,",
              "  camera angle, or whether sidewalks are visible.", ""]
    (REPORTS / "mapillary_coverage_audit.md").write_text("\n".join(lines))
    print(f"Wrote {REPORTS / 'mapillary_coverage_audit.md'}")

    # --- map ------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 10))
        seg[~seg["covered"]].plot(ax=ax, color="#d9d4c7", linewidth=0.3)
        seg[seg["covered"]].plot(ax=ax, color="#2e7d4f", linewidth=0.5)
        ax.set_axis_off()
        ax.set_title(f"Mapillary coverage — green = covered "
                     f"({100*seg['covered'].mean():.0f}% of segments)")
        fig.savefig(REPORTS / "mapillary_coverage_map.png", dpi=150,
                    bbox_inches="tight")
        print(f"Wrote {REPORTS / 'mapillary_coverage_map.png'}")
    except Exception as e:
        print(f"(map skipped: {e})")

    print("\n" + "\n".join(lines[8:30]))


if __name__ == "__main__":
    main()
