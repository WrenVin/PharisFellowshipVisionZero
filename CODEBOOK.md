# Codebook — Houston Segment Dataset

Documents every variable in the segment datasets. One row = one **road segment**: a stretch of street between two intersections (or an intersection and a dead end), undirected — a two-way street is one row, not two, and (after the merge) a divided boulevard is one row, not two.

> **Scope: city-OWNED streets across the City of Houston** (73,330 segments), rebuilt 2026-06-14 from District C via `AREA` in `src/config.py`. TxDOT roads are excluded (crashes: CRIS Road_Cls_ID==5; road lines: TxDOT on-system inventory) so this is what the City owns/operates. Headline crash counts below are the displayed city-owned figures. Some inline coverage %s may still reflect the District C build; current coverage is in README. **Land use (`landuse_*`) is deferred** and absent.

**Files** (in `data/processed/`):

| File / layer | What it is | Use for |
|---|---|---|
| `district_c_segments_enriched.gpkg`, layer `segments` | **The analysis network**, clean network + conflated city data (speed; more to come). Canonical once conflation began. | All analysis and mapping. |
| `district_c_segments_clean.gpkg`, layer `segments` | Clean network before any external conflation (divided roads merged, slivers cleaned). | Provenance / rebuild base for conflation. |
| `district_c_segments_clean.gpkg`, layer `removed_slivers` | Audit: dropped turn lanes/slip roads (`*_link`) and unnamed sub-50-ft fragments, with `removal_reason`. | Audits; crash-assignment context. |
| `district_c_segments_clean.gpkg`, layer `merged_away` | Audit: removed halves of divided roads, `rep_seg_id` points to the representative segment. | Crash assignment (search both geometries, credit the representative). |
| `district_c_segments_merged.gpkg` | Post-merge, pre-cleanup snapshot. | Provenance only. |
| `district_c_segments.gpkg` | Pre-merge snapshot (every OSM half separate). | Provenance only. |
| `district_c_crashes.gpkg`, layer `crashes` | **Cleaned crash points** (TxDOT CRIS), deduped, geocoded, clipped to District C, severity-classified. Built by `src/build_crashes.py`. | Crash analysis; segment assignment (next step). |

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

### Neighborhood demographics (Census ACS — confounder + equity analysis)

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

> **Ecological attribution:** these are *neighborhood* values attached to every street in that neighborhood — appropriate as a DAG confounder and the basis for equity analysis, but NOT a street-level measurement; don't read a block-group figure as a property of one street. Block-group ACS estimates also carry non-trivial margins of error (especially median income). Substitutions made because the detailed poverty (B17001) and vehicle (B08201) tables are not published at block-group level: poverty via **C17002**, vehicles via **B25044**.

### Sidewalks (OSM-derived — no official Houston inventory exists)

Houston publishes no complete sidewalk inventory, so this is built from OSM's ~344 mi of separately-mapped `footway=sidewalk` lines in District C, associated to each street by side. Search distance scales with road width (half-width + 25 ft, clamped 30–60 ft). See `reports/sidewalk_conflation_report.md`.

