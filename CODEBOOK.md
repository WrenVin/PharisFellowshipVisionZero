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
| `lanes` | float | count | **85%** | **Total cross-section traffic lanes, both directions.** On merged divided roads this is the sum of both halves (e.g., Memorial = 3+3 = 6), so it means the same thing on every row. NaN if either half untagged. |
| `maxspeed_mph` | float | mph | 14% | **Original OSM** posted speed (kept for provenance). For analysis use `posted_speed_mph` below instead. |
| `width_ft` | float | feet | **0%** | Roadway width. Untagged in Houston OSM — must come from another source (city inventory, lanes × standard width, aerial imagery). Kept as a placeholder column. |
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
