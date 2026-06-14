"""Export segment + boundary GeoJSON for the interactive web map (docs/).

The web app (docs/index.html) loads these and does all styling/filtering live
in the browser. We keep the files lean: simplify geometry, round coordinates,
round attribute values, and carry only display/filter-relevant columns.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DOCS = ROOT / "docs"

# column -> rounding (None = keep as-is / string)
COLS = {
    "seg_id": None, "name": None, "highway": None,
    "lanes_final": 0, "lanes_source": None,
    "roadway_width_ft": 0,
    "posted_speed_mph": 0, "speed_source": None,
    "op_speed_85_mph": 0,
    "adt": 0, "adt_source": None,
    "median_type": None,
    "sidewalk_presence": None,
    "landuse_dominant": None, "pct_commercial": 0, "pct_industrial": 0,
    "median_hh_income": 0, "pct_poverty": 1, "pct_hispanic": 1,
    "pct_black_nh": 1, "pct_white_nh": 1, "pct_zero_car_hh": 1,
    "pop_density_sqmi": 0,
    # crash outcomes (per segment, from CRIS)
    "n_crash": 0, "n_injury": 0, "n_severe": 0, "n_fatal": 0,
    "n_ped": 0, "n_bike": 0, "n_ped_severe": 0, "n_bike_severe": 0,
    "n_signals": 0, "oneway": None, "merged_dual": None, "length_ft": 0,
}

FRIENDLY_CLASS = {
    "primary": "Major arterial", "secondary": "Arterial", "tertiary": "Collector",
    "residential": "Local street", "unclassified": "Minor street",
}

seg = gpd.read_file(PROCESSED / "district_c_segments_enriched.gpkg", layer="segments")

# friendly road class (collapse *_link to Minor)
base = seg["highway"].str.replace("_link", "", regex=False)
seg["road_class"] = base.map(FRIENDLY_CLASS).fillna("Minor street")
seg.loc[seg["highway"].str.endswith("_link"), "road_class"] = "Minor street"

keep = seg[[c for c in COLS if c in seg.columns] + ["road_class", "geometry"]].copy()
for c, nd in COLS.items():
    if c in keep.columns and nd is not None:
        keep[c] = keep[c].round(nd)
        if nd == 0:
            keep[c] = keep[c].astype("Int64")  # nullable int -> clean JSON
for c in ("oneway", "merged_dual"):
    if c in keep.columns:
        keep[c] = keep[c].astype("boolean")

# simplify in feet (EPSG:2278) for display, then reproject to WGS84
keep["geometry"] = keep.geometry.simplify(12, preserve_topology=False)
keep = keep.to_crs(4326)

DOCS.mkdir(exist_ok=True)
out = DOCS / "segments.geojson"
if out.exists():
    out.unlink()
keep.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)

boundary = gpd.read_file(ROOT / "data/raw/district_c_boundary.geojson").to_crs(4326)
bpath = DOCS / "boundary.geojson"
if bpath.exists():
    bpath.unlink()
boundary[["geometry"]].to_file(bpath, driver="GeoJSON", COORDINATE_PRECISION=5)

print(f"Wrote {len(keep):,} segments -> {out} ({out.stat().st_size/1e6:.1f} MB)")
print(f"Wrote boundary -> {bpath}")

# crash points for the VZ dashboard "Crash locations" view + the by-month,
# by-time-of-day, and years-of-life-lost panels:
# [lat, lon, sev, fatal, ped, bike, year, date, hour, yll]
cr = gpd.read_file(PROCESSED / "district_c_crashes.gpkg", layer="crashes").to_crs(4326)
pts = []
for g, sv, ft, pd_, bk, yr, dt, hr, yl in zip(
        cr.geometry, cr.severe, cr.fatal, cr.involves_ped, cr.involves_bike,
        cr.year, cr.date, cr.hour, cr.yll):
    if g is None or g.is_empty:
        continue
    pts.append([round(g.y, 5), round(g.x, 5), int(bool(sv)), int(bool(ft)),
                int(bool(pd_)), int(bool(bk)), int(yr) if pd.notna(yr) else None,
                dt if isinstance(dt, str) else None,
                int(hr) if pd.notna(hr) else None,
                round(float(yl), 1) if pd.notna(yl) and yl else 0])
cpath = DOCS / "crash_points.json"
cpath.write_text(json.dumps(pts, separators=(",", ":")))
print(f"Wrote {len(pts):,} crash points -> {cpath} ({cpath.stat().st_size/1e6:.1f} MB)")
