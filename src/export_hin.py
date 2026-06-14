"""Export the City of Houston's official Vision Zero High Injury Network (2022),
clipped to the study area, for the dashboard overlay (docs/hin.geojson).

This is the City's authoritative crash-based screening — the comparison baseline
the project's systemic model will eventually be measured against. Area-aware via
config (clips to whatever AREA's boundary is).
"""

import config as cfg
from arcgis_fetch import fetch_layer

HIN_URL = ("https://mycity2.houstontx.gov/pubgis02/rest/services/"
           "HoustonMap/Transportation/MapServer/20")  # Vision Zero HIN 2022

hin = fetch_layer(HIN_URL, out_fields="*", bbox_4326=cfg.bbox_4326(), out_sr=cfg.CRS_FT)
boundary = cfg.boundary(cfg.CRS_FT).geometry.iloc[0]
hin = hin[hin.intersects(boundary)].copy()
hin["geometry"] = hin.geometry.simplify(15, preserve_topology=False)  # ft
hin = hin.to_crs(cfg.CRS_WGS)

out = cfg.DOCS / "hin.geojson"
if out.exists():
    out.unlink()
hin[["geometry"]].to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
print(f"Wrote {len(hin):,} HIN segments -> {out} ({out.stat().st_size/1e6:.2f} MB)")
