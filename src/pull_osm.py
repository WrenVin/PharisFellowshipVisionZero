"""Pull the OSM street network for District C, clipped to the official boundary.

Scope: city-controlled surface streets. Excludes motorways (freeways) and
motorway links (ramps); excludes service roads (alleys, driveways, parking
aisles) via network_type="drive".

Output:
  data/raw/district_c_drive.graphml   - full simplified graph (for topology work)
  data/raw/district_c_edges_raw.gpkg  - edges with OSM tags (for inspection)
"""

import re
from pathlib import Path

import geopandas as gpd
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# Tags we want preserved on every way (tier 1 + tier 2 features)
ox.settings.useful_tags_way = list(
    set(ox.settings.useful_tags_way)
    | {
        "lanes",
        "lanes:forward",
        "lanes:backward",
        "maxspeed",
        "width",
        "oneway",
        "sidewalk",
        "sidewalk:left",
        "sidewalk:right",
        "sidewalk:both",
        "cycleway",
        "cycleway:left",
        "cycleway:right",
        "cycleway:both",
        "parking:lane:left",
        "parking:lane:right",
        "parking:lane:both",
        "parking:left",
        "parking:right",
        "parking:both",
        "lit",
        "surface",
        "shoulder",
        "dual_carriageway",
    }
)

boundary = gpd.read_file(RAW / "district_c_boundary.geojson").to_crs(4326)
polygon = boundary.geometry.iloc[0]

print("Pulling drivable network from Overpass...")
G = ox.graph_from_polygon(
    polygon,
    network_type="drive",  # excludes service roads (alleys/driveways)
    simplify=True,
    retain_all=True,  # keep disconnected bits; we filter consciously later
    truncate_by_edge=True,  # keep edges that cross the boundary
)
print(f"Raw graph: {len(G.nodes):,} nodes, {len(G.edges):,} edges")

# Drop freeways, ramps, and frontage/feeder roads (TxDOT right-of-way,
# part of the highway facility -- not city-redesignable; decision 2026-06-12)
EXCLUDE = {"motorway", "motorway_link"}
FRONTAGE = re.compile(r"frontage|feeder|service road", re.I)


def _classes(hwy):
    return set(hwy) if isinstance(hwy, list) else {hwy}


def _names(nm):
    vals = nm if isinstance(nm, list) else [nm]
    return [v for v in vals if isinstance(v, str)]


drop = [
    (u, v, k)
    for u, v, k, d in G.edges(keys=True, data=True)
    if _classes(d.get("highway")) & EXCLUDE
    or any(FRONTAGE.search(n) for n in _names(d.get("name")))
]
G.remove_edges_from(drop)
G.remove_nodes_from([n for n in G.nodes if G.degree(n) == 0])
print(f"Removed {len(drop):,} motorway/ramp/frontage edges")
print(f"Filtered graph: {len(G.nodes):,} nodes, {len(G.edges):,} edges")

ox.save_graphml(G, RAW / "district_c_drive.graphml")

edges = ox.graph_to_gdfs(G, nodes=False)
# GeoPackage can't store lists (OSMnx merges tag values when simplifying)
edges_out = edges.copy()
for col in edges_out.columns:
    if col == "geometry":
        continue
    edges_out[col] = edges_out[col].apply(
        lambda v: "|".join(map(str, v)) if isinstance(v, list) else v
    )
edges_out.to_file(RAW / "district_c_edges_raw.gpkg", layer="edges", driver="GPKG")

print("\nHighway class breakdown (edge count):")
hw = edges["highway"].apply(lambda v: "|".join(v) if isinstance(v, list) else v)
print(hw.value_counts().to_string())
print(f"\nSaved graphml + gpkg to {RAW}")
