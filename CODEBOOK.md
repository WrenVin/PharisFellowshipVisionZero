# Codebook — District C Segment Dataset

Documents every variable in the segment datasets. One row = one **road segment**: a stretch of street between two intersections (or an intersection and a dead end), undirected — a two-way street is one row, not two, and (after the merge) a divided boulevard is one row, not two.

**Files** (in `data/processed/`):

| File / layer | What it is | Use for |
|---|---|---|
| `district_c_segments_enriched.gpkg`, layer `segments` | **The analysis network**, clean network + conflated city data (speed; more to come). Canonical once conflation began. | All analysis and mapping. |
| `district_c_segments_clean.gpkg`, layer `segments` | Clean network before any external conflation (divided roads merged, slivers cleaned). | Provenance / rebuild base for conflation. |
| `district_c_segments_clean.gpkg`, layer `removed_slivers` | Audit: dropped turn lanes/slip roads (`*_link`) and unnamed sub-50-ft fragments, with `removal_reason`. | Audits; crash-assignment context. |
| `district_c_segments_clean.gpkg`, layer `merged_away` | Audit: removed halves of divided roads, `rep_seg_id` points to the representative segment. | Crash assignment (search both geometries, credit the representative). |
| `district_c_segments_merged.gpkg` | Post-merge, pre-cleanup snapshot. | Provenance only. |
| `district_c_segments.gpkg` | Pre-merge snapshot (every OSM half separate). | Provenance only. |

Source data: OpenStreetMap (OSM), pulled 2026-06-12, clipped to the official District C boundary. Freeways, ramps, **frontage/feeder roads** (TxDOT right-of-way), and service roads (alleys/driveways) are excluded. Pipeline: `src/pull_osm.py` → `src/build_segments.py` → `src/merge_dual_carriageways.py` → `src/clean_slivers.py`.

**Sliver cleanup** (see `reports/sliver_cleanup_report.md`): `*_link` segments (turn lanes/slip roads — intersection plumbing, not streets) dropped; short (<100 ft) named pieces (median crossings, intersection interiors) **absorbed** into their longest same-named neighbor with geometry and length preserved; unnamed fragments <50 ft dropped. An absorbed segment's `length_ft` includes everything it absorbed; its endpoint columns (`u`/`v`, `deg_*`, `signal_*`) reflect the new, post-absorption endpoints.

**Coverage** = % of segments with a non-missing value (from `reports/feature_coverage.md`). Missing means "not tagged in OSM," **not** "feature absent on the ground."

## Identifiers & topology

| Variable | Type | Description |
|---|---|---|
| `seg_id` | text | **Stable segment ID** (`C-00001`...), assigned before the dual-carriageway merge. The permanent key for joins across all layers and pipeline steps. |
| `u`, `v` | int | OSM node IDs of the segment's two endpoints (its intersections). Stable keys for joining back to the street graph. |
| `key` | int | Disambiguator when two distinct segments connect the same pair of intersections (e.g., both halves of a divided road, a loop). Almost always 0. |
| `osmid` | text | OSM way ID(s) the segment was built from. Pipe-separated when several short ways were merged. Use to look any segment up at `openstreetmap.org/way/<id>`. |
| `name` | text | Street name (e.g., "Westheimer Road"). Missing on some unnamed links/alleys. |

## Road classification

| Variable | Type | Description |
|---|---|---|
| `highway` | text | OSM road class — the functional hierarchy. **Translations below.** When merged ways disagreed, the first value; see `highway_all` for all of them. |
| `highway_all` | text | All road-class values across merged ways, pipe-separated. Audit column. |

**OSM road class → plain English** (these are the map colors):

