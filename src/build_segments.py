"""Build intersection-to-intersection segments from the OSM graph.

Steps:
  1. Load the simplified directed graph, collapse to undirected
     (one row per physical street segment between junction nodes).
  2. Project to EPSG:2278 (TX State Plane South Central, US ft) so all
     distances are in honest feet.
  3. Normalize OSM tags into per-segment feature columns.
  4. Attach node context: junction degree and signal presence at each end.
  5. Detect (not yet merge) dual-carriageway pairs: one-way segments with a
     same-named antiparallel one-way twin nearby.
  6. Save segments GeoPackage + feature coverage report (markdown).
"""

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

import config as cfg
ROOT, RAW, PROCESSED, REPORTS = cfg.ROOT, cfg.RAW, cfg.PROCESSED, cfg.REPORTS

CRS_FT = 2278  # NAD83 / Texas South Central, US survey feet

G = ox.load_graphml(cfg.raw("drive.graphml"))
Gu = ox.convert.to_undirected(G)
Gp = ox.projection.project_graph(Gu, to_crs=CRS_FT)

nodes, edges = ox.graph_to_gdfs(Gp)
edges = edges.reset_index()  # u, v, key columns
print(f"Undirected segments: {len(edges):,}")


def first(v):
    """OSMnx stores merged-way tags as lists; take the first value.

    Missing tags arrive as None or float NaN depending on column presence —
    normalize both to None.
    """
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def joined(v):
    """Preserve all merged values for audit, pipe-joined."""
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    return None if v is None else str(v)


def parse_lanes(v):
    v = first(v)
    if v is None:
        return np.nan
    try:
        return float(str(v).split(";")[0])
    except ValueError:
        return np.nan


def parse_maxspeed_mph(v):
    v = first(v)
    if v is None:
        return np.nan
    s = str(v).lower().replace("mph", "").strip()
    try:
        return float(s.split(";")[0])
    except ValueError:
        return np.nan


def parse_width_ft(v):
    """OSM width is meters unless a unit is given."""
    v = first(v)
    if v is None:
        return np.nan
    s = str(v).strip().lower()
    try:
        if s.endswith("ft") or s.endswith("'"):
            return float(s.rstrip("ft'").strip())
        if s.endswith("m"):
            return float(s.rstrip("m").strip()) * 3.28084
        return float(s) * 3.28084  # bare number = meters per OSM convention
    except ValueError:
        return np.nan


def sidewalk_status(row):
    """Collapse sidewalk tagging variants into none/one_side/both/unknown."""
    main = first(row.get("sidewalk"))
    both = first(row.get("sidewalk:both"))
    left = first(row.get("sidewalk:left"))
    right = first(row.get("sidewalk:right"))
    yes = {"yes", "both", "left", "right", "separate"}
    if main in {"both", "separate"} or both == "yes":
        return "both"
    if main in {"left", "right"}:
        return "one_side"
    if main in {"no", "none"} or both == "no":
        return "none"
    l = left in yes, right in yes
    ln = left in {"no", "none"}, right in {"no", "none"}
    if any(x is not None for x in (left, right)):
        if all(l):
            return "both"
        if any(l):
            return "one_side"
        if all(ln):
            return "none"
    if main == "yes":
        return "one_side"  # tagged present, side unspecified
    return None  # untagged


def cycleway_status(row):
    vals = {
        first(row.get(c))
        for c in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
    } - {None}
    if not vals:
        return None
    if vals <= {"no", "none"}:
        return "none"
    return "|".join(sorted(vals - {"no", "none"}))


def parking_status(row):
    vals = {
        first(row.get(c))
        for c in (
            "parking:lane:left", "parking:lane:right", "parking:lane:both",
            "parking:left", "parking:right", "parking:both",
        )
    } - {None}
    if not vals:
        return None
    if vals <= {"no", "no_parking", "no_stopping", "none"}:
        return "none"
    return "present"


def bool_tag(v, true_vals=("yes", "true", "1")):
    v = first(v)
    if v is None:
        return None
    return str(v).lower() in true_vals


seg = gpd.GeoDataFrame(
    {
        "u": edges["u"],
        "v": edges["v"],
        "key": edges["key"],
        "osmid": edges["osmid"].apply(joined),
        "name": edges["name"].apply(first) if "name" in edges else None,
        "highway": edges["highway"].apply(first),
        "highway_all": edges["highway"].apply(joined),
        "oneway": edges["oneway"].apply(first).astype(bool),
        "length_ft": edges.geometry.length,
        "lanes": edges.get("lanes", pd.Series(index=edges.index)).apply(parse_lanes),
        "maxspeed_mph": edges.get("maxspeed", pd.Series(index=edges.index)).apply(
            parse_maxspeed_mph
        ),
        "width_ft": edges.get("width", pd.Series(index=edges.index)).apply(
            parse_width_ft
        ),
        "surface": edges.get("surface", pd.Series(index=edges.index)).apply(first),
        "lit": edges.get("lit", pd.Series(index=edges.index)).apply(bool_tag),
    },
    geometry=edges.geometry,
    crs=edges.crs,
)
seg["sidewalk"] = edges.apply(sidewalk_status, axis=1)
seg["cycleway"] = edges.apply(cycleway_status, axis=1)
seg["parking"] = edges.apply(parking_status, axis=1)

