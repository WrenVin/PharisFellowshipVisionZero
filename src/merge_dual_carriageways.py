"""Merge dual-carriageway halves into single analysis segments.

Problem: divided roads (Memorial, the Braeswoods, Heights Blvd...) exist in
OSM as two parallel one-way ways. Left as-is, one physical street is two
segments: crashes assign ambiguously and exposure is split in half.

Method (auditable, no geometry synthesis):
  1. Pair twins: same-named, antiparallel (135-225 deg), one-way segments
     whose geometries pass within SEARCH_FT of each other.
  2. Connected components of the twin relation = divided corridors.
     2-color each component to split it into its two sides (robust on
     curved corridors where absolute bearings rotate).
  3. The side with more total length is the representative centerline.
     The other side's segments are moved to a `merged_away` audit layer
     with a pointer (rep_seg_id) to the segment that now represents them
     (nearest representative by midpoint distance).
  4. Attribute aggregation onto the representative:
       lanes        -> rep half + length-weighted mean of its twins' lanes
                       (= total cross-section, same meaning as on undivided
                       two-way streets); NaN if either half untagged
       maxspeed_mph -> max of halves
       sidewalk/cycleway/parking/lit/surface -> rep's value, else twin's
       oneway       -> False; merged_dual -> True
  5. Stable IDs: every segment gets seg_id ("C-00001"...) BEFORE the merge,
     so identities persist across layers and future pipeline steps.

Outputs:
  data/processed/district_c_segments_merged.gpkg
      layer "segments"     - analysis network (twins collapsed)
      layer "merged_away"  - removed halves + rep_seg_id mapping
  reports/dual_merge_report.md
"""

from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

import config as cfg
ROOT, PROCESSED, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.REPORTS

SEARCH_FT = 150

seg = gpd.read_file(cfg.processed("segments.gpkg"), layer="segments")
seg["seg_id"] = [f"{cfg.SEG_PREFIX}-{i:05d}" for i in range(len(seg))]
n_before, mi_before = len(seg), seg["length_ft"].sum() / 5280

# --- 1. twin pairs ------------------------------------------------------------
ow = seg[seg["oneway"] & seg["name"].notna()]
sidx = ow.sindex
pairs = []
for idx, row in ow.iterrows():
    hits = ow.iloc[sidx.query(row.geometry.buffer(SEARCH_FT), predicate="intersects")]
    hits = hits[(hits.index > idx) & (hits["name"] == row["name"])]
    for jdx, other in hits.iterrows():
        diff = (row["bearing"] - other["bearing"]) % 360
        if 135 <= diff <= 225:
            pairs.append((idx, jdx))
print(f"Twin pairs: {len(pairs):,}")

# --- 2. corridors + 2-coloring into sides ------------------------------------
T = nx.Graph(pairs)
side = {}          # index -> 0/1 within its component
conflicts = 0
for comp in nx.connected_components(T):
    comp = set(comp)
    start = next(iter(comp))
    side[start] = 0
    for u, v in nx.bfs_edges(T.subgraph(comp), start):
        if v in side and side[v] == side[u]:
            conflicts += 1  # odd cycle (false-positive edge); keep first color
        side.setdefault(v, 1 - side[u])
print(f"Corridor components: {nx.number_connected_components(T):,}; "
      f"coloring conflicts: {conflicts}")

# --- 3. pick representative side per corridor ---------------------------------
drop_to_rep = {}   # dropped index -> representative index
for comp in nx.connected_components(T):
    comp = list(comp)
    lengths = seg.loc[comp, "length_ft"]
    sides = pd.Series({i: side[i] for i in comp})
    len_by_side = lengths.groupby(sides).sum()
    rep_side = int(len_by_side.idxmax())
    reps = [i for i in comp if side[i] == rep_side]
    drops = [i for i in comp if side[i] != rep_side]
    rep_geoms = seg.loc[reps].geometry
    for d in drops:
        mid = seg.loc[d].geometry.interpolate(0.5, normalized=True)
        drop_to_rep[d] = reps[int(np.argmin([mid.distance(g) for g in rep_geoms]))]

dropped = set(drop_to_rep)
rep_targets = set(drop_to_rep.values())
print(f"Dropping {len(dropped):,} half-segments into merged_away; "
      f"{len(rep_targets):,} representatives absorb them")

