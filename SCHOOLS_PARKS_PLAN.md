# Schools and Parks: Plan (not started)

Status: planned 2026-10-29 from form feedback (submitted 2026-07-22, "Feature idea"): put schools and parks on the map, preferably as a toggle, because Safe Routes to Schools and Parks funding is available within 3 miles of each, and overlaying them with the injury network would help justify applications.

## Check first (before building)

- **The program and its radius.** Confirm which program the submitter means and its actual eligibility rule. Federal Safe Routes to School guidance commonly uses about 2 miles for K-8; "3 miles" may be a specific state or local program. The radius drives the design, so confirm it (Vincent can ask the submitter; a reply draft is easy).
- **Which schools and parks count.** Public only, or private and charter too? Grade bands? City parks only, or county parks, trails, and greenways too?

## What to build

1. **Overlays** in the Overlay group, next to the City's HIN, off by default: **Schools** (points, small icon) and **Parks** (green outlines). Popups give the name, plus type and grades for schools. Same within-city rule as the Area filter.
2. **"Near schools / parks" filter**, the part that serves grant applications: pick Schools or Parks and a distance (1/4, 1/2, 1, 2, 3 miles), and every total, chart, and the street shading narrows to crashes and streets within that distance. Caution: 3 miles around every school covers nearly the whole city, so the citywide version won't discriminate. The smaller walking distances are where the pattern shows.
3. **One school or park at a time**, the version an application actually needs: click a school or park, or pick it from a search list, and the dashboard focuses on the area within the chosen distance of it (KPIs, worst streets, HIN segments inside the radius). This reuses the Area filter machinery: the buffer becomes the selected area.
4. **Report:** "Create report" with a school or park selected prints "Within X miles of [name]": deaths and serious injuries, years, modes (walking and biking matter most here), the HIN streets inside the radius, and the map. That page is the application exhibit.

## Data

- **Schools:** City of Houston GIS `HoustonMap/Neighborhood/MapServer/0` ("Schools"); cross-check against TEA campus locations or NCES for type and grades.
- **Parks:** City of Houston GIS `HoustonMap/Neighborhood/MapServer/14` ("Parks (City of Houston)"), polygons. Decide whether to add Harris County parks inside the city.
- A new `src/export_schools_parks.py` (same pattern as `export_area_layers.py`) writes `docs/schools.geojson` and `docs/parks.geojson`, loaded only when a toggle or filter is used.

## How the distance test works (no pipeline or crash-file changes)

- **One school:** a circle polygon (~64 points) at the chosen radius feeds the existing `polyTester`, so it gets the same caching, outline, zoom, links, and report.
- **One park:** buffer the park polygon by the radius in the browser (or precompute buffers at the five radii in the export), then use `polyTester`.
- **All schools / all parks:** a grid index of school points (and densified park outlines) answers "within r of any?" for each crash and segment midpoint, cached per (kind, radius), the same lazy pattern as `inPoly`. Expect well under a second for ~700k crash points.

## Order

1. Confirm the program rule (radius, eligible schools and parks).
2. Export script plus the two overlays (a small, quick, visible win on its own).
3. Single school or park radius selection plus report section.
4. Citywide "near any" filter.
5. Verify: counts within a radius match an independent shapely buffer count (expect small boundary-line differences, as with ZIPs); docs, LOG, roadmap.

## Reply to the submitter

They left an email address and asked for a reply. Vincent's call on whether and when to send it; a short draft can confirm the idea is planned and ask which program and radius they're applying under (that answer is step 1 above).
