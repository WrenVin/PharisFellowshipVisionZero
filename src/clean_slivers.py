"""Remove sliver segments that are not real analysis units.

Profiling (2026-06-12) found three distinct populations among short segments:

  A. `*_link` class (turn lanes / slip roads): intersection plumbing at any
     length, not streets. -> DROP to audit layer.
  B. Short pieces of *named* streets (median crossings of divided
     boulevards, intersection interiors; mostly 25-100 ft, degree 3-4 at
     both ends). Real streets, wrong units. -> ABSORB into the longest
     same-named neighboring segment (geometry merged, length summed,
     endpoints updated). Iterates so chains collapse.
  C. Remaining unnamed fragments < DROP_FT (connectors, stubs).
     -> DROP to audit layer.

Named short segments with no same-named neighbor are KEPT (conservative:
some are real short streets at the district edge).

Outputs:
  data/processed/houston_segments_clean.gpkg
    layer "segments"         - THE analysis network
    layer "removed_slivers"  - dropped segments + reason
    layer "merged_away"      - dual-carriageway audit layer, carried over
                               with rep_seg_id remapped where absorbed
  reports/sliver_cleanup_report.md
"""


import geopandas as gpd
import pandas as pd
from shapely.ops import linemerge, unary_union

import config as cfg
ROOT, PROCESSED, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.REPORTS

ABSORB_FT = 100  # named short pieces below this get absorbed into neighbors
DROP_FT = 50     # unnamed fragments below this get dropped

src = cfg.processed("segments_merged.gpkg")
net = gpd.read_file(src, layer="segments").set_index("seg_id", drop=False)
merged_away = gpd.read_file(src, layer="merged_away")
n0, mi0 = len(net), net["length_ft"].sum() / 5280

# node -> (degree, signal) lookup from both endpoint columns
node_info = {}
for end in ("u", "v"):
    for n, deg, sig in zip(net[end], net[f"deg_{end}"], net[f"signal_{end}"]):
        node_info[n] = (deg, sig)

# --- Rule A: drop link segments ------------------------------------------------
is_link = net["highway"].str.endswith("_link")
links = net[is_link].copy()
links["removal_reason"] = "link_class (turn lane / slip road)"
net = net[~is_link].copy()

# --- Rule B: absorb short named pieces into same-named neighbors ----------------
absorbed_into = {}  # absorbed seg_id -> absorber seg_id
passes = 0
while passes < 5:
    passes += 1
    changed = 0
    short = net[(net["length_ft"] < ABSORB_FT) & net["name"].notna()]
    for sid, row in short.sort_values("length_ft").iterrows():
        if sid not in net.index:
            continue  # absorbed earlier this pass
        nbrs = net[
            (net.index != sid)
            & (net["name"] == row["name"])
            & (
                net["u"].isin([row["u"], row["v"]])
                | net["v"].isin([row["u"], row["v"]])
            )
        ]
        nbrs = nbrs[nbrs["length_ft"] >= row["length_ft"]]
        if nbrs.empty:
            continue
        a = nbrs["length_ft"].idxmax()  # longest same-named neighbor absorbs
        arow = net.loc[a]
        merged_geom = linemerge(unary_union([arow.geometry, row.geometry]))
        if merged_geom.geom_type != "LineString":
            continue  # don't force non-contiguous merges
        # new endpoints: the two nodes NOT shared between the pair
        shared = ({arow["u"], arow["v"]} & {row["u"], row["v"]})
        ends = list(({arow["u"], arow["v"]} | {row["u"], row["v"]}) - shared)
        if len(ends) == 2:
            for col, n in zip(("u", "v"), ends):
                net.loc[a, col] = n
                deg, sig = node_info.get(n, (pd.NA, False))
                net.loc[a, f"deg_{col}"] = deg
                net.loc[a, f"signal_{col}"] = sig
            net.loc[a, "n_signals"] = int(net.loc[a, "signal_u"]) + int(
                net.loc[a, "signal_v"]
            )
        net.loc[a, "geometry"] = merged_geom
        net.loc[a, "length_ft"] = arow["length_ft"] + row["length_ft"]
        absorbed_into[sid] = a
        net = net.drop(index=sid)
        changed += 1
    if changed == 0:
        break
# follow absorption chains (S1 absorbed into S2, S2 later into S3)
for sid in list(absorbed_into):
    while absorbed_into[sid] in absorbed_into:
        absorbed_into[sid] = absorbed_into[absorbed_into[sid]]

# --- Rule C: drop remaining unnamed short fragments -----------------------------
is_junk = (net["length_ft"] < DROP_FT) & net["name"].isna()
junk = net[is_junk].copy()
junk["removal_reason"] = f"unnamed fragment < {DROP_FT} ft"
net = net[~is_junk].copy()

kept_short = ((net["length_ft"] < DROP_FT)).sum()

# --- remap merged_away pointers --------------------------------------------------
removed = pd.concat([links, junk])
removed_ids = set(removed["seg_id"])
merged_away["rep_seg_id"] = merged_away["rep_seg_id"].map(
    lambda s: absorbed_into.get(s, s)
)
orphans = merged_away["rep_seg_id"].isin(removed_ids).sum()

# --- save -------------------------------------------------------------------------
out = cfg.processed("segments_clean.gpkg")
net.reset_index(drop=True).to_file(out, layer="segments", driver="GPKG")
removed.reset_index(drop=True).to_file(out, layer="removed_slivers", driver="GPKG")
merged_away.to_file(out, layer="merged_away", driver="GPKG")

n1, mi1 = len(net), net["length_ft"].sum() / 5280
report = f"""# Sliver Cleanup Report

Generated by `src/clean_slivers.py`. Input: `houston_segments_merged.gpkg`.
Thresholds: absorb named pieces < {ABSORB_FT} ft; drop unnamed fragments < {DROP_FT} ft.

## Before / after

| | before | after |
|---|---|---|
| Segments | {n0:,} | {n1:,} |
| Centerline miles | {mi0:,.1f} | {mi1:,.1f} |

## Actions

| Rule | Action | Count | Miles |
|---|---|---|---|
| A | `*_link` (turn lanes / slip roads) dropped to audit | {len(links):,} | {links["length_ft"].sum() / 5280:.1f} |
| B | short named pieces absorbed into same-named neighbor | {len(absorbed_into):,} | (length preserved in absorbers) |
| C | unnamed fragments < {DROP_FT} ft dropped to audit | {len(junk):,} | {junk["length_ft"].sum() / 5280:.2f} |

- Absorption passes: {passes}; named short segments kept for lack of a
  same-named neighbor (conservative): {kept_short:,}
- `merged_away` rep pointers remapped through absorptions; pointers landing
  on removed segments (orphans): {orphans}
- Minimum segment length after cleanup (named kept): {net["length_ft"].min():.0f} ft;
  p5 = {net["length_ft"].quantile(0.05):.0f} ft (was 40 ft pre-cleanup)

## Use

All analysis now uses layer `segments` of `houston_segments_clean.gpkg`.
Removed segments live in `removed_slivers` with a `removal_reason`; crash
assignment may still match crashes near them to surviving segments via the
buffer method.
"""
(REPORTS / "sliver_cleanup_report.md").write_text(report)
print(report)
