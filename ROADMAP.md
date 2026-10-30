# Dashboard Roadmap

Running checklist of improvements to the public Vision Zero dashboard. Newest ideas go at the bottom of "Open"; finished items move to "Done" with the date and commit.

## Open

- [ ] **Decide on frontage roads.** Frontage ("SER") roads currently count as freeways: hidden by default, included by the Freeways toggle. They have driveways, bus stops, and people walking (at least 15 deaths in 2024). Judgment call: keep them with freeways, or move them onto the default city-street view.
- [ ] **Visitor analytics.** No way to see usage. Add a privacy-friendly, cookie-free counter (e.g. GoatCounter).
- [ ] **Link-preview image.** The og:image tag is commented out, so shared links show no picture. Make a 1200x630 preview image and enable the tag.
- [ ] **Repo size.** `data/processed/houston_crashes.gpkg` is 66 MB and committed; GitHub warns above 50 MB and blocks pushes above 100 MB. It grows with every data refresh. Options: stop committing it (it regenerates from raw CRIS) or move it to Git LFS.
- [ ] **Custom domain (optional).** Site lives on a personal github.io address. A custom domain can be added later without breaking existing links.

## Done

- [x] 2026-10-29 Freeways toggle (off by default): adds freeway, toll-road, ramp and frontage-road crashes to every total and chart; also makes the freeway exclusion visible in the sidebar (replaces the "label the freeway exclusion" item).
- [x] 2026-10-29 Faster first load: column-packed data files cut the first-visit download from about 10.5 MB to about 3.8 MB (`src/pack_webmap_data.py`). Further option if data grows: vector tiles or per-area loading.
- [x] 2026-10-29 Data refresh: crashes now through 2026-10-01, from a statewide CRIS pull (`src/extract_cris_houston.py`); also fixed the KPI span label to include the partial year.
- [x] 2026-10-15 Basemap: CARTO began requiring an API key; switched to keyless Esri Light Gray Canvas (`4e9cb67`).
- [x] 2026-07-28 Concept Proactive Safety Network overlay (`cb41510`).
