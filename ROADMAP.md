# Dashboard Roadmap

Running checklist of improvements to the public Vision Zero dashboard. Newest ideas go at the bottom of "Open"; finished items move to "Done" with the date and commit.

## Open

- [ ] **Idea (pinned 2026-10-30): statewide version by Texas House district.** Separate project, possibly with Farm and City. Statewide CRIS is already on disk. Plan sketched in chat: one data file per district; TxDOT Roadway Inventory as the statewide road network; include all road systems (rural highways matter); confirm the statewide files may be republished at crash-point level. Possible deadline: the January 2027 legislative session. First step if picked up: one urban and one rural district end to end.
- [ ] **Schools and parks (from form feedback, 2026-07-22).** Overlays plus a "near schools / parks" distance filter and a per-school/park report for Safe Routes applications. Plan in [SCHOOLS_PARKS_PLAN.md](SCHOOLS_PARKS_PLAN.md). Part 1 (overlays) done 2026-10-29; next: confirm the radius with the submitter (federal SRTS uses about 2 miles), then the per-school/park radius view and report.
- [ ] **Name the remaining management districts.** HCID #8, #10-A, #12, #16, #24 and Harris County PID #2 are inside the city but listed only by number in City data; add them once their names are confirmed.
- [ ] **School districts.** None qualify under the within-the-city rule (Houston ISD is 91% inside). Revisit only if the dashboard expands beyond the city.
- [ ] **Custom domain (optional).** Site lives on a personal github.io address. A custom domain can be added later without breaking existing links.

## Done

- [x] 2026-10-31 Map readability: zoomed out, only the top fifth of intersections show; zoomed in, blocks are bands that stop at intersections.
- [x] 2026-10-31 Streets only is the default Roads included setting (frontage roads led the street table once intersections were split out).
- [x] 2026-10-31 Intersections (Vision Zero Austin method, 75 / 125 ft legs from the police-code check): 34,141 polygons; crashes inside one count for it (64%); Most dangerous intersections table; whole streets include their intersections.
- [x] 2026-10-31 Roads included (streets / + frontage / + freeways) everywhere incl. the street table; freeway interchanges as units; cross-street and exit labels; TxDOT milepost placement; Most dangerous freeway sections list.
- [x] 2026-10-31 Freeway sections v1: 1,051 main-lane sections (one per direction, between ramps) and 1,416 ramps; 97.2% of freeway crashes placed; shaded and clickable with the Freeways toggle.
- [x] 2026-10-31 City GIS scripts moved to the gisweb02 server (HIN layer 22); large regenerable files untracked (validator checks packed files in CI); date range in the page text comes from the data.
- [x] 2026-10-31 Frontage roads added to the dashboard's street map (3,460 blocks, 364 mi; their crashes now in the default view); data files revalidate on load so caches never mix versions.
- [x] 2026-10-31 Renamed the site Houston Traffic Crash Dashboard ("Street Safety" could read as policing).
- [x] 2026-10-31 Counts are of people, not crashes (1,822 killed, 9,868 seriously injured); travel mode, age and sex per person; link-preview image; GoatCounter visit counter; frontage-road coding checked; report trend sentence fixed.
- [x] 2026-10-31 Concentration KPI restored with plain wording ("2.3% of street miles had 50% of deaths and serious injuries"); Top 10 streets KPI dropped.
- [x] 2026-10-31 KPI "Top 10 streets" replaces "Harm is concentrated"; notice bar under the header removed (notice kept in the guide, footer and report).
- [x] 2026-10-31 Quality pass: sticky Showing bar with removable filter chips; every panel names its area and dates and says when it shows its own filter's full split; filtered street ranks in popups; plain trend wording.
- [x] 2026-10-31 Smooth updates (count-up timing, panels drawn after the map, bars and charts transition); report form holds every option; sidebar controls fit beside the scrollbar; Segments renamed Blocks.
- [x] 2026-10-30 Printed report redone: two pages (summary, map and top streets; then all charts), civic styling, map captured at report shape, not-official notice.
- [x] 2026-10-30 First-visit welcome guide (per-browser flag) with a How to use link; report and share buttons in the header; Reset in the sidebar; title row removed.
- [x] 2026-10-30 Report dialog rebuilt: edits title, area, dates, map and sections; lists every other active filter read-only.
- [x] 2026-10-30 Sidebar scrolls inside a fixed height beside the map; info tips float beside their button; street table shows 5 per page.
- [x] 2026-10-30 Collapsible sidebar sections with filter badges; map matches sidebar height; lighting split into defined categories (street lights or not); contributing-factor filter; Previous/Next pager for the street table.
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
