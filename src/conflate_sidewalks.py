"""Conflate sidewalk presence onto the study area's segments (OSM-derived).

Houston publishes no complete citywide sidewalk inventory, so OSM is the best
available source. In the study area, OSM maps ~344 mi of sidewalks as SEPARATE
`footway=sidewalk` lines (far richer than the 16% of roads carrying a
`sidewalk=*` tag). This script associates those footway lines to each street
and infers which SIDE(S) have a sidewalk.

Method: sample points along each segment; at each point find the nearest
sidewalk footway within TOL_FT and decide which side of the road it's on
(left/right via the cross product with the segment's direction). Per segment:
  left_frac  = share of sample points with a sidewalk on the left
  right_frac = share on the right
  sidewalk_presence: both / one_side / none / partial
Falls back to the OSM road `sidewalk` tag where no footway is mapped but the
road is explicitly tagged. Provenance in `sidewalk_source`.

CAVEAT (documented): OSM sidewalk completeness is uneven — "none" means "no
sidewalk mapped near here", which is strong evidence but not a field survey.
"""

import math

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

import config as cfg
ROOT, PROCESSED, EXTERNAL, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.EXTERNAL, cfg.REPORTS

# Search distance scales with road width: a sidewalk sits just past the curb,
# which is ~half the roadway width from the centerline. tol = width/2 + setback.
SETBACK_FT = 25       # curb-to-sidewalk allowance
TOL_MIN, TOL_MAX = 30, 60  # clamp (avoid catching a parallel street's sidewalk)
N_SAMPLES = 11        # sample points per segment
SIDE_THRESH = 0.5     # >= this share of points => that side has a sidewalk
OWNED = ["sidewalk_presence", "sidewalk_source", "sw_left_frac", "sw_right_frac"]

seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")
seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])
print(f"Segments: {len(seg):,}")

# --- fetch + cache OSM sidewalk footways --------------------------------------
EXTERNAL.mkdir(parents=True, exist_ok=True)
cache = cfg.external("sidewalks.gpkg")
if cache.exists():
    sw = gpd.read_file(cache)
else:
    boundary = cfg.boundary(4326)
    f = ox.features_from_polygon(
        boundary.geometry.iloc[0], tags={"highway": "footway", "footway": "sidewalk"}
    )
    sw = f[f.geometry.type.isin(["LineString", "MultiLineString"])][["geometry"]].to_crs(2278)
    sw = sw.reset_index(drop=True)
    sw.to_file(cache, driver="GPKG")
print(f"Sidewalk footways: {len(sw):,} ({sw.length.sum()/5280:.0f} mi)")

# --- sample points + segment direction ----------------------------------------
fracs = np.linspace(0.05, 0.95, N_SAMPLES)
width = seg["roadway_width_ft"].fillna(24.0)  # default 2-lane if unknown
seg_tol = (width / 2 + SETBACK_FT).clip(lower=TOL_MIN, upper=TOL_MAX)
rows, pid = [], 0
for sid, geom, brg, tol in zip(seg["seg_id"], seg.geometry, seg["bearing"], seg_tol):
    b = math.radians(brg)
    dx, dy = math.sin(b), math.cos(b)  # unit direction (bearing 0 = +y/north)
    for fr in fracs:
        p = geom.interpolate(fr, normalized=True)
        rows.append({"pid": pid, "seg_id": sid, "dx": dx, "dy": dy,
                     "px": p.x, "py": p.y, "tol": tol, "geometry": p})
        pid += 1
pts = gpd.GeoDataFrame(rows, crs=seg.crs)

# Find ALL sidewalks within tolerance of each point (not just the nearest) so
# we can detect left AND right independently. Buffer each point by TOL_FT and
# intersect with the footway lines.
sw_idx = sw.reset_index(drop=True)
pts_buf = pts.copy()
pts_buf["geometry"] = pts.geometry.buffer(pts["tol"].values)
pairs = gpd.sjoin(pts_buf, sw_idx[["geometry"]], how="inner", predicate="intersects")

