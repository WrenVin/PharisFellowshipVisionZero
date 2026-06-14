# Vision Zero District C

A traffic-safety analysis and dashboard for **Houston City Council District C**, built in partnership with the office of Council Member Joseph Panzarella. This is the author's research project for the **Pharis Fellowship** (University of Houston Honors College / HPE Data Science Institute, summer 2026).

**Two public dashboards (one GitHub Pages site, shared data):**
- **🚦 Vision Zero view** (safety-first): https://wrenvin.github.io/PharisFellowshipVisionZero/vision-zero.html — the toll (people killed / seriously injured, city streets only), where it concentrates (6% of streets → 78% of KSI), a walking/biking lens, a by-travel-mode breakdown, a yearly trend you can **click to drill into a single year**, a **shaded-streets / crash-locations toggle**, and the City's official High Injury Network as a comparison overlay. Click any street for its crash history and design.
- **🗺️ Street Explorer** (data-first): https://wrenvin.github.io/PharisFellowshipVisionZero/ — every street, **color by any attribute** (design, traffic, demographics, crashes), **stacking filters**, search, click-to-pin info. Mobile-friendly; sources + vintages disclosed in-app.

## Research question

Does a **feature-based (systemic) risk model** identify dangerous District C streets that Houston's **crash-based High Injury Network (HIN)** misses — and how much risk lies "off the HIN"?

- **Reactive screening (status quo):** the HIN maps where severe crashes have already clustered. It cannot flag a street that is dangerous by design but hasn't yet produced a recorded severe crash, and it inherits police-reporting bias.
- **Proactive screening (this project):** identify the road-design features that make streets dangerous (lanes, width, speed, missing crossings, land use) and flag every segment carrying those features, crash history or not (per FHWA systemic safety / NCHRP 893).
- The **divergence analysis** between the two maps is the headline output. Texas's ban on automated enforcement (HB 1631, 2019) makes this more than academic: a city that cannot enforce its way to safety must design its way there.

## Repo structure

```
data/
  raw/         # as-downloaded inputs (boundary, OSM pulls)
  processed/   # analysis-ready layers (segments GeoPackage)
  external/    # third-party deliveries (CRIS extract, when it arrives)
src/
  pull_osm.py                  # pull OSM street network clipped to District C
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
  build_crashes.py             # clean CRIS crashes -> District C points (severity + mode)
  assign_crashes.py            # assign crashes to segments (200-ft buffer) -> counts
  export_csv.py                # flat CSV of all segments (Excel/Sheets, with map links)
  export_webmap_data.py        # export GeoJSON for the web apps (docs/)
  export_vz_summary.py         # export headline Vision Zero stats (docs/vz_summary.json)
docs/                          # public web apps (GitHub Pages)
  vision-zero.html             # Vision Zero dashboard (story-first: toll, HIN, mode, equity)
  index.html                   # Street Explorer (data-first: color/filter/search)
  segments.geojson             # per-street data both apps load
  boundary.geojson             # District C outline
  vz_summary.json              # district-wide toll / trend / concentration numbers
  hin.geojson                  # City of Houston official Vision Zero HIN (2022)
  crash_records.json           # per-crash records (seg/year/severity/mode) for year drill-down
  crash_points.json            # crash coordinates for the "Crash locations" points view
reports/
  feature_coverage.md       # segment & feature coverage report (generated)
  dual_merge_report.md      # divided-road merge report (generated)
  sliver_cleanup_report.md  # sliver cleanup report (generated)
  speed_conflation_report.md # speed limit conflation report (generated)
  …plus one report per conflation step (lanes/width/median, ADT, demographics, sidewalks, land use)
notebooks/     # exploratory analysis
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
.venv/bin/python src/export_csv.py               # refresh inspection CSV
.venv/bin/python src/export_webmap_data.py       # refresh docs/ GeoJSON for the web app
```

The web app is `docs/index.html` (static Leaflet, no build step). Preview locally with `python3 -m http.server --directory docs` and open `localhost:8000`; GitHub Pages serves it live.

