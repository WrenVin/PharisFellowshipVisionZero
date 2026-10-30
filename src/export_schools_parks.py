"""Export schools and parks for the dashboard's Schools / Parks overlays.

Schools: the City GIS copy of TEA's public-school directory (district and
charter campuses, 2022-23), active campuses inside the official city limits.
Parks: City of Houston parks at least 95% inside the official city limits (the
Area filter's rule), excluding esplanade "CSTs/Spaceway" slivers; clipped to
the dashboard's full-purpose boundary and simplified ~20 ft.

Writes docs/schools.geojson ({name, grades, district, charter}) and
docs/parks.geojson ({name, acres}), loaded only when a visitor turns an overlay on.

    .venv/bin/python src/export_schools_parks.py
"""

import config as cfg
from arcgis_fetch import fetch_layer

COH = "https://mycity2.houstontx.gov/gisweb02/rest/services/HoustonMap"


def main():
    boundary = cfg.boundary(cfg.CRS_FT).geometry.union_all()
    limits = fetch_layer(f"{COH}/Administrative_Boundary/MapServer/0",
                         out_sr=cfg.CRS_FT).geometry.union_all()

    sc = fetch_layer(f"{COH}/Neighborhood/MapServer/0",
                     out_fields="School_Name,Grade_Range,District_Name,District_Type,School_Status",
                     out_sr=cfg.CRS_FT)
    sc = sc[(sc["School_Status"].astype(str).str.strip() == "Active")
            & sc.geometry.within(limits) & sc.geometry.within(boundary)].copy()
    sc["name"] = sc["School_Name"].astype(str).str.title()
    sc["grades"] = sc["Grade_Range"].astype(str).str.strip()
    sc["district"] = sc["District_Name"].astype(str).str.title()
    sc["charter"] = sc["District_Type"].astype(str).str.upper().eq("CHARTER").astype(int)
    out = cfg.DOCS / "schools.geojson"
    sc.sort_values("name").to_crs(4326)[["name", "grades", "district", "charter", "geometry"]] \
        .to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"Wrote {len(sc)} schools ({int(sc.charter.sum())} charter) -> {out.name} "
          f"({out.stat().st_size/1e3:.0f} KB)")

    pk = fetch_layer(f"{COH}/Neighborhood/MapServer/14", out_fields="Name,Park_Acres,Park_Type",
                     out_sr=cfg.CRS_FT)
    pk = pk[~pk["Park_Type"].astype(str).str.contains("Spaceway", case=False)].copy()
    share = pk.geometry.intersection(limits).area / pk.geometry.area
    left_out = pk.loc[share < 0.95, "Name"].astype(str).str.title().tolist()
    pk = pk[share >= 0.95].copy()
    pk["geometry"] = pk.geometry.intersection(boundary).simplify(20, preserve_topology=True)
    pk = pk[~pk.geometry.is_empty]
    pk["name"] = pk["Name"].astype(str).str.title()
    pk["acres"] = pk["Park_Acres"].astype(float).round(1)
    out = cfg.DOCS / "parks.geojson"
    pk.sort_values("name").to_crs(4326)[["name", "acres", "geometry"]] \
        .to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"Wrote {len(pk)} parks -> {out.name} ({out.stat().st_size/1e3:.0f} KB); "
          f"left out {len(left_out)} that cross the city line: {', '.join(left_out[:10])}")


if __name__ == "__main__":
    main()
