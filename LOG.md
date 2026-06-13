# Project Log — Vision Zero District C

Dated record of what was done, what was decided, and why. Newest entries at the top. Companion to `README.md` (which describes the project as it *is*; this file records how it *got* there).

---

## 2026-06-13 — Street Explorer refinements: mobile, speed floor, data-vintage transparency

Three asks from Vincent on the new app:
1. **Mobile-friendly.** Panel becomes an off-canvas drawer below 760px with a "☰ Controls" toggle; info panel becomes a bottom sheet; count badge centers; Leaflet zoom control moved to bottom-right so it never collides with the toggle. Verified at 375px (preview).
2. **Speed filter floor = 30.** Only 22 segments are below 30 mph (all OSM oddities: one 5, some 20/25) vs 5,973 at 30 — so the posted-speed slider now starts at 30, not the raw data min of 5. Implemented a domain-aware filter rule: a bound only excludes once its handle moves off the slider end, so those 22 sub-30 segments still show at the default floor (nothing silently hidden).
3. **Data-vintage transparency.** Added an "ⓘ Data sources & dates" modal listing every source and its vintage: OSM (June 2026 snapshot), City Traffic_gx (June 2026), ADT readings 2012–2026, HCAD land use (June 2026), Census ACS 2023 5-yr (2019–2023), boundary (current districts). Plus the "no data ≠ absent" and "TX 30 mph default" caveats. Map-compiled date shown.