# side of road for each (point, sidewalk) pair: cross product of segment
# direction and (point -> nearest point on that sidewalk)
def side_of(r):
    g = sw_idx.geometry.iloc[int(r["index_right"])]
    from shapely.geometry import Point
    p = Point(r["px"], r["py"])
    q = g.interpolate(g.project(p))
    vx, vy = q.x - r["px"], q.y - r["py"]
    return "L" if (r["dx"] * vy - r["dy"] * vx) >= 0 else "R"

pairs["side"] = pairs.apply(side_of, axis=1)
# per sample point: is there a sidewalk on the left? on the right?
per_pt = pairs.groupby("pid")["side"].agg(lambda s: set(s))
left_pt = per_pt.apply(lambda s: "L" in s)
right_pt = per_pt.apply(lambda s: "R" in s)

pts = pts.set_index("pid")
pts["left"] = left_pt.reindex(pts.index).fillna(False)
pts["right"] = right_pt.reindex(pts.index).fillna(False)
side_frac = pts.groupby("seg_id")[["left", "right"]].mean()
side_frac = side_frac.reindex(seg["seg_id"]).fillna(0)
seg["sw_left_frac"] = side_frac["left"].round(2).values
seg["sw_right_frac"] = side_frac["right"].round(2).values

def classify(l, r):
    hi = (l >= SIDE_THRESH) + (r >= SIDE_THRESH)
    if hi == 2:
        return "both"
    if hi == 1:
        return "one_side"
    if l + r == 0:
        return "none"
    return "partial"

inferred = [classify(l, r) for l, r in zip(seg["sw_left_frac"], seg["sw_right_frac"])]
seg["sidewalk_presence"] = inferred
seg["sidewalk_source"] = "osm_footway"

# fall back to the road sidewalk TAG where no footway was found near the segment
no_footway = (seg["sw_left_frac"] + seg["sw_right_frac"] == 0) & seg["sidewalk"].notna()
seg.loc[no_footway, "sidewalk_presence"] = seg.loc[no_footway, "sidewalk"]
seg.loc[no_footway, "sidewalk_source"] = "osm_road_tag"

out = cfg.processed("segments_enriched.gpkg")
seg.to_file(out, layer="segments", driver="GPKG")
print(f"Saved {out}")

# --- report -------------------------------------------------------------------
def pct(m):
    return round(100 * m.mean(), 1)

arterial = seg["highway"].isin(["primary", "secondary", "tertiary"])
dist = seg["sidewalk_presence"].value_counts()
src = seg["sidewalk_source"].value_counts()
report = f"""# Sidewalk Conflation Report

Generated by `src/conflate_sidewalks.py`. **No official Houston sidewalk
inventory exists**, so this is OSM-derived: ~{sw.length.sum()/5280:.0f} mi of
`footway=sidewalk` lines associated to each street by side, with the OSM road
`sidewalk` tag as fallback. Sample points per segment: {N_SAMPLES}; match
distance scales with road width (half-width + {SETBACK_FT} ft, clamped
{TOL_MIN}–{TOL_MAX} ft); a side counts as present at >= {int(SIDE_THRESH*100)}%
of points.

## Sidewalk presence (all segments)

{dist.to_string()}

- Both sides: {pct(seg.sidewalk_presence.eq('both'))}% of segments
  ({pct(seg.loc[arterial,'sidewalk_presence'].eq('both'))}% of arterials/collectors).
- At least one side (both/one_side/partial): {pct(seg.sidewalk_presence.isin(['both','one_side','partial']))}%.
- None mapped: {pct(seg.sidewalk_presence.eq('none'))}%.

## Source

{src.to_string()}

## Notes

- **Missing ≠ absent.** "none" = no sidewalk mapped within the width-scaled
  search distance — strong evidence of a gap, but OSM completeness is uneven,
  not a field survey. Best available source given Houston has no published inventory.
- `sw_left_frac` / `sw_right_frac` give the continuous per-side coverage behind
  the category, for modeling or a finer map.
- Side (left/right) is relative to the segment's digitized direction, not
  compass N/S — it distinguishes "both vs one side", not which cardinal side.
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "sidewalk_conflation_report.md").write_text(report)
print(report)