| Variable | Type | Values | Description |
|---|---|---|---|
| `sidewalk_presence` | text | `both` / `one_side` / `partial` / `none` | Sidewalk on both sides, one side, partial (some coverage but neither side ≥50% of the segment), or none mapped. |
| `sw_left_frac`, `sw_right_frac` | float | 0–1 | Continuous per-side coverage (share of the segment's sample points with a sidewalk on that side). Side is relative to digitized direction, not compass — it separates "both vs one side", not which cardinal side. |
| `sidewalk_source` | text | `osm_footway` / `osm_road_tag` | Inferred from separate footway lines, or (fallback where none mapped) the road's OSM `sidewalk=*` tag. |

Coverage: at least one side on ~56% of segments (22% of arterials have both sides); `none` on ~44%.

> **Missing ≠ absent**, strongly here: `none` means no sidewalk *mapped* within the search distance. It's good evidence of a gap, but OSM completeness is uneven — not a field survey. Supersedes the raw OSM `sidewalk` column (16% coverage) for analysis.

### Adjacent land use (City of Houston / HCAD parcels — confounder)

Source: City of Houston "Land Use (Grouped)" parcel layer (HCAD). For each segment, parcels whose polygon comes within 100 ft are summarized **area-weighted** by category. See `reports/landuse_conflation_report.md`.

| Variable | Type | Values / units | Description |
|---|---|---|---|
| `landuse_dominant` | text | Residential / Commercial / Industrial / Institutional / Parks-Open / Undeveloped / Other | Land-use category with the largest adjacent land **area** within 100 ft. |
| `pct_residential`, `pct_commercial`, `pct_industrial` | float | % | Area share of nearby land in each category (Commercial = commercial+office). |
| `n_parcels_nearby` | int | count | Parcels within 100 ft of the segment. |
| `landuse_source` | text | `hcad_parcels` / `none` | Present on 79% of segments (78% of arterials). |

> Coverage is 79% because ~21% of segments are roads through **large non-parceled areas** — Hermann Park, Rice University, the Texas Medical Center, cemeteries, bayou greenways (nearest parcel a median ~340 ft away). Those are left `none`, not mislabeled. HCAD "stacked" condo records (shared footprint) are de-duplicated. Confounder, not mediator: land use shapes both road design and crash counts.

## Crash points — `district_c_crashes.gpkg` (separate file, not a segment column yet)

TxDOT CRIS crashes (public extracts), one row per crash, deduped by `Crash_ID`, geocoded, clipped to the City of Houston (EPSG:2278). **City-OWNED streets only**, two filters: (1) keep crashes the state classifies on a City Street (**CRIS `Road_Cls_ID` == 5**) — drops Interstate/US-State/FM/County/Tollway; (2) drop roads on **TxDOT's on-system inventory** (at-grade state routes: S Main/US-90A, SH 6, FM 1093 / Westheimer west of the Galleria). Displayed: **349,160 crashes, 7,927 KSI** = 52% of all in-city KSI, matching the City's VZAP (~51% on city-owned). (The `crashes.gpkg` holds the class-5 stage, 381,322 / 8,821 KSI, before the TxDOT-road drop applied at export.) See `reports/crash_build_report.md`.

| Variable | Type | Values | Description |
|---|---|---|---|
| `Crash_ID` | int | — | TxDOT CRIS crash identifier (unique). |
| `year`, `month`, `date` | int / int / text | — | Crash year, month (1–12), and date (from `Crash_Date`). Month powers the dashboard's by-month drill-down. |
| `hour` | int | 0–23 | Hour of day (from `Crash_Time`). Powers the by-time-of-day chart. ~99.9% parseable. |
| `kabco` | text | K / A / B / C / O / UNK | Severity on the KABCO scale (K=fatal, A=serious, B=minor, C=possible, O=none). Decoded from `Crash_Sev_ID` (4=K,1=A,2=B,3=C,5=O,0=UNK), verified against the fatal flag + injury counts. |
| `fatal`, `serious`, `severe` | bool | — | `severe` = K or A — the negative-binomial **outcome** (matches the HIN definition). **7,927 severe on city-owned streets (1,267 K + 6,660 A).** |
| `yll` | float | years | **Years of Life Lost (estimated)** — YPLL before age 75 (CDC convention): Σ max(0, 75 − age) over the people killed in the crash, from the CRIS person table. The public extract records a victim age for only ~half of fatal crashes (person detail suppressed on the rest), so fatal crashes without a recorded age get the mean (~40 yr/fatality). **Total ≈ 52,000 estimated YLL** city-owned; anchored to the 1,267 fatal crashes. 0 for non-fatal crashes. |
| `any_injury` | bool | — | Any injury (Tot_Injry_Cnt > 0). |
| `mode` | text | pedestrian / bicycle / motor vehicle | Crash mode (pedestrian takes precedence if a crash has both). |
| `involves_ped` | bool | — | Any pedestrian in the crash (CRIS `unit` Unit_Desc_ID=4, union with `person` Prsn_Type_ID=4). **7,621 ped crashes, 1,787 severe, 410 fatal** (city-owned streets). |
| `involves_bike` | bool | — | Any pedalcyclist (Unit_Desc_ID=3 / Prsn_Type_ID=3). **2,954 bike crashes, 402 severe, 74 fatal** (city-owned streets). |
| `Crash_Sev_ID` | int | 0–5 | Raw CRIS severity code (see `kabco`). |
| `speed_limit` | float | mph | Crash-record posted speed limit (`Crash_Speed_Limit`). |
| `coord_source` | text | cris / reported | CRIS-geocoded lat/long, or officer-reported fallback. |

> ~10% of citywide crashes are ungeocoded and excluded — relevant to the reporting-collider/underreporting concern. Mode is now included (`mode`/`involves_ped`/`involves_bike`); note vulnerable users are **~3% of all crashes but ~30% of severe crashes and ~35% of deaths** on District C city streets.

## Crash outcome counts (per segment — assigned from CRIS)

Added by `src/assign_crashes.py`: each crash credited to its single nearest segment within 200 ft (divided-road halves searched too, credited to the representative segment). Counts sum back to the assigned-crash total (each crash counted once). Reflects whatever years are in `data/raw/CRIS/` (currently 2016–2025 + partial 2026). See `reports/crash_assignment_report.md`.

| Variable | Type | Description |
|---|---|---|
| `n_crash` | int | All assigned crashes on the segment. |
| `n_injury` | int | Crashes with any injury. |
| `n_severe` | int | **Severe (K+A) crashes — the negative-binomial outcome.** 5,400 segments (7.4%) have ≥1; max ~11. City-owned streets only. |
| `n_fatal` | int | Fatal (K) crashes. |
| `n_ped`, `n_bike` | int | Crashes involving a pedestrian / cyclist. |
| `n_ped_severe`, `n_bike_severe` | int | Severe ped / bike crashes (the policy-relevant vulnerable-user outcome). |

> ~99% of city-owned-street crashes assigned (median 4 ft to segment) now that TxDOT roads are filtered out upstream. Intersection crashes go to the nearest leg (count-preserving simplification). The Vision Zero dashboard also overlays the City of Houston's official Vision Zero HIN (2022) — `docs/hin.geojson`, 1,261 segments citywide — distinct from these CRIS-derived counts.

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
5. **Operating speed is sparse** (`op_speed_85_mph`, ~4% coverage) — the design→severity mediator is measured at only a handful of count stations, so any analysis using it leans on those few segments. ADT, land use, demographics, and crash counts are all now conflated in (see sections above).
