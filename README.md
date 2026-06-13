# Vision Zero District C

A traffic-safety analysis and dashboard for **Houston City Council District C**, built in partnership with the office of Council Member Joseph Panzarella. This is the author's research project for the **Pharis Fellowship** (University of Houston Honors College / HPE Data Science Institute, summer 2026).

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
  make_map.py                  # interactive network map (legend + plain-English labels)
reports/
  feature_coverage.md      # segment & feature coverage report (generated)
  dual_merge_report.md     # divided-road merge report (generated)
  sliver_cleanup_report.md # sliver cleanup report (generated)
  network_map.html      # interactive network map (generated)
notebooks/     # exploratory analysis
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
.venv/bin/python src/make_map.py                 # reports/network_map.html
```

**Analysis dataset:** `data/processed/district_c_segments_clean.gpkg` (layer `segments`).

Variable definitions for everything in `data/processed/` live in **`CODEBOOK.md`** — keep it in sync with any schema change.

## Key data decisions (details in LOG.md)

- **Unit of analysis:** intersection-to-intersection road segments (split at junction nodes), undirected — one row per physical street segment.
- **Scope:** city-controlled surface streets only. Freeways and ramps (I-610, US-59/I-69) are excluded — TxDOT controls them and the city cannot redesign them. Locals are kept. Service roads (alleys, driveways) excluded.
- **Boundary:** official post-redistricting District C polygon from the City of Houston GIS ArcGIS REST service (`HoustonMap/Administrative_Boundary/MapServer/2`), verified current (lists CM Panzarella).
- **CRS:** EPSG:2278 (Texas State Plane South Central, US survey feet) for all distance work, so buffer distances are honest feet.
- **Geometry source:** OpenStreetMap as the geometric spine; TxDOT RHiNo (AADT), city parcels (land use), and ACS (demographics) to be conflated on later.

## Current status (as of 2026-06-12)

Road network built and cleaned: **7,635 segments / 663 centerline miles** (divided roads merged, slivers cleaned, stable `seg_id`s). Feature coverage measured (lanes 85%, maxspeed 14%, width 0% — see `reports/feature_coverage.md`). Open scope question: freeway frontage roads in/out. Next: tier-3 conflation (AADT, speed limits, sidewalks, parcels, ACS). Awaiting TxDOT CRIS crash extract via the council office.

## Data sources

| Layer | Source | Status |
|---|---|---|
| District C boundary | COH GIS ArcGIS REST | downloaded |
| Street network + design features | OpenStreetMap (Overpass) | downloaded |
| Crashes | TxDOT CRIS (district extract) | pending via council office |
| Traffic volume (AADT) | TxDOT RHiNo | planned |
| Land use | City of Houston parcels | planned |
| Demographics / exposure | ACS | planned |
