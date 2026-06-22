"""Pull the City of Houston FULL-PURPOSE (full-service) boundary and save it as the
study-area boundary the whole pipeline clips to.

Source: COH GIS, Administrative_Boundary MapServer, layer 0 "Houston City Limit"
(https://mycity2.houstontx.gov/pubgis02/rest/services/HoustonMap/Administrative_Boundary/MapServer/0).
Each polygon carries SERVICE_TY in {FULL, LIMITED}. We keep ONLY SERVICE_TY='FULL'
(the fully-annexed, full-service city: police/EMS/fire/etc.) and dissolve to one
polygon. The LIMITED-purpose annexations (749 slivers — the "tentacles") are dropped
because the City provides only limited services there and CRIS does not attribute
their crashes to the City of Houston, so they hold essentially no data.

Writes data/raw/<AREA>_boundary.geojson (cfg.BOUNDARY). Rerun the pipeline after this
to re-clip the network + crashes to the new boundary.
"""

import json
import geopandas as gpd
from shapely.ops import unary_union
import requests

import config as cfg

LAYER = ("https://mycity2.houstontx.gov/pubgis02/rest/services/"
         "HoustonMap/Administrative_Boundary/MapServer/0")


def main():
    r = requests.get(LAYER + "/query", params={
        "where": "SERVICE_TY='FULL'", "outFields": "SERVICE_TY,ENTITY_NAM",
        "outSR": 4326, "f": "geojson"}, timeout=120)
    feats = r.json().get("features", [])
    if not feats:
        raise SystemExit("No FULL-service polygons returned from COH GIS.")
    full = gpd.GeoDataFrame.from_features(feats, crs=4326)
    poly = unary_union(full.geometry.values)
    out = gpd.GeoDataFrame(
        {"NAME": ["City of Houston (full-purpose)"],
         "SOURCE": ["COH GIS Administrative_Boundary 'Houston City Limit' (layer 0), "
                    "SERVICE_TY='FULL', dissolved"],
         "YEAR": [2026]},
        geometry=[poly], crs=4326)
    sq_mi = out.to_crs(2278).area.iloc[0] / 27878400
    cfg.RAW.mkdir(parents=True, exist_ok=True)
    if cfg.BOUNDARY.exists():
        cfg.BOUNDARY.unlink()
    out.to_file(cfg.BOUNDARY, driver="GeoJSON")
    print(f"Pulled {len(full)} FULL-service polygon(s); dissolved -> {cfg.BOUNDARY} "
          f"({sq_mi:.1f} sq mi)")


if __name__ == "__main__":
    main()