| OSM value | Means | District C examples |
|---|---|---|
| `primary` | Major arterial — the biggest city streets | Main St, Kirby Dr (parts) |
| `secondary` | Arterial — major through-streets | Richmond Ave, Shepherd Dr, Westheimer Rd |
| `tertiary` | Collector — connects neighborhoods to arterials | Dunlavy St, W 20th St |
| `residential` | Local / neighborhood street | most streets in the Heights, Montrose, Meyerland |
| `unclassified` | Minor street that doesn't fit the hierarchy (often industrial/edge cases) | scattered |
| `*_link` (e.g., `secondary_link`) | Turn lane, connector, or slip road between two roads | turn ramps at major intersections |

## Geometry & measurement

| Variable | Type | Units | Description |
|---|---|---|---|
| `length_ft` | float | feet | Segment centerline length, measured in EPSG:2278 (Texas State Plane, US ft). Median ≈ 304 ft ≈ one Houston block. |
| `bearing` | float | degrees (0–360, 0 = north) | Compass direction from the segment's start node to its end node. Used internally for dual-carriageway detection; not a design feature. |
| `geometry` | LineString | — | The segment's shape, CRS EPSG:2278. |

## Street design features (tier 2 — from OSM tags, coverage varies)

| Variable | Type | Units / values | Coverage | Description |
|---|---|---|---|---|
| `oneway` | bool | true/false | 100% | One-way traffic? In the merged network this means *genuinely* one-way (Montrose-style couplets etc.) — merged divided roads are `false`. |
| `lanes` | float | count | 85% | **OSM** total cross-section lanes (sum of both halves on merged roads). For analysis use `lanes_final` (tier 3) which prefers the city's authoritative count. |
| `maxspeed_mph` | float | mph | 14% | **Original OSM** posted speed (kept for provenance). For analysis use `posted_speed_mph` below instead. |
| `width_ft` | float | feet | **0%** | OSM roadway width — untagged in Houston. Superseded by `roadway_width_ft` (tier 3), now 98.6% covered. |
| `sidewalk` | text | `both`, `one_side`, `none`, missing | 17% | Sidewalk presence, collapsed from several OSM tagging styles. Missing = untagged, NOT "no sidewalk." |
| `cycleway` | text | `none`, `lane`, `track`, `shared_lane`, … (pipe-joined if mixed) | 10% | Bike infrastructure on the segment. Same caveat: missing = untagged. |
| `parking` | text | `present`, `none`, missing | 2% | On-street parking. Too sparse to use; conflate from city data later. |
| `lit` | text | `yes`, `no`, missing | 22% | Street lighting. |
| `surface` | text | `asphalt`, `concrete`, … | 73% | Pavement surface type. |

## Conflated city data (tier 3 — joined from City of Houston / Public Works)

Source for speed: Houston Public Works "Speed Limit" layer (`TDO/Traffic_gx/2`), via the city GeoHub (staging host `geogimstest`; production host was unreachable 2026-06-12). Matched by snapping 5 sample points per segment to the nearest city speed line within 60 ft. See `reports/speed_conflation_report.md`.

| Variable | Type | Units / values | Description |
|---|---|---|---|
| `posted_speed_mph` | float | mph | **Final posted speed for analysis** — 100% populated. Value priority recorded in `speed_source`. |
| `speed_source` | text | see below | Where `posted_speed_mph` came from. |
| `maxspeed_city` | float | mph | Raw city-matched posted speed (NaN if no confident match). |
| `match_frac` | float | 0–1 | Share of the segment's 5 sample points that snapped to a city speed line. |
| `city_name` | text | — | Street name from the matched city line (for audit). |
| `speed_name_match` | bool | — | Does the city street name agree with the OSM `name`? Confidence flag on the spatial match (~86% true on city matches). |

`speed_source` values:
- **`city`** — matched to the city's posted-speed network. Authoritative. (~18% of segments, ~48% of arterials/collectors.)
- **`osm`** — no city match, but OSM carried a posted speed.
- **`default_30_local`** — residential/local class, unposted → Texas prima facie 30 mph (legal default, not a measurement).
- **`default_30_unposted`** — higher OSM class but not on the city's posted network (median ~1,100 ft from any city speed line, i.e. genuinely unposted) → also 30 mph by TX default. **This is the set to sensitivity-test** if posted speed ever drives a published figure.

