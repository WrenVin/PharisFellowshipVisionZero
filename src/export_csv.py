"""Export the segment dataset to CSV for easy human inspection (Excel/Sheets).

GeoPackages are geospatial databases and don't open in a spreadsheet. This
writes a flat CSV: all attribute columns, geometry dropped, plus a midpoint
lat/lon and a Google Maps link so any row can be located instantly.
"""

from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

enr = PROCESSED / "district_c_segments_enriched.gpkg"
src = enr if enr.exists() else PROCESSED / "district_c_segments_clean.gpkg"

seg = gpd.read_file(src, layer="segments")

# midpoint in lat/lon for a human-locatable reference + a maps link
mid = seg.geometry.interpolate(0.5, normalized=True)
mid_ll = gpd.GeoSeries(mid, crs=seg.crs).to_crs(4326)
df = seg.drop(columns="geometry").copy()
df["mid_lat"] = mid_ll.y.round(6)
df["mid_lon"] = mid_ll.x.round(6)
df["google_maps"] = [f"https://maps.google.com/?q={la},{lo}"
                     for la, lo in zip(df["mid_lat"], df["mid_lon"])]

# put the columns a human reads first up front
front = [c for c in ["seg_id", "name", "highway", "road_class", "posted_speed_mph",
                     "speed_source", "lanes_final", "lanes_source", "roadway_width_ft",
                     "median_type", "adt", "adt_source", "op_speed_85_mph",
                     "length_ft", "oneway", "merged_dual",
                     "n_signals", "mid_lat", "mid_lon", "google_maps"]
         if c in df.columns]
df = df[front + [c for c in df.columns if c not in front]]

out = PROCESSED / "district_c_segments.csv"
df.to_csv(out, index=False)
print(f"Wrote {len(df):,} rows x {len(df.columns)} cols -> {out}")
print("Columns:", ", ".join(df.columns))
