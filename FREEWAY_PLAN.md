# Freeway Segments: Plan (not started)

Status: planned 2026-10-29, not implemented. Decisions marked **DECIDE** need Vincent's call before work starts.

## Problem

With the Freeways toggle on, freeway crashes draw as dots over the shaded street segments. Streets are clickable, shaded segments; freeways are unclickable points. The two don't read as one map. Freeways have no intersections, so the street method (split at every intersection) doesn't apply.

## Approach

Split freeways the way federal freeway safety analysis does (Highway Safety Manual Part C, Ch. 18 and 19): a freeway **section** runs between consecutive ramp junctions, where conditions stay roughly uniform. Four kinds of feature:

| Feature | Split rule | Example |
|---|---|---|
| **Main-lane section** | Between consecutive ramp gore points (where an exit leaves or an entrance joins), per direction | I-10 eastbound, Exit 765 (Washington Ave) to Exit 766 |
| **Ramp** | Each exit or entrance ramp is one feature | I-10 EB exit to Washington Ave |
| **Interchange** | Each freeway-to-freeway (system) interchange is one feature covering its connectors and flyovers; main-lane sections stop at its edge | I-610 / US-59 (Southwest Fwy) |
| **Frontage road** | Not a freeway: split at intersections like any street | Katy Fwy frontage between two cross streets |

Toll roads (Sam Houston Tollway, Hardy, Westpark) get the same treatment and keep their "Toll road" ownership.

## Pipeline (new step, dashboard only; does not touch segments or the model)

1. **Pull geometry** from OpenStreetMap inside the city boundary: `highway=motorway` (main lanes), `motorway_link` (ramps and connectors), and `motorway_junction` nodes (exit numbers and names). Same Overpass approach as `pull_osm.py`.
2. **Split main lanes** at every node where a `motorway_link` attaches. Keep each direction separate (OSM draws divided freeways as two one-way lines; exits don't line up across directions).
3. **Group interchanges:** cluster links that connect two motorways (system connectors) plus the main-lane pieces inside them into one interchange feature. Starting rule: links joining two different `ref`s within ~0.5 mi; tune by eye on the big ones (610 Loop, Beltway 8, downtown spaghetti).
4. **Frontage roads** (`highway=trunk/primary` tagged as frontage or service roads parallel to freeways, already partly in the OSM pull but filtered out by `build_segments.py`) become ordinary street segments, split at intersections. This also settles the open frontage-road roadmap item.
5. **Label** each section from the junction nodes: highway name, direction, and the exits at each end.
6. **Assign crashes**, which is the hard part. Main lanes, ramps and frontage roads run within ~100 ft of each other, so nearest-line matching would often pick the wrong one. Instead:
   - Use the crash record's road part (`Rpt_Road_Part_ID`: main lane, ramp, frontage, connector) to choose the feature type.
   - Use TxDOT linear referencing to place it: `Hwy_Sys` + `Hwy_Nbr` + `Dfo` (distance from origin, the TxDOT milepost). Each section gets a DFO range by snapping its ends to TxDOT's roadway inventory (already used for ownership), so a crash falls in the section whose range contains its DFO. Coverage check on 2025 freeway-class crashes: DFO 87%, highway number 92%, road part 100%.
   - Fallback for crashes without a DFO: nearest feature of the matching type and highway within ~250 ft.
   - Direction: `Rpt_Dir_Traffic` where present; otherwise nearest of the two directional lines. **Measure how often direction is recorded before relying on it.**
7. **Export** `freeway_sections.geojson` (slim properties: id, label, kind, highway, direction, owner, length, counts by mode/severity) and attach a section id to each freeway crash row, replacing the null `seg_id`, so clicking a section cross-filters exactly like a street. Pack it like the other exports and add both to the validator (sections non-empty, every crash's section id exists, counts reconcile).

## Dashboard

- With Freeways on, sections draw as lines, clickable, with a popup ("I-10 Katy Freeway eastbound, Exit 765 to 766 · 1.1 mi · 4 killed, 21 seriously injured") and cross-filtering. The dot layer goes away.
- **Color scale, the main design risk.** A 1.5-mile I-10 section carrying 200,000 vehicles a day has far more crashes than a one-block city segment; on the shared count scale every freeway hits the darkest red and drowns out the streets. **DECIDE:**
  - (a) Separate scale for freeways (own legend, distinct line style, e.g. thicker with a casing), or
  - (b) Shade freeways by crashes per mile, or
  - (c) Both: per-mile, own legend.
  Recommendation: (c). Per-mile makes short and long sections comparable; its own legend keeps it from competing with city streets.
- **Direction display. DECIDE:** draw each direction as its own offset line (accurate, more cluttered at city zoom) or merge to one centerline per section (cleaner, loses direction). Recommendation: directional lines, shown merged below a zoom threshold.
- **Rankings:** keep freeways out of "Most dangerous streets" (length and volume make them incomparable). Optionally add a separate "Most dangerous freeway sections" list when the toggle is on.
- Area filter, time filters, mode, owner and Reset already handle freeway rows; sections follow the same rules (area by midpoint).

## Verification

- Every freeway crash ends up in exactly one section, ramp, interchange, or frontage segment, or is reported as unassigned with a reason. Target: at least 95% assigned.
- Spot-check about 20 crashes by hand across kinds (main lane, ramp, interchange, frontage) against satellite imagery and the crash narrative fields.
- Totals with Freeways on must not change (2,793 killed citywide as of the 2026-10-01 data); only where the crashes are drawn changes.
- Visual review of the big interchanges and the downtown loop before shipping.

## Effort and order

Largest dashboard item since the summer. Rough order: (1) geometry and splitting, reviewed on a map; (2) crash assignment plus coverage report; (3) export, pack, validator; (4) page layer, scale, popup; (5) docs. Data is small (likely 1,000 to 2,000 features). Steps 1 and 2 can be reviewed before any page work.

## Interim option

Until this ships, freeway dots over the street views could be made clickable (open the existing crash popup). A few lines; separate from this plan.
