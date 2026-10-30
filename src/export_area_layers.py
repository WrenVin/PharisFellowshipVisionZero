"""Export extra area boundaries for the dashboard's Area filter.

Council districts and Super Neighborhoods are tagged onto every crash and
segment by export_webmap_data.py. The layers here are filtered in the browser
instead (point-in-polygon on a selection), so adding a new way to cut the city
only needs a GeoJSON in docs/ and an entry in the page's POLY_TYPES.

Only areas that lie within the city are offered: an area is kept when at least
INSIDE_MIN of it falls inside the official City of Houston limits (full- and
limited-purpose). Areas that straddle the city line (all school districts,
county precincts, many ZIP codes and tracts) are left out entirely rather than
shown as a misleading partial piece. Kept areas are then clipped to the
dashboard's full-purpose boundary for drawing; the few limited-purpose slivers
dropped by that clip carry no crash data (CRIS doesn't code them to Houston).

Writes docs/areas_<kind>.geojson, each feature {id, name}, simplified ~50 ft:
    tirz   the City's 27 active Tax Increment Reinvestment Zones, by TIRZ number
    mgmt   management districts with a confirmed name
    hpd    Houston Police patrol divisions
    zip    ZIP codes
    tract  2020 Census tracts
and prints what was kept and left out per kind.

    .venv/bin/python src/export_area_layers.py
"""

import config as cfg
from arcgis_fetch import fetch_layer

COH = "https://mycity2.houstontx.gov/gisweb02/rest/services/HoustonMap"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer"
INSIDE_MIN = 0.95
SIMPLIFY_FT = 50
SQFT_PER_SQMI = 27878400

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

# Management districts: the COH layer mixes ~75 special districts (MUDs, PIDs,
# proposed districts). Keep only management districts whose name is confirmed;
# HCID #9 is the Hobby Area District per the City's board listing. Numbered-only
# districts (HCID #8, #10-A, #12, #16, #24, Harris County PID #2) are left out
# until their names are confirmed. The inside-the-city test still applies.
MGMT_NAME = {
    "Houston Downtown": "Downtown", "Midtown MD": "Midtown",
    "East Downtown MD": "East Downtown", "East End MD": "East End",
    "Greater Northside MD": "Greater Northside", "Greater Southeast MD": "Greater Southeast",
    "Montrose Management District": "Montrose", "Westchase MD": "Westchase",
    "Sharpstown MD": "Sharpstown", "HCID #5 (Brays Oaks)": "Brays Oaks",
    "HCID #3 (Upper Kirby)": "Upper Kirby", "UPTOWN MD HCID #1": "Uptown",
    "Memorial City MD": "Memorial City", "SAINT GEORGE PLACE MD": "St. George Place",
    "Five Corners HCID #10B": "Five Corners", "Spring Branch MD": "Spring Branch",
    "HCID #4 (Energy Corridor)": "Energy Corridor", "HCID #9": "Hobby Area",
    "Greater Greenspoint MD": "Greater Greenspoint", "Near Northwest MD": "Near Northwest",
    "International MD": "International",
}
COUNTY = {"201": "Harris", "157": "Fort Bend", "339": "Montgomery"}


def keep_inside(gdf, limits, boundary, kind):
    """Keep areas >= INSIDE_MIN inside the official limits; clip to the map boundary."""
    gdf = gdf.to_crs(cfg.CRS_FT)
    gdf = gdf.dissolve(by="id", as_index=False, aggfunc="first")
    share = gdf.geometry.intersection(limits).area / gdf.geometry.area
    dropped = gdf.loc[(share < INSIDE_MIN) & (share > 0.01)].assign(s=share)
    gdf = gdf[share >= INSIDE_MIN].copy()
    gdf["geometry"] = gdf.geometry.intersection(boundary)
    gdf = gdf[gdf.geometry.area / SQFT_PER_SQMI >= 0.01].copy()
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_FT, preserve_topology=True)
    names = [f"{n} {s:.0%}" for n, s in zip(dropped["name"], dropped["s"])]
    print(f"{kind}: kept {len(gdf)}; left out {len(names)} that cross the city line"
          + (f" ({', '.join(names[:12])}{', ...' if len(names) > 12 else ''})" if names else ""))
    return gdf


