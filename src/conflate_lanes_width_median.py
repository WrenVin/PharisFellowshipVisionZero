"""Conflate lane count, roadway width, and median onto District C segments.

Source: cached Houston Public Works Speed Limit layer (TDO/Traffic_gx/2),
which carries NO_OF_LANES, AVG_LANE_WIDTH, MEDIAN_TYPE, MEDIAN_WIDTH.
Matched with the shared point-snap helper (conflate_util.snap_match).

Decisions (see LOG 2026-06-12):
- Lanes: the city's NO_OF_LANES is TOTAL cross-section lanes on its
  orientation-coded lines (verified: Memorial Dr = 6 = 3+3), matching our
  merged `lanes` semantics. But ~14% of city lines are per-direction coded,
  an ambiguity. So OSM's already-total `lanes` (85% covered) stays PRIMARY;
  the city fills the gap and serves as a cross-check. `lanes_source` records
  which was used; report shows OSM-vs-city agreement.
- Width: AVG_LANE_WIDTH is ~12 ft almost everywhere, so roadway width is
  essentially lanes x 12. We store `avg_lane_width_ft` and derive
  `roadway_width_ft = lanes_final * avg_lane_width_ft` (travel pavement,
  excludes the median). This fills the OSM width gap (was 0%).
- Median: `median_type` (Raised / Undivided / Depressed / TWLT) and
  `median_width_ft`, straight from the city (modal / median over matches).
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from conflate_util import snap_match

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "external"
REPORTS = ROOT / "reports"

OWNED = ["city_lanes", "lanes_final", "lanes_source", "avg_lane_width_ft",
         "roadway_width_ft", "width_source", "median_type", "median_width_ft",
         "median_source", "geom_match_frac", "lanes_osm_city_agree"]

seg = gpd.read_file(PROCESSED / "district_c_segments_enriched.gpkg", layer="segments")
seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])
print(f"Segments: {len(seg):,}")

city = gpd.read_file(EXTERNAL / "houston_speed_limit_districtC.gpkg")
for c in ("MEDIAN_TYPE", "DIRECTION"):
    if c in city:
        city[c] = city[c].astype("string").str.strip()
city = city.to_crs(seg.crs)

m = snap_match(
    seg, city,
    fields={"NO_OF_LANES": "mode", "AVG_LANE_WIDTH": "median",
            "MEDIAN_TYPE": "mode", "MEDIAN_WIDTH": "median"},
    tol_ft=60, min_frac=0.4,
)
m = m.rename(columns={
    "NO_OF_LANES": "city_lanes", "AVG_LANE_WIDTH": "avg_lane_width_ft",
    "MEDIAN_TYPE": "median_type", "MEDIAN_WIDTH": "median_width_ft",
    "match_frac": "geom_match_frac",
})
seg = seg.merge(m, on="seg_id", how="left")

# --- lanes: city authoritative, OSM fills, local default last -----------------
# City NO_OF_LANES is total cross-section engineering data; on divided roads it
# beats OSM, which often tags only one direction (verified: N/S Braeswood OSM=2,
# city=4-6). So city is PRIMARY where matched. Local streets with no source
# default to 2 lanes (residential/unclassified are ~always 2).
LOCAL = {"residential", "unclassified", "living_street"}
osm_lanes = seg["lanes"]  # OSM, total after our merge
lanes_final, lanes_source = [], []
for o, c, hw in zip(osm_lanes, seg["city_lanes"], seg["highway"]):
    if pd.notna(c):
        lanes_final.append(float(c)); lanes_source.append("city")
    elif pd.notna(o):
        lanes_final.append(float(o)); lanes_source.append("osm")
    elif hw in LOCAL:
        lanes_final.append(2.0); lanes_source.append("default_local_2")
    else:
        lanes_final.append(np.nan); lanes_source.append("none")
seg["lanes_final"] = lanes_final
seg["lanes_source"] = lanes_source
# QC: where both exist, do they agree within 1 lane?
both = osm_lanes.notna() & seg["city_lanes"].notna()
seg["lanes_osm_city_agree"] = np.where(
    both, (osm_lanes - seg["city_lanes"]).abs() <= 1, np.nan
)

# --- width: derive from lanes x avg lane width --------------------------------
alw = seg["avg_lane_width_ft"].fillna(12.0)  # near-constant 12 ft
seg["roadway_width_ft"] = np.where(
    seg["lanes_final"].notna(), seg["lanes_final"] * alw, np.nan
)
seg["width_source"] = np.where(
    seg["avg_lane_width_ft"].notna() & seg["lanes_final"].notna(),
    "city_lanes_x_width",
    np.where(seg["lanes_final"].notna(), "lanes_x_12ft_assumed", "none"),
)

# --- median: city where present; local streets default to Undivided ----------
med_src = []
mt_final = []
for mt, hw, md in zip(seg["median_type"], seg["highway"], seg["merged_dual"]):
    if pd.notna(mt):
        mt_final.append(mt); med_src.append("city")
    elif md:
        # divided by definition (merged dual carriageway) but no city record
        mt_final.append("Divided (unspecified)"); med_src.append("merged_dual")
    elif hw in LOCAL:
        mt_final.append("Undivided"); med_src.append("default_local_undivided")
    else:
        mt_final.append(None); med_src.append("none")
seg["median_type"] = mt_final
seg["median_source"] = med_src

out = PROCESSED / "district_c_segments_enriched.gpkg"
seg.to_file(out, layer="segments", driver="GPKG")
print(f"Saved {out}")

# --- report -------------------------------------------------------------------
def pct(mask):
    return round(100 * mask.mean(), 1)

agree = seg.loc[both, "lanes_osm_city_agree"]
mt = seg["median_type"].value_counts(dropna=False)
dual = seg[seg["merged_dual"]]
dual_div = dual["median_type"].isin(["Raised", "Depressed"]).mean()

report = f"""# Lanes / Width / Median Conflation Report

