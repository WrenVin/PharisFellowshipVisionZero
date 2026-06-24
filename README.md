# Vision Zero Houston

A traffic-safety analysis and dashboard for the **City of Houston**, built in partnership with the office of Council Member Joseph Panzarella (District C). This is the author's research project for the **Pharis Fellowship** (University of Houston Honors College / HPE Data Science Institute, summer 2026). The pipeline is area-agnostic (see *Retargeting* below) — it began on District C and now covers the whole city.

**Two public dashboards (one GitHub Pages site, shared data):**
- **🚦 Vision Zero view** (safety-first): https://wrenvin.github.io/PharisFellowshipVisionZero/vision-zero.html — the toll (people killed, **years of life lost**, seriously injured, and the **economic cost** of those crashes) and a concentration measure (about half of all KSI sits on ~2% of street-miles; a threshold-free **Gini coefficient** ~0.94 and a **Lorenz/concentration-curve panel** describe the whole distribution rather than one arbitrary "top X%" cutoff, with the City's 6% High Injury Network marked on the curve for comparison). Left-sidebar filters: find a street (search), council district (All / A–K, zooms and recomputes everything), super neighborhood (Houston's 88 named planning areas like Montrose or Second Ward; mutually exclusive with district, since the two geographies overlap), travel mode (everyone / driving / walking / biking), road owner (all / city-owned / TxDOT-owned), Show (people killed or injured vs all crashes), Display as (three map levels: shaded whole streets, shaded street segments per block [the default], or crash-location points), and an overlay of the City's official High Injury Network (2022) for comparison. Breakdowns respond to the active filters (including **Show**: with **all crashes** selected, every breakdown counts every crash rather than only KSI, so a street with crashes but no KSI still shows a distribution instead of empty bars): **by year (with a trend line), by month (seasonality across all years), by time of day, and by day of week** — each filterable by clicking a bar (one bucket) or dragging its range slider; the cyclical sliders (month / time of day / day of week) wrap, so a range like 6 PM–6 AM works — plus by travel mode, by neighborhood income (the equity angle), by road owner (city vs TxDOT), and a clickable "most dangerous streets" top-5 list. **Clicking any street or segment cross-filters the whole dashboard** (every KPI and panel recomputes for that selection); the popup shows the road's physical makeup and a "view this whole street" link widens a block to its corridor. Also: **draggable, reorderable data panels**; a manual "Blink crash locations" button; a shareable URL that encodes the current filters/selection; a **"Create report" button** that opens a full-screen "Build your report" dialog (filters pre-filled from the current view, plus checkboxes to include/omit each section), then exports a clean, page-break-safe **printable PDF** (headline stats, a one-line summary, the map, the selected breakdown charts, and a most-affected-streets table, with no UI chrome) for city-council and print use; and a "Data & methods" modal with linked official sources. Single-screen desktop layout, keyboard-accessible, mobile-responsive.
- **🗺️ Street Explorer** (data-first): https://wrenvin.github.io/PharisFellowshipVisionZero/ — every street, **color by any attribute** (design, traffic, demographics, crashes), **stacking filters**, search, click-to-pin info. Mobile-friendly; sources + vintages disclosed in-app. A **shareable URL** encodes the current color/filters/selection so a copied link reopens the same view (Share button, with a native share sheet on mobile); plus a loading spinner and a clear message if the large street file fails to load.

## Research question

Does a **feature-based (systemic) risk model** identify dangerous Houston streets that the City's **crash-based High Injury Network (HIN)** misses — and how much risk lies "off the HIN"?

- **Reactive screening (status quo):** the HIN maps where severe crashes have already clustered. It cannot flag a street that is dangerous by design but hasn't yet produced a recorded severe crash, and it inherits police-reporting bias.
- **Proactive screening (this project):** identify the road-design features that make streets dangerous (lanes, width, speed, missing crossings, land use) and flag every segment carrying those features, crash history or not (per FHWA systemic safety / NCHRP 893).
- The **divergence analysis** between the two maps is the headline output. Texas's ban on automated enforcement (HB 1631, 2019) makes this more than academic: a city that cannot enforce its way to safety must design its way there.

## Repo structure

