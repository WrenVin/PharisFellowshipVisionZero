"""Export extra area boundaries for the dashboard's Area filter.

Council districts and Super Neighborhoods are tagged onto every crash and
segment by export_webmap_data.py. The layers here are filtered in the browser
instead (point-in-polygon on load of a selection), so adding a new way to cut
the city only needs a GeoJSON in docs/ and an entry in the page's AREA_TYPES.

Writes (clipped to the full-purpose city boundary, simplified ~50 ft, lon/lat):

    docs/areas_precinct.geojson   county commissioner precincts (Harris, Fort Bend,
                                  Montgomery: Houston spans all three counties)
    docs/areas_tirz.geojson       Tax Increment Reinvestment Zones (27)

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
    fb = fetch_layer(f"{COH}/13", out_fields="PRECINCT", out_sr=cfg.CRS_FT)
    fb["id"] = "fortbend-" + fb["PRECINCT"].astype(str)
    fb["name"] = "Fort Bend County Precinct " + fb["PRECINCT"].astype(str)
    fb["sort"] = "2-" + fb["PRECINCT"].astype(str)
    parts.append(fb)
    mc = fetch_layer(f"{COH}/12", out_fields="PRECINCT", out_sr=cfg.CRS_FT)
    mc = mc[mc["PRECINCT"].astype(str).isin(["1", "2", "3", "4"])]   # '100' is not a commissioner precinct
    mc["id"] = "montgomery-" + mc["PRECINCT"].astype(str)
    mc["name"] = "Montgomery County Precinct " + mc["PRECINCT"].astype(str)
    mc["sort"] = "3-" + mc["PRECINCT"].astype(str)
    parts.append(mc)
    pct = pd.concat([p[["id", "name", "sort", "geometry"]].to_crs(cfg.CRS_FT) for p in parts],
                    ignore_index=True)
    write(clip(gpd.GeoDataFrame(pct, crs=cfg.CRS_FT), boundary), "areas_precinct.geojson")

    tz = fetch_layer(f"{COH}/5", out_fields="OBJECTID,NAME", out_sr=cfg.CRS_FT)
    tz["id"] = "tirz-" + tz["OBJECTID"].astype(int).astype(str)
    tz["name"] = tz["NAME"].astype(str).str.title()
    tz["name"] = tz["name"].str.replace("/Fb ", "/Fort Bend ", regex=False)
    tz["sort"] = tz["name"]
    write(clip(tz, boundary), "areas_tirz.geojson")


if __name__ == "__main__":
    main()
