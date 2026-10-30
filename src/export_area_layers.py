"""Export extra area boundaries for the dashboard's Area filter.

Council districts and Super Neighborhoods are tagged onto every crash and
segment by export_webmap_data.py. The layers here are filtered in the browser
instead (point-in-polygon on load of a selection), so adding a new way to cut
the city only needs a GeoJSON in docs/ and an entry in the page's AREA_TYPES.

Writes (clipped to the full-purpose city boundary, simplified ~50 ft, lon/lat):

    docs/areas_precinct.geojson   Harris County commissioner precincts (the part of
                                  each inside the city). Fort Bend and Montgomery
                                  precincts are left out: only slivers of them fall
                                  inside Houston, so a "precinct" view would mislead.
    docs/areas_tirz.geojson       the 27 active Tax Increment Reinvestment Zones,
                                  labeled with their City TIRZ number

Each feature carries {id, name}. Pieces smaller than MIN_SQMI inside the city
(slivers along a county line) are dropped.

    .venv/bin/python src/export_area_layers.py
"""

import geopandas as gpd
import pandas as pd

import config as cfg
from arcgis_fetch import fetch_layer

COH = "https://mycity2.houstontx.gov/gisweb02/rest/services/HoustonMap/Administrative_Boundary/MapServer"
HC_PCT = "https://www.gis.hctx.net/arcgis/rest/services/CommPrecinct/MapServer/0"   # Harris County GIS, 2022 plan
MIN_SQMI = 0.05
SIMPLIFY_FT = 50
# City TIRZ number for each zone name in the COH layer (which carries no number).
# Sources: City of Houston board listing and houstontx.gov/ecodev/tirz/<n>.html;
# TIRZ 4 (Village Enclaves) was terminated in 2013; 28 (Medical Center) created 2022.
TIRZ_NUMBER = {
    "St. George Place": 1, "Midtown": 2, "Market Square": 3, "Memorial Heights": 5,
    "Eastside": 6, "O.S.T./Almeda": 7, "Gulfgate": 8, "South Post Oak": 9,
    "Lake Houston": 10, "Greenspoint": 11, "City Park": 12, "Old Sixth Ward": 13,
    "Fourth Ward": 14, "East Downtown": 15, "Uptown": 16, "Memorial City": 17,
    "Fifth Ward": 18, "Upper Kirby": 19, "Southwest Houston": 20,
    "Hardy/Near Northside": 21, "Leland Woods": 22, "Harrisburg": 23,
    "Greater Houston": 24, "Hiram Clarke/Fort Bend Houston": 25, "Sunnyside": 26,
    "Montrose": 27, "Medical Center Area": 28,
}


def clip(gdf, boundary):
    gdf = gdf.to_crs(cfg.CRS_FT)
    gdf = gdf.dissolve(by="id", as_index=False, aggfunc="first")
    gdf["geometry"] = gdf.geometry.intersection(boundary)
    gdf = gdf[gdf.geometry.area / 27878400 >= MIN_SQMI].copy()
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_FT, preserve_topology=True)
    return gdf


def write(gdf, name):
    out = cfg.DOCS / name
    if out.exists():
        out.unlink()
    gdf = gdf.sort_values("sort").to_crs(4326)[["id", "name", "geometry"]]
    gdf.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"Wrote {len(gdf)} areas -> {out.name} ({out.stat().st_size/1e3:.0f} KB): "
          + ", ".join(gdf["name"]))


def main():
    boundary = cfg.boundary(cfg.CRS_FT).geometry.union_all()

    parts = []
    hc = fetch_layer(HC_PCT, out_fields="PCT_NO,COMMISSION", out_sr=cfg.CRS_FT)
    hc["id"] = "harris-" + hc["PCT_NO"].astype(int).astype(str)
    hc["name"] = ("Harris County Precinct " + hc["PCT_NO"].astype(int).astype(str)
                  + " (" + hc["COMMISSION"].str.split().str[-1] + ")")
    hc["sort"] = "1-" + hc["PCT_NO"].astype(int).astype(str)
    parts.append(hc)
    pct = pd.concat([p[["id", "name", "sort", "geometry"]].to_crs(cfg.CRS_FT) for p in parts],
                    ignore_index=True)
    write(clip(gpd.GeoDataFrame(pct, crs=cfg.CRS_FT), boundary), "areas_precinct.geojson")

    tz = fetch_layer(f"{COH}/5", out_fields="OBJECTID,NAME", out_sr=cfg.CRS_FT)
    nm = tz["NAME"].astype(str).str.title().str.replace("/Fb ", "/Fort Bend ", regex=False)
    missing = sorted(set(nm) - set(TIRZ_NUMBER))
    if missing:
        raise SystemExit(f"TIRZ names with no known number (update TIRZ_NUMBER): {missing}")
    num = nm.map(TIRZ_NUMBER)
    tz["id"] = "tirz-" + num.astype(str)
    tz["name"] = "TIRZ " + num.astype(str) + " · " + nm
    tz["sort"] = num
    write(clip(tz, boundary), "areas_tirz.geojson")


if __name__ == "__main__":
    main()