```
data/
  raw/         # as-downloaded inputs (boundary, OSM pulls, CRIS crash extracts [gitignored])
  processed/   # analysis-ready layers (segments + crashes GeoPackages, inspection CSV)
  external/    # cached third-party pulls (city Traffic_gx, HCAD parcels, Census; API key gitignored)
src/
  config.py                    # central study-area config (area slug, boundary, derived bbox, paths) — change to retarget
  pull_osm.py                  # pull OSM street network clipped to the study area (City of Houston)
  build_segments.py            # intersection-to-intersection segments + coverage report
  merge_dual_carriageways.py   # collapse divided-road halves into single segments
  clean_slivers.py             # drop turn-lane links, absorb median-crossing pieces
  arcgis_fetch.py              # reusable paged ArcGIS REST fetcher (city data pulls)
  conflate_util.py             # shared point-snap matcher for city-data conflation
  conflate_speed.py            # join City of Houston posted speed limits
  conflate_lanes_width_median.py # join city lane count, roadway width, median
  conflate_adt.py              # join traffic volume (ADT) + operating speed
  conflate_demographics.py     # join Census ACS neighborhood demographics
  conflate_sidewalks.py        # infer sidewalk presence from OSM footways
  conflate_landuse.py          # join adjacent land use from HCAD parcels
  build_crashes.py             # clean CRIS crashes -> study-area points (severity + mode)
  assign_crashes.py            # assign crashes to segments (200-ft buffer) -> counts
  export_csv.py                # flat CSV of all segments (Excel/Sheets, with map links)
  export_webmap_data.py        # export GeoJSON for the web apps (docs/)
  export_vz_summary.py         # export headline Vision Zero stats (docs/vz_summary.json)
  export_hin.py                # export the City's official HIN, clipped to the area (docs/hin.geojson)
  fetch_superneighborhoods.py  # pull Houston's 88 Super Neighborhood boundaries (data/raw/)
docs/                          # public web apps (GitHub Pages)
  vision-zero.html             # Vision Zero dashboard (story-first: toll, HIN, travel mode, year drill-down)
  index.html                   # Street Explorer (data-first: color/filter/search)
  segments.geojson             # full per-street data (Street Explorer)
  segments_vz.geojson          # slim per-street data (VZ dashboard; only the 20 fields it uses, incl. sn)
  boundary.geojson             # study-area outline (City of Houston)
  districts.geojson            # the 11 council-district outlines (district filter + zoom)
  superneighborhoods.geojson   # the 88 Super Neighborhood outlines (SN filter + zoom)
  vz_summary.json              # citywide toll / trend / concentration / equity numbers
  hin.geojson                  # City of Houston official Vision Zero HIN (2022)
  crash_points.json            # one row per crash; powers the points view, KPIs, charts, and all time/area filtering
reports/
  feature_coverage.md       # segment & feature coverage report (generated)
  dual_merge_report.md      # divided-road merge report (generated)
  sliver_cleanup_report.md  # sliver cleanup report (generated)
  speed_conflation_report.md # speed limit conflation report (generated)
  …plus one report per conflation step (lanes/width/median, ADT, demographics, sidewalks, land use)
ELI5.md        # plain-English story of the project (start here if non-technical)
LOG.md         # dated project log: decisions, findings, rationale
CODEBOOK.md    # definition of every variable in the segment dataset
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Pipeline (run in order)

```bash
.venv/bin/python src/pull_osm.py                 # needs network; hits Overpass API
.venv/bin/python src/build_segments.py           # segments + coverage report
.venv/bin/python src/merge_dual_carriageways.py  # merge divided-road halves
.venv/bin/python src/clean_slivers.py            # sliver cleanup
.venv/bin/python src/conflate_speed.py           # join city posted speed limits
.venv/bin/python src/conflate_lanes_width_median.py  # join lanes / width / median
.venv/bin/python src/conflate_adt.py             # join traffic volume + operating speed
.venv/bin/python src/conflate_demographics.py    # join ACS demographics (needs CENSUS_API_KEY)
.venv/bin/python src/conflate_sidewalks.py       # infer sidewalks from OSM footways
.venv/bin/python src/conflate_landuse.py         # join adjacent land use (HCAD parcels)
.venv/bin/python src/build_crashes.py            # clean CRIS crashes (severity + mode), city streets only
.venv/bin/python src/assign_crashes.py           # assign crashes to segments -> per-segment counts
.venv/bin/python src/export_csv.py               # refresh inspection CSV
.venv/bin/python src/fetch_superneighborhoods.py # pull Super Neighborhood boundaries (once; feeds the export below)
.venv/bin/python src/export_webmap_data.py       # refresh docs/ GeoJSON + crash points (tags segments/crashes by district + SN)
.venv/bin/python src/export_vz_summary.py        # refresh docs/vz_summary.json (toll/trend/HIN)
.venv/bin/python src/export_hin.py               # refresh docs/hin.geojson (official HIN overlay)
```

The web apps are static Leaflet (`docs/index.html`, `docs/vision-zero.html`; no build step). Preview locally with `python3 -m http.server --directory docs`; GitHub Pages serves them live.

**Analysis dataset:** `data/processed/houston_segments_enriched.gpkg` (layer `segments`) — clean network plus conflated city data.
**To inspect by hand:** `data/processed/houston_segments.csv` (run `src/export_csv.py` to refresh) — opens in Excel/Sheets, one row per segment, with a Google Maps link per row.

Variable definitions for everything in `data/processed/` live in **`CODEBOOK.md`** — keep it in sync with any schema change.

## Retargeting to another area (or the whole city)

The pipeline is **boundary-driven** and all study-area settings live in one file, `src/config.py`. To build a different council district — or all of Houston — instead of District C:

1. Drop the new outline at `data/raw/<area>_boundary.geojson`.
2. In `src/config.py`, set `AREA` to that slug (and `AREA_LABEL` / `SEG_PREFIX`).
3. Rerun the pipeline.

Everything follows from there: the clip polygon, the city-data query bounding box (derived from the boundary — no hand-coded coordinates), and every output filename (prefixed with `AREA`, so areas don't collide). All input sources (OSM, CRIS, City `Traffic_gx`, Census, TxDOT ownership, the official HIN) are already city-wide and just clipped — no new data wiring needed. (Only HCAD land use is deferred at city scale; its citywide fetch needs a tiled approach.) The remaining work at full-city scale is the **web app**, which currently loads all features client-side; that would need vector tiles or per-area pages (see LOG).

## Key data decisions (details in LOG.md)

- **Unit of analysis:** intersection-to-intersection road segments (split at junction nodes), undirected — one row per physical street segment.
- **Scope: surface streets citywide; only limited-access freeways excluded.** This follows standard Vision Zero practice and Austin's Vision Zero dashboard (all crashes in the city's full-purpose jurisdiction) and the City's own HIN: at-grade **state-owned arterials are kept** (S Main/US-90A, SH 6, Westheimer/FM 1093) because that's where a large share of KSI occur and they're part of the city's Vision Zero picture; only **limited-access freeways/tollways/ramps/frontage** are dropped (different facility type; state DOT process; they snap onto nearby streets). **Ownership is labeled, not excluded:** every street and crash is tagged city-owned vs TxDOT-owned (from TxDOT's roadway inventory), so the dashboard can show the state-owned share (the City must partner with TxDOT to redesign those). **~11% of the surface-street KSI shown are on TxDOT-owned arterials**, the rest on city streets. (Counting freeways too, about half of all in-city KSI are on state-owned roads — per the City's VZAP, ~51% are on city-owned streets — but limited-access freeways are out of scope here, so within the streets shown the TxDOT share is ~1 in 9.) A street counts as TxDOT-owned only where it runs *along* a state on-system roadway (within 60 ft AND bearing within 30 degrees, for >=50% of its length), so a plain city street that merely bridges over a freeway is no longer mislabeled as state-owned. Interstates (`RTE_PRFX` 'IH') are excluded from the match, and a small hand-curated list of false positives is forced city-owned (see `src/export_webmap_data.py`).
- **Boundary:** the City of Houston **full-purpose (full-service) service area** — COH GIS "Houston City Limit" (`HoustonMap/Administrative_Boundary/MapServer/0`), the polygons tagged `SERVICE_TY='FULL'`, dissolved into one ~598 sq mi boundary (pulled by `src/fetch_boundary.py`). Limited-purpose annexation slivers are excluded (the City provides only limited services there, and CRIS does not attribute their crashes to Houston, so they held essentially no data). (Swap `AREA` in `config.py` back to `district_c` to rebuild a single district.)
- **CRS:** EPSG:2278 (Texas State Plane South Central, US survey feet) for all distance work, so buffer distances are honest feet.
- **Geometry source:** OpenStreetMap as the geometric spine; design/traffic features conflated from City of Houston Public Works (`Traffic_gx`), demographics from Census ACS, crashes from TxDOT CRIS, ownership from TxDOT's roadway inventory. (Land use from HCAD parcels is deferred at city scale; see below.)

## Current status (as of 2026-06-14) — citywide build

- **Road network:** 66,917 surface-street segments / ~6,407 centerline miles across the full-purpose City of Houston (limited-access freeways + frontage roads excluded; at-grade arterials incl. state-owned kept and labeled `on_txdot`; divided roads merged, slivers cleaned, `seg_id`s prefixed `H-`). 6,165 segments (9.2%) carry at least one severe crash; the worst single segment has 16. About 974 segments are labeled TxDOT-owned (state). (The enriched analysis network is the comprehensive ~75k-segment build; the dashboard serves the full-purpose subset.)
- **Predictor set** (per segment): posted speed (100%), lane count (95.1%), roadway width (95.1%), median type (87.6%), traffic volume/ADT (~25% overall, dense on arterials) and operating speed — City of Houston Public Works; neighborhood demographics — Census ACS (96.8% assigned, 89% with income); sidewalk presence — OSM. **Land use (HCAD) is deferred** at city scale (1.5 M parcels; the fetch needs a tiled/bbox approach) — `landuse_*` columns are absent for now.
- **Crash outcome:** TxDOT CRIS 2016–2025 (plus partial 2026), **surface streets** (limited-access freeways/tollways excluded; at-grade arterials incl. state-owned kept). 421,699 crashes; **9,928 KSI (1,687 killed, 8,241 seriously injured)**; ~69,500 estimated years of life lost; mode-tagged; assigned to segments (200-ft buffer, 98% assigned, median 4 ft). Each crash is labeled city- vs TxDOT-owned; ~11% (1,109) of KSI are on TxDOT-owned arterials, the rest on city streets. KSI are up ~19% vs 2016–2018.
- **Vulnerable road users:** walking and biking are only ~3% of all crashes but ~27% of severe crashes and ~41% of deaths. Walking: 597 killed, 2,226 KSI, 8,772 crashes. Biking: 89 killed, 459 KSI, 3,293 crashes.
- **Economic cost:** applying FHWA per-person costs by KABCO injury severity (FHWA-SA-25-021, 2024 dollars) to the people hurt in each crash, the citywide crashes carry an estimated **~$15.3B in economic cost** (~$64.8B comprehensive, which additionally values lost quality/length of life and overlaps the YLL figure). The dashboard recomputes this live for any filter; it is a conservative floor (unknown-severity injuries excluded, reported crashes undercount).
- **Equity:** neighborhoods under $100k median household income account for ~81% of KSI; the citywide block-group median is ~$71k.
- Both dashboards are live and citywide; the Vision Zero page overlays the City's official HIN 2022 (1,261 segments).
- **Web-app note:** the dashboards load all features client-side. The Vision Zero page loads the slim `segments_vz.geojson` (~34 MB) plus `crash_points.json` (~30 MB), `hin.geojson`, and the boundary/district outlines (~65 MB total); the Street Explorer loads the full `segments.geojson` (~66 MB). It works but first load is heavy — vector tiles or per-area pages are the scalable next step.
- **Next: modeling** — spatial baseline (Moran's I / Getis-Ord) → negative binomial → divergence analysis (now citywide).

Setup note: demographics need a free Census API key (env `CENSUS_API_KEY` or `data/external/.census_api_key`, gitignored).

## Data sources

| Layer | Source | Status |
|---|---|---|
| City boundary | COH GIS "Houston City Limit" full-purpose (`SERVICE_TY='FULL'`), dissolved | downloaded (`src/fetch_boundary.py`) |
| Street network + design features | OpenStreetMap (Overpass) | downloaded |
| Posted speed limits | Houston Public Works (Traffic_gx) | done |
| Lanes / width / median | Houston Public Works (Traffic_gx) | done |
| Traffic volume (ADT) + operating speed | Houston Public Works (Traffic_gx) | done |
| Demographics (income, poverty, race, vehicles) | Census ACS 2023 5-yr | done |
| Sidewalk presence | OpenStreetMap footways | done (no official inventory) |
| Adjacent land use | City of Houston / HCAD parcels | **deferred** — citywide fetch (1.5 M parcels) needs a tiled approach |
| Roadway ownership (city vs TxDOT) | TxDOT Roadways inventory (on/off-system) | done — labels each street/crash city- vs state-owned (kept, not excluded) |
| Crashes | TxDOT CRIS public extracts | done — 2016–2025 + partial 2026, surface streets (limited-access freeways excluded; at-grade arterials incl. state-owned kept) |
| Official High Injury Network (2022) | City of Houston GIS (`src/export_hin.py`) | done — `docs/hin.geojson`, on the VZ dashboard |
