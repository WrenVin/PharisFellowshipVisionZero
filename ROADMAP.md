# Dashboard Roadmap

Running checklist of improvements to the public Vision Zero dashboard. Newest ideas go at the bottom of "Open"; finished items move to "Done" with the date and commit.

## Open

- [ ] **People killed: count people or fatal crashes?** The KPI counts fatal crashes (1,729); person records now give 1,822 people killed. Vincent's call.
- [ ] **Schools and parks (from form feedback, 2026-07-22).** Overlays plus a "near schools / parks" distance filter and a per-school/park report for Safe Routes applications. Plan in [SCHOOLS_PARKS_PLAN.md](SCHOOLS_PARKS_PLAN.md). Part 1 (overlays) done 2026-10-29; next: confirm the radius with the submitter (federal SRTS uses about 2 miles), then the per-school/park radius view and report.
- [ ] **Freeway segments.** Freeway crashes currently show as dots on top of the street shading. Written plan in [FREEWAY_PLAN.md](FREEWAY_PLAN.md): ramp-to-ramp main-lane sections, ramps, interchanges as units, frontage roads as streets, crashes placed by TxDOT milepost. Two decisions open (color scale, direction display). Not started.
- [ ] **Fix retired City GIS address.** `src/fetch_superneighborhoods.py`, `src/export_hin.py`, `src/fetch_boundary.py` and `src/conflate_landuse.py` use `mycity2.houstontx.gov/pubgis02/...`, which no longer responds; the City moved to `.../gisweb02/...`. Boundaries already on disk are fine; a re-fetch would fail until updated.
- [ ] **Name the remaining management districts.** HCID #8, #10-A, #12, #16, #24 and Harris County PID #2 are inside the city but listed only by number in City data; add them once their names are confirmed.
- [ ] **School districts.** None qualify under the within-the-city rule (Houston ISD is 91% inside). Revisit only if the dashboard expands beyond the city.
- [ ] **Decide on frontage roads.** Frontage ("SER") roads currently count as freeways: hidden by default, included by the Freeways toggle. They have driveways, bus stops, and people walking (at least 15 deaths in 2024). Judgment call: keep them with freeways, or move them onto the default city-street view.
- [ ] **Visitor analytics.** No way to see usage. Add a privacy-friendly, cookie-free counter (e.g. GoatCounter).
- [ ] **Link-preview image.** The og:image tag is commented out, so shared links show no picture. Make a 1200x630 preview image and enable the tag.
- [ ] **Repo size.** `data/processed/houston_crashes.gpkg` is 66 MB and committed; GitHub warns above 50 MB and blocks pushes above 100 MB. It grows with every data refresh. Options: stop committing it (it regenerates from raw CRIS) or move it to Git LFS.
- [ ] **Custom domain (optional).** Site lives on a personal github.io address. A custom domain can be added later without breaking existing links.

## Done

- [x] 2026-10-30 Lower-half rebuild: street table first, year with year-to-date, travel mode donut, day-and-time heatmap, contributing factors, age and sex, lighting, income as a rate per resident; Who / When filters in the sidebar; drag-to-reorder removed. Fixed the person-record dedupe bug (years of life lost now 59,461 from actual ages).
- [x] 2026-10-30 Rewrote page copy in plainer, shorter language; removed the Source data header link.
- [x] 2026-10-30 Named the site "Houston Street Safety Dashboard" (tab, search and link-preview titles); sticky header; removed center-dot separators.
- [x] 2026-10-30 Full page redesign toward a city-dashboard look: navy header with links, not-official notice, descriptive title, ruled KPI band, blue controls with red reserved for data, three-column footer.
- [x] 2026-10-29 Area filter: removed county precincts (partial); added management districts, HPD patrol divisions, ZIP codes and Census tracts, offering only areas at least 95% inside the city limits.
- [x] 2026-10-29 Area filter: one control for council districts, super neighborhoods, county commissioner precincts and TIRZs; removed the PSN overlay; Freeways toggle restyled to match the other segmented toggles.
- [x] 2026-10-29 Freeways toggle (off by default): adds freeway, toll-road, ramp and frontage-road crashes to every total and chart; also makes the freeway exclusion visible in the sidebar (replaces the "label the freeway exclusion" item).
- [x] 2026-10-29 Faster first load: column-packed data files cut the first-visit download from about 10.5 MB to about 3.8 MB (`src/pack_webmap_data.py`). Further option if data grows: vector tiles or per-area loading.
- [x] 2026-10-29 Data refresh: crashes now through 2026-10-01, from a statewide CRIS pull (`src/extract_cris_houston.py`); also fixed the KPI span label to include the partial year.
- [x] 2026-10-15 Basemap: CARTO began requiring an API key; switched to keyless Esri Light Gray Canvas (`4e9cb67`).
- [x] 2026-07-28 Concept Proactive Safety Network overlay (`cb41510`).