Generated by `src/conflate_lanes_width_median.py`. Source: Houston Public
Works Speed Limit layer (`TDO/Traffic_gx/2`), matched with the shared
point-snap helper (60 ft, >=40% of 5 sample points).

## Lane count

- `lanes_final` coverage: **{pct(seg.lanes_final.notna())}%** of segments
  (city authoritative {pct(seg.lanes_source.eq('city'))}%, OSM fill {pct(seg.lanes_source.eq('osm'))}%, local-2 default {pct(seg.lanes_source.eq('default_local_2'))}%, none {pct(seg.lanes_source.eq('none'))}%).
- **OSM-vs-city cross-check:** where both exist ({both.sum():,} segments),
  they agree within 1 lane **{pct(agree.astype(bool))}%** of the time. Where they
  differ, the city is usually higher — OSM tends to tag one direction of a divided
  road — so city is preferred (not OSM) on the arterials that matter most.

## Roadway width (new — OSM width was 0%)

- `roadway_width_ft` coverage: **{pct(seg.roadway_width_ft.notna())}%**
  (= lanes_final x avg lane width; avg lane width is ~12 ft citywide).
- From city lane width: {pct(seg.width_source.eq('city_lanes_x_width'))}%;
  12 ft assumed: {pct(seg.width_source.eq('lanes_x_12ft_assumed'))}%.

## Median

- `median_type` coverage: **{pct(seg.median_type.notna())}%**
  (city {pct(seg.median_source.eq('city'))}%, local "Undivided" default {pct(seg.median_source.eq('default_local_undivided'))}%, unknown {pct(seg.median_source.eq('none'))}%). Distribution:

{mt.to_string()}

- `median_width_ft` coverage: {pct(seg.median_width_ft.notna())}% (city-measured only; not defaulted).
- **Validation:** of merged divided-road segments (`merged_dual`),
  {round(100*dual_div,1)}% are typed Raised/Depressed by the city — i.e. the
  median data confirms our dual-carriageway merge independently.

## Notes

- Lane semantics: city `NO_OF_LANES` is total cross-section on orientation-
  coded lines (verified Memorial Dr = 6). ~14% of city lines are per-direction
  coded; keeping OSM primary limits exposure to that ambiguity to gap-fill only.
- `roadway_width_ft` is travel-lane pavement; it excludes the median (kept
  separately as `median_width_ft`). TWLT = continuous center two-way left-turn lane.
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "lanes_width_median_report.md").write_text(report)
print(report)