**Analysis dataset:** `data/processed/district_c_segments_enriched.gpkg` (layer `segments`) — clean network plus conflated city data.
**To inspect by hand:** `data/processed/district_c_segments.csv` (run `src/export_csv.py` to refresh) — opens in Excel/Sheets, one row per segment, with a Google Maps link per row.

Variable definitions for everything in `data/processed/` live in **`CODEBOOK.md`** — keep it in sync with any schema change.

## Key data decisions (details in LOG.md)

- **Unit of analysis:** intersection-to-intersection road segments (split at junction nodes), undirected — one row per physical street segment.
- **Scope:** city-controlled surface streets only. Freeways, ramps, **and frontage/feeder roads** (I-610, US-59/I-69 and their feeders) are excluded — TxDOT right-of-way, part of the highway facility, not city-redesignable. Locals are kept. Service roads (alleys, driveways) excluded.
- **Boundary:** official post-redistricting District C polygon from the City of Houston GIS ArcGIS REST service (`HoustonMap/Administrative_Boundary/MapServer/2`), verified current (lists CM Panzarella).
- **CRS:** EPSG:2278 (Texas State Plane South Central, US survey feet) for all distance work, so buffer distances are honest feet.
- **Geometry source:** OpenStreetMap as the geometric spine; TxDOT RHiNo (AADT), city parcels (land use), and ACS (demographics) to be conflated on later.

## Current status (as of 2026-06-12)

Road network built and cleaned: **7,381 segments / 638 centerline miles** (frontage roads excluded, divided roads merged, slivers cleaned, stable `seg_id`s). **Crash data prep complete.** TxDOT CRIS 2016–2025 (+ partial 2026), **city streets only** — freeway/tollway crashes excluded (they were snapping onto cross-streets). **41,177 crashes; 712 severe K+A (88 killed, 624 seriously injured)**; mode-tagged; assigned to segments (200-ft buffer, 99.6% assigned, median 4 ft). Both dashboards show it; the Vision Zero page also overlays the City's official HIN (2022). Next: modeling (spatial baseline → negative binomial → divergence). **Predictor set complete.** Joined from Houston Public Works: **posted speed** (100%), **lane count** (98.6%), **roadway width** (98.6%, was 0%), **median type** (82%), **traffic volume / ADT** (98% of arterials), **operating speed** (the DAG mediator). From Census ACS: **neighborhood demographics** (income, poverty, race, car-free households; 100%). OSM-derived: **sidewalk presence** (~56% have ≥1 side). From HCAD: **adjacent land use** (79%). The only remaining input is the **crash outcome** — awaiting the TxDOT CRIS District C extract via the council office — after which: crash assignment → spatial baseline → negative binomial → divergence analysis.

Setup note: demographics need a free Census API key (env `CENSUS_API_KEY` or `data/external/.census_api_key`, gitignored).

## Data sources

| Layer | Source | Status |
|---|---|---|
| District C boundary | COH GIS ArcGIS REST | downloaded |
| Street network + design features | OpenStreetMap (Overpass) | downloaded |
| Posted speed limits | Houston Public Works (Traffic_gx) | done |
| Lanes / width / median | Houston Public Works (Traffic_gx) | done |
| Traffic volume (ADT) + operating speed | Houston Public Works (Traffic_gx) | done |
| Demographics (income, poverty, race, vehicles) | Census ACS 2023 5-yr | done |
| Sidewalk presence | OpenStreetMap footways | done (no official inventory) |
| Adjacent land use | City of Houston / HCAD parcels | done |
| Crashes | TxDOT CRIS public extracts | done — 2016–2025 + partial 2026, city streets only (freeway excluded) |
| Official High Injury Network (2022) | City of Houston GIS | pulled — `docs/hin.geojson`, on the VZ dashboard |
| Official HIN baseline (2018/2022) | COH GIS Transportation | located, not yet pulled |
| Land use | City of Houston parcels | planned |
| Demographics / exposure | ACS | planned |
