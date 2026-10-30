# Dashboard Roadmap

Running checklist of improvements to the public Vision Zero dashboard. Newest ideas go at the bottom of "Open"; finished items move to "Done" with the date and commit.

## Open

- [ ] **Label the freeway exclusion.** KPI tiles say "on city streets" but nothing on the main view says freeways, tollways, ramps, and frontage roads are excluded (about a third of Houston traffic deaths; e.g. 2024: 201 shown vs 338 citywide). Add "(freeways excluded)" to the tiles and one line to Data & Methods.
- [ ] **Decide on frontage roads.** The freeway filter drops frontage ("SER") roads, which have driveways, bus stops, and people walking (at least 15 deaths in 2024). Judgment call: keep excluding, or move them onto the dashboard.
- [ ] **Faster first load.** About 68 MB downloads on first visit (crash_points.json ~36 MB, segments_vz.geojson ~31 MB). Slow on phones. Options: trim fields and coordinate precision, compress, split by year, or vector tiles.
- [ ] **Visitor analytics.** No way to see usage. Add a privacy-friendly, cookie-free counter (e.g. GoatCounter).
- [ ] **Link-preview image.** The og:image tag is commented out, so shared links show no picture. Make a 1200x630 preview image and enable the tag.
- [ ] **Custom domain (optional).** Site lives on a personal github.io address. A custom domain can be added later without breaking existing links.

## Done

- [x] 2026-10-29 Data refresh: crashes now through 2026-10-01, from a statewide CRIS pull (`src/extract_cris_houston.py`); also fixed the KPI span label to include the partial year.
- [x] 2026-10-15 Basemap: CARTO began requiring an API key; switched to keyless Esri Light Gray Canvas (`4e9cb67`).
- [x] 2026-07-28 Concept Proactive Safety Network overlay (`cb41510`).