> `posted_speed_mph` is **posted**, not **operating**, speed. The causal model treats *operating* speed as the design→severity mediator; that needs a different source (speed studies / probe data) and is not this column.

### Lanes, width, median (Houston Public Works Speed Limit layer)

Same source and snap-match as speed. See `reports/lanes_width_median_report.md`.

| Variable | Type | Units / values | Description |
|---|---|---|---|
| `lanes_final` | float | count | **Total cross-section lanes for analysis** — 98.6% covered. Priority: city → OSM → local 2-lane default. |
| `lanes_source` | text | `city` / `osm` / `default_local_2` / `none` | Where `lanes_final` came from. |
| `city_lanes` | float | count | Raw city-matched lane count (NaN if no match). |
| `lanes_osm_city_agree` | bool | — | Where both OSM and city exist, do they agree within 1 lane? (79% true.) QC flag — where they differ the city is usually higher (OSM tags one direction of a divided road). |
| `roadway_width_ft` | float | feet | **Roadway (travel-lane) width for analysis** — 98.6% covered, was 0% in OSM. = `lanes_final` × avg lane width. Excludes the median. |
| `avg_lane_width_ft` | float | feet | City average lane width (~12 ft almost everywhere; 11 occasionally). |
| `width_source` | text | `city_lanes_x_width` / `lanes_x_12ft_assumed` / `none` | How `roadway_width_ft` was derived. |
| `median_type` | text | `Raised` / `Depressed` / `TWLT` / `Undivided` / `Divided (unspecified)` | Median design. `TWLT` = continuous center two-way left-turn lane. `Divided (unspecified)` = a merged divided road with no city median record. |
| `median_source` | text | `city` / `merged_dual` / `default_local_undivided` / `none` | Where `median_type` came from. |
| `median_width_ft` | float | feet | City-measured median width (not defaulted; 17% covered). |
| `geom_match_frac` | float | 0–1 | Share of the segment's sample points that snapped to a city line in this conflation. |

Lane semantics note: the city's `NO_OF_LANES` is **total cross-section** on its orientation-coded lines (verified Memorial Dr = 6 = 3+3), matching our merged `lanes`. ~14% of city lines are per-direction coded — a residual ambiguity, mitigated by preferring whole-road matches and the OSM cross-check.

### Traffic volume & operating speed (Houston Public Works count stations)

Source: Traffic_gx count stations (layers 4 major / 5 local) joined to count readings (table 22) by `LocationID`. Most recent valid reading per station; stations snapped to nearest segment (≤150 ft), then ADT propagated along same-named corridors. See `reports/adt_conflation_report.md`.

