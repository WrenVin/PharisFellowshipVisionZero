"""Frontage roads for the dashboard's street map (dashboard only; not the model network).

pull_osm.py drops frontage/feeder roads from the analysis network (decision
2026-06-12), so the research model never sees them. The dashboard now shows them
as ordinary streets (decision 2026-10-31): crashes police code as frontage road
(Rpt_Road_Part_ID 2) move from the Freeways toggle into the default view.

This pulls the same roads pull_osm.py removes (drivable ways named frontage,
feeder or service road, plus ways tagged frontage_road=yes) and splits them into
blocks wherever a street in the analysis network meets them, so a frontage block
runs from one cross street to the next, like any other segment.

Writes data/processed/houston_frontage_segments.gpkg with
    seg_id (H-300000 and up), name, oneway, length_ft, geometry (EPSG:2278).

    .venv/bin/python src/build_frontage.py
"""

import geopandas as gpd
import osmnx as ox
import pandas as pd

import config as cfg

SEG_ID0 = 300000          # frontage ids sit far above the analysis network's (max ~110k)
MIN_FT = 30               # drop slivers
FILTERS = [
    '["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential)(_link)?$"]'
    '["name"~"[Ff]rontage|[Ff]eeder|[Ss]ervice [Rr]oad"]',
    '["highway"~"^(trunk|primary|secondary|tertiary|unclassified|residential)(_link)?$"]["frontage_road"="yes"]',
]


def first(v):
    return v[0] if isinstance(v, list) else v


def main():
    boundary = cfg.boundary(2278).geometry.union_all()
    poly = cfg.boundary(4326).geometry.union_all().buffer(0.005)
    print("Pulling frontage roads from Overpass...")
    G = ox.graph_from_polygon(poly, custom_filter=FILTERS, simplify=False, retain_all=True, truncate_by_edge=True)
    print(f"Frontage graph: {len(G.nodes):,} nodes, {len(G.edges):,} edges (unsimplified)")

    # nodes shared with the analysis network are where a cross street meets the frontage road
    net = gpd.read_file(cfg.raw("edges_raw.gpkg"), layer="edges", columns=["u", "v"], ignore_geometry=True)
    cross = set(pd.unique(net[["u", "v"]].astype("int64").values.ravel()))
    n_x = 0
    for n in G.nodes:
        if n in cross:
            G.nodes[n]["xing"] = True
            n_x += 1
    print(f"Cross-street nodes on frontage roads: {n_x:,}")
    G = ox.simplify_graph(G, node_attrs_include=["xing"])
    G = ox.convert.to_undirected(G)          # one feature per piece of road (two-way pieces were doubled)
    e = ox.graph_to_gdfs(G, nodes=False).reset_index(drop=True).to_crs(2278)

    e["name"] = e["name"].apply(first)
    e["oneway"] = e["oneway"].apply(first).fillna(False).astype(bool)
    e["geometry"] = e.geometry.intersection(boundary)
    e = e[~e.geometry.is_empty & e.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    e = e.explode(index_parts=False)
    e["length_ft"] = e.geometry.length
    e = e[e["length_ft"] >= MIN_FT].copy().reset_index(drop=True)
    # unnamed pieces take the name of the nearest named frontage block (usually the same
    # road across a gap in the tagging); still-unnamed ones stay null, like other unnamed streets
    named, unnamed = e[e["name"].notna()], e[e["name"].isna()]
    if len(unnamed) and len(named):
        j = gpd.sjoin_nearest(unnamed[["geometry"]], named[["name", "geometry"]], how="left", max_distance=500)
        j = j[~j.index.duplicated(keep="first")]
        e.loc[unnamed.index, "name"] = j["name"].reindex(unnamed.index).values
    print(f"Unnamed frontage blocks: {len(unnamed):,}; still unnamed after borrowing a neighbor's name: {int(e['name'].isna().sum()):,}")
    e["seg_id"] = [f"H-{SEG_ID0 + i}" for i in range(len(e))]
    out = e[["seg_id", "name", "oneway", "length_ft", "geometry"]]
    dst = cfg.processed("frontage_segments.gpkg")
    out.to_file(dst, layer="segments", driver="GPKG")
    print(f"Wrote {len(out):,} frontage blocks, {out['length_ft'].sum()/5280:,.0f} mi -> {dst.name}")
    print("Most common names:", out["name"].value_counts().head(10).to_dict())


if __name__ == "__main__":
    main()
