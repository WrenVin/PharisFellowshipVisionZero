# Project Log — Vision Zero District C

Dated record of what was done, what was decided, and why. Newest entries at the top. Companion to `README.md` (which describes the project as it *is*; this file records how it *got* there).

---

## 2026-06-12 (evening) — Sliver cleanup

**Profiling first, rule second.** Short segments turned out to be three different things: (A) 470 `*_link` turn lanes/slip roads (13.3 mi) — intersection plumbing at any length; (B) ~1,000 short *named* pieces, mostly degree 3-4 both ends — the bits of real cross streets passing through boulevard medians / intersection interiors; (C) 30 unnamed sub-50-ft fragments — junk.

**Rules** (`src/clean_slivers.py`): A → dropped to `removed_slivers` audit layer. B → **absorbed** into longest same-named neighboring segment (geometry linemerged, length summed, endpoints + degree/signal context updated; iterative so chains collapse; non-contiguous merges refused). C → dropped to audit. Named shorts with no same-named neighbor conservatively kept (31).

**Results:** 9,097 → **7,635 segments**; 677.0 → **663.4 mi** (loss = exactly the dropped links + junk; absorption preserved all street length). 962 pieces absorbed in 2 passes. p5 segment length 40 → **145 ft**. 0 orphaned `merged_away` pointers (remapped through absorption chains).

**New analysis file:** `district_c_segments_clean.gpkg` (layers: `segments`, `removed_slivers`, `merged_away`). Map regenerated from it.

**Flagged, not actioned — freeway frontage roads.** Sliver profiling surfaced "West Loop South Frontage Road" / "Southwest Freeway Frontage Road" segments in the network (tagged secondary/primary in OSM, so they survived the motorway filter). Feeders are TxDOT right-of-way — arguably outside "streets the city can redesign," same logic as excluding freeways. Decision needed: keep or exclude. Affects scope, not slivers; raised with Vincent.

---

## 2026-06-12 (later still) — Dual-carriageway merge

**Problem:** divided roads (Memorial, the Braeswoods, Heights Blvd...) were two parallel one-way segments each — ambiguous crash assignment, halved exposure per unit. ~25% of network mileage.

**Method** (`src/merge_dual_carriageways.py`): no geometry synthesis (averaging mismatched halves is fragile). Instead: (1) pair twins — same-named, antiparallel, one-way, within 150 ft; (2) connected components = corridors, **2-colored** into their two sides (robust on curved corridors like T.C. Jester where bearings rotate); (3) keep the longer side as representative centerline, move the other side's segments to a `merged_away` audit layer with `rep_seg_id` pointers — nothing deleted, crash assignment searches both layers and credits the representative; (4) aggregate attributes: `lanes` = sum of halves (now means total cross-section on every row), `maxspeed` = max, `oneway` = False; (5) stable `seg_id` (`C-#####`) assigned to all segments pre-merge so identities persist.

**Results:** 3,768 twin pairs, 160 corridors, **0 coloring conflicts** (twin graph perfectly bipartite — no false-positive tangles). 1,248 halves (86.2 mi) merged into 1,193 representatives. Network: 10,345 → **9,097 segments**, 763 → **677 mi**. One-way share 35.6% → **13.7%** (residual = genuine one-ways). Merged-lanes coverage 92.9%.

**Validation:** every top corridor halved its mileage (N. Braeswood 9.6→4.8 mi); ground-truth lane checks pass (Heights Blvd 2+2=4, Memorial 3+3=6); merged-lanes distribution dominated by 4s and 6s as divided boulevards should be.

**Downstream rule:** all analysis uses `district_c_segments_merged.gpkg` layer `segments`; pre-merge file is provenance only. Map regenerated from merged network.

---

## 2026-06-12 (later) — Codebook + map made legible

Feedback from Vincent: the network map was unreadable to anyone who didn't build it — unexplained colors, raw variable names in tooltips. Two fixes:

- **`CODEBOOK.md` created** (repo root): defines every column in `district_c_segments.gpkg` — meaning, units, source, value sets, coverage % — plus OSM road-class → plain-English translations and a "known limitations" section (missing ≠ absent; divided roads currently doubled; sliver tail; posted ≠ operating speed). Standing rule: **codebook stays in sync with any schema change.**
- **Map rebuilt** (`src/make_map.py`, replacing the inline throwaway): fixed legend box with plain-English road types ("Major arterial", "Collector", "Local street"...), short network explainer, per-class toggleable layers, tooltips with human labels ("Traffic lanes", "Posted speed", "Divided road half"), "not tagged" shown instead of NaN, divided-road layer off by default. Verified legend/layers/tooltips present in output HTML.

---

## 2026-06-12 — Road network built: boundary, OSM pull, segmentation, coverage report

### Decisions made (with rationale)

1. **Unit of analysis: intersection-to-intersection segments.** Split the network at junction nodes (degree ≥ 3). Chosen over fixed-length segments because it matches the crash-modeling literature (Dumbaugh tradition), is interpretable to a council-office audience ("this block of Westheimer"), and makes intersection-vs-midblock a clean later distinction. Variable segment length is handled by carrying length as an exposure offset in the negative binomial.
2. **Scope: city-controlled surface streets only.** Freeways and ramps (I-610, US-59/I-69) excluded — TxDOT jurisdiction, not city-redesignable, and they behave differently from surface streets. Locals *kept* (full functional hierarchy below freeway). Service roads (alleys, driveways, parking aisles) excluded via OSMnx `network_type="drive"`. Rationale: the project's thesis is about streets the city can actually redesign.
3. **Geometry source: OpenStreetMap as the spine**, with TxDOT RHiNo (AADT/exposure), city parcels (land use), and ACS (demographics) to be conflated on later. OSM has the best free design-feature coverage and clean topology for segmentation.
4. **CRS: EPSG:2278** (Texas State Plane South Central, US survey ft) for all distance work — the 200-ft crash-assignment buffer must be honest feet, not degrees.
5. **Dual carriageways: merge is now mandatory** (was "optional, quantify first"). See finding below — at ~25% of network mileage, leaving divided roads as two parallel segments would double-count streets and halve their apparent exposure in the model.

