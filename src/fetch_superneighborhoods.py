"""Fetch the City of Houston Super Neighborhood boundaries to data/raw.

Houston's 88 Super Neighborhoods are an official City planning geography (a
coarser-than-block-group, recognizable-name unit: Downtown, Second Ward,
Montrose, etc.). They are published on the City GIS in the same
Administrative_Boundary service as the council districts (layer 3). We pull them
once here; export_webmap_data.py then tags each segment and crash with its
Super Neighborhood (by POLYID) so the dashboard can filter by it.

Run:  .venv/bin/python src/fetch_superneighborhoods.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg
from arcgis_fetch import fetch_layer

SN_URL = ("https://mycity2.houstontx.gov/pubgis02/rest/services/"
          "HoustonMap/Administrative_Boundary/MapServer/3")  # Super Neighborhoods

def main():
    # POLYID = the official Super Neighborhood number; SNBNAME = its name.
    gdf = fetch_layer(SN_URL, out_fields="POLYID,SNBNAME", out_sr=4326)
    if gdf.empty:
        raise SystemExit("No Super Neighborhood features returned; check the URL.")
    gdf = gdf[["POLYID", "SNBNAME", "geometry"]].copy()
    cfg.RAW.mkdir(parents=True, exist_ok=True)
    out = cfg.raw("superneighborhoods.geojson")
    if out.exists():
        out.unlink()
    gdf.to_file(out, driver="GeoJSON")
    print(f"Wrote {len(gdf)} Super Neighborhoods -> {out}")
    print("Sample:", ", ".join(sorted(gdf["SNBNAME"].astype(str))[:6]), "...")

if __name__ == "__main__":
    main()