UI-only (no data/schema change). Next: add school-zone data (Vincent's request).

---

## 2026-06-13 — Interactive map rebuilt as a custom Leaflet app

Vincent: the folium map was hard to use — thin lines hard to click, hover-only tooltip vanished, and only colorable by road type. He wanted full control, public-facing. Agreed to graduate from folium (static, baked styling) to a **custom Leaflet web-app** where all styling/filtering happens live in the browser.

**Built** (`docs/index.html`, ~700 lines, vanilla JS + Leaflet, no build step) + `src/export_webmap_data.py` (exports simplified `docs/segments.geojson` 5.7 MB + `boundary.geojson`). Replaces folium `make_map.py` (deleted) and the 14 MB generated html.

Features: **color streets by any attribute** (categorical palettes + numeric quantile gradient, legend redraws); **stacking filters** — road-type/sidewalk/land-use chips + dual-range sliders for speed/lanes/ADT (e.g. "4+ lanes, ≥35 mph, no sidewalk" → 243 candidates, a dangerous-by-design pre-screen); **street search**; **click-to-pin info panel** (grouped, source-tagged, persists); appearance controls (line width/opacity/basemap). Easy selection via **canvas renderer with click-tolerance** (fixes the thin-line problem) + hover highlight.

**Verified in-browser** via the preview server: clean load (no console errors), gradient legend on numeric color-by, info panel populates correctly (Westheimer: 5 lanes/OSM, 30 mph TX-default, 14k veh/day corridor-est, Commercial, block-group demographics), filter scenario narrows 7,381→243. Fixed count-badge overlapping the zoom control (moved bottom-left).

Pipeline/refresh: map now refreshes via `export_webmap_data.py` (not make_map). Added `.claude/launch.json` for local preview.

---

## 2026-06-13 — Conflate adjacent land use (HCAD parcels) — last predictor

DAG confounder. Source: COH "Land Use (Grouped)" parcel layer (HCAD). New `src/conflate_landuse.py`. For each segment, parcels whose polygon comes within 100 ft are summarized area-weighted into `landuse_dominant` + `pct_residential/commercial/industrial`.

**Three bugs fought through (good case study in not trusting the first number):**
1. `resultOffset` paging silently broke — the server caps geojson pages by transfer SIZE (~750–4000 features, variable) and sets `exceededTransferLimit`; offset paging then **duplicated some parcels and skipped others** (108k rows, only 44k unique, ~34k missing). Fixed with an **OBJECTID cursor** (`where OBJECTID > last_max`, ordered) — bulletproof.
2. Merge crash: built results with `seg_id` as index then merged `on="seg_id"` → reset_index.
3. geojson/gpkg round-trip upper-cased the field (`GROUP_DSCR`) → case-robust lookup.
4. First spatial pass used parcel **centroids** within 100 ft → only 57% coverage because deep lots have centroids set far back. Switched to parcel **polygon** intersects buffer → 79%.

**Reconciliation:** 44,116 unique parcels vs a returnCountOnly of 77,931 — the gap is HCAD **stacked condo records** (multiple ownership rows at one footprint), redundant for land use; de-duplicated. **Verified the 21% NaN is real, not a gap:** those segments are a median ~340 ft from any parcel — roads through Hermann Park, Rice University, the Texas Medical Center, cemeteries, and bayou greenways. Left `none`, not mislabeled.

**Result:** `landuse_dominant` on 79% of segments (78% arterials): Residential 3,859, Commercial 1,121, Institutional 303, Industrial 258, Undeveloped 225, Parks 32. Added to map tooltip + CSV.

**Tier-3 conflation complete** — all predictors assembled (speed, lanes, width, median, ADT, operating speed, demographics, sidewalks, land use). Only the CRIS crash outcome (pending) remains before modeling.

---

## 2026-06-13 — Conflate sidewalks (OSM-derived)

**No official Houston sidewalk inventory exists** (checked: city "Sidewalk Service Areas" = admin sectors; "Sidewalk Permits" = construction points; Traffic_gx "Bike and Pedestrian" = count stations — none is a presence inventory). OSM is best-available. Key find: OSM maps **~344 mi of separate `footway=sidewalk` lines** in District C — far richer than the 16% of roads carrying a `sidewalk=*` tag. New `src/conflate_sidewalks.py`.

**Method:** sample 11 points per segment; at each, find ALL sidewalk footways within a width-scaled distance and classify each by side (left/right via cross product with segment direction); per segment, left_frac/right_frac → `sidewalk_presence` (both / one_side / partial / none). Falls back to the road `sidewalk` tag where no footway is mapped.

**Two fixes during build:**
1. First pass used `sjoin_nearest` (single nearest sidewalk per point) → could only ever mark ONE side, so "both" was undercounted at 3.4%. Switched to buffer-intersect (all sidewalks near each point, left & right independently) → both-sides rose to a realistic 12.5%.
2. Fixed 35 ft centerline tolerance → it missed sidewalks on wide arterials (sidewalk sits 40–50 ft from centerline on a 6-lane road). Scaled search distance to `roadway_width_ft/2 + 25 ft` (clamped 30–60). Arterial both-sides 18.6% → **22.4%**.

**Result:** at least one side on **56.5%** of segments; both sides 13.9% (22.4% arterials); **none mapped 43.5%** — consistent with Houston's known sidewalk gaps. Added to map tooltip + CSV.

**Caveat (documented prominently):** missing ≠ absent — `none` = none *mapped* within range; OSM completeness is uneven, not a field survey.

---

## 2026-06-13 — Conflate neighborhood demographics (ACS)

The DAG demographics confounder + equity-overlay basis. Source: Census ACS 2023 5-year at **block group**; geometry from TIGERweb (no key); attributes from the Census Data API. New `src/conflate_demographics.py`.

**Census API now requires a free key** (used to be keyless) — Vincent signed up and provided one; stored in gitignored `data/external/.census_api_key` (added to `.gitignore`, verified ignored). Key never committed.

**Attribution method:** each segment inherits the block group containing its midpoint (ecological — neighborhood value attached to streets, not a street-level measurement; documented). 100% of segments assigned; ~233 block groups span District C.

**Two data gotchas hit + fixed:**
1. Median income carried Census's `-666666666` "not available" sentinel → cleaned all negative counts/income to NaN.
2. The detailed poverty (B17001) and vehicle (B08201) tables **return null at block-group level**. Verified, then swapped to the BG-published equivalents: poverty via **C17002** (below = ratio<0.50 + 0.50–0.99), vehicles via **B25044** (no-veh = owner + renter no-vehicle). Both 100% covered.

**Result (District C block-group range):** median HH income $25k–$250k (median ~$147k — affluent inner-loop core), % below poverty 0–56 (median 5), % Hispanic 0–89 (median 16), % zero-car households 0–39 (median 2). Plausible for inner-loop Houston.

Added median income + zero-car to map tooltip (labeled "Neighborhood"), full demographic set to CSV; 4 docs updated.

---

## 2026-06-13 — Conflate traffic volume (ADT) + operating speed

The exposure confounder. Source: Traffic_gx count **stations** (layers 4 major / 5 local) joined to count **readings** (table 22) by `LocationID = station GlobalID`. Added `fetch_table` to `arcgis_fetch.py` for the non-spatial table; new `src/conflate_adt.py`.

**Method:** most-recent valid reading per station (stations span 2012–2026, multiple readings each) → snap station to nearest segment (≤150 ft) → segment ADT = mean of its stations → propagate along same-named corridors (`street_median`) → leave the rest blank (deliberately NOT class-imputed; imputing a confounder is a modeling decision to make + sensitivity-test explicitly).

**Diagnostic that reframed the result:** initial 30% overall coverage looked weak until I clipped stations to the actual district polygon — the bbox pull had 985 stations but **only ~320 are inside District C** (ADT's true measurement density). 99% of in-district stations sit within 150 ft of a segment, so tolerance was never the issue. Also fixed a report-metric bug (coverage was divided by all segments, not per-class). Corrected picture: **ADT covers 98% of primary and 97% of secondary arterials**, 34% tertiary, 6% residential — i.e. dense exactly where crashes and the HIN live. Median arterial ADT ~13.6k veh/day (p95 ~25k).

**Bonus — operating speed.** Table 22 also carries `PercentileSpeed85` (85th-pct measured speed) = the **DAG mediator**. Captured as `op_speed_85_mph` (~4% coverage). Flagged in codebook: model as the mechanism, do NOT adjust for it. First real data we have on the mediator (vs. posted speed).

All values provenance-tagged; ADT + volume added to map tooltip and CSV front; 4 docs updated; map republished to Pages.

---

## 2026-06-13 — Map tooltips updated + published to GitHub Pages

Vincent flagged the map still showed OSM `lanes` and lacked width/median. Fixed `make_map.py` tooltips to use `lanes_final` (with source), `roadway_width_ft`, and `median_type`.

Then published the map live. `make_map.py` now also writes `docs/index.html` (+ `.nojekyll`); enabled GitHub Pages via the REST API (token from osxkeychain credential helper) serving `main` `/docs`. Repo is public so Pages works on the free tier. **Live: https://wrenvin.github.io/PharisFellowshipVisionZero/** — council office / reviewers can view without running anything. Verified the 14 MB map serves (HTTP 200, legend + tooltips present). Note: `docs/index.html` is force-committed (the `reports/` copy stays gitignored); regenerating the map updates both. Caveat: each regen commits a fresh ~14 MB blob — fine for now, revisit if history bloats.

---

## 2026-06-12 (night, cont.) — Conflate lanes, width, median

Same city source (cached `Traffic_gx/2`, re-fetched to add `MEDIAN_WIDTH`/`DIRECTION`). New shared helper `src/conflate_util.py::snap_match` (the point-snap match logic, now reusable). New `src/conflate_lanes_width_median.py`.

**Verified lane semantics before trusting them.** City `DIRECTION` is mostly *orientation* (N/S, E/W) → each line is the whole road and `NO_OF_LANES` is **total** cross-section (Memorial Dr = 6 = 3+3, matches our merged `lanes`). ~14% of lines are per-direction coded (Allen Pkwy) — a residual ambiguity.

**Lane priority decision — and a mid-task correction.** Started with OSM primary / city gap-fill. The OSM-vs-city cross-check (1,276 shared segments, agree-within-1-lane 79%) showed disagreements are systematic: where they differ the **city is usually higher** because OSM tags only one direction of a divided road (e.g., N/S Braeswood OSM=2, city=4–6). So flipped to **city authoritative → OSM fill → local 2-lane default**. `lanes_final` now 98.6% (city 18%, OSM 69%, local-2 12%, none 1.4%); `lanes_osm_city_agree` kept as a QC flag.

**Width — fills the 0% gap.** Avg lane width is ~12 ft citywide (rarely 11), so `roadway_width_ft = lanes_final × avg_lane_width` (travel pavement, excludes median). **98.6% covered, was 0%.** `width_source` distinguishes city-measured lane width (18%) from the 12-ft assumption (81%).

**Median.** `median_type` ∈ {Raised 984, Depressed 59, TWLT 53 (center turn lane), Undivided, Divided (unspecified)}. Filled: city where present (18%), local streets → Undivided (64%), merged-dual-without-city → "Divided (unspecified)" (216, so we never mislabel a divided road as undivided), higher-class unknown → NaN (17.7%). `median_width_ft` city-only (not defaulted). **Independent validation: 76.9% of our merged dual-carriageway segments are typed Raised/Depressed by the city** — the median data confirms the merge.

All conflated columns provenance-tagged (`*_source`). CSV (now 50 cols, key new fields surfaced up front) + map refreshed.

---

## 2026-06-12 (night) — Tier-3 conflation begins: posted speed limits

First external data joined onto the network. Doing conflation one layer at a time; speed first (Vincent's call).

**Major data discovery.** Houston Public Works' `TDO/Traffic_gx` ArcGIS service (found via the city GeoHub) is an engineering goldmine for the whole conflation phase: a **Speed Limit** layer carrying `POSTED_SPEED`, `NO_OF_LANES`, `AVG_LANE_WIDTH` (fills our 0%-coverage width gap!), `MEDIAN_TYPE`, and classification — already in EPSG:2278 — plus separate **Major Thoroughfare ADT** and **Local Street ADT** layers (city counts traffic on locals too, solving the AADT-coverage worry I'd flagged for TxDOT RHiNo). Also in the same `HoustonMap/Transportation` service: the **official Vision Zero HIN 2022 & 2018** polylines with per-segment crash/death counts and rates, ped/bike dangerous-roads layers, and a social-vulnerability layer — i.e. the city's crash-based baseline for the divergence analysis is publicly downloadable. Caveat: speed source is on staging host `geogimstest` (production `geogims` unreachable 2026-06-12); flagged.

**Infrastructure.** New reusable `src/arcgis_fetch.py` (paged, bbox-clipped ArcGIS REST → GeoDataFrame) for all city pulls. New **enrichment model**: `district_c_segments_enriched.gpkg` = clean network + conflated columns, grown one conflation step at a time; each `conflate_*.py` is idempotent (drops its own columns on reload). This is now the canonical analysis file.

**Speed method** (`src/conflate_speed.py`): geometries differ between OSM and the city network, so no exact join — snap 5 sample points per segment to the nearest city speed line within 60 ft, take modal `POSTED_SPEED` if ≥40% of points match. Fill priority recorded in `speed_source`: city → osm → TX 30 mph default.

**Key finding — coverage is a *posting* fact, not a match failure.** City-posted speed matched only 18% of segments / 48% of arterials. Diagnostic: the unmatched higher-class segments sit a **median ~1,100 ft from any city speed line** (only 4 of 1,104 within 100 ft) — they're genuinely not on Houston's posted-thoroughfare network. Under TX Transportation Code §545.352 an unposted urban street is **30 mph** by default, so these legally default to 30 (tagged `default_30_unposted`, kept distinct for sensitivity testing). Corrected an initial bug where I restricted the 30 mph default to residential classes only — the prima facie default applies to any unposted urban street regardless of OSM class.

**Result:** `posted_speed_mph` now 100% populated (was 14% OSM-only), every value provenance-tagged. City matches: 35 mph dominant (1,152), then 40 (123), 45 (35), 50 (22). Spatial-join name-agreement 86% (sanity OK). Map tooltips now show speed + its source.

**Staged for next steps (already visible in the same city layer):** lanes, lane width, median type, ADT.

---

## 2026-06-12 (night) — ELI5 doc added

Created `ELI5.md` at Vincent's request: a plain-English, conversational story of the whole project — the big idea (reactive vs. proactive street safety, the Texas camera ban), and a step-by-step of the road-network build with no jargon. Now FOUR docs to keep current: README (facts), LOG (diary), CODEBOOK (dictionary), ELI5 (story).

---

## 2026-06-12 (evening, cont.) — Frontage roads excluded; scope question resolved

**Vincent's decision:** feeder/frontage roads are part of the highway facility — TxDOT right-of-way — and are excluded like the freeways they serve.

**Implementation:** name-based exclusion (`frontage|feeder|service road`, case-insensitive) added to `src/pull_osm.py` beside the motorway filter; full pipeline rerun. All 11 frontage road names removed (244 segments / 24.5 mi in the previous network), including the marginal cases Allen Parkway Frontage Road (0.7 mi; Allen Pkwy itself is city-owned and stays) and South Post Oak Road Frontage Road (0.6 mi) — easily whitelisted back if ever needed. Verified zero frontage segments remain.

**Final analysis network: 7,381 segments / 637.8 mi.** Note: `seg_id`s were regenerated by the rerun (nothing external referenced them yet; from here on they're stable).

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