def write(gdf, kind):
    out = cfg.DOCS / f"areas_{kind}.geojson"
    if out.exists():
        out.unlink()
    gdf = gdf.sort_values("sort").to_crs(4326)[["id", "name", "geometry"]]
    gdf.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"  -> {out.name} ({out.stat().st_size/1e3:.0f} KB)")


def main():
    boundary = cfg.boundary(cfg.CRS_FT).geometry.union_all()
    limits = fetch_layer(f"{COH}/Administrative_Boundary/MapServer/0",
                         out_sr=cfg.CRS_FT).geometry.union_all()
    bbox = cfg.bbox_4326()

    tz = fetch_layer(f"{COH}/Administrative_Boundary/MapServer/5", out_fields="NAME", out_sr=cfg.CRS_FT)
    nm = tz["NAME"].astype(str).str.title().str.replace("/Fb ", "/Fort Bend ", regex=False)
    missing = sorted(set(nm) - set(TIRZ_NUMBER))
    if missing:
        raise SystemExit(f"TIRZ names with no known number (update TIRZ_NUMBER): {missing}")
    num = nm.map(TIRZ_NUMBER)
    tz["id"], tz["name"], tz["sort"] = "tirz-" + num.astype(str), "TIRZ " + num.astype(str) + " · " + nm, num
    write(keep_inside(tz, limits, boundary, "tirz"), "tirz")

    md = fetch_layer(f"{COH}/Administrative_Boundary/MapServer/4", out_fields="NAME", out_sr=cfg.CRS_FT)
    md = md[md["NAME"].isin(MGMT_NAME)].copy()
    md["name"] = md["NAME"].map(MGMT_NAME)
    md["id"] = "md-" + md["name"].str.lower().str.replace(r"[^a-z0-9]+", "-", regex=True)
    md["sort"] = md["name"]
    write(keep_inside(md, limits, boundary, "mgmt"), "mgmt")

    hpd = fetch_layer(f"{COH}/Public_Safety/MapServer/3", out_fields="Division", out_sr=cfg.CRS_FT)
    hpd["name"] = hpd["Division"].astype(str).str.strip() + " Division"
    hpd["id"] = "hpd-" + hpd["Division"].astype(str).str.lower().str.replace(r"[^a-z0-9]+", "-", regex=True)
    hpd["sort"] = hpd["name"]
    write(keep_inside(hpd, limits, boundary, "hpd"), "hpd")

    zp = fetch_layer(f"{COH}/Administrative_Boundary/MapServer/7", out_fields="Zip_Code",
                     out_sr=cfg.CRS_FT, bbox_4326=bbox)
    zp["name"] = zp["Zip_Code"].astype(str).str.strip()
    zp["id"], zp["sort"] = "zip-" + zp["name"], zp["name"]
    write(keep_inside(zp, limits, boundary, "zip"), "zip")

    tr = fetch_layer(f"{TIGER}/8", out_fields="GEOID,COUNTY,BASENAME", out_sr=cfg.CRS_FT, bbox_4326=bbox)
    tr = tr[tr["COUNTY"].astype(str).isin(COUNTY)].copy()
    tr["name"] = "Tract " + tr["BASENAME"].astype(str) + " (" + tr["COUNTY"].astype(str).map(COUNTY) + ")"
    tr["id"], tr["sort"] = "tract-" + tr["GEOID"].astype(str), tr["GEOID"].astype(str)
    write(keep_inside(tr, limits, boundary, "tract"), "tract")


if __name__ == "__main__":
    main()