| Variable | Type | Units | Description |
|---|---|---|---|
| `adt` | float | vehicles/day | **Average daily traffic — the exposure confounder.** Coverage: **98% of primary, 97% of secondary** arterials; 34% tertiary, 6% residential; 30% overall (ADT is measured at ~320 stations citywide-in-district, so it's dense on big roads, sparse on locals). |
| `adt_source` | text | `measured` / `street_median` / *(blank)* | `measured` = a count station on this segment; `street_median` = inherited from same-named corridor; blank = no count (NOT imputed here — ADT imputation is a deliberate, separate modeling step). |
| `adt_year` | int | year | Year of the reading used (range 2012–2026). |
| `n_adt_stations` | int | count | Number of count stations mapped onto the segment. |
| `op_speed_85_mph` | float | mph | **85th-percentile measured (operating) speed** — the design→severity **MEDIATOR** in the DAG. ~4% coverage. **Model as the mechanism; do NOT adjust for it.** Not a risk predictor. Distinct from `posted_speed_mph`. |
| `op_speed_source` | text | `measured` / *(blank)* | Provenance of `op_speed_85_mph`. |

> ADT is treated as total (both directions) at the count location. Most local streets have no station; we intentionally leave their ADT blank rather than class-impute, because imputing a confounder is a modeling choice to be made (and sensitivity-tested) explicitly.

### Neighborhood demographics (Census ACS — confounder + equity overlay)

Source: U.S. Census ACS 2023 5-year, **block group** level; each segment inherits the block group containing its midpoint (geometry from Census TIGERweb). 100% of segments assigned; District C spans ~233 block groups. See `reports/demographics_conflation_report.md`.

| Variable | Type | Units | Description |
|---|---|---|---|
| `bg_geoid` | text | — | 12-digit Census block-group ID the segment falls in. |
| `pop` | float | people | Block-group population. |
| `pop_density_sqmi` | float | people/sq mi | Population density. |
| `median_hh_income` | float | $ | Median household income (top-coded ~$250k; `-666666666` "not available" sentinels cleaned to blank). |
| `pct_poverty` | float | % | Share below the poverty line (from C17002, the BG-available poverty table). |
| `pct_white_nh`, `pct_black_nh`, `pct_hispanic` | float | % | Race/ethnicity shares (B03002). |
| `pct_zero_car_hh` | float | % | Households with no vehicle (from B25044) — ties demographics to walking/transit exposure and the equity question. |

> **Ecological attribution:** these are *neighborhood* values attached to every street in that neighborhood — appropriate as a DAG confounder and equity overlay, but NOT a street-level measurement; don't read a block-group figure as a property of one street. Block-group ACS estimates also carry non-trivial margins of error (especially median income). Substitutions made because the detailed poverty (B17001) and vehicle (B08201) tables are not published at block-group level: poverty via **C17002**, vehicles via **B25044**.

## Intersection context (tier 1 — computed from the street graph)

| Variable | Type | Description |
|---|---|---|
| `deg_u`, `deg_v` | int | Number of street legs meeting at each endpoint. 1 = dead end, 2 = pseudo-node, 3 = T-intersection, 4 = crossroads, 5+ = complex junction. |
| `signal_u`, `signal_v` | bool | Traffic signal at that endpoint (OSM `highway=traffic_signals` node). |
| `n_signals` | int (0–2) | How many of the segment's two ends are signalized. |

## Divided-road merge variables

| Variable | Type | Description |
|---|---|---|
| `dual_carriageway` | bool | Segment was part of a confirmed divided-road pair (either side). |
| `merged_dual` | bool | This segment is the **representative centerline of a divided road** — its opposite half was merged into it. Geometry is the longer half's line (offset from the true median by up to ~75 ft; analysis-irrelevant, crash assignment uses both layers). |
| `n_twins_merged` | int | How many opposite-half segments were merged into this one. |
| `twin_seg_ids` | text | `seg_id`s of the merged-away halves, pipe-separated. |
| `lanes_rep_half`, `lanes_twin_half` | float | Audit columns: lanes of this half and of the merged half(s) before summing into `lanes`. |
| `rep_seg_id` | text | **(`merged_away` layer only.)** The `seg_id` of the representative segment that replaced this half. |

Merge method (see `reports/dual_merge_report.md`): twins = same-named, antiparallel, one-way segments within 150 ft; corridors are connected components of the twin relation, 2-colored into sides; the longer side is kept. 1,248 halves (86 mi) merged into 1,193 representatives; zero coloring conflicts.

## Known limitations (read before analyzing)

1. **Missing ≠ absent.** Every tier-2 OSM feature gap means "nobody tagged it," not "it isn't there." Coverage percentages above tell you how much to trust each column.
2. **Merged divided-road geometry is one half's line**, not the true median axis — fine for analysis and mapping, but don't measure median widths from it.
3. **Sliver cleanup applied** (p5 length now 145 ft). 31 named short segments without a same-named neighbor were conservatively kept; `*_link` turn lanes live in `removed_slivers`, not the network.
4. **`maxspeed` is posted speed**, not the operating speed that mediates crash severity in the causal model.
5. Crash counts, AADT (traffic volume), land use, and demographics are **not in this dataset yet** — they arrive with tier-3 conflation and the CRIS extract.