### What was built

- Python venv (`.venv`) with geopandas / osmnx / folium stack; `requirements.txt` pinned.
- `src/pull_osm.py` — pulls drivable OSM network clipped to the boundary via Overpass; drops motorway/motorway_link (225 freeway edges removed); preserves tier-1/tier-2 tags (lanes, maxspeed, width, oneway, sidewalk, cycleway, parking, lit, surface).
- `src/build_segments.py` — collapses directed graph to undirected segments (one row per physical street), projects to EPSG:2278, parses messy OSM tags into typed columns (lanes, maxspeed→mph, width→ft, sidewalk/cycleway/parking status), attaches junction degree + traffic-signal presence per segment end, detects dual-carriageway candidates (same-named antiparallel one-way twin within 150 ft), writes GeoPackage + coverage report.
- Outputs: `data/processed/district_c_segments.gpkg`, `reports/feature_coverage.md`, `reports/network_map.html` (interactive sanity-check map).

### Findings

- **Boundary verified (prospectus open item resolved).** The COH GIS council-districts layer (`HoustonMap/Administrative_Boundary/MapServer/2`) is current — District C lists CM Joe Panzarella. Single clean polygon, inner loop down to Meyerland/Braeswood.
- **Network size: 10,345 segments, 763.2 centerline miles.** Median segment 304 ft (a Houston block — segmentation behaved). Composition: residential 5,243 segs / 434 mi; secondary 2,759 / 185 mi; tertiary 1,092 / 73 mi; primary 529 / 41 mi; rest links/unclassified.
- **Feature coverage (the tier-2 reality check):**
  - `lanes` **84.8%** overall, 90.8% on arterials/collectors — much better than feared; the top design predictor is largely usable as-is.
  - `surface` 72.8%.
  - `maxspeed` **14.2%** (4.8% on locals) — needs city speed-limit layer or Texas-default imputation (30 mph urban prima facie).
  - `sidewalk` 17.1%, `lit` 21.8%, `cycleway` 9.6%, `parking` 1.7% — too thin to use raw; look for city inventories (Houston sidewalk gaps are themselves part of the story).
  - `width` **0.0%** — must come from elsewhere entirely: city inventory, lanes × standard lane-width estimate, or aerial imagery.
- **Dual-carriageway finding (bigger than expected):** 2,608 segments / 177.3 mi (~25% of mileage) have a same-named antiparallel one-way twin within 150 ft. Top streets validate the detector: N/S Braeswood, Memorial, Richmond, W/E T.C. Jester, Ella, Heights Blvd, Allen Pkwy, Main — exactly District C's bayou-divided and esplanade boulevards. Consequence: crash assignment would be ambiguous between twins and exposure would be split, so **merging divided pairs into single centerlines is a confirmed prerequisite before crash assignment**.
- One-way share (35.6%) is inflated by the dual carriageways; will drop after the merge.
- **Sliver-segment tail:** p5 segment length = 40 ft — tiny fragments, mostly `*_link` turn lanes and median crossovers. Need an absorb-or-drop rule before modeling.

### Issues hit (and fixes)

- OSM tags arrive as `None` *or* float `NaN` depending on column presence; normalized both in the tag parser (`first()`), which fixed a crash in cycleway parsing.
- GeoPackage can't store list-valued columns (OSMnx merges tags when simplifying ways) — pipe-joined for audit columns, first-value for typed columns.
- `tabulate` needed for `DataFrame.to_markdown` — added to env.

### Next steps (in order)

1. **Merge dual-carriageway pairs** into single centerline segments (pre-crash-assignment requirement).
2. **Sliver cleanup rule** for the sub-~50-ft fragment tail.
3. **Tier-3 conflation:** TxDOT RHiNo (AADT — the exposure confounder), city speed limits, sidewalk inventory, parcels (land use), ACS.
4. Nothing committed to git yet — first commit of skeleton + scripts pending.

---

## Pre-2026-06-12 — Context (before this log existed)

- Prospectus written; methodology fixed: negative binomial on segment-level severe-crash counts, Moran's I / Getis-Ord Gi* as the HIN-reconstruction baseline, unsupervised street typologies, spatially blocked CV, divergence analysis as headline output. DAG identification strategy: adjust land use / exposure / demographics; do **not** adjust operating speed (mediator); crash reporting is a collider (formal basis of the underreporting concern).
- TxDOT CRIS geocoded extract is agency-restricted; request in motion via CM Panzarella's office (chiefs of staff Anna and Cole). Questions doc drafted for Austin's Vision Zero team.
- Austin's `cityofaustin/vision-zero` (CC0) identified as schema/UI reference — mine the schema, do not clone-and-run (their stack needs their prod DB/VPN; the hard part of CRIS ingestion is credentialed access, not code).
- Fellowship timeline: ends 2026-07-31; ~7 weeks remaining as of this entry.
