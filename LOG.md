# Project Log — Vision Zero, City of Houston

Dated record of what was done, what was decided, and why. Newest entries at the top. Companion to `README.md` (which describes the project as it *is*; this file records how it *got* there).

---

## 2026-06-15 — VZ report: config modal + page-break-safe layout + text dedup

Vincent printed the first report and flagged: charts clipped by page breaks, and too much redundant prose (the narrative restated the stats and the chart notes). He also wanted a pre-report selector to choose what to include. Designed + drafted via a 3-agent workflow (report-redesign drafter, config-modal drafter, adversarial reviewer with a shared generateReport(cfg) contract), then integrated + verified in-browser.
- **Config modal.** "Create report" now opens a full-screen "Build your report" overlay (#rcfg) instead of generating directly. It pre-fills filters from the current view (district / super neighborhood, travel mode, road owner, show KSI-vs-all, year range, map display-as, HIN overlay) and has a checkbox per section (summary, map, by year, time of day, day of week, travel mode, neighborhood income, road owner, most dangerous streets; headline stats always on) plus a report-title field. Generate applies the chosen filters to the dashboard (render()), gathers cfg, closes the overlay, and prints. District/SN mutually exclusive; Escape/backdrop/Cancel close it.
- **Page-break fix.** The report charts were a CSS grid; grid rows clip across page boundaries. Switched to inline-block 2-up with break-inside:avoid + legacy page-break-inside:avoid on every atomic block (stats, map, each chart, the table), so a chart+title+legend stays together and pushes to the next page instead of clipping. Verified 2-up rows [2,2,2], uniform width.
- **Text dedup.** Replaced the 5-sentence narrative (which restated the stats + chart notes) with at most ONE qualitative synthesis sentence (no restated numbers), gated by the summary checkbox. Removed the duplicate per-chart prose notes; kept only the by-year trend takeaway. Verified: old narrative gone, exactly 1 chart note.
- **buildReport -> generateReport(cfg)**: section flags gate inclusion (stats always); captureMap only runs when the map is included; title is escaped. Made the pre-print image wait timeout-bounded (was an unconditional `img.decode()` await that could hang) so it never stalls.
Verified in-browser: modal opens + prefills (District C), deselecting Map + road-owner omits them, filter changes apply (Walking + 2020-2023 reflected in the subtitle + data), single synthesis sentence, 6 charts 2-up, map captured, no console errors, no em dashes.

---

## 2026-06-15 — VZ dashboard: "Create report" PDF export (council-ready)

New substantive feature: a "Create report" button (header) that turns the current view into a clean, static, printable PDF for city-council offices, with the map + data + narrative but none of the interactive UI.
- **Mechanism.** Builds a dedicated `#report` section from the current state, then `window.print()`; the print stylesheet hides the whole dashboard (`.wrap`, modal) and shows only `#report` (Save as PDF). No external libraries.
- **Map.** Captured to a static PNG by compositing the basemap tiles + the vector overlay canvas onto one canvas (`captureMap()`). Added `crossOrigin:true` to the tile layers so the canvas is not tainted; falls back to the overlay alone if a basemap blocks CORS. Forces a synchronous `renderer._redraw()` before reading pixels so the snapshot reflects the current styling (Leaflet's redraw is rAF-deferred, which otherwise captured a stale/default-blue frame).
- **Content.** Eyebrow + title + subtitle describing the view (region, year range, mode, selection) + prepared-date; four headline stats; an auto-written narrative (killed/serious/YLL, concentration, walking/biking deaths, the equity sentence, the most-affected street) built from the same live values; the map image with a gradient legend caption; the six breakdown charts cloned from the live SVG/bars (vector, so they print crisply); a most-affected-streets table; and a sources/methods footer.
- Verified in-browser: report builds for a District C view (88 killed / 624 KSI / 3,592 YLL / 6%→73%, 5-sentence narrative, map captured to a valid ~900 KB PNG with the correct red shading, 6 charts with content, 5-row table); no console errors; no em dashes. Also refreshed the README dashboard blurb (added the report + range sliders + draggable panels, removed the now-deleted auto-pulse).

---

## 2026-06-15 — VZ dashboard: fix street-rank usefulness + slider drag lag

Two fixes from Vincent's testing of the prior change.
- **Street benchmark was useless** (almost every crash street read "top 1-2%") because the denominator was all named streets, ~92% of which have zero KSI. Now `streetKsiRank()` ranks only streets that HAVE a severe crash (1,755 citywide, vs 14,582 before), with competition ranking (ties share). The info panel leads with the ordinal "#N of M streets with a severe crash" and only adds a "(top X%)" badge when it is genuinely top-tier (pct <= 10). Result: Westheimer "#1 of 1,755 (top 1%)", a 2-KSI street "#582 of 1,755" (no badge), a 1-KSI street "#868 of 1,755" (no badge) instead of the old misleading "top 1%". Region scoping unchanged.
- **Range-slider drag was laggy** because `render()` (a full 421k-point rescan) ran on every `input` event. Split `wireSlider` into a cheap `preview` on `input` (updates only the fill bar + label) and a `commit` on `change` (fires on release: writes the globals and recomputes once). Verified: dragging updates the label live without recomputing; releasing commits and recomputes.

---

## 2026-06-15 — VZ dashboard: custom range sliders, region-aware benchmark, draggable panels

Three features Vincent requested, drafted by 3 parallel read-only subagents (region benchmark, draggable panels, temporal sliders) and integrated sequentially.

- **Region-aware "Top X%" benchmark.** The info-panel street benchmark now ranks within the active region: with a district or super neighborhood selected it reads "Top X% of District C streets by KSI (#N of M)" (or the SN name), else "Houston". Reworked `streetKsiRank()` to scope by `district`/`sn` and cache per region; `regionLabel()` supplies the wording. Verified: Memorial Drive is #30 of 14,582 citywide but #1 of 954 in District C.
- **Custom range sliders (year, time of day, day of week).** Dual-handle sliders under each of those three charts let you set a custom range that filters the whole dashboard. Centralized all temporal filtering in one `timeOk(p, skip)` predicate (year-range + month + hour-range + dow-range); `skip` lets each chart show its own full distribution while filtered by the other two, with out-of-range bars faded. The single-`year` model is preserved as a derived value (`yrLo===yrHi ? yrLo : null`) so month drill-down and all labels keep working; clicking a year bar collapses the range to that year. `computeCounts()` now counts from crash points whenever any temporal filter is narrowed (else the fast geo path). Reused the Street Explorer's proven `.dual` slider component. Ranges are in the URL (`yr`/`hr`/`dow=lo-hi`), Reset, the Reset-button visibility, and the Viewing banner. Verified: 2020–2023 → 706 killed; 6–10am → 1,302 KSI; weekend → 2,781 KSI; and all compose with district/SN.
- **Draggable / swappable data panels.** Each panel header has a grip handle (handle-only drag, so it never fights the charts/sliders inside). Drag to reorder the cards in the `.below` grid; order persists in `localStorage`. Reordering is safe because every draw function targets elements by id. The hidden HIN card stays pinned. Verified: a saved custom order restores on reload and the panels still render correctly.

Verified in-browser: all three slider dimensions filter + fade + label correctly, region benchmark switches denominators, drag order persists, combined filters compose (District C + 2021–2023 + Fri–Sun + 6–11pm = 26 KSI), Reset clears everything, no console errors, no em dashes.

---

## 2026-06-15 — VZ dashboard: four high-value additions (day of week, freshness, OG tags, street benchmark)

Four small features Vincent picked from a "what are we missing" review. Drafted by 4 parallel read-only subagents (one per feature; disjoint regions of the single file), integrated sequentially.
- **By day of week panel.** New card next to "By time of day": stacked killed+serious KSI by weekday (Mon→Sun so weekends sit together), fully filter-aware. New `dayStacks()` (weekday via `new Date(date+'T00:00:00').getDay()`, remapped Mon-first) + `drawDayOfWeek()`, registered in `render()`. The panels grid is now 7 cards (3 rows).
- **Data freshness line.** A subtle footer line, built once from `vz.years`: "Data: TxDOT CRIS crashes, 2016–2025 plus partial 2026. Compiled June 2026." (partial-year suffix is derived, so it self-updates).
- **Social/SEO meta tags.** Open Graph + Twitter Card + meta description + canonical in `<head>`, so shared links render a proper preview card. `twitter:card=summary` for now; left a commented `og:image` pointer (add a 1200x630 PNG at `docs/og-vision-zero.png` to upgrade to a large-image card).
- **Street KSI benchmark in the info panel.** Selecting a street/block now shows "Top X% of Houston streets by KSI (#N of 14,582)". A lazily-built, filter-independent citywide ranking by all-time `n_severe` grouped by street name (`streetKsiRank()`); denominator is all named streets, so any street with KSI lands in the low single-digit percent. Verified: Westheimer #1, Bissonnet #2, Richmond #3, all "Top 1%".
Verified in-browser: day-of-week 14 bars + correct sub, freshness line populated, OG tags present, benchmark renders for whole-street and single-block selections, no console errors, no em dashes.

---

## 2026-06-15 — VZ dashboard: rewrote Data & methods with linked sources

Vincent wanted the Data & methods modal fully current and with links to every official data source so a user can see exactly where the data comes from.
- Added a **Data sources** section listing every dataset used with a clickable link to its official home: crashes (TxDOT CRIS / txdot.gov), street network + sidewalks (OpenStreetMap), road ownership (TxDOT Roadway Inventory / TxDOT Open Data Portal), street design + traffic volume (City of Houston Public Works / COH GIS Open Data), the HIN overlay (City of Houston Vision Zero), neighborhood income (U.S. Census ACS 2023 5-yr), and city boundary / council districts / super neighborhoods (COH GIS). All open in a new tab; the CODEBOOK link points to the specific layers/methods. Verified each public URL resolves (cris.txdot.gov 403s to curl behind its bot-filter but loads in a browser; linked txdot.gov alongside it).
- Fixed a stale line that mis-attributed street design/traffic volume to "City of Houston / HCAD" (HCAD is land use, which is deferred and not used by the dashboard).
- Added a **Neighborhood income** definition and a **"Counts, not rates"** section explaining that the dashboard ranks by burden (KSI counts), matching Vision Zero / the HIN, and is not exposure-normalized (and why) — documenting the limitation Vincent flagged rather than shipping a misleading normalization toggle.
Verified in-browser: modal opens with 7 sections and 9 source links, no console errors, no em dashes.

---

## 2026-06-15 — VZ dashboard: filter by Super Neighborhood

Vincent asked to add a Super Neighborhood filter (and noted SN + district can't both be active at once, since the two geographies overlap).

- **Data.** New `src/fetch_superneighborhoods.py` pulls Houston's 88 official Super Neighborhoods (POLYID + SNBNAME) from the City GIS (Administrative_Boundary MapServer layer 3, same service as the council districts) to `data/raw/houston_superneighborhoods.geojson`. `export_webmap_data.py` now tags each segment (`sn`, point-in-polygon on its representative point) and each crash (`sn`) with its Super Neighborhood POLYID, adds `sn` to the slim `segments_vz.geojson` (`WEB_KEEP`) and as the 16th field of `crash_points.json`, and writes `docs/superneighborhoods.geojson` (POLYID + SNBNAME, simplified). Unlike districts, SNs don't tile the city, so I used point-in-polygon (not nearest): 66,715/75,260 segments and 416,580/421,699 crashes fall in an SN; the rest are left unlabeled. The POLYID (a small int) is stored per crash rather than the name string, to keep `crash_points.json` lean. `sn` is added to the slim file only, so the 68 MB full `segments.geojson` did not churn.
- **Dashboard.** New "Super neighborhood" dropdown (88 areas, title-cased + alphabetized) below District. Selecting one filters every KPI, panel, map shading and crash point to that SN, draws its dashed outline, and zooms to it. Implemented by folding SN into the area predicates: kept `inDist`, added `snOk`, and replaced the call sites with combined helpers `inArea(p)` / `inAreaProp(p)` / `inAreaSeg(seg)` (district AND SN). **District and SN are mutually exclusive**: choosing one clears the other (dropdown, outline, and state). SN is wired into the "Viewing…" banner, the shareable URL (`?sn=<POLYID>`, applied only when no district is set), Reset, and clear-view.
- Verified in-browser: 88 SNs load; Kashmere Gardens filters to 12 killed / 69 KSI with only its ~433 segments shown inside the outline; Downtown to 305 KSI; selecting a district clears the SN and vice versa; `?sn=61` restores; no console errors.

---

## 2026-06-15 — Street Explorer (index.html): brought over the VZ dashboard upgrades

The Street Explorer had drifted behind the Vision Zero dashboard. Ported the relevant improvements (the morph/count-up animations don't apply: no charts/KPIs here):
- **Shareable URL state + Share button.** New `syncURL()`/`applyURLState()` encode the full view in the query string: color field, basemap, the three category chip filters (road type / sidewalks / land use), the four numeric dual-range filters (only when moved off their ends), line width/opacity, and the selected segment. A copied link reopens the exact view (restoring controls and reselecting/zooming to the street). A "Share this view" button in the panel copies the link with a "Link copied" confirmation, and uses the native share sheet on touch devices. Wired `syncURL` into refresh/selection/appearance/basemap; chips got a `data-key` so the URL can re-check them. Guard: `_suspend` starts true and the params are captured at parse time, so the dual-range sliders' initial `setTimeout` `upd()` calls (which fire before `applyURLState`) can't clobber the incoming URL.
- **Loading spinner.** The big-file load now shows a spinning ring + "Loading the street network… (large file, may take a moment)" instead of bare text.
- **Load-failure handling.** The `Promise.all` (which fetches the ~69 MB `segments.geojson`) has a `.catch` that swaps the spinner for "Could not load the street network… Reload" instead of hanging forever.
- Minor: a `:focus-visible` outline for keyboard users, matching the VZ dashboard.

Verified in-browser: 75,260 streets load; changing color/chip/basemap/width writes the URL; reloading restores color + basemap + chip + width (3,017 major arterials) and a `sev=3-16` range + `sel=H-00041` (reopens Chimney Rock Road's info panel and pans to it); Share copies; dark basemap layer confirmed active; no console errors.

---

## 2026-06-14 — VZ dashboard: loading spinner, load-failure handling, mobile share, Reset

Four small robustness/UX touches:
- **Loading spinner.** The map overlay now shows a spinning ring + "Loading citywide crash data…" instead of a bare "Loading…" over a blank page.
- **Load-failure handling.** The `Promise.all` data fetch has a `.catch` that swaps the spinner for "Could not load the dashboard data. Check your connection and try again." with a Reload link, instead of hanging on the spinner forever if a file 404s.
- **Native share on mobile.** The Share button uses `navigator.share` (the OS share sheet) on touch devices (`pointer:coarse`), falling back to the existing clipboard-copy + "Link copied" confirmation on desktop (and if the sheet errors). A cancelled sheet does nothing.
- **One-tap Reset.** A "Reset" button (top-right, left of Share) returns every filter and selection to the default citywide view (mode/sev/view/owner/district/year/month/selection + HIN overlay) and syncs all the controls. It only appears when something is off-default (`updateResetBtn()` from `render()` and the HIN toggle), so it stays out of the way otherwise.

Verified in-browser: spinner animates (`spin .8s`); Reset hidden at default, appears on filter, and fully resets state + URL on click; no console errors.

---

## 2026-06-14 — VZ dashboard: dedicated Share button

The shareable-URL state was already being written on every render (`syncURL`), but there was no obvious way to grab the link. Added a **"Share view"** button top-right in the header. On click it re-syncs the URL and copies it to the clipboard (`navigator.clipboard.writeText`, with a hidden-textarea + `execCommand('copy')` fallback for old/non-secure contexts), then flashes a green "Link copied" confirmation for 2s (or "Press Ctrl+C to copy" if both copy paths fail). The copied link reopens the exact filters/selection. Verified in-browser: with mode=Walking + year=2020 the link is `?mode=ped&year=2020`, the button confirms and resets, sits top-right at desktop width, no console errors.

---

## 2026-06-14 — VZ dashboard: filter-transition polish (animations)

Vincent wanted a little polish: smoother transitions when filters change. Everything re-renders via `innerHTML` on each `render()`, so the animations are entrance/refresh effects re-fired per update, all gated by `prefers-reduced-motion`.

- **KPI numbers count up.** The three numeric KPIs (people killed, years of life lost, seriously injured, and the "all crashes" figure when a street is selected) carry `data-key`/`data-num`; `animateKPIs()` tweens each from its previous value to the new one (easeOutCubic, ~520 ms) on every filter change, with a generation counter so a newer render cancels an in-flight tween. The concentration KPI ("6% → 69%") is text, not a single number, so it's left static.
- **Stacked bars morph in place** (travel mode, neighborhood income, road owner). First pass wiped the whole bar in on each render; Vincent found that fast rebuild jarring ("what i imagined was the values going from where they currently are and subtly shifting to their new values"). Reworked: a `setStack(id, segs)` helper keeps one persistent `<div>` per category (stable keys) and only updates each one's `width`/`label`, so a `width .55s cubic-bezier(.4,0,.2,1)` CSS transition slides the segments from their old proportions to the new ones instead of regenerating the HTML. Empty-data states set all segments to 0% so the bar collapses smoothly too.
- **SVG bar charts morph in place** (by-year and time-of-day). First pass faded a freshly-rebuilt `<svg>` in on each render (`riseIn`); Vincent found that flash distracting too. Reworked `barChartSVG` into `drawBarChart(container, ...)`, which builds the SVG via the DOM and keeps one `rect.bar` per bar (plus gridlines, labels, hit areas, trend line) across renders, updating only `y`/`height`/`opacity` so a `y`/`height .55s` CSS transition slides the bars to their new heights. The SVG is rebuilt only when the bar set itself changes (drilling year ↔ month: different count, and the trend line drops in month view), where a morph isn't meaningful and it just snaps (no flash). Gridlines stay at fixed pixels while their axis labels update with the scale; hit-rect `onclick`/tooltips are refreshed in place. Verified: nodes are reused on mode/district/owner/sev changes (heights transition), rebuilt on year-drill, and click-to-drill still fires.
- **Most-dangerous-streets rows** fade/slide in with a 45 ms stagger.
- **Info panel** fades in, but only when it first opens (not on every filter change while a selection is held).

All animations are pure CSS with no destructive resting state (no-fill animations revert to the fully visible base; the worst-row uses `both` and ends visible), so nothing is left hidden if an animation is skipped. Verified in-browser: data loads, no console errors, KPI `data-num` updates correctly across mode switches, layout intact. (The motion itself can't be screenshotted because the headless preview freezes CSS animations / rAF at frame 0; it runs normally in a real painting browser.)

---

## 2026-06-14 — Repo accuracy pass: docs refreshed, source de-"District C"-ed

Vincent: "walk through the repo and clean any old/outdated info and make sure everything is accurate." Anchored everything to the canonical citywide numbers in `docs/vz_summary.json` and the current `docs/vision-zero.html` feature set. Done with parallel subagents (one per file; disjoint files so edits don't collide), then verified.

- **README / CODEBOOK / ELI5 refreshed.** Replaced the stale dashboard descriptions with the current feature set (three "Display as" map levels, the full sidebar filter list, click-to-cross-filter the whole dashboard, year-to-month drill-down with trend + zero-by-2030 progress, the six panels incl. most-dangerous-streets top 5, pulsing locators + Blink, shareable URL, Data & methods modal, single-screen/keyboard/mobile). Corrected stale numbers and the web payload note (the non-existent `crash_records.json` → the real `crash_year.json` + slim `segments_vz.geojson` + `crash_points.json`); added `districts.geojson` to the repo map. CODEBOOK got verified coverage figures from the reports and a new "Dashboard export fields" section documenting `on_hin`/`on_txdot`/per-crash `seg_id` and the four export files (with field orders checked against `export_webmap_data.py`/`assign_crashes.py`). ELI5 kept its warm tone and District C origin story but fixed the "no crash analysis yet" framing and stale stats.
- **Concentration figure.** Docs now use the dashboard's live **~6% of streets → ~69% of KSI** (what a visitor actually sees) rather than the precomputed `vz_summary.json` 71%.
- **Source + reports de-"District C"-ed.** The pipeline is area-agnostic via `config.py` but 9 `src/*.py` files and 4 generated `reports/*.md` still hardcoded "District C" in docstrings, prints, and report templates. Rewrote docstrings/comments to area-generic wording ("the study area") and switched runtime report/title strings to `{cfg.AREA_LABEL}` (= "Houston") so they track the configured area; edited the already-generated reports' text directly (no numbers touched). Verified zero "District C" left in `src/` and `reports/` (ignoring `__pycache__`/`cache`). Remaining mentions are intentional: README's partnership credit + retargeting example, ELI5's origin story, CODEBOOK's land-use history, and this diary.
- **Constraints upheld:** no em dashes in `docs/*.html` (verified clean); no numeric values changed anywhere.

---

## 2026-06-14 — VZ dashboard: whole-street selection, modal, filter-aware KPI, legend fix

Four review fixes (each its own commit):
- **Data & methods** is now an organized modal (sectioned: what's shown, which roads, ownership, crash assignment, definitions, sources) instead of one run-on `alert()`.
- **Select a street selects the whole street.** Clicking a segment or searching now selects every in-filter segment of that street name, highlights the entire corridor in blue, and the info panel SUMS crash counts across the blocks (KSI, killed, severe walking/biking, all crashes) with design shown as ranges (lanes, width, speed, traffic) plus block count and total miles. The selection is filter-aware: changing district or owner re-derives it to just the part within the filter (e.g. Westheimer 236 blocks, District G 161, TxDOT-only 162 + city 74), and clears if nothing remains. Replaced single-segment `selId` with `selStreet`/`selIds`; removed the now-dead `openInfo`. Also fixed the control dropdowns rendering white-on-white under macOS dark mode (`color-scheme:light` + explicit option colors).
- **Legend** no longer floats in a whitespace band below the map: the map fills the wrapper (`min-height` + `height:100%` + an `invalidateSize` after load).
- **"A few streets carry most harm" KPI** now updates with all filters (mode/severity/year/district/owner) by ranking on the already-filter-aware `activeCounts`; sub-label says "of crashes" when showing all crashes.

(Drafted via parallel subagents, integrated and verified one at a time. Fixed one drafting bug where a district change cleared the street selection instead of narrowing it.)

---

## 2026-06-14 — VZ dashboard: controls back in the sidebar (compact) + contrast bump

Vincent's feedback on the map toolbar: move it to the left (it ate vertical map space), "HIN" was undefined jargon, and the sidebar now had whitespace; also the whole thing was too white-on-white.

- **Selectors back in the left sidebar.** Removed the on-map toolbar; Show, Display-as, Overlay, and Blink return to the sidebar, filling the whitespace below the four primary filters (sidebar content 476 ≈ box 478, no gap). To avoid re-growing the map's height, Show and Display-as are now compact **segmented pills** (`.seg`, `:has(input:checked)` styling) instead of stacked radio rows. Map height ~478, fits one screen at 1512x1180 with no scroll.
- **HIN defined.** The overlay is labeled "City's High Injury Network" (not "HIN") with an 'i' explaining it in plain words ("the City's official map of the streets with the most severe crashes..."). Show pill reads "Killed/injured" rather than the KSI acronym.
- **Contrast.** Page background is now a light gray (#e9edf2) with white cards/KPIs/controls (added `background:#fff` + borders) and a slightly stronger line color (--line #d7dce2), so elements separate cleanly instead of white-on-white. "Viewing/tip" banner moved back to the map top.

Verified: segmented controls drive the map, 'i' tips work, fits one screen, no console errors.

## 2026-06-14 — VZ dashboard: secondary controls moved to a map toolbar (single-screen)

Per Vincent: to fit one screen without shrinking the map or squishing the panels, moved the four secondary controls (Show, Display-as, Overlay/HIN, Blink) out of the left sidebar into a compact toolbar overlaid on the top of the map (`#maptools`), styled as segmented pills (KSI/All; Streets/Segments/Points) + an HIN toggle + the Blink button. Kept Find a street, District, Travel mode, Road owner in the sidebar. The inputs keep their original name/id, so all existing handlers (sev/view radios, #hin, #blink) work unchanged; the per-control tooltips became `title=` attributes and the Blink note became the button's title. Moved the "Viewing / tip" banner to the bottom of the map to clear the toolbar; dropped the map min-height to 460.

This frees the map from being anchored to the (tall) control column, so total content is ~1150-1180px: fits a large display with zero scroll (verified at 1512x1180), map stays prominent (~460), and the 3x2 data panels stay roomy. Narrower screens drop the panel grid to 2 then 1 column; mobile wraps the toolbar. updateBlinkBtn no longer references the removed #blink-note.

## 2026-06-14 — VZ dashboard: balanced vertical layout (reverted the forced 100vh shell)

The two single-screen attempts both read badly: the app-shell put panels in a right column (whitespace, awkward), and the forced-100vh vertical version made the map balloon on big screens while squishing the bottom panels into a thin strip. Reverted the layout to the normal document flow (`git checkout 763fb27 -- docs/vision-zero.html`, which kept every feature) and re-tuned for balance instead of a hard 100vh:
- Normal flow (no `100vh`/`overflow:hidden`), so the map is a sensible height (~540, tied to the control column) rather than flex-growing huge.
- Restored the **By road owner** panel and the 6-panel set; laid them out in a roomy **3-column grid (2 rows)** with `align-items:start` (the uneven/organic heights Vincent liked) instead of the squished single row. Wide cards, readable charts.
- Compacted the control sidebar, KPIs, and charts (h:108) so total content is ~1280px. Worst-streets kept at top 5; trend note back to one line. Mobile: 3-col grid collapses to 2 then 1 via media queries.

Honest limitation noted to Vincent: the content is ~1280px tall even compacted (control sidebar ~540 + 6 panels ~450 + KPIs/map), so it fits tall/large monitors with no scroll but still scrolls a little on a standard ~1000px laptop. The remaining lever to guarantee no-scroll on any screen is relocating the secondary toggles (Show, Display-as, Overlay, Blink) into a compact map toolbar (~250px freed) — offered, pending his call.

## 2026-06-14 — VZ dashboard: single-screen, vertical flow (reverted the side-panel shell)

Vincent disliked the app-shell (map center, panels in a right column): too much whitespace, awkward. Reverted to the vertical flow he liked (headline stats on top, then the map + selectors, then the data views below) but kept it fitting one screen with no scroll.

The blocker was total height: the control sidebar alone is ~570-700px and six data panels add ~420px, so stacked it exceeds a laptop screen. Per Vincent's pick ("fewer data panels"), dropped the **By road owner** panel (already covered by the Road owner filter and the popup's owner line) and laid the remaining five (by-year, time of day, travel mode, neighborhood income, most dangerous streets) in a single row (`.below` = `repeat(5,1fr)`, `align-items:start` for the uneven/organic card heights he liked). Also compacted the control sidebar (tighter padding/margins, shorter Blink note) and the charts (h:106). Result at a 14" MacBook (1512x982): map ~564px tall, controls fully visible, data row ~218px, everything fits with zero scrolling. Larger screens (16"/external) have room to spare; below ~940px tall the control sidebar scrolls a little; under 900px wide it reverts to the normal stacked scrolling page (mobile unaffected). `drawOwnership` call removed from render (function left in place, unused).

## 2026-06-14 — VZ dashboard: single-screen desktop layout (no page scroll)

Per Vincent: the dashboard had grown to require scrolling. Restructured into a fixed-viewport app shell: `.wrap` is a 100vh flex column (title + KPIs across the top, footer at the bottom), and the middle row fills the rest with controls (left, ~200px) | map (center, flexible, fills full height) | breakdown panels (right, ~540px, 2-wide grid). The map is now much larger. Moved `.below` inside `.main` as the right column.

Fitting six chart panels in a side column without scroll took compaction: widened the panel column so legends/notes stop wrapping into many lines (a wider column is actually *shorter*), trimmed the worst-streets list to top 5, shortened the by-year/time-of-day charts (h~118), one-lined the trend note, and tightened card padding / stack height / legend spacing. Result: fully fits with zero scroll at 1440x900 (and larger); at 1280x800 the page stays fixed and only the panel column scrolls ~29px; below 900px wide it reverts to the normal stacked scrolling page (mobile unaffected). `body{overflow:hidden}` on desktop, re-enabled in the <=900px media query. Verified at 1440x900, 1280x800, and 375px; no console errors.

## 2026-06-14 — VZ dashboard: four additions (progress, worst-streets, share URLs, a11y/mobile)

Drafted via 3 parallel subagents (one per feature), integrated and verified one at a time; the accessibility/mobile pass done last on the integrated file.

- **Progress toward zero.** The by-year chart now shows a linear trend line over the yearly KSI bars, a headline comparing recent full years to the earliest ("KSI are up 19% vs 2016 to 2018", red rising / green falling, partial 2026 excluded), and a note on the city's zero-by-2030 goal. Reflects the active filters. `barChartSVG` gained an optional `opt.line` overlay.
- **Most dangerous streets.** New card ranking the top 10 streets by KSI (or crashes) within the active filters, each row clickable (and keyboard-operable) to select that street and cross-filter the dashboard. Built from `activeCounts` grouped by street name (`drawWorstStreets`).
- **Shareable URL state.** The active view (mode/sev/year/month/district/owner/view + selected street or segment) is encoded in the URL via `replaceState` (`syncURL` at the end of render), and restored on load (`applyURL`), syncing the UI controls. A shared link reopens the exact view.
- **Accessibility + mobile.** Mobile already reflowed cleanly (single column, no horizontal overflow); verified at 375px. A11y: travel-mode pills made keyboard-operable (role=button, tabindex, aria-pressed, Enter/Space) instead of mouse-only spans; aria-labels on the street search and district select; a global `:focus-visible` outline; the worst-street rows made focusable + Enter/Space activatable.

## 2026-06-14 — VZ dashboard: manual Blink button + logo in the header

- **Logo.** Added the Houston Vision Zero logo to the header (top-left, beside the title), 56px tall with the same 12px corner radius as the cards. Copied `HoustonVisionZeroLogo.png` into `docs/` so Pages serves it.
- **Manual "Blink crash locations" button.** Complements the automatic pulse (which only fires at <=50 crashes): the button flashes every crash in the current filtered view on demand, as a short burst (5 quick pulses, ~4 s, then it clears itself). Works at any filtered level up to `BLINK_MAX=800` crashes; it's disabled (with a note) at the citywide default or other very large views, where flashing hundreds/thousands of markers isn't useful. Enable state is driven by `_shownCount` (sum of activeCounts) computed in computeCounts. Refactored the shared crash filter into `filteredCrashes(cap)` used by both the auto-pulse and the button.

Verified: logo loads with 12px radius; button disabled citywide ("too many"), enabled at District C 2019 (68 crashes) and flashes 68 markers; no console errors.

## 2026-06-14 — VZ dashboard: pulsing locators when the filtered view is sparse

Per Vincent: when you filter down hard (e.g. District C, April 2020 → a death and a few injuries), the few crashes are tiny and faint on the citywide map and hard to find. Added a pulsing locator on each crash when the filtered set is small (`PULSE_MAX=50`). `buildPulse()` collects the crashes matching all active filters (year/month/mode/sev/district/owner/selection), and if there are 1–50 it drops an animated DOM marker (`L.divIcon`, CSS box-shadow pulse) on each; >50 shows nothing (the normal view reads fine). Severe crashes pulse red, others orange. Markers are non-interactive so clicks pass through to the streets, and they show in every display mode (the canvas renderer can't animate, so DOM markers sit on top). Verified: citywide 0 pulses; District C Sep 2019 shows 9 clearly visible pulses; clearing returns to 0. No console errors.

## 2026-06-14 — VZ dashboard: clearer chart hover (small-N hiding reverted)

- **Hover.** The year/month bar hover was barely visible (8% red wash). Strengthened it: 16% fill plus a red 1.5px outline + rounded corners on the hovered column, so it reads clearly.
- **Reverted the small-N panel hiding.** An earlier pass hid the time-of-day / neighborhood-income cards and swapped the concentration KPI when a view dropped below 25 KSI. Vincent found the disappearing panels confusing, so removed it entirely (`SMALL_N`/`_viewSmall` gone). All panels now always render regardless of how small the filtered set is. The only remaining swap is concentration → "All crashes" when a specific street/segment is selected (concentration of one street is degenerate), which was accepted earlier. Also kept the dropped stale "(all years)" note on the concentration sub.

---

## 2026-06-14 — VZ dashboard: month drill-down within a selected year

Per Vincent: after selecting a year, you can now click a month in the by-year chart to filter the whole dashboard to that month, the same way years already worked. Added a `month` state (1-12) and a `monthOk(p)` predicate (parses the crash date string p[7]); gated tally, yllTotal, equity, ownership, the time-of-day hours, the points layer, and the crash-dot picker on it. The by-year chart's month bars are now clickable (`selectMonth`), the selected month is highlighted (others faded), and the subtitle offers "back to all months / all years". `selectYear` clears the month; `clearView` clears both.

Map shading also narrows to the month: `computeCounts` now has a month branch that counts per segment straight from the crash points (which carry seg_id + date since the cross-filter change) instead of the per-year aggregates, so the map and panels agree. KPI span, legend, time-of-day subtitle, and the Viewing banner all show e.g. "Jul 2022" / "July 2022". Also dropped the now-stale "(all years)" note on the concentration KPI, which became filter-aware earlier. Verified year→month→clear in-browser; no console errors.

---

## 2026-06-14 — VZ dashboard: clicking a street/segment cross-filters the whole dashboard

Per Vincent: a click is now a filter for the entire dashboard, not just a popup. Selecting a street (search or click) or a single block narrows every KPI and panel (by-year, time-of-day, travel mode, neighborhood income, road owner) to that selection; the map popup now holds the road's physical makeup (lanes, width, speed, sidewalks, traffic, owner) and points crash data to the panels.

- **Crash to segment link.** This needed each crash tagged with its street, which the per-crash points lacked. Added the nearest segment id to every crash point (`export_webmap_data.py`, captured from the existing nearest-segment join) as field [14]; crash_points.json 26 -> 30 MB. A `selOk(p)` predicate (`selIds.size===0 || selIds.has(p[SEG])`) now gates tally, yllTotal, modeKSI (so by-year/month/hour), drawEquity, drawOwnership, buildPoints, and the crash-dot picker.
- **Selection drives a full render.** selectSeg / selectStreet / clearSel now call render(), which resolves the selection within the active district/owner filter, redraws all panels, and opens the makeup popup. Compounds with year/district/owner/mode.
- **KPIs:** the concentration KPI (citywide-only) swaps to "All crashes on this street/block" when a selection is active; killed/injured subtitles read "on this street/block."
- **Popups:** openInfoSeg / openInfoStreet now show road makeup + owner only (single values for a block, min–max ranges for a street, plus block count + miles), with a "crash data is in the panels below" note. "View this whole street" link retained.
- **Banner:** the "Viewing …" strip now leads with the selected street/block name; clear ✕ resets selection + year + district.

Verified in-browser: Westheimer narrows to 75 killed / 191 injured / 9,804 crashes with mode/income/time-of-day all street-specific; street+year compounds; single-block click works; clear restores citywide; no console errors.

---

## 2026-06-14 — VZ dashboard: default to block view; higher-contrast color ramp

Per Vincent: corridor view read messy as the default, so switched the default back to block ("Shaded street segments"). Also reworked the color ramp after he noted safe streets were hard to see.

Discussion captured: kept the map count-based (not normalized). The dashboard is descriptive ("where is the harm"), which is what counts and the City's HIN measure; rate/exposure normalization (per-VMT) is the systemic-risk model's job and isn't viable as a map anyway (ADT covers ~25% of streets). Defaulting to block segments also sidesteps the main length confound, since blocks are near-uniform units; the only view that confounds length is corridor (a per-mile toggle could be added there later).

Color changes (kept red = dangerous, sequential):
- **Percentile cap.** The ramp now tops out at the 97th percentile of nonzero counts, not the max, so a single outlier (one street has 773 crashes; max KSI on a block is 16) no longer squashes everything into the palest bucket. Values above the cap clamp to the deepest red; the legend shows e.g. "0 … 5+" (KSI) or "0 … 69+" (all crashes). Shared `buildRamp()` used by both block and corridor.
- **Muted low end / popped high end.** New palette starts paler (`#ffe2ba`) and ends deeper (`#a50f15`); weight and opacity now scale with severity (low buckets thin + slightly transparent so they recede, high buckets thick + solid so dangerous streets pop). 0-crash streets fainter (opacity .3).

Verified KSI and all-crashes block views in-browser: dangerous blocks clearly stand out, safe streets recede; no console errors.

---

## 2026-06-14 — VZ dashboard: three display granularities (corridor / block / point)

Per Vincent: added a third "Display as" level so the map reads at three zooms of detail:
- **Shaded streets (corridor, NEW default):** colors each whole street by its total crashes. A street is split where ownership changes (Westheimer's TxDOT/FM 1093 part = 231 KSI vs its city part = 33 are shaded separately), keyed by `name + on_txdot`; unnamed segments are their own corridor. Built by rolling the per-segment `activeCounts` up to corridor totals (`computeCorridorCounts`, separate `_cbreaks` ramp).
- **Shaded street segments (block):** the previous "Shaded streets" view, renamed; colors each block on its own.
- **Crash locations (point):** unchanged.

Chose corridor as the default: at the opening citywide zoom it's the most legible (whole streets read as continuous lines instead of speckle) and it answers "which corridors should the City prioritize," matching the Vision Zero high-injury-network framing. Caveat noted: corridor totals aren't length-normalized, so long arterials naturally read darker; the block view is better for pinpointing specific hot blocks, and the concentration KPI stays segment-based. Clicking still selects a single block in any shaded view (with the "view whole street" link); search still selects the whole street. Verified all three views + the ownership split in-browser, no errors.

---

## 2026-06-14 — VZ dashboard: click = single block; whole street is opt-in

Per Vincent: clicking a single segment was selecting the entire street, which he didn't want. Reverted clicks to single-segment selection (`selectSeg`): the panel shows just that block's crash history and design (and its city/TxDOT owner), and highlights only that one segment. Whole-street selection (summed totals, full-corridor highlight) now happens only from the search box, or from a new "View this whole street →" link added to the single-block popup. State: added `selSeg` alongside `selStreet`; render() re-derives whichever is active within the current filter (clears a single block if a filter hides it). Verified in-browser: click shows one block + the link; the link/search expand to the full street.

---

## 2026-06-14 — TxDOT label: drop interstates + curate the last false positives

Two more fixes after Vincent spotted residual bad pieces (e.g. Pierce St running under the Pierce Elevated / I-45, parallel to the freeway):
- **Drop interstates from the match set.** Interstates (RTE_PRFX='IH') are limited-access freeways not in our network; a surface street running parallel directly under an elevated interstate passes the parallel test and gets mislabeled. Excluding IH from the TxDOT geometry fixed the downtown Pierce case with zero legitimate loss (no at-grade arterial is on an interstate). The TxDOT layer has no functional-class field, so prefix is the available signal; US/SH-prefixed freeways (US 59, SH 288) can't be separated this way.
- **Curated false-positive list.** For the handful that remain (US/SH freeway-adjacent), the TxDOT network is static, so per Vincent's suggestion I inspected the TxDOT-only map, found the short, disconnected city-street stubs that don't belong (Pierce, Bagby, Milam, Chartres, Burlington, West Alabama, Zephyr, Calhoun, Hardy, Sue Barnett, Monroe, N Durham, W Montgomery, plus unnamed stubs), and hard-listed their seg_ids (`TXDOT_FALSE_POSITIVES`, 42 segments) to force them city-owned. Genuine short state routes (Highway 6, La Porte Fwy, FM 1960/Cypress Creek, FM 528/NASA Pkwy, Spur 5, Hempstead Hwy, Wayside, Cullen, Westheimer) are kept. Found the candidates by connected-component analysis of the on_txdot network (real arterials are long corridors; false positives are isolated < 0.35 mi pieces).

Result: TxDOT segments 1,480 -> 1,438; KSI on TxDOT ~11%. The override runs before the crash-to-segment join, so crash ownership labels stay consistent. Verified in-browser: the downtown freeway tangle is clean, remaining TxDOT shading is coherent corridors.

---

## 2026-06-14 — Fix: ownership label flagged freeway OVERPASSES as TxDOT-owned

Vincent spotted plain city streets being shown as TxDOT-owned where they cross over interstates. Cause: the `on_txdot` label used a distance-only test (>=50% of a segment's length within 60 ft of a TxDOT on-system roadway). A street that bridges over a freeway runs directly above the wide freeway corridor, so a short overpass had most of its length inside the buffer and got mislabeled state-owned even though it crosses the freeway perpendicularly.

Fix in `export_webmap_data.py`: break both the city network and the TxDOT roadways into straight 2-point pieces with a compass bearing, then a city piece counts as TxDOT only if its nearest TxDOT piece is within 60 ft **and roughly parallel** (bearing within 30 deg). A segment is `on_txdot` when >=50% of its length matches. Crossings are perpendicular, so they no longer qualify; segments running *along* a state arterial still do.

Effect: TxDOT-labeled segments 1,930 -> 1,475; KSI on TxDOT 16% -> 11% (1,104 of 9,928). The ~473 dropped segments are dominated by city cross-streets over freeways/arterials (Broadway, Bissonnet, W Bellfort, Lawndale, Jensen, Beechnut) and Beltway-crossing pieces; the kept set is coherent state arterials (Westheimer/FM 1093, Cullen, Old Spanish Trail, Cypress Creek Pkwy/FM 1960, Galveston Rd, Highway 6, Telephone, Almeda, Main/US-90A). Crash `on_txdot` is derived from the segment label, so it's corrected too. Re-ran the export (segments.geojson, segments_vz.geojson, crash_points.json regenerated); the slim VZ file is re-minified. Docs (README, CODEBOOK, ELI5) updated 16%->11% / "1 in 6"->"1 in 9" and the method note. Verified in-browser: TxDOT-only view now shows clean arterial corridors, no per-crossing speckle.

---

## 2026-06-14 — VZ dashboard: clarify the time-of-day chart, tidy ownership/labels

Small clarity fixes from Vincent's review:
- **Time of day:** subtitle now reads "By hour of day, totals over 2016–2025" (or the selected year), and an 'i' explains each bar is the *total* KSI in that clock hour summed across all years shown, not an average day.
- **Ownership card:** removed the prose note under the bar; the city-vs-TxDOT explanation now lives only behind the 'i'.
- Renamed the "Map shows" control to "Show".

---

## 2026-06-14 — VZ dashboard: street + design context in the crash popup

Clicking a crash dot now also shows the street it is on (name, class) and that street's design: lanes, roadway width, posted speed, sidewalks, traffic volume, and city-vs-TxDOT owner. Crash points carry no segment link, so rather than bloat crash_points.json we find the nearest segment geometrically at click time (`nearestSegProps`: point-to-segment distance in flat lon·cosLat space, bbox-prefiltered, ~150 m cutoff). Crashes were assigned to their nearest segment in the pipeline (median 4 ft), so this reproduces that link client-side.

---

## 2026-06-14 — VZ dashboard: "Find a street" search

Added a street search to the control panel (top), mirroring the Street Explorer. Builds a name index once on load (14,582 unique names, also fed to a `<datalist>` for type-ahead). Enter or pick from the list finds all matching segments, zooms to them, and opens the details panel for the highest-KSI match. A "clear ✕" link resets it. No new data shipped.

---

## 2026-06-14 — Cut the VZ dashboard's memory use (was reloading low-memory tabs)

The Vision Zero page was loading ~105 MB of JSON (segments 69 MB + crash_points 26 MB + crash_records 10 MB), enough to crash/reload memory-constrained tabs. Trimmed the two biggest offenders without losing any displayed data:

- **Slim segments for the VZ map.** The dashboard only reads 19 of the 36 segment fields, but properties were ~52 MB of the 69 MB file. Added a `WEB_KEEP` whitelist in `export_webmap_data.py` and now write a second, slim `docs/segments_vz.geojson` (34 MB) for the dashboard; the full `segments.geojson` stays for the Street Explorer (which uses every design/demographic field). VZ page now fetches `segments_vz.geojson`.
- **Pre-aggregate the year drill-down.** Replaced the one-row-per-crash `crash_records.json` (414k rows, 10 MB) with `crash_year.json`: `{seg_id: {year: [n_crash, n_severe, n_ped, n_ped_severe, n_bike, n_bike_severe]}}` (~152k cells, 3.7 MB), built in `assign_crashes.py`. The dashboard's per-year shading now reads these six counts via `segCountYear()` (mirrors the all-years `segCount`), so any mode/severity combo is still exact. Dropped `recMatch`.

Net: ~105 MB → ~64 MB of payload, and far fewer JS objects (152k vs 414k crash arrays; 19 vs 36 keys per segment). Verified in-browser: KPIs, year drill-down, mode/owner filters, and the map all reconcile; no console errors.

---

## 2026-06-14 — Doc audit: sync README / CODEBOOK / ELI5 / LOG to the city build

Per Vincent, before making further changes: went through the repo for out-of-date or incorrect information, especially the 4 documents. Found that several figures and labels still reflected the original District C build.

- **CODEBOOK:** fixed `seg_id` example (`C-` → `H-`, prefix from `cfg.SEG_PREFIX`); filenames `district_c_*` → `houston_*`; OSM pull date → 2026-06-14; tier-2 coverage to city values (lanes 56%, maxspeed 8%, sidewalk 8%, cycleway 5%, parking 1%, lit 9%, surface 26%); tier-3 (lanes_final/roadway_width 95.1%, lanes-agree 78%, median width 16%); demographics 96.8% assigned / ~2,445 block groups; sidewalk 2,410 mi, one+ side 29% / none 71%; dual-merge 17,043 halves → 16,138 reps; vulnerable users ~3% of crashes but ~27% of severe / ~41% of deaths. Marked the **land-use section deferred** (absent citywide; numbers there reflect the old District C run).
- **README:** demographics "100% assigned" → 96.8%; file-listing comments "District C" → study area; `district_c_*` filenames → `houston_*`. (Concentration "6% → 71%" left as-is; verified against `docs/vz_summary.json` — pct_ksi is 71.)
- **ELI5:** sidewalk story 344 mi → 2,410 mi and 56/44 → 29/71; rewrote the "land use" paragraph from "just done" to **deferred at city scale** (1.5 M parcels need a tiled fetch).
- **LOG:** title "District C" → "City of Houston."

Not changed: stale `src/*.py` docstrings/print-strings and auto-generated `reports/*.md` still say "District C" in places; those are internal and the reports would need a pipeline re-run to refresh. Flagged for later, not blocking.

---

## 2026-06-14 — Ownership as a filterable dimension; hide the HIN card

Per Vincent: turned road ownership from a static text disclaimer into a proper, interactive part of the dashboard, and hid the HIN-comparison card.

- **Hid** the "Crashes vs. the High Injury Network" card (`display:none`, kept in the HTML + `drawHIN` for easy re-enable; `drawHIN` dropped from `render`). The HIN map overlay toggle stays.
- **Removed** the top-of-page ownership text note; added a **"By road owner" card** (stacked bar: city-owned vs TxDOT/state KSI, mode/year/district aware) alongside the other breakdowns. Citywide: 84% city / 16% TxDOT.
- **Added a "Road owner" filter** to the control panel (All roads / City-owned only / TxDOT (state) only). It filters everything — map, KPIs, all charts, concentration, crash dots — via an `on_txdot` flag on segments (`seg2tx` lookup) and crash points (field 13). The "By road owner" card itself shows the full split regardless of the filter (it IS the split).

Verified in-browser (all three owner modes; TxDOT-only isolates the state arterials on the map; KPIs reconcile), no console errors.

---

## 2026-06-14 — Scope decision (revised): keep state arterials, LABEL ownership (don't exclude)

Reconsidered the previous "drop all TxDOT roads" change — Vincent felt conflicted because the City's HIN includes TxDOT arterials. Researched peer practice and concluded he was right; **reverted to keeping at-grade state arterials, excluding only limited-access freeways, and labeling ownership instead.**

Findings:
- **Austin's Vision Zero Viewer** includes ALL crashes in the city's full-purpose jurisdiction, state-owned roads included — Austin explicitly notes *state-owned roadways are most of its traffic fatalities.*
- **Vision Zero best practice** (Vision Zero Network / standard HIN methodology): exclude **limited-access freeways** (different facility, state DOT process, skew thresholds) but **include state-owned arterials** that serve the community.
- **Houston's own HIN** includes state arterials (our `hin.geojson` covers SH 6 and most of Westheimer). So excluding them would make us *diverge* from the City, not match it.

So the city-owned-only filter (Road_Cls_ID==5 + dropping TxDOT road lines) was too narrow. Reverted:
- `build_crashes.py`: back to the limited-access-freeway filter (keep at-grade arterials incl. state-owned). → 421,699 crashes, **9,928 KSI (1,687 K, 8,241 A), ~69,500 YLL**.
- `export_webmap_data.py`: keep TxDOT segments/crashes; the `on_txdot` flag is now a **label** (segment attribute + crash field), not an exclusion.
- Dashboard: new one-line **ownership view** under the KPIs — "~16% of these KSI are on TxDOT-owned (state) arterials; the City must partner with the state to redesign them." (Freeways, which are state-owned and ~half of all in-city KSI, are excluded entirely, so within the surface streets shown the TxDOT share is ~1 in 6.) Turns the TxDOT work into Austin's framing.

Net: the data matches the City/Austin scope, and the ownership question is surfaced transparently rather than resolved by deletion. The earlier entry below (drop-TxDOT) is superseded.

---

## 2026-06-14 — Data accuracy: restrict to city-OWNED streets (drop TxDOT roads) + no em dashes

Vincent flagged crashes showing on Alt-90 (S Main/US-90A), Westheimer west of 610, and Highway 6 — roads TxDOT owns, not the city. He was right; we were including ~20% non-city KSI. Two-part fix, both using authoritative ownership sources:

- **Crashes — CRIS `Road_Cls_ID`.** CRIS classifies each crash's roadway; we now keep **only class 5 (City Street)**, dropping Interstate/US-State/FM/County/Tollway (replaces the old freeway-name heuristic, which let at-grade US/SH/FM highways through). `build_crashes.py`.
- **Road lines — TxDOT roadway inventory.** Fetch TxDOT on-system main lanes (`TxDOT_Roadways`, SYSTEM='On') and drop our segments that run ≥50% within 60 ft of one. This removes SH 6, US-90A/S Main, and FM 1093 (Westheimer **west of ~the Galleria**, confirmed: FM 1093 main lanes end at lon −95.458). `export_webmap_data.py`.
- **Consistency:** matched the two — a crash whose nearest road is TxDOT-owned is dropped along with that road (no orphan dots), and the year-drilldown only counts city segments. CRIS-class-5 alone disagreed with TxDOT on FM arterials (officers code Westheimer-west as "city"); TxDOT is authoritative for ownership, so we side with it.

**Result:** 73,330 city-owned segments; **349,160 crashes, 7,927 KSI (1,267 K, 6,660 A), ~52,000 YLL** (was 9,928 KSI). That's **52% of all in-city KSI — matching Houston's VZAP (~51% on city-owned streets)**, a strong external validation. Westheimer's city portion (east of the Galleria) stays; downtown Main stays; Highway 6 fully removed.

**HIN nuance (Vincent asked to check the methodology):** the City's official HIN *includes* some TxDOT corridors (most of Westheimer, parts of SH 6) — it flags high-injury streets regardless of ownership. This project scopes tighter to **city-redesignable** streets, so we intentionally diverge from the HIN on TxDOT roads. Noted in README/CODEBOOK.

Also: **removed all em dashes from both dashboards** (per Vincent's standing preference) — replaced with commas/colons/parens; kept en dashes in numeric ranges ($50–100k, 2016–2025).

(Open: TxDOT exclusion is applied at export, not yet baked into the enriched analysis gpkg or `pull_osm` — fine for the dashboard; worth folding upstream before modeling.)

---

## 2026-06-14 — VZ dashboard: clearer HIN overlay + "Crashes vs. the HIN" stats

The official HIN overlay was muddy (translucent purple over the red shading). Fixed + added a comparison panel:

- **Legibility:** HIN now drawn as a white casing under a crisp full-opacity purple core (round caps) — reads clearly over the shaded streets at any zoom.
- **Tagging:** `export_webmap_data` now flags each segment `on_hin` (≥50% of its length within 50 ft of an HIN line) and each crash (nearest segment's flag). Citywide the HIN is **~8% of street-miles** but on-HIN segments carry **~52% of KSI**.
- **New card "Crashes vs. the High Injury Network":** stacked bar of KSI on-HIN vs off-HIN (mode/year/district aware) with the takeaway "The HIN is X% of street-miles here but carries Y% of KSI — Z% fall off it." Citywide: 8% / 49% / **51% off**; District C 7% / 36% / 64% off; District B 7% / 48% / 52% off. (Descriptive preview of the divergence theme — not the model.)

Verified in-browser (overlay legibility, card per-district, no console errors).

---

## 2026-06-14 — VZ dashboard: "By neighborhood income" equity panel

Added an equity panel now that the build is citywide (it was meaningless in affluent District C alone — which is exactly what the data shows). Each crash is tagged with the median household income of its neighborhood (nearest segment's block-group income → tier; `export_webmap_data`, new `inc_tier` field on crash points). New "By neighborhood income" card: a stacked bar of KSI across four income tiers (<$50k / $50–100k / $100–150k / $150k+), mode/year/district aware, with a takeaway ("neighborhoods under $100k account for X% of KSI here") and an ecological caveat.

The story validates the angle: **citywide 81% of KSI is in neighborhoods under $100k**; but District C (affluent) skews high-income (only 28% under $100k) while District B (lower-income) is 99% under $100k. Time of day was kept (briefly considered removing it). Verified offline (JS syntax + a Python simulation of the panel/tally/concentration logic — District C reproduces 88 K / 712 KSI) because the local preview server is down this session (a tooling `os.getcwd` permission error, unrelated to the code).

---

## 2026-06-14 — VZ dashboard: per-council-district filter

Added a **District dropdown** (All districts / A–K) to the Vision Zero dashboard so you can zoom into one council district and have *everything* recompute for it.

- **Data:** `export_webmap_data.py` now tags every segment (nearest of the 11 council districts) and every crash (point-in-district) with its `district`, and writes `docs/districts.geojson` (the simplified district polygons) for the dropdown + outline + zoom. Saved the 11 polygons to `data/raw/houston_districts.geojson`. Area-aware: if no districts file exists (single-district build) the dropdown stays hidden.
- **Dashboard:** selecting a district filters the map (other districts hidden), KPIs, the years-of-life-lost total, the by-year / by-month / by-time-of-day / by-travel-mode panels, the crash dots, and the "few streets carry most harm" concentration — and fits the map to the district with a dashed outline. The year drill-down composes with it. A "clear ✕" chip resets to the city.
- **Implementation notes:** the toll KPIs now compute from the crash points (uniformly year+district filterable, replacing the precomputed `vz.toll`); concentration is computed client-side per district from each segment's `n_severe` + `length_ft`. Sanity ✓: selecting District C reproduces the standalone District C build exactly (88 killed, 712 KSI, mode 500/163/49).

Verified in-browser (multiple districts, year drill within a district, clear), no console errors. (Not yet added to the Street Explorer — easy follow-up since its segments now carry `district`.)

---

## 2026-06-14 — Scaled the whole project from District C to the entire City of Houston

Flipped `config.py` `AREA` from `district_c` to `houston` and reran the full pipeline citywide. The area-agnostic refactor paid off — no per-script edits were needed to retarget; the work was getting the boundary, fixing two scale-exposed bugs, and deferring land use.

**City boundary.** The COH staging host that served our District C boundary (`geogimstest`) is down; found the live production host (`mycity2.houstontx.gov/pubgis02`, same `HoustonMap/Administrative_Boundary/MapServer/2`). Pulled all **11 council districts (A–K)**, verified District C matches our existing file exactly (35.19 sq mi, CM Panzarella), and **dissolved them into one City of Houston polygon = 671.8 sq mi** (a MultiPolygon — the city has detached annexed parts). Saved `data/raw/houston_boundary.geojson`.

**Scale (≈10×).** OSM 176,886 edges → **109,476 segments** → merge → **92,433** → sliver cleanup → **75,260 segments / 7,337 mi** (`H-#####` ids). Crashes: 421,699 city-street (257k freeway excluded) → **9,928 KSI (1,687 K + 8,241 A)**, ~69,500 est. years of life lost; 98.2% assigned, median 4 ft. Concentration is **6% of streets → 71% of KSI** citywide (vs 78% in District C). Top severe corridors (Westheimer, Bissonnet, Richmond, Main, Tidwell…) are Houston's known HIN streets — sanity ✓.

**Two bugs the bigger data exposed:**
1. `conflate_speed` cached the speed layer **without `MEDIAN_WIDTH`/`DIRECTION`**, which `conflate_lanes_width_median` needs (masked for District C by an older fuller cache). Added those fields to the shared fetch.
2. `conflate_landuse` passed the **whole boundary polygon** as the ArcGIS spatial filter — fine for District C's small polygon, but the 8 MB city MultiPolygon isn't valid esri "rings" and is too big, so it returned nothing. **Land use is deferred** (1.5 M parcels citywide also needs a tiled/bbox fetch + lighter join). `landuse_*` columns are absent for now; it's a model confounder, not used by the dashboards.

**Predictor coverage citywide:** speed 100%, lanes/width 95.1%, median 87.6%, ADT ~25% overall (dense on arterials), demographics 100% assigned / 89% income, sidewalks 100% classified. Land use deferred.

**Official HIN, now scripted.** The HIN overlay was a one-off District-C pull. Wrote `src/export_hin.py` (area-aware) and regenerated **citywide HIN 2022 = 1,261 segments** (was 113).

**Dashboards** retitled District C → Houston (both pages) and verified citywide in-browser (KPIs 1,687 / 69,513 / 8,241 / 6%→71%, all charts, HIN overlay, no console errors).

**Repo hygiene.** Citywide data is heavy. Generalized `.gitignore` (`*_edges_raw.gpkg`; added the pre-enrichment provenance snapshots `*_segments.gpkg`, `*_segments_merged.gpkg`). Kept the analysis dataset (`*_segments_enriched.gpkg`), `*_segments_clean.gpkg`, crashes, CSV, external caches, and `docs/`. **Web payload is the open issue:** dashboards load ~95 MB client-side (62 MB segments + 22 MB points + 10 MB records); works but heavy first load — vector tiles or per-area pages are the scalable fix.

---

## 2026-06-14 — Make the pipeline area-agnostic (config.py) for future city-scale expansion

Refactor so the project can retarget from District C to another district — or the whole City of Houston — by changing one file, without touching the 15 pipeline scripts. No behavior change for District C: the regenerated `docs/` and `data/processed/` outputs are byte-identical.

- **New `src/config.py`** — the single source of study-area truth: `AREA` slug, `AREA_LABEL`, `SEG_PREFIX`, the boundary path, CRS constants, dir constants, a **boundary-derived** bbox (`bbox_4326()`, replacing the three hand-coded `(-95.51, …)` envelopes), and area-scoped path helpers `processed()` / `external()` / `raw()`. Every script now `import config as cfg`.
- **Output filenames are area-prefixed** (`{AREA}_segments.gpkg`, etc.) so multiple areas can be built side by side. With `AREA="district_c"` the names are exactly today's, so nothing regenerated.
- **External caches renamed** to the area convention (`district_c_speed_limit.gpkg`, `district_c_census_bg.gpkg`, …) via `git mv` so they stay valid.
- Found & fixed two buried area-specifics: the hand-coded query bbox (now derived) and the `C-#####` seg-id prefix (now `cfg.SEG_PREFIX`).
- The `STATE/COUNTY = 48/201` (Harris) in demographics is left as-is — Houston is ~99% Harris; noted in-code to expand to a county list if ever going beyond it.

Retargeting is now: drop `data/raw/<area>_boundary.geojson`, set `AREA`, rerun (README "Retargeting" section). All data sources are already city-wide; the remaining city-scale work is the web app (client-side rendering → vector tiles or per-area pages). Verified: all scripts byte-compile, config resolves, the three export scripts reproduce identical outputs.

---

## 2026-06-14 — VZ dashboard: layout & legibility polish

- **Travel-mode selector moved into the left control panel** (with Map shows / Display as / Overlay), freeing the header — pills wrap within the sidebar.
- **Display-mode and HIN explanations tucked behind ⓘ buttons** (click to reveal) instead of always-on paragraphs, decluttering the panel.
- **Bigger, darker chart axis labels** — years, counts, and hours were too small/faint; bumped to 12 px and a darker gray, taller chart canvas, so the by-year and by-time-of-day charts read easily.
- **KPI refinements:** added an ⓘ on the Years-of-Life-Lost card explaining the YPLL-before-75 calc (and the age-imputation estimate), so the "estimated" qualifier could come off the subtitle; changed the 3rd KPI from "Killed or seriously injured" to **"Seriously injured"** (624) since deaths are already the 1st card. (KSI remains the underlying metric for the map, charts, and concentration stat.)

Verified in-browser, no console errors.

---

## 2026-06-14 — VZ dashboard: Years of Life Lost, by-month + by-time-of-day, KPI icons

Round of Austin-inspired upgrades (Vincent shared Austin's Vision Zero dashboard as the bar to clear):

- **Years of Life Lost KPI.** YPLL before age 75 (CDC convention): Σ max(0, 75 − age) over the people killed, from the CRIS person table. Data caveat fought through: the public extract records a victim age for only ~half of fatal crashes (person detail suppressed on the rest), and the person-level death count (49 in District C) badly undercounts the reliable crash-level K flag (88). So we anchor to the 88 fatal crashes — use recorded ages where present (47 crashes), impute the mean years-lost-per-fatality (~40) to the rest — making YLL an **estimate** (~3,564 yrs), clearly labelled in the methods note. Found two person-file gotchas: `primaryperson` (drivers/non-motorists) and `person` (passengers) reuse `Prsn_Nbr`, so dedupe each type separately then concat (never cross-dedupe).
- **By time of day** chart — hourly distribution (clear afternoon/evening peak).
- **By year → by month drill-down** — the yearly chart now stacks killed (dark) over seriously injured (light); click a year and it expands into that year's 12 months. Reuses the existing year-selection state; "‹ Back to all years" to exit.
- **Icons** on the four KPI cards (heartbeat / hourglass / medkit / bars, color-coded) and the breakdown card titles, like Austin.
- All new panels respect the travel-mode lens and the selected year (verified: 2024 → 7 killed / 244 YLL / 79 KSI; walking-2024 YLL 81 — all reconcile against an independent client recompute).
- Legend tidy: dropped "on one street" from the shaded-streets max label.

Pipeline: `build_crashes.py` now also captures `month`, `hour`, and per-crash `yll`; `export_webmap_data.py` adds `hour`+`yll` to `crash_points.json` (now 10 fields/point, 2.1 MB). Verified in-browser (all lenses, year drill, both new charts), no console errors.

---

## 2026-06-14 — VZ dashboard: "Driving" travel-mode lens + stale-label cleanup

- **Added a Driving lens** to the travel-mode toggle (Everyone / Driving / Walking / Biking). Vehicle-occupant crashes = total − walking − biking; verified exact (0 crashes involve both a pedestrian and a cyclist, so the subtraction never double-counts). Works across all code paths — all-years segment shading, single-year drill-down (records recompute), crash-locations dots, KPIs, and legend — via shared `modeMatch()` / `segCount()` helpers. Driving toll: 57 killed / 500 KSI (vs 712 all, 163 walking, 49 biking). The "By travel mode" breakdown card is unchanged (it always shows the full split). Cleaned the KPI subtitle wording ("people · walking" instead of the doubled "people · people walking").
- **Trimmed the VZ subtitle** — dropped the inner-loop neighborhood list, ends at "Houston City Council District C."
- **Stale-label sweep** (missed in the earlier doc audit): Street Explorer data-sources modal and crash legend no longer say "2020/2025 pending"; CODEBOOK crash-year range → 2016–2025 and Known-limitations item 5 rewritten (all predictors are conflated in now). `assign_crashes.py` now derives its report's year range from the data so it can't go stale again.

Verified in-browser (all four lenses, points view, year drill-down), no console errors.

---

## 2026-06-13 — VZ dashboard: crash-locations (points) view + clearer wording

Vincent's point: showing crash *points* as shaded *segments* can confuse — a hotspot at an intersection lights one approach leg red while the adjacent block reads grey (an artifact of nearest-leg assignment + discrete unequal-length blocks). Fix: added a **"Display as" toggle — Shaded streets / Crash locations.** Crash locations plots each crash as a dot (red = KSI, light = other), so the real spatial pattern shows without segment boundaries; shaded-streets stays the analytical/HIN view. Both respect the mode lens, year drill-down, and KSI/all metric.

- Exported `docs/crash_points.json` (41,177 city-street crashes: lat/lon/severity/mode/year) via `export_webmap_data.py`.
- Points rendered on canvas (interactive:false so street clicks pass through); 41k draw in ~250 ms.
- Clearer wording: control hint + legend now state "Streets shaded by count on each block" vs "Each dot is one crash location."
- Underlying data/model unchanged — purely a presentation option.

Verified in-browser. Follow-up: clicking a dot now opens a popup with that crash (severity / mode / date) via a map-click nearest-point search; street info is suppressed in points view.

---

## 2026-06-13 — Dashboard typography + label polish

- **Inter font** (Google Fonts) applied to both dashboards + antialiasing — more professional than the prior Helvetica/Arial fallback.
- Legend labels capitalized ("Killed or seriously injured", "Crashes"); legend low end "none" → "0".
- Year bars now show a hover state (pointer cursor + outline) signalling they're clickable.

Verified in-browser, no console errors.

---

## 2026-06-13 — VZ dashboard: year drill-down, neutral copy, legend + basemap fixes

Round of fixes from Vincent's review:
- **Neutral language.** Removed point-of-view copy ("a decade in, the trend isn't falling", "worst year") from the VZ dashboard; all chart/label text is now descriptive only. (Standing note to self: dashboard describes, doesn't editorialize.)
- **Year drill-down.** Click a year bar → the whole dashboard (map colors, KPI numbers, mode breakdown, legend) recomputes for that single year; click the same bar again to clear. Implemented by exporting per-crash records (`docs/crash_records.json`, 40,997 rows: seg_id/year/severe/fatal/ped/bike from `assign_crashes.py`) and aggregating client-side; all-years view still uses the precomputed segment totals. Selected bar highlights, others dim; subtitle shows the active year.
- **Legend "none401" spacing bug fixed** (min-width + full-width gradient + flex gap).
- **Basemap selector moved off the panel** onto the map as a compact Leaflet layers control (top-left); panel is now shorter.

Verified in-browser (2020/2024 drill-downs, all-crashes legend, clear), no console errors.

---

## 2026-06-13 — Major data fix (freeway crashes) + 2020/25 + VZ dashboard rebuild

**Freeway-crash contamination (Vincent spotted it).** Crashes physically on I-610 / US-59 etc. were being snapped onto nearby city cross-streets by the 200-ft buffer. Diagnosed: of 69,513 geocoded District C crashes, **28,336 (41%) were on freeway/tollway facilities** (Road_Cls_ID Interstate/Tollway, service-road/ramp/connector road parts, or class-2 US/State-hwy with a freeway street name — careful to KEEP class-2 surface arterials like Shepherd/Kirby/Braeswood). Added the filter to `build_crashes.py` and excluded them. Impact: **deaths 138→88, KSI 1,039→712** (the removed ones were genuinely on freeways); assignment jumped to **99.6%** (median crash now 4 ft from its street) — confirming the remainder really are on city streets. Also fixed the inflated all-crashes max (693→401).

**2020 & 2025 added** (Vincent dropped the folders) — picked up automatically by the year-agnostic pipeline. Now 2016–2025 + partial 2026; 2020 shows the COVID dip (42).

**Official High Injury Network.** Vincent asked whether the HIN was ours or the city's. Pulled the **City of Houston's official Vision Zero HIN 2022** (COH Transportation layer 20), clipped to District C (`docs/hin.geojson`, 113 seg / 43 mi). It's now a distinct purple overlay on the VZ dashboard — answers the source question and is the authoritative comparison network.

**VZ dashboard rebuilt** per the rest of the review:
- Crash colors were near-white/invisible → OrRd ramp visible at 1 KSI + thickness scaled with severity (fixed earlier, retained).
- Removed the equity overlay/card (District C too affluent — $147k median; "skews lower-income" read absurdly). Replaced with a **mode breakdown** card: KSI by vehicle / walking / biking (70% / 23% / 7%).
- "Isolate HIN" (ineffective) → replaced by the official-HIN overlay toggle.
- Info-panel header "THE STREET DESIGN THAT DRIVES RISK" → neutral "Street design" (no claim).
- Trend chart **given a real Y axis** (gridlines + labels), bars 2016–2025 + faded partial 2026.
- Fixed the "none693" legend spacing bug.

**Street Explorer** unchanged content-wise (already renamed + linked last commit). All re-verified in-browser, no console errors.

---

## 2026-06-13 — Dashboard polish (both pages) from Vincent's review

**Street Explorer (`index.html`):** renamed "Vision Zero · District C" → "District C Street Explorer" (the Vision Zero name belongs to the other page); added a "→ Vision Zero dashboard" link; moved the "Data sources & dates" trigger to the bottom of the panel.

**Vision Zero dashboard (`vision-zero.html`)** — fixed the "sloppy/hard-to-see" issues:
- Low crash values were near-white and vanished into the basemap. Switched the count ramp to OrRd starting at a saturated orange (visible even at 1 KSI), thickened crash streets, and **scaled line weight with severity** (darker = thicker) so hotspots pop; zero-KSI streets are now faint thin grey context.
- "Isolate the High Injury Network" barely changed anything (zeros were already invisible). With bold colored lines it now reads clearly — removing the grey network leaves just the red HIN.
- Equity overlay promised "red lines" that weren't drawn, and income was vague. Rebuilt as **two layers**: streets shaded by neighbourhood income (blue, now with real $25k–$250k labels) + a **red KSI overlay on top** — you can actually see where the harm falls vs income.

Verified all states in-browser (KSI/walking/biking, HIN isolate, equity), no console errors.

---

## 2026-06-13 — Removed the "blind spot" strip from the VZ dashboard

Vincent: the 93%-zero-KSI / "built to be dangerous, a design model can see them" strip is a *research claim* (the divergence thesis, not yet demonstrated) and doesn't belong on a public dashboard showing current crash data. Removed the strip (HTML + drawStrip + CSS). The dashboard now reports only what the data shows; the divergence story stays in the research/analysis where it'll be proven. Verified clean load, no errors. (Lesson: keep the public dashboard descriptive; reserve claims for the analysis.)

---

## 2026-06-13 — Second dashboard: a Vision Zero view

Vincent: the Street Explorer is data-first (built around road type); a *Vision Zero* dashboard should put harm front and center. Researched how Austin/NYC/LA/Seattle/SF present publicly — all reactive, toll-led, organized around "are we ending traffic deaths?": big KSI numbers, a severe-crash map as the homepage, the "X% of streets = Y% of harm" High Injury Network stat, a mode lens (walking/biking), equity disparities named explicitly, and a flat yearly trend. None show *predicted* risk (streets dangerous by design but not-yet-bloody) — that's our differentiator (Act 3, after modeling).

Mocked it up first (visualize widget, real numbers) → Vincent approved direction, flagged AI-sounding wording, and asked to **keep the Street Explorer as-is and build a separate second dashboard**. Both host on the one Pages site (shared geojson).

Built `docs/vision-zero.html` (+ `src/export_vz_summary.py` → `docs/vz_summary.json`). Story-first, real District C numbers, proper VZ vocabulary (KSI / High Injury Network / killed-or-seriously-injured / walking-biking / street design). Features: toll KPI header (updates by mode), blind-spot strip (93% of streets zero-KSI → sets up the model), KSI hotspot map as default (log-scale count color), walking/biking lens, "isolate the High Injury Network" + "equity overlay (income)" toggles, click panel (crash history + the street design behind the risk), yearly KSI trend (2020/25 gaps shown), equity split, cross-link to the Explorer.

Headline stat computed from our data: **6% of District C street-miles carry 82% of KSI** (vs Houston citywide 6%/60%, LA 6%/70%); 93% of streets have zero KSI. Fixed a load bug (count-type default style called geo.eachLayer before geo was assigned → build layer first, then style). Verified in-browser: KPIs, mode lens, info panel, equity overlay, trend all work, no console errors. Left index.html untouched per Vincent.

---

## 2026-06-13 — Crashes on the dashboard

Surfaced the per-segment crash counts in the Street Explorer (Vincent: finish the dashboard before modeling). `export_webmap_data.py` now exports the crash columns; `docs/index.html` gains a **Crashes** color-by group (severe/all/injury/fatal/ped-severe/bike-severe), a **Crash history** block in the click panel, a **severe-crash range filter**, and a CRIS row in the data-sources modal.

New `count` color type for the zero-heavy crash data: 0 = neutral grey, 1+ on a red ramp. First used quantile breaks → collapsed (most streets have 1–2, hotspots didn't stand out); switched to a **log scale to the max** so the worst streets (Kirby Dr = 11 severe) render darkest. Verified in-browser: legend, filter, info panel, and the hotspot map all correct, no console errors. The severe-crash map reads as District C's High Injury Network — 93% grey, arterials (Westheimer/Richmond/Kirby/Montrose/Washington) glowing red.

Dashboard now shows the full picture: design + context + crash outcome. Modeling (HIN reconstruction → NB → divergence) still to come.

---

## 2026-06-13 — Crash Step 3: assign crashes to segments (buffer method)

`src/assign_crashes.py`. Each crash → single nearest segment within **200 ft** (Dumbaugh/Rae/Wunneburger). Nearest-only (not all-within-buffer) so counts sum back to the crash total. Divided roads handled: also searched the `merged_away` halves and credited hits to the representative `seg_id` (no boulevard crashes orphaned). Adds per-segment counts to the enriched layer (idempotent): `n_crash`, `n_injury`, `n_severe`, `n_fatal`, `n_ped`, `n_bike`, `n_ped_severe`, `n_bike_severe`.

**Results:** 47,929/57,848 (82.9%) assigned; median distance **5 ft** (p99 189) — buffer well-calibrated. **Count integrity verified**: per-segment sums == assigned totals exactly (n_crash 47,929, n_severe 832, n_ped 730) → each crash counted once. 17% unassigned = freeway/feeder crashes (excluded roads) + geocode error. **539/7,381 segments (7.3%) have ≥1 severe crash** → 92.7% zero, the overdispersed/zero-heavy pattern NB is built for and the reason the feature model matters. **Sanity ✓:** top severe corridors = Memorial, Washington, Montrose, Kirby, Westheimer, Richmond, N. Braeswood — Houston's known HIN arterials.

Crash data prep is now complete (clean → severity → mode → segment counts). Did NOT touch the dashboard (Vincent: set up data right before display). Crash refresh pipeline: `build_crashes.py` → `assign_crashes.py`. Next: display on dashboard, or modeling (Moran's I / Getis-Ord baseline → negative binomial → divergence).

---

## 2026-06-13 — Crash Step 2: pedestrian/bicycle mode

Folded mode into `build_crashes.py` (not a separate script) so one rerun recomputes severity AND mode when 2020/2025 arrive. Mode from CRIS `unit` table (Unit_Desc_ID 4=pedestrian, 3=pedalcyclist), unioned with the `person` table (Prsn_Type_ID 4/3) for robustness; codes confirmed from the CRIS lookup table. New columns: `mode`, `involves_ped`, `involves_bike`.

**Results:** 755 pedestrian crashes (171 severe, 42 fatal), 437 bicycle (50 severe, 7 fatal). **Vulnerable users = 2.1% of all crashes but 21.3% of severe and ~36% of deaths (49/138)** — real-data confirmation of the project's pedestrian-harm premise (prospectus cited ~36%). Data integrity: unit-based vs person-based flags agree to within 1 of 755 ped crashes — classification trustworthy.

This lets us later model ped/bike severe crashes specifically, not just all-severe. Next step: buffer-assign crashes to segments.

---

## 2026-06-13 — CRIS crash data arrived; Step 1: clean District C crash points

**The outcome variable is here.** Vincent added TxDOT CRIS public extracts to `data/raw/CRIS/` (years 2016–2019, 2021–2024, partial 2026; 2020 & 2025 still coming). ~740 MB — gitignored (an accidental `git add -A` had committed+pushed it; fixed by soft-reset + force-push of the tip commit `c7c8645`, CRIS purged from the remote, kept on local disk). Going forward: tighter `git add`, never `-A` with large raw data staged.

**Good surprise:** the public extract IS geocoded (`Latitude`/`Longitude`), so buffer-based segment assignment is feasible — the earlier worry was unfounded.

**Step 1 (`src/build_crashes.py`):** glob all `Houston_Crash_*` folders → dedupe by `Crash_ID` → geocode (CRIS coords, officer-reported fallback) → clip to District C → KABCO severity. Result: **57,848 District C crashes; 1,039 severe (K+A) = 138 fatal + 901 serious** — the NB outcome. Severity decode verified two ways (Sev_ID vs fatal-flag/injury-counts agree exactly). 89.7% of citywide crashes geocoded (~10% dropped → reporting-collider flag). Output `district_c_crashes.gpkg` + report + preview PNG (crashes follow the grid, severe cluster on arterials — sanity ✓).

**Built for easy re-runs** (Vincent is awaiting 2020/2025): fully year-agnostic — drop a new `Houston_Crash_<year>/` folder in and rerun; year comes from `Crash_Date` not the folder, dedupe handles overlap, outputs overwrite, and the report computes present-years/gaps live (currently flags 2020 & 2025).

**Doing crash integration one step at a time (Vincent's request).** Next step: pedestrian/bike **mode** via person/unit join, then buffer-assign crashes to segments.

---

## 2026-06-13 — Street Explorer refinements: mobile, speed floor, data-vintage transparency

Three asks from Vincent on the new app:
1. **Mobile-friendly.** Panel becomes an off-canvas drawer below 760px with a "☰ Controls" toggle; info panel becomes a bottom sheet; count badge centers; Leaflet zoom control moved to bottom-right so it never collides with the toggle. Verified at 375px (preview).
2. **Speed filter floor = 30.** Only 22 segments are below 30 mph (all OSM oddities: one 5, some 20/25) vs 5,973 at 30 — so the posted-speed slider now starts at 30, not the raw data min of 5. Implemented a domain-aware filter rule: a bound only excludes once its handle moves off the slider end, so those 22 sub-30 segments still show at the default floor (nothing silently hidden).
3. **Data-vintage transparency.** Added an "ⓘ Data sources & dates" modal listing every source and its vintage: OSM (June 2026 snapshot), City Traffic_gx (June 2026), ADT readings 2012–2026, HCAD land use (June 2026), Census ACS 2023 5-yr (2019–2023), boundary (current districts). Plus the "no data ≠ absent" and "TX 30 mph default" caveats. Map-compiled date shown.

UI-only (no data/schema change). Next: add school-zone data (Vincent's request).

---

## 2026-06-13 — Interactive map rebuilt as a custom Leaflet app

Vincent: the folium map was hard to use — thin lines hard to click, hover-only tooltip vanished, and only colorable by road type. He wanted full control, public-facing. Agreed to graduate from folium (static, baked styling) to a **custom Leaflet web-app** where all styling/filtering happens live in the browser.

**Built** (`docs/index.html`, ~700 lines, vanilla JS + Leaflet, no build step) + `src/export_webmap_data.py` (exports simplified `docs/segments.geojson` 5.7 MB + `boundary.geojson`). Replaces folium `make_map.py` (deleted) and the 14 MB generated html.

Features: **color streets by any attribute** (categorical palettes + numeric quantile gradient, legend redraws); **stacking filters** — road-type/sidewalk/land-use chips + dual-range sliders for speed/lanes/ADT (e.g. "4+ lanes, ≥35 mph, no sidewalk" → 243 candidates, a dangerous-by-design pre-screen); **street search**; **click-to-pin info panel** (grouped, source-tagged, persists); appearance controls (line width/opacity/basemap). Easy selection via **canvas renderer with click-tolerance** (fixes the thin-line problem) + hover highlight.

**Verified in-browser** via the preview server: clean load (no console errors), gradient legend on numeric color-by, info panel populates correctly (Westheimer: 5 lanes/OSM, 30 mph TX-default, 14k veh/day corridor-est, Commercial, block-group demographics), filter scenario narrows 7,381→243. Fixed count-badge overlapping the zoom control (moved bottom-left).

Pipeline/refresh: map now refreshes via `export_webmap_data.py` (not make_map). Added `.claude/launch.json` for local preview.

---

## 2026-06-13 — Conflate adjacent land use (HCAD parcels) — last predictor

DAG confounder. Source: COH "Land Use (Grouped)" parcel layer (HCAD). New `src/conflate_landuse.py`. For each segment, parcels whose polygon comes within 100 ft are summarized area-weighted into `landuse_dominant` + `pct_residential/commercial/industrial`.

**Three bugs fought through (good case study in not trusting the first number):**
1. `resultOffset` paging silently broke — the server caps geojson pages by transfer SIZE (~750–4000 features, variable) and sets `exceededTransferLimit`; offset paging then **duplicated some parcels and skipped others** (108k rows, only 44k unique, ~34k missing). Fixed with an **OBJECTID cursor** (`where OBJECTID > last_max`, ordered) — bulletproof.
2. Merge crash: built results with `seg_id` as index then merged `on="seg_id"` → reset_index.
3. geojson/gpkg round-trip upper-cased the field (`GROUP_DSCR`) → case-robust lookup.
4. First spatial pass used parcel **centroids** within 100 ft → only 57% coverage because deep lots have centroids set far back. Switched to parcel **polygon** intersects buffer → 79%.

**Reconciliation:** 44,116 unique parcels vs a returnCountOnly of 77,931 — the gap is HCAD **stacked condo records** (multiple ownership rows at one footprint), redundant for land use; de-duplicated. **Verified the 21% NaN is real, not a gap:** those segments are a median ~340 ft from any parcel — roads through Hermann Park, Rice University, the Texas Medical Center, cemeteries, and bayou greenways. Left `none`, not mislabeled.

**Result:** `landuse_dominant` on 79% of segments (78% arterials): Residential 3,859, Commercial 1,121, Institutional 303, Industrial 258, Undeveloped 225, Parks 32. Added to map tooltip + CSV.

**Tier-3 conflation complete** — all predictors assembled (speed, lanes, width, median, ADT, operating speed, demographics, sidewalks, land use). Only the CRIS crash outcome (pending) remains before modeling.

---

## 2026-06-13 — Conflate sidewalks (OSM-derived)

**No official Houston sidewalk inventory exists** (checked: city "Sidewalk Service Areas" = admin sectors; "Sidewalk Permits" = construction points; Traffic_gx "Bike and Pedestrian" = count stations — none is a presence inventory). OSM is best-available. Key find: OSM maps **~344 mi of separate `footway=sidewalk` lines** in District C — far richer than the 16% of roads carrying a `sidewalk=*` tag. New `src/conflate_sidewalks.py`.

**Method:** sample 11 points per segment; at each, find ALL sidewalk footways within a width-scaled distance and classify each by side (left/right via cross product with segment direction); per segment, left_frac/right_frac → `sidewalk_presence` (both / one_side / partial / none). Falls back to the road `sidewalk` tag where no footway is mapped.

**Two fixes during build:**
1. First pass used `sjoin_nearest` (single nearest sidewalk per point) → could only ever mark ONE side, so "both" was undercounted at 3.4%. Switched to buffer-intersect (all sidewalks near each point, left & right independently) → both-sides rose to a realistic 12.5%.
2. Fixed 35 ft centerline tolerance → it missed sidewalks on wide arterials (sidewalk sits 40–50 ft from centerline on a 6-lane road). Scaled search distance to `roadway_width_ft/2 + 25 ft` (clamped 30–60). Arterial both-sides 18.6% → **22.4%**.

**Result:** at least one side on **56.5%** of segments; both sides 13.9% (22.4% arterials); **none mapped 43.5%** — consistent with Houston's known sidewalk gaps. Added to map tooltip + CSV.

**Caveat (documented prominently):** missing ≠ absent — `none` = none *mapped* within range; OSM completeness is uneven, not a field survey.

---

## 2026-06-13 — Conflate neighborhood demographics (ACS)

The DAG demographics confounder + equity-overlay basis. Source: Census ACS 2023 5-year at **block group**; geometry from TIGERweb (no key); attributes from the Census Data API. New `src/conflate_demographics.py`.

**Census API now requires a free key** (used to be keyless) — Vincent signed up and provided one; stored in gitignored `data/external/.census_api_key` (added to `.gitignore`, verified ignored). Key never committed.

**Attribution method:** each segment inherits the block group containing its midpoint (ecological — neighborhood value attached to streets, not a street-level measurement; documented). 100% of segments assigned; ~233 block groups span District C.

**Two data gotchas hit + fixed:**
1. Median income carried Census's `-666666666` "not available" sentinel → cleaned all negative counts/income to NaN.
2. The detailed poverty (B17001) and vehicle (B08201) tables **return null at block-group level**. Verified, then swapped to the BG-published equivalents: poverty via **C17002** (below = ratio<0.50 + 0.50–0.99), vehicles via **B25044** (no-veh = owner + renter no-vehicle). Both 100% covered.

**Result (District C block-group range):** median HH income $25k–$250k (median ~$147k — affluent inner-loop core), % below poverty 0–56 (median 5), % Hispanic 0–89 (median 16), % zero-car households 0–39 (median 2). Plausible for inner-loop Houston.

Added median income + zero-car to map tooltip (labeled "Neighborhood"), full demographic set to CSV; 4 docs updated.

---

## 2026-06-13 — Conflate traffic volume (ADT) + operating speed

The exposure confounder. Source: Traffic_gx count **stations** (layers 4 major / 5 local) joined to count **readings** (table 22) by `LocationID = station GlobalID`. Added `fetch_table` to `arcgis_fetch.py` for the non-spatial table; new `src/conflate_adt.py`.

**Method:** most-recent valid reading per station (stations span 2012–2026, multiple readings each) → snap station to nearest segment (≤150 ft) → segment ADT = mean of its stations → propagate along same-named corridors (`street_median`) → leave the rest blank (deliberately NOT class-imputed; imputing a confounder is a modeling decision to make + sensitivity-test explicitly).

**Diagnostic that reframed the result:** initial 30% overall coverage looked weak until I clipped stations to the actual district polygon — the bbox pull had 985 stations but **only ~320 are inside District C** (ADT's true measurement density). 99% of in-district stations sit within 150 ft of a segment, so tolerance was never the issue. Also fixed a report-metric bug (coverage was divided by all segments, not per-class). Corrected picture: **ADT covers 98% of primary and 97% of secondary arterials**, 34% tertiary, 6% residential — i.e. dense exactly where crashes and the HIN live. Median arterial ADT ~13.6k veh/day (p95 ~25k).

**Bonus — operating speed.** Table 22 also carries `PercentileSpeed85` (85th-pct measured speed) = the **DAG mediator**. Captured as `op_speed_85_mph` (~4% coverage). Flagged in codebook: model as the mechanism, do NOT adjust for it. First real data we have on the mediator (vs. posted speed).

All values provenance-tagged; ADT + volume added to map tooltip and CSV front; 4 docs updated; map republished to Pages.

---

## 2026-06-13 — Map tooltips updated + published to GitHub Pages

Vincent flagged the map still showed OSM `lanes` and lacked width/median. Fixed `make_map.py` tooltips to use `lanes_final` (with source), `roadway_width_ft`, and `median_type`.

Then published the map live. `make_map.py` now also writes `docs/index.html` (+ `.nojekyll`); enabled GitHub Pages via the REST API (token from osxkeychain credential helper) serving `main` `/docs`. Repo is public so Pages works on the free tier. **Live: https://wrenvin.github.io/PharisFellowshipVisionZero/** — council office / reviewers can view without running anything. Verified the 14 MB map serves (HTTP 200, legend + tooltips present). Note: `docs/index.html` is force-committed (the `reports/` copy stays gitignored); regenerating the map updates both. Caveat: each regen commits a fresh ~14 MB blob — fine for now, revisit if history bloats.

---

## 2026-06-12 (night, cont.) — Conflate lanes, width, median

Same city source (cached `Traffic_gx/2`, re-fetched to add `MEDIAN_WIDTH`/`DIRECTION`). New shared helper `src/conflate_util.py::snap_match` (the point-snap match logic, now reusable). New `src/conflate_lanes_width_median.py`.

**Verified lane semantics before trusting them.** City `DIRECTION` is mostly *orientation* (N/S, E/W) → each line is the whole road and `NO_OF_LANES` is **total** cross-section (Memorial Dr = 6 = 3+3, matches our merged `lanes`). ~14% of lines are per-direction coded (Allen Pkwy) — a residual ambiguity.

**Lane priority decision — and a mid-task correction.** Started with OSM primary / city gap-fill. The OSM-vs-city cross-check (1,276 shared segments, agree-within-1-lane 79%) showed disagreements are systematic: where they differ the **city is usually higher** because OSM tags only one direction of a divided road (e.g., N/S Braeswood OSM=2, city=4–6). So flipped to **city authoritative → OSM fill → local 2-lane default**. `lanes_final` now 98.6% (city 18%, OSM 69%, local-2 12%, none 1.4%); `lanes_osm_city_agree` kept as a QC flag.

**Width — fills the 0% gap.** Avg lane width is ~12 ft citywide (rarely 11), so `roadway_width_ft = lanes_final × avg_lane_width` (travel pavement, excludes median). **98.6% covered, was 0%.** `width_source` distinguishes city-measured lane width (18%) from the 12-ft assumption (81%).

**Median.** `median_type` ∈ {Raised 984, Depressed 59, TWLT 53 (center turn lane), Undivided, Divided (unspecified)}. Filled: city where present (18%), local streets → Undivided (64%), merged-dual-without-city → "Divided (unspecified)" (216, so we never mislabel a divided road as undivided), higher-class unknown → NaN (17.7%). `median_width_ft` city-only (not defaulted). **Independent validation: 76.9% of our merged dual-carriageway segments are typed Raised/Depressed by the city** — the median data confirms the merge.

All conflated columns provenance-tagged (`*_source`). CSV (now 50 cols, key new fields surfaced up front) + map refreshed.

---

## 2026-06-12 (night) — Tier-3 conflation begins: posted speed limits

First external data joined onto the network. Doing conflation one layer at a time; speed first (Vincent's call).

**Major data discovery.** Houston Public Works' `TDO/Traffic_gx` ArcGIS service (found via the city GeoHub) is an engineering goldmine for the whole conflation phase: a **Speed Limit** layer carrying `POSTED_SPEED`, `NO_OF_LANES`, `AVG_LANE_WIDTH` (fills our 0%-coverage width gap!), `MEDIAN_TYPE`, and classification — already in EPSG:2278 — plus separate **Major Thoroughfare ADT** and **Local Street ADT** layers (city counts traffic on locals too, solving the AADT-coverage worry I'd flagged for TxDOT RHiNo). Also in the same `HoustonMap/Transportation` service: the **official Vision Zero HIN 2022 & 2018** polylines with per-segment crash/death counts and rates, ped/bike dangerous-roads layers, and a social-vulnerability layer — i.e. the city's crash-based baseline for the divergence analysis is publicly downloadable. Caveat: speed source is on staging host `geogimstest` (production `geogims` unreachable 2026-06-12); flagged.

**Infrastructure.** New reusable `src/arcgis_fetch.py` (paged, bbox-clipped ArcGIS REST → GeoDataFrame) for all city pulls. New **enrichment model**: `district_c_segments_enriched.gpkg` = clean network + conflated columns, grown one conflation step at a time; each `conflate_*.py` is idempotent (drops its own columns on reload). This is now the canonical analysis file.

**Speed method** (`src/conflate_speed.py`): geometries differ between OSM and the city network, so no exact join — snap 5 sample points per segment to the nearest city speed line within 60 ft, take modal `POSTED_SPEED` if ≥40% of points match. Fill priority recorded in `speed_source`: city → osm → TX 30 mph default.

**Key finding — coverage is a *posting* fact, not a match failure.** City-posted speed matched only 18% of segments / 48% of arterials. Diagnostic: the unmatched higher-class segments sit a **median ~1,100 ft from any city speed line** (only 4 of 1,104 within 100 ft) — they're genuinely not on Houston's posted-thoroughfare network. Under TX Transportation Code §545.352 an unposted urban street is **30 mph** by default, so these legally default to 30 (tagged `default_30_unposted`, kept distinct for sensitivity testing). Corrected an initial bug where I restricted the 30 mph default to residential classes only — the prima facie default applies to any unposted urban street regardless of OSM class.

**Result:** `posted_speed_mph` now 100% populated (was 14% OSM-only), every value provenance-tagged. City matches: 35 mph dominant (1,152), then 40 (123), 45 (35), 50 (22). Spatial-join name-agreement 86% (sanity OK). Map tooltips now show speed + its source.

**Staged for next steps (already visible in the same city layer):** lanes, lane width, median type, ADT.

---

## 2026-06-12 (night) — ELI5 doc added

Created `ELI5.md` at Vincent's request: a plain-English, conversational story of the whole project — the big idea (reactive vs. proactive street safety, the Texas camera ban), and a step-by-step of the road-network build with no jargon. Now FOUR docs to keep current: README (facts), LOG (diary), CODEBOOK (dictionary), ELI5 (story).

---

## 2026-06-12 (evening, cont.) — Frontage roads excluded; scope question resolved

**Vincent's decision:** feeder/frontage roads are part of the highway facility — TxDOT right-of-way — and are excluded like the freeways they serve.

**Implementation:** name-based exclusion (`frontage|feeder|service road`, case-insensitive) added to `src/pull_osm.py` beside the motorway filter; full pipeline rerun. All 11 frontage road names removed (244 segments / 24.5 mi in the previous network), including the marginal cases Allen Parkway Frontage Road (0.7 mi; Allen Pkwy itself is city-owned and stays) and South Post Oak Road Frontage Road (0.6 mi) — easily whitelisted back if ever needed. Verified zero frontage segments remain.

**Final analysis network: 7,381 segments / 637.8 mi.** Note: `seg_id`s were regenerated by the rerun (nothing external referenced them yet; from here on they're stable).

---

## 2026-06-12 (evening) — Sliver cleanup

**Profiling first, rule second.** Short segments turned out to be three different things: (A) 470 `*_link` turn lanes/slip roads (13.3 mi) — intersection plumbing at any length; (B) ~1,000 short *named* pieces, mostly degree 3-4 both ends — the bits of real cross streets passing through boulevard medians / intersection interiors; (C) 30 unnamed sub-50-ft fragments — junk.

**Rules** (`src/clean_slivers.py`): A → dropped to `removed_slivers` audit layer. B → **absorbed** into longest same-named neighboring segment (geometry linemerged, length summed, endpoints + degree/signal context updated; iterative so chains collapse; non-contiguous merges refused). C → dropped to audit. Named shorts with no same-named neighbor conservatively kept (31).

**Results:** 9,097 → **7,635 segments**; 677.0 → **663.4 mi** (loss = exactly the dropped links + junk; absorption preserved all street length). 962 pieces absorbed in 2 passes. p5 segment length 40 → **145 ft**. 0 orphaned `merged_away` pointers (remapped through absorption chains).

**New analysis file:** `district_c_segments_clean.gpkg` (layers: `segments`, `removed_slivers`, `merged_away`). Map regenerated from it.

**Flagged, not actioned — freeway frontage roads.** Sliver profiling surfaced "West Loop South Frontage Road" / "Southwest Freeway Frontage Road" segments in the network (tagged secondary/primary in OSM, so they survived the motorway filter). Feeders are TxDOT right-of-way — arguably outside "streets the city can redesign," same logic as excluding freeways. Decision needed: keep or exclude. Affects scope, not slivers; raised with Vincent.

---

## 2026-06-12 (later still) — Dual-carriageway merge

**Problem:** divided roads (Memorial, the Braeswoods, Heights Blvd...) were two parallel one-way segments each — ambiguous crash assignment, halved exposure per unit. ~25% of network mileage.

**Method** (`src/merge_dual_carriageways.py`): no geometry synthesis (averaging mismatched halves is fragile). Instead: (1) pair twins — same-named, antiparallel, one-way, within 150 ft; (2) connected components = corridors, **2-colored** into their two sides (robust on curved corridors like T.C. Jester where bearings rotate); (3) keep the longer side as representative centerline, move the other side's segments to a `merged_away` audit layer with `rep_seg_id` pointers — nothing deleted, crash assignment searches both layers and credits the representative; (4) aggregate attributes: `lanes` = sum of halves (now means total cross-section on every row), `maxspeed` = max, `oneway` = False; (5) stable `seg_id` (`C-#####`) assigned to all segments pre-merge so identities persist.

**Results:** 3,768 twin pairs, 160 corridors, **0 coloring conflicts** (twin graph perfectly bipartite — no false-positive tangles). 1,248 halves (86.2 mi) merged into 1,193 representatives. Network: 10,345 → **9,097 segments**, 763 → **677 mi**. One-way share 35.6% → **13.7%** (residual = genuine one-ways). Merged-lanes coverage 92.9%.

**Validation:** every top corridor halved its mileage (N. Braeswood 9.6→4.8 mi); ground-truth lane checks pass (Heights Blvd 2+2=4, Memorial 3+3=6); merged-lanes distribution dominated by 4s and 6s as divided boulevards should be.

**Downstream rule:** all analysis uses `district_c_segments_merged.gpkg` layer `segments`; pre-merge file is provenance only. Map regenerated from merged network.

---

## 2026-06-12 (later) — Codebook + map made legible

Feedback from Vincent: the network map was unreadable to anyone who didn't build it — unexplained colors, raw variable names in tooltips. Two fixes:

- **`CODEBOOK.md` created** (repo root): defines every column in `district_c_segments.gpkg` — meaning, units, source, value sets, coverage % — plus OSM road-class → plain-English translations and a "known limitations" section (missing ≠ absent; divided roads currently doubled; sliver tail; posted ≠ operating speed). Standing rule: **codebook stays in sync with any schema change.**
- **Map rebuilt** (`src/make_map.py`, replacing the inline throwaway): fixed legend box with plain-English road types ("Major arterial", "Collector", "Local street"...), short network explainer, per-class toggleable layers, tooltips with human labels ("Traffic lanes", "Posted speed", "Divided road half"), "not tagged" shown instead of NaN, divided-road layer off by default. Verified legend/layers/tooltips present in output HTML.

---

## 2026-06-12 — Road network built: boundary, OSM pull, segmentation, coverage report

### Decisions made (with rationale)

1. **Unit of analysis: intersection-to-intersection segments.** Split the network at junction nodes (degree ≥ 3). Chosen over fixed-length segments because it matches the crash-modeling literature (Dumbaugh tradition), is interpretable to a council-office audience ("this block of Westheimer"), and makes intersection-vs-midblock a clean later distinction. Variable segment length is handled by carrying length as an exposure offset in the negative binomial.
2. **Scope: city-controlled surface streets only.** Freeways and ramps (I-610, US-59/I-69) excluded — TxDOT jurisdiction, not city-redesignable, and they behave differently from surface streets. Locals *kept* (full functional hierarchy below freeway). Service roads (alleys, driveways, parking aisles) excluded via OSMnx `network_type="drive"`. Rationale: the project's thesis is about streets the city can actually redesign.
3. **Geometry source: OpenStreetMap as the spine**, with TxDOT RHiNo (AADT/exposure), city parcels (land use), and ACS (demographics) to be conflated on later. OSM has the best free design-feature coverage and clean topology for segmentation.
4. **CRS: EPSG:2278** (Texas State Plane South Central, US survey ft) for all distance work — the 200-ft crash-assignment buffer must be honest feet, not degrees.
5. **Dual carriageways: merge is now mandatory** (was "optional, quantify first"). See finding below — at ~25% of network mileage, leaving divided roads as two parallel segments would double-count streets and halve their apparent exposure in the model.

### What was built

- Python venv (`.venv`) with geopandas / osmnx / folium stack; `requirements.txt` pinned.
- `src/pull_osm.py` — pulls drivable OSM network clipped to the boundary via Overpass; drops motorway/motorway_link (225 freeway edges removed); preserves tier-1/tier-2 tags (lanes, maxspeed, width, oneway, sidewalk, cycleway, parking, lit, surface).
- `src/build_segments.py` — collapses directed graph to undirected segments (one row per physical street), projects to EPSG:2278, parses messy OSM tags into typed columns (lanes, maxspeed→mph, width→ft, sidewalk/cycleway/parking status), attaches junction degree + traffic-signal presence per segment end, detects dual-carriageway candidates (same-named antiparallel one-way twin within 150 ft), writes GeoPackage + coverage report.
- Outputs: `data/processed/district_c_segments.gpkg`, `reports/feature_coverage.md`, `reports/network_map.html` (interactive sanity-check map).

### Findings

- **Boundary verified (prospectus open item resolved).** The COH GIS council-districts layer (`HoustonMap/Administrative_Boundary/MapServer/2`) is current — District C lists CM Joe Panzarella. Single clean polygon, inner loop down to Meyerland/Braeswood.
- **Network size: 10,345 segments, 763.2 centerline miles.** Median segment 304 ft (a Houston block — segmentation behaved). Composition: residential 5,243 segs / 434 mi; secondary 2,759 / 185 mi; tertiary 1,092 / 73 mi; primary 529 / 41 mi; rest links/unclassified.
- **Feature coverage (the tier-2 reality check):**
  - `lanes` **84.8%** overall, 90.8% on arterials/collectors — much better than feared; the top design predictor is largely usable as-is.
  - `surface` 72.8%.
  - `maxspeed` **14.2%** (4.8% on locals) — needs city speed-limit layer or Texas-default imputation (30 mph urban prima facie).
  - `sidewalk` 17.1%, `lit` 21.8%, `cycleway` 9.6%, `parking` 1.7% — too thin to use raw; look for city inventories (Houston sidewalk gaps are themselves part of the story).
  - `width` **0.0%** — must come from elsewhere entirely: city inventory, lanes × standard lane-width estimate, or aerial imagery.
- **Dual-carriageway finding (bigger than expected):** 2,608 segments / 177.3 mi (~25% of mileage) have a same-named antiparallel one-way twin within 150 ft. Top streets validate the detector: N/S Braeswood, Memorial, Richmond, W/E T.C. Jester, Ella, Heights Blvd, Allen Pkwy, Main — exactly District C's bayou-divided and esplanade boulevards. Consequence: crash assignment would be ambiguous between twins and exposure would be split, so **merging divided pairs into single centerlines is a confirmed prerequisite before crash assignment**.
- One-way share (35.6%) is inflated by the dual carriageways; will drop after the merge.
- **Sliver-segment tail:** p5 segment length = 40 ft — tiny fragments, mostly `*_link` turn lanes and median crossovers. Need an absorb-or-drop rule before modeling.

### Issues hit (and fixes)

- OSM tags arrive as `None` *or* float `NaN` depending on column presence; normalized both in the tag parser (`first()`), which fixed a crash in cycleway parsing.
- GeoPackage can't store list-valued columns (OSMnx merges tags when simplifying ways) — pipe-joined for audit columns, first-value for typed columns.
- `tabulate` needed for `DataFrame.to_markdown` — added to env.

### Next steps (in order)

1. **Merge dual-carriageway pairs** into single centerline segments (pre-crash-assignment requirement).
2. **Sliver cleanup rule** for the sub-~50-ft fragment tail.
3. **Tier-3 conflation:** TxDOT RHiNo (AADT — the exposure confounder), city speed limits, sidewalk inventory, parcels (land use), ACS.
4. Nothing committed to git yet — first commit of skeleton + scripts pending.

---

## Pre-2026-06-12 — Context (before this log existed)

- Prospectus written; methodology fixed: negative binomial on segment-level severe-crash counts, Moran's I / Getis-Ord Gi* as the HIN-reconstruction baseline, unsupervised street typologies, spatially blocked CV, divergence analysis as headline output. DAG identification strategy: adjust land use / exposure / demographics; do **not** adjust operating speed (mediator); crash reporting is a collider (formal basis of the underreporting concern).
- TxDOT CRIS geocoded extract is agency-restricted; request in motion via CM Panzarella's office (chiefs of staff Anna and Cole). Questions doc drafted for Austin's Vision Zero team.
- Austin's `cityofaustin/vision-zero` (CC0) identified as schema/UI reference — mine the schema, do not clone-and-run (their stack needs their prod DB/VPN; the hard part of CRIS ingestion is credentialed access, not code).
- Fellowship timeline: ends 2026-07-31; ~7 weeks remaining as of this entry.