# --- node context: junction degree + signals at segment ends -----------------
degree = pd.Series(dict(Gp.degree()), name="degree")
signal_nodes = {
    n for n, d in Gp.nodes(data=True) if d.get("highway") == "traffic_signals"
}
seg["deg_u"] = seg["u"].map(degree)
seg["deg_v"] = seg["v"].map(degree)
seg["signal_u"] = seg["u"].isin(signal_nodes)
seg["signal_v"] = seg["v"].isin(signal_nodes)
seg["n_signals"] = seg["signal_u"].astype(int) + seg["signal_v"].astype(int)

# --- dual-carriageway detection ----------------------------------------------


def bearing_deg(geom):
    (x0, y0), (x1, y1) = geom.coords[0], geom.coords[-1]
    return math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360


seg["bearing"] = seg.geometry.apply(bearing_deg)

oneway = seg[seg["oneway"] & seg["name"].notna()].copy()
candidates = set()
SEARCH_FT = 150  # max separation between divided-road centerlines
sidx = oneway.sindex
for idx, row in oneway.iterrows():
    hits = oneway.iloc[
        sidx.query(row.geometry.buffer(SEARCH_FT), predicate="intersects")
    ]
    hits = hits[(hits.index != idx) & (hits["name"] == row["name"])]
    for jdx, other in hits.iterrows():
        diff = abs(row["bearing"] - other["bearing"]) % 360
        if 135 <= diff <= 225:  # antiparallel twin
            candidates.add(idx)
            candidates.add(jdx)
            break

seg["dual_carriageway"] = seg.index.isin(candidates)
n_dual = int(seg["dual_carriageway"].sum())
dual_mi = seg.loc[seg["dual_carriageway"], "length_ft"].sum() / 5280

# --- save ---------------------------------------------------------------------
PROCESSED.mkdir(parents=True, exist_ok=True)
seg_out = seg.copy()
seg_out["lit"] = seg_out["lit"].map({True: "yes", False: "no"})
seg_out.to_file(cfg.processed("segments.gpkg"), layer="segments", driver="GPKG")
print(f"Saved {len(seg):,} segments -> data/processed/district_c_segments.gpkg")

# --- coverage report -----------------------------------------------------------
total_mi = seg["length_ft"].sum() / 5280
by_class = seg.groupby("highway").agg(
    n=("length_ft", "size"), miles=("length_ft", lambda s: s.sum() / 5280)
)
by_class["miles"] = by_class["miles"].round(1)
by_class = by_class.sort_values("n", ascending=False)

FEATURES = [
    "lanes", "maxspeed_mph", "width_ft", "sidewalk",
    "cycleway", "parking", "lit", "surface",
]
cov_rows = []
arterial = seg["highway"].isin(["primary", "secondary", "tertiary",
                                "primary_link", "secondary_link", "tertiary_link"])
for f in FEATURES:
    notna = seg[f].notna()
    cov_rows.append(
        {
            "feature": f,
            "overall_pct": round(100 * notna.mean(), 1),
            "arterial_collector_pct": round(100 * notna[arterial].mean(), 1),
            "local_pct": round(100 * notna[~arterial].mean(), 1),
        }
    )
cov = pd.DataFrame(cov_rows)

q = seg["length_ft"].quantile([0.05, 0.25, 0.5, 0.75, 0.95]).round(0)

report = f"""# {cfg.AREA_LABEL} Road Network — Segment & Feature Coverage Report

Generated by `src/build_segments.py`. Source: OpenStreetMap (Overpass),
clipped to official {cfg.AREA_LABEL} boundary, motorways/ramps and service
roads excluded. CRS: EPSG:2278 (US ft).

## Network summary

- **Segments (intersection-to-intersection, undirected):** {len(seg):,}
- **Total centerline length:** {total_mi:,.1f} mi
- **Median segment length:** {seg['length_ft'].median():,.0f} ft
- Length percentiles (ft): p5={q[0.05]:,.0f}, p25={q[0.25]:,.0f}, p50={q[0.5]:,.0f}, p75={q[0.75]:,.0f}, p95={q[0.95]:,.0f}
- **Signalized segment ends:** {int(seg['n_signals'].gt(0).sum()):,} segments touch >=1 signal
- **One-way segments:** {int(seg['oneway'].sum()):,} ({100 * seg['oneway'].mean():.1f}%)
- **Dual-carriageway candidates:** {n_dual:,} segments ({dual_mi:,.1f} mi) — same-named antiparallel one-way twin within {SEARCH_FT} ft

## Segments by highway class

{by_class.to_markdown()}

## Tier-2 feature coverage (% of segments with a value)

{cov.to_markdown(index=False)}

## Notes

- `maxspeed` is **posted** speed, not operating speed (the model's mediator).
- `width` parsed to feet assuming OSM meters convention for bare numbers.
- Coverage gaps on locals are expected; decide impute-vs-conflate per feature.
"""

REPORTS.mkdir(exist_ok=True)
(REPORTS / "feature_coverage.md").write_text(report)
print(report)