# --- 4. aggregate attributes onto representatives ------------------------------
twins_of = {}
for d, r in drop_to_rep.items():
    twins_of.setdefault(r, []).append(d)

seg["merged_dual"] = False
seg["n_twins_merged"] = 0
seg["twin_seg_ids"] = None
seg["lanes_rep_half"] = np.nan
seg["lanes_twin_half"] = np.nan

PREFER_NONNULL = ["sidewalk", "cycleway", "parking", "lit", "surface"]
for r, ds in twins_of.items():
    tw = seg.loc[ds]
    w = tw["length_ft"].to_numpy()
    lv = tw["lanes"].to_numpy(dtype=float)
    ok = ~np.isnan(lv)
    twin_lanes = float(np.average(lv[ok], weights=w[ok])) if ok.any() else np.nan
    own_lanes = seg.at[r, "lanes"]
    seg.at[r, "lanes_rep_half"] = own_lanes
    seg.at[r, "lanes_twin_half"] = twin_lanes
    seg.at[r, "lanes"] = (
        own_lanes + twin_lanes
        if not (pd.isna(own_lanes) or pd.isna(twin_lanes))
        else np.nan
    )
    ms = pd.concat([pd.Series([seg.at[r, "maxspeed_mph"]]), tw["maxspeed_mph"]])
    seg.at[r, "maxspeed_mph"] = ms.max() if ms.notna().any() else np.nan
    for col in PREFER_NONNULL:
        if pd.isna(seg.at[r, col]) and tw[col].notna().any():
            seg.at[r, col] = tw[col].dropna().iloc[0]
    seg.at[r, "oneway"] = False
    seg.at[r, "merged_dual"] = True
    seg.at[r, "n_twins_merged"] = len(ds)
    seg.at[r, "twin_seg_ids"] = "|".join(seg.loc[ds, "seg_id"])

# refresh the flag: only confirmed paired segments count as dual now
seg["dual_carriageway"] = seg.index.isin(dropped | rep_targets)

merged_away = seg.loc[sorted(dropped)].copy()
merged_away["rep_seg_id"] = [seg.at[drop_to_rep[d], "seg_id"] for d in sorted(dropped)]
network = seg.drop(index=list(dropped)).copy()

n_after, mi_after = len(network), network["length_ft"].sum() / 5280

out = cfg.processed("segments_merged.gpkg")
network.to_file(out, layer="segments", driver="GPKG")
merged_away.to_file(out, layer="merged_away", driver="GPKG")
print(f"Saved {out}")

# --- 5. report ------------------------------------------------------------------
corr = network[network["merged_dual"]]
top = (corr.groupby("name")["length_ft"].sum() / 5280).sort_values(ascending=False)
sep_note = (
    "Twin pairing: same name, both one-way, antiparallel (135-225 deg), "
    f"geometries within {SEARCH_FT} ft."
)
report = f"""# Dual-Carriageway Merge Report

Generated by `src/merge_dual_carriageways.py`. {sep_note}

## Before / after

| | before | after |
|---|---|---|
| Segments | {n_before:,} | {n_after:,} |
| Centerline miles | {mi_before:,.1f} | {mi_after:,.1f} |
| One-way share | {35.6}% | {100 * network["oneway"].mean():.1f}% |

- Twin pairs found: {len(pairs):,}; corridor components: {nx.number_connected_components(T):,}; 2-coloring conflicts (false-positive edges tolerated): {conflicts}
- Half-segments moved to `merged_away`: {len(dropped):,} ({seg.loc[sorted(dropped), "length_ft"].sum() / 5280:,.1f} mi removed from network length)
- Representative segments now carrying merged attributes: {len(rep_targets):,}
- `lanes` on merged segments = sum of both halves (total cross-section, same meaning as undivided streets). Coverage of merged lanes: {100 * corr["lanes"].notna().mean():.1f}% of merged segments.

## Top merged corridors (mi, representative side)

{top.head(15).round(1).to_markdown()}

## Audit trail

Every removed half lives in layer `merged_away` of
`district_c_segments_merged.gpkg` with `rep_seg_id` pointing at the segment
that now represents it. Crash assignment should search BOTH layers'
geometries and credit hits to the representative.
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "dual_merge_report.md").write_text(report)
print(report)
