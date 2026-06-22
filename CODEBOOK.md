# Codebook — Houston Segment Dataset

Documents every variable in the segment datasets. One row = one **road segment**: a stretch of street between two intersections (or an intersection and a dead end), undirected — a two-way street is one row, not two, and (after the merge) a divided boulevard is one row, not two.

> **Scope: surface streets across the City of Houston** (75,260 segments), rebuilt 2026-06-14 (area set by `AREA` in `src/config.py`; `seg_id` prefix `H-` from `cfg.SEG_PREFIX`). Only limited-access freeways/tollways are excluded; at-grade arterials including state-owned ones (S Main/US-90A, SH 6, Westheimer/FM 1093) are kept and **labeled** `on_txdot` (city vs TxDOT ownership, from TxDOT's roadway inventory) rather than dropped — matching Austin's Vision Zero dashboard and the City's own HIN. ~11% of the surface-street KSI shown are on TxDOT-owned arterials (the rest city streets; freeways, which are state-owned, are excluded entirely). `on_txdot` is set only where a segment runs *along* a TxDOT on-system roadway (within 60 ft AND bearing within 30 deg for >=50% of its length); interstates (`RTE_PRFX` 'IH') are dropped from the match set and a hand-curated list of ~42 false-positive `seg_id`s is forced city-owned, so streets that merely cross over or run under a freeway are not mislabeled. ~1,438 segments are labeled TxDOT. Processed filenames are `houston_*.gpkg`. **Land use (`landuse_*`) is deferred** at city scale and absent from the current data.

**Files** (in `data/processed/`):

| File / layer | What it is | Use for |
|---|---|---|
| `houston_segments_enriched.gpkg`, layer `segments` | **The analysis network**, clean network + all conflated layers (speed, lanes/width/median, ADT + operating speed, sidewalks, ACS demographics, crash counts). Land use deferred at city scale. The canonical dataset. | All analysis and mapping. |
| `houston_segments_clean.gpkg`, layer `segments` | Clean network before any external conflation (divided roads merged, slivers cleaned). | Provenance / rebuild base for conflation. |
| `houston_segments_clean.gpkg`, layer `removed_slivers` | Audit: dropped turn lanes/slip roads (`*_link`) and unnamed sub-50-ft fragments, with `removal_reason`. | Audits; crash-assignment context. |
| `houston_segments_clean.gpkg`, layer `merged_away` | Audit: removed halves of divided roads, `rep_seg_id` points to the representative segment. | Crash assignment (search both geometries, credit the representative). |
| `houston_segments_merged.gpkg` | Post-merge, pre-cleanup snapshot. | Provenance only. |
| `houston_segments.gpkg` | Pre-merge snapshot (every OSM half separate). | Provenance only. |
| `houston_crashes.gpkg`, layer `crashes` | **Cleaned crash points** (TxDOT CRIS), deduped, geocoded, clipped to the City of Houston, severity-classified. Built by `src/build_crashes.py`. | Crash analysis; segment assignment (next step). |

Source data: OpenStreetMap (OSM), pulled 2026-06-14, clipped to the City of Houston boundary. Freeways, ramps, **frontage/feeder roads** (TxDOT right-of-way), and service roads (alleys/driveways) are excluded. Pipeline: `src/pull_osm.py` → `src/build_segments.py` → `src/merge_dual_carriageways.py` → `src/clean_slivers.py`.

**Sliver cleanup** (see `reports/sliver_cleanup_report.md`): `*_link` segments (turn lanes/slip roads — intersection plumbing, not streets) dropped; short (<100 ft) named pieces (median crossings, intersection interiors) **absorbed** into their longest same-named neighbor with geometry and length preserved; unnamed fragments <50 ft dropped. An absorbed segment's `length_ft` includes everything it absorbed; its endpoint columns (`u`/`v`, `deg_*`, `signal_*`) reflect the new, post-absorption endpoints.

**Coverage** = % of segments with a non-missing value (from `reports/feature_coverage.md`). Missing means "not tagged in OSM," **not** "feature absent on the ground."

## Identifiers & topology

| Variable | Type | Description |
|---|---|---|
| `seg_id` | text | **Stable segment ID** (`H-00001`...; prefix set by `cfg.SEG_PREFIX`), assigned before the dual-carriageway merge. The permanent key for joins across all layers and pipeline steps. |
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

| OSM value | Means | Examples |
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
| `length_ft` | float | feet | Segment centerline length, measured in EPSG:2278 (Texas State Plane, US ft). Median ≈ 352 ft ≈ one Houston block. |
| `bearing` | float | degrees (0–360, 0 = north) | Compass direction from the segment's start node to its end node. Used internally for dual-carriageway detection; not a design feature. |
| `geometry` | LineString | — | The segment's shape, CRS EPSG:2278. |

## Street design features (tier 2 — from OSM tags, coverage varies)

| Variable | Type | Units / values | Coverage | Description |
|---|---|---|---|---|
| `oneway` | bool | true/false | 100% | One-way traffic? In the merged network this means *genuinely* one-way (Montrose-style couplets etc.) — merged divided roads are `false`. |
| `lanes` | float | count | 56% | **OSM** total cross-section lanes (sum of both halves on merged roads). For analysis use `lanes_final` (tier 3) which prefers the city's authoritative count. |
| `maxspeed_mph` | float | mph | 8% | **Original OSM** posted speed (kept for provenance). For analysis use `posted_speed_mph` below instead. |
| `width_ft` | float | feet | **0%** | OSM roadway width — untagged in Houston. Superseded by `roadway_width_ft` (tier 3), now 95.1% covered. |
| `sidewalk` | text | `both`, `one_side`, `none`, missing | 8% | Sidewalk presence, collapsed from several OSM tagging styles. Missing = untagged, NOT "no sidewalk." |
| `cycleway` | text | `none`, `lane`, `track`, `shared_lane`, … (pipe-joined if mixed) | 5% | Bike infrastructure on the segment. Same caveat: missing = untagged. |
| `parking` | text | `present`, `none`, missing | 0.6% | On-street parking. Too sparse to use; conflate from city data later. |
| `lit` | text | `yes`, `no`, missing | 9% | Street lighting. |
| `surface` | text | `asphalt`, `concrete`, … | 26% | Pavement surface type. |

## Conflated city data (tier 3 — joined from City of Houston / Public Works)

Source for speed: Houston Public Works "Speed Limit" layer (`TDO/Traffic_gx/2`), via the city GeoHub (staging host `geogimstest`; production host was unreachable 2026-06-12). Matched by snapping 5 sample points per segment to the nearest city speed line within 60 ft. See `reports/speed_conflation_report.md`.

| Variable | Type | Units / values | Description |
|---|---|---|---|
| `posted_speed_mph` | float | mph | **Final posted speed for analysis** — 100% populated. Value priority recorded in `speed_source`. |
| `speed_source` | text | see below | Where `posted_speed_mph` came from. |
| `maxspeed_city` | float | mph | Raw city-matched posted speed (NaN if no confident match). |
| `match_frac` | float | 0–1 | Share of the segment's 5 sample points that snapped to a city speed line. |
| `city_name` | text | — | Street name from the matched city line (for audit). |
| `speed_name_match` | bool | — | Does the city street name agree with the OSM `name`? Confidence flag on the spatial match (85.0% true on city matches). |

`speed_source` values:
- **`city`** — matched to the city's posted-speed network. Authoritative. (17.0% of segments, 45.5% of arterials/collectors.)
- **`osm`** — no city match, but OSM carried a posted speed.
- **`default_30_local`** — residential/local class, unposted → Texas prima facie 30 mph (legal default, not a measurement).
- **`default_30_unposted`** — higher OSM class but not on the city's posted network (median ~1,100 ft from any city speed line, i.e. genuinely unposted) → also 30 mph by TX default. **This is the set to sensitivity-test** if posted speed ever drives a published figure.

> `posted_speed_mph` is **posted**, not **operating**, speed. The causal model treats *operating* speed as the design→severity mediator; that needs a different source (speed studies / probe data) and is not this column.

### Lanes, width, median (Houston Public Works Speed Limit layer)

Same source and snap-match as speed. See `reports/lanes_width_median_report.md`.

| Variable | Type | Units / values | Description |
|---|---|---|---|
| `lanes_final` | float | count | **Total cross-section lanes for analysis** — 95.1% covered. Priority: city → OSM → local 2-lane default. |
| `lanes_source` | text | `city` / `osm` / `default_local_2` / `none` | Where `lanes_final` came from. |
| `city_lanes` | float | count | Raw city-matched lane count (NaN if no match). |
| `lanes_osm_city_agree` | bool | — | Where both OSM and city exist (10,990 segments), do they agree within 1 lane? (78.4% true.) QC flag — where they differ the city is usually higher (OSM tags one direction of a divided road). |
| `roadway_width_ft` | float | feet | **Roadway (travel-lane) width for analysis** — 95.1% covered, was 0% in OSM. = `lanes_final` × avg lane width. Excludes the median. |
| `avg_lane_width_ft` | float | feet | City average lane width (~12 ft almost everywhere; 11 occasionally). |
| `width_source` | text | `city_lanes_x_width` / `lanes_x_12ft_assumed` / `none` | How `roadway_width_ft` was derived. |
| `median_type` | text | `Raised` / `Depressed` / `TWLT` / `Undivided` / `Divided (unspecified)` | Median design. `TWLT` = continuous center two-way left-turn lane. `Divided (unspecified)` = a merged divided road with no city median record. |
| `median_source` | text | `city` / `merged_dual` / `default_local_undivided` / `none` | Where `median_type` came from. |
| `median_width_ft` | float | feet | City-measured median width (not defaulted; 16.3% covered). |
| `geom_match_frac` | float | 0–1 | Share of the segment's sample points that snapped to a city line in this conflation. |

Lane semantics note: the city's `NO_OF_LANES` is **total cross-section** on its orientation-coded lines (verified Memorial Dr = 6 = 3+3), matching our merged `lanes`. ~14% of city lines are per-direction coded — a residual ambiguity, mitigated by preferring whole-road matches and the OSM cross-check.

### Traffic volume & operating speed (Houston Public Works count stations)

Source: Traffic_gx count stations (layers 4 major / 5 local) joined to count readings (table 22) by `LocationID`. Most recent valid reading per station; stations snapped to nearest segment (≤150 ft), then ADT propagated along same-named corridors. See `reports/adt_conflation_report.md`.

| Variable | Type | Units | Description |
|---|---|---|---|
| `adt` | float | vehicles/day | **Average daily traffic — the exposure confounder.** Coverage: **84.6% of primary, 81.3% of secondary** arterials; 34.7% tertiary, 4.4% residential; 25.2% overall (ADT is measured at ~2,494 count stations citywide, so it's dense on big roads, sparse on locals). |
| `adt_source` | text | `measured` / `street_median` / *(blank)* | `measured` = a count station on this segment; `street_median` = inherited from same-named corridor; blank = no count (NOT imputed here — ADT imputation is a deliberate, separate modeling step). |
| `adt_year` | int | year | Year of the reading used (range 2012–2026). |
| `n_adt_stations` | int | count | Number of count stations mapped onto the segment. |
| `op_speed_85_mph` | float | mph | **85th-percentile measured (operating) speed** — the design→severity **MEDIATOR** in the DAG. ~3.1% coverage (2,370 segments). **Model as the mechanism; do NOT adjust for it.** Not a risk predictor. Distinct from `posted_speed_mph`. |
| `op_speed_source` | text | `measured` / *(blank)* | Provenance of `op_speed_85_mph`. |

> ADT is treated as total (both directions) at the count location. Most local streets have no station; we intentionally leave their ADT blank rather than class-impute, because imputing a confounder is a modeling choice to be made (and sensitivity-tested) explicitly.

### Neighborhood demographics (Census ACS — confounder + equity analysis)

Source: U.S. Census ACS 2023 5-year, **block group** level; each segment inherits the block group containing its midpoint (geometry from Census TIGERweb). 96.8% of segments assigned; the city spans ~2,445 block groups. See `reports/demographics_conflation_report.md`.

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

Houston publishes no complete sidewalk inventory, so this is built from OSM's ~2,410 mi of separately-mapped `footway=sidewalk` lines citywide, associated to each street by side. Search distance scales with road width (half-width + 25 ft, clamped 30–60 ft). See `reports/sidewalk_conflation_report.md`.

| Variable | Type | Values | Description |
|---|---|---|---|
| `sidewalk_presence` | text | `both` / `one_side` / `partial` / `none` | Sidewalk on both sides, one side, partial (some coverage but neither side ≥50% of the segment), or none mapped. |
| `sw_left_frac`, `sw_right_frac` | float | 0–1 | Continuous per-side coverage (share of the segment's sample points with a sidewalk on that side). Side is relative to digitized direction, not compass — it separates "both vs one side", not which cardinal side. |
| `sidewalk_source` | text | `osm_footway` / `osm_road_tag` | Inferred from separate footway lines, or (fallback where none mapped) the road's OSM `sidewalk=*` tag. |

Coverage: at least one side on 29.2% of segments; both sides 4.9%; `none` on 70.8% (OSM completeness is uneven).

> **Missing ≠ absent**, strongly here: `none` means no sidewalk *mapped* within the search distance. It's good evidence of a gap, but OSM completeness is uneven — not a field survey. Supersedes the raw OSM `sidewalk` column (16% coverage) for analysis.

### Adjacent land use (City of Houston / HCAD parcels — confounder)

> **Deferred at city scale — these columns are currently absent.** Land use was conflated for the District C build (numbers below reflect that run), but the citywide fetch (~1.5 M HCAD parcels) needs a tiled/bbox approach not yet built, so `landuse_*` is not present in the current `houston_*` datasets. Section kept for when it is rebuilt.

Source: City of Houston "Land Use (Grouped)" parcel layer (HCAD). For each segment, parcels whose polygon comes within 100 ft are summarized **area-weighted** by category. See `reports/landuse_conflation_report.md`.

| Variable | Type | Values / units | Description |
|---|---|---|---|
| `landuse_dominant` | text | Residential / Commercial / Industrial / Institutional / Parks-Open / Undeveloped / Other | Land-use category with the largest adjacent land **area** within 100 ft. |
| `pct_residential`, `pct_commercial`, `pct_industrial` | float | % | Area share of nearby land in each category (Commercial = commercial+office). |
| `n_parcels_nearby` | int | count | Parcels within 100 ft of the segment. |
| `landuse_source` | text | `hcad_parcels` / `none` | Present on 79% of segments (78% of arterials). |

> Coverage is 79% because ~21% of segments are roads through **large non-parceled areas** — Hermann Park, Rice University, the Texas Medical Center, cemeteries, bayou greenways (nearest parcel a median ~340 ft away). Those are left `none`, not mislabeled. HCAD "stacked" condo records (shared footprint) are de-duplicated. Confounder, not mediator: land use shapes both road design and crash counts.

## Crash points — `houston_crashes.gpkg` (separate file, not a segment column yet)

TxDOT CRIS crashes (public extracts), one row per crash, deduped by `Crash_ID`, geocoded, clipped to the City of Houston (EPSG:2278). **Surface streets**: only limited-access freeways/tollways/ramps/frontage are excluded; at-grade arterials incl. state-owned (S Main/US-90A, SH 6, Westheimer/FM 1093) are KEPT and labeled city- vs TxDOT-owned (`on_txdot`). **421,699 crashes, 9,928 KSI** (2016–2025 + partial 2026). ~11% of these are on TxDOT-owned arterials (rest city streets); freeways (state-owned) are excluded entirely, so the often-cited "~half of KSI on state roads" is mostly freeways, out of scope here. See `reports/crash_build_report.md`.

| Variable | Type | Values | Description |
|---|---|---|---|
| `Crash_ID` | int | — | TxDOT CRIS crash identifier (unique). |
| `year`, `month`, `date` | int / int / text | — | Crash year, month (1–12), and date (from `Crash_Date`). Month powers the dashboard's by-month drill-down. |
| `hour` | int | 0–23 | Hour of day (from `Crash_Time`). Powers the by-time-of-day chart. ~99.9% parseable. |
| `kabco` | text | K / A / B / C / O / UNK | Severity on the KABCO scale (K=fatal, A=serious, B=minor, C=possible, O=none). Decoded from `Crash_Sev_ID` (4=K,1=A,2=B,3=C,5=O,0=UNK), verified against the fatal flag + injury counts. |
| `fatal`, `serious`, `severe` | bool | — | `severe` = K or A — the negative-binomial **outcome** (matches the HIN definition). **9,928 severe on surface streets (1,687 K + 8,241 A).** |
| `yll` | float | years | **Years of Life Lost (estimated)** — YPLL before age 75 (CDC convention): Σ max(0, 75 − age) over the people killed in the crash, from the CRIS person table. The public extract records a victim age for only ~half of fatal crashes (person detail suppressed on the rest), so fatal crashes without a recorded age get the mean (~40 yr/fatality). **Total ≈ 69,500 estimated YLL**; anchored to the 1,687 fatal crashes. 0 for non-fatal crashes. |
| `any_injury` | bool | — | Any injury (Tot_Injry_Cnt > 0). |
| `mode` | text | pedestrian / bicycle / motor vehicle | Crash mode (pedestrian takes precedence if a crash has both). |
| `involves_ped` | bool | — | Any pedestrian in the crash (CRIS `unit` Unit_Desc_ID=4, union with `person` Prsn_Type_ID=4). **8,772 ped crashes, 2,226 severe, 597 fatal** (surface streets). |
| `involves_bike` | bool | — | Any pedalcyclist (Unit_Desc_ID=3 / Prsn_Type_ID=3). **3,293 bike crashes, 459 severe, 89 fatal** (surface streets). |
| `Crash_Sev_ID` | int | 0–5 | Raw CRIS severity code (see `kabco`). |
| `speed_limit` | float | mph | Crash-record posted speed limit (`Crash_Speed_Limit`). |
| `coord_source` | text | cris / reported | CRIS-geocoded lat/long, or officer-reported fallback. |

> ~10% of citywide crashes are ungeocoded and excluded — relevant to the reporting-collider/underreporting concern. Mode is now included (`mode`/`involves_ped`/`involves_bike`); note vulnerable users are **~3% of all crashes but ~27% of severe crashes and ~41% of deaths** on city streets.

## Crash outcome counts (per segment — assigned from CRIS)

Added by `src/assign_crashes.py`: each crash credited to its single nearest segment within 200 ft (divided-road halves searched too, credited to the representative segment). Counts sum back to the assigned-crash total (each crash counted once). Reflects whatever years are in `data/raw/CRIS/` (currently 2016–2025 + partial 2026). See `reports/crash_assignment_report.md`.

| Variable | Type | Description |
|---|---|---|
| `n_crash` | int | All assigned crashes on the segment. |
| `n_injury` | int | Crashes with any injury. |
| `n_severe` | int | **Severe (K+A) crashes — the negative-binomial outcome.** 6,169 segments (8.2%) have ≥1; max 16. Surface streets (state arterials labeled `on_txdot`). |
| `n_fatal` | int | Fatal (K) crashes. |
| `n_ped`, `n_bike` | int | Crashes involving a pedestrian / cyclist. |
| `n_ped_severe`, `n_bike_severe` | int | Severe ped / bike crashes (the policy-relevant vulnerable-user outcome). |

> 98.2% of surface-street crashes assigned (median 4 ft to segment) now that freeways are filtered out upstream. Intersection crashes go to the nearest leg (count-preserving simplification). The Vision Zero dashboard also overlays the City of Houston's official Vision Zero HIN (2022) — `docs/hin.geojson`, 1,261 segments citywide — distinct from these CRIS-derived counts.

## Dashboard export fields (derived in `src/export_webmap_data.py` / `src/assign_crashes.py`)

These are not columns in the processed `.gpkg`; they are computed at export time for the web map (`docs/`).

| Variable | Where | Description |
|---|---|---|
| `on_hin` | per segment | True if >=50% of the segment's length runs within 50 ft of a 2022 HIN line (`docs/hin.geojson`), so a cross-street merely crossing an HIN arterial is not flagged. Attached to each crash point via its nearest segment. |
| `on_txdot` | per segment | True if the segment runs ALONG a TxDOT on-system roadway (within 60 ft AND bearing within 30 deg for >=50% of its length); interstates (`RTE_PRFX` 'IH') are excluded from the match set and ~42 hand-curated false-positive `seg_id`s are forced city-owned. ~1,438 segments labeled TxDOT. A LABEL (ownership view), not an exclusion. Also attached to each crash point via its nearest segment. |
| `seg_id` (on crash) | per crash | The nearest segment to each crash point, so the dashboard can cross-filter every panel to a clicked street/segment. |

**Exported files for the dashboard:**

- `docs/segments.geojson` — full per-segment property set (Street Explorer / `index.html`).
- `docs/segments_vz.geojson` — slim copy for the Vision Zero dashboard (`vision-zero.html`), only the 20 fields in `WEB_KEEP`: `seg_id`, `name`, `road_class`, `district`, `sn`, `on_txdot`, `on_hin`, `n_crash`, `n_severe`, `n_fatal`, `n_ped`, `n_ped_severe`, `n_bike`, `n_bike_severe`, `length_ft`, `lanes_final`, `roadway_width_ft`, `posted_speed_mph`, `sidewalk_presence`, `adt`.
- `docs/crash_points.json` — one array per crash, 21 fields in order: `[lat, lon, sev, fatal, ped, bike, year, date, hour, yll, district, inc_tier, on_hin, on_txdot, seg_id, sn, n_k, n_a, n_b, n_c, n_noinj]`. Fields 16–20 are the **per-crash person counts by KABCO injury severity** (`n_k` killed, `n_a` serious, `n_b` minor, `n_c` possible, `n_noinj` no-injury), pulled from the raw CRIS crash-level injury-count fields (`Death_Cnt`, `Sus_Serious_Injry_Cnt`, `Nonincap_Injry_Cnt`, `Poss_Injry_Cnt`, `Non_Injry_Cnt`) and matched by `Crash_ID`. `sev`/`fatal` are still the crash-level flags (`sev`=K or A, `fatal`=K). (The processed gpkg also carries a `kabco` letter, but the web export uses person counts, not `kabco`.)

### Crash costs (dashboard metric)

The Vision Zero dashboard shows an **economic** and **comprehensive** dollar cost of the crashes in view, computed live as `sum over people hurt of (FHWA per-person cost for that person's injury severity)`. Costs are **per person** (each victim counted at their KABCO injury level) from **FHWA, *Updated Crash Costs for Highway Safety Analysis* (FHWA-SA-25-021, Oct 2025), 2024 dollars** — the per-person table:

| KABCO injury | Economic | Comprehensive |
|---|---|---|
| K (killed) | $1,606,644 | $11,258,495 |
| A (serious) | $172,179 | $1,089,524 |
| B (minor) | $44,490 | $224,597 |
| C (possible) | $25,933 | $111,281 |
| O (no injury) | $6,269 | $10,196 |

Unknown-severity injuries carry no FHWA cost and are not counted. **Economic** = societal economic loss (medical, lost productivity, property, services); **comprehensive** adds the monetized value of lost quality/length of life, so its fatal portion overlaps the years-of-life-lost metric (different units, not additive). National figures, no state adjustment. Citywide all-severity, all years (2016–2025 + partial 2026): **~$15.3B economic / ~$64.8B comprehensive** (surface streets only). A conservative floor (CRIS undercount, ~10% ungeocoded crashes excluded, surface streets only, unknown-severity injuries excluded).

> **Per-person vs per-crash basis:** FHWA publishes both a per-crash-unit table (e.g. fatal crash = $2,238,500 economic, which bundles the average ~1.09 deaths + other injuries per fatal crash) and this per-person table (e.g. fatality = $1,606,644). The dashboard uses the **per-person** table on CRIS person counts to match how transportation cost analyses (and District Adjacent's own work) report the toll. This counts every victim of a multi-victim crash, unlike the dashboard's crash-based `killed`/KSI KPI counts.
- `district` (segment + crash) is the council-district letter; `sn` is the **Super Neighborhood POLYID** (1–88, or NA where the segment/crash falls in no Super Neighborhood — they don't tile the whole city). Both are export-time spatial joins from the City GIS Administrative_Boundary service (district by nearest, SN by point-in-polygon). `docs/superneighborhoods.geojson` carries each `POLYID` + `SNBNAME` for the dashboard's SN dropdown and outline; the dashboard treats district and SN as mutually exclusive filters.
- The dashboard's year/month/hour/day shading and charts all filter `crash_points.json` directly by the per-crash `date`/`year`/`hour` fields, so no pre-aggregated per-year file is needed. (An earlier `crash_year.json` served that role and has been removed.)

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

Merge method (see `reports/dual_merge_report.md`): twins = same-named, antiparallel, one-way segments within 150 ft; corridors are connected components of the twin relation, 2-colored into sides; the longer side is kept. 17,043 halves (1,255 mi) merged into 16,138 representatives; zero coloring conflicts.

## Known limitations (read before analyzing)

1. **Missing ≠ absent.** Every tier-2 OSM feature gap means "nobody tagged it," not "it isn't there." Coverage percentages above tell you how much to trust each column.
2. **Merged divided-road geometry is one half's line**, not the true median axis — fine for analysis and mapping, but don't measure median widths from it.
3. **Sliver cleanup applied** (p5 length now 134 ft). 292 named short segments without a same-named neighbor were conservatively kept; `*_link` turn lanes live in `removed_slivers`, not the network.
4. **`maxspeed` is posted speed**, not the operating speed that mediates crash severity in the causal model.
5. **Operating speed is sparse** (`op_speed_85_mph`, ~3.1% coverage) — the design→severity mediator is measured at only a handful of count stations, so any analysis using it leans on those few segments. ADT, demographics, and crash counts are all now conflated in (see sections above); land use is deferred at city scale.
