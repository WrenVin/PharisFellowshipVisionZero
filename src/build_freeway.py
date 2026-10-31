"""Freeway sections for the dashboard's Freeways toggle (dashboard only; see FREEWAY_PLAN.md).

Pulls freeway and toll-road main lanes (OSM highway=motorway) and ramps and connectors
(motorway_link) inside the city, then splits the main lanes into sections the way
freeway safety analysis does (Highway Safety Manual Part C): a section runs between
consecutive ramp junctions, where an exit leaves or an entrance joins, and also breaks
where the route changes. OSM draws each direction of a divided freeway as its own
one-way line, so every section is one direction of travel. Each ramp or connector is
its own feature.

Writes data/processed/houston_freeway_sections.gpkg with
    seg_id (H-500000 and up), name (e.g. "I-10 Katy Freeway eastbound"), kind
    ("main" or "ramp"), road_class ("Freeway", "Toll road" or "Ramp"), toll,
    hwy (route numbers, e.g. "10" or "69 59"), direction, length_ft, geometry (EPSG:2278).

    .venv/bin/python src/build_freeway.py
"""

import math
import re

import geopandas as gpd
import osmnx as ox

import config as cfg

SEG_ID0 = 500000
MIN_FT = 30
FILTER = '["highway"~"^(motorway|motorway_link)$"]'


def first(v):
    return v[0] if isinstance(v, list) else v


def as_list(v):
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return [v] if isinstance(v, str) else []


def route_label(refs):
    """'I 69;US 59' -> 'I-69/US 59'."""
    parts = []
    for r in refs:
        for p in re.split(r"[;,]", r):
            p = p.strip()
            if p:
                p = re.sub(r"^I\s+", "I-", p)
                if p not in parts:
                    parts.append(p)
    return "/".join(parts)


def route_numbers(refs):
    return " ".join(sorted({n.lstrip("0") for r in refs for n in re.findall(r"\d+", r)}))


LOOPS = {"610", "8"}       # loops are labeled by compass heading, not by route parity
MANAGED = re.compile(r"HOV|HOT|managed|express|\bToll\b(?!way)", re.I)
TOLLNAME = re.compile(r"toll|SHT\b|westpark|hardy|fort bend parkway|grand parkway", re.I)


def direction(geom, refs):
    """Signed direction: odd Interstate/US route numbers run north/south, even ones east/west;
    loops, state highways and unnumbered roads use the compass heading."""
    cs = list(geom.coords) if geom.geom_type == "LineString" else list(geom.geoms[0].coords) + list(geom.geoms[-1].coords)
    (x0, y0), (x1, y1) = cs[0], cs[-1]
    dx, dy = x1 - x0, y1 - y0
    n = [m.group(2) for r in refs for p in re.split(r"[;,]", r) for m in [re.match(r"\s*(I|US)\s*-?\s*(\d+)", p)] if m]
    n = [x for x in n if x not in LOOPS]
    ns = int(n[0]) % 2 == 1 if n else abs(dy) > abs(dx)
    if ns:
        return "northbound" if dy > 0 else "southbound"
    return "eastbound" if dx > 0 else "westbound"


def main():
    boundary = cfg.boundary(2278).geometry.union_all()
    poly = cfg.boundary(4326).geometry.union_all().buffer(0.01)
    print("Pulling freeways and ramps from Overpass...")
    G = ox.graph_from_polygon(poly, custom_filter=FILTER, simplify=False, retain_all=True, truncate_by_edge=True)
    print(f"Freeway graph: {len(G.nodes):,} nodes, {len(G.edges):,} edges (unsimplified)")

    # a main-lane node where a ramp leaves or joins ends a section
    kinds = {}
    for u, v, d in G.edges(data=True):
        hw = first(d.get("highway"))
        for n in (u, v):
            kinds.setdefault(n, set()).add(hw)
    n_split = 0
    for n, ks in kinds.items():
        if "motorway" in ks and "motorway_link" in ks:
            G.nodes[n]["junction_split"] = True
            n_split += 1
    print(f"Ramp junctions on main lanes: {n_split:,}")
    for u, v, k, d in G.edges(keys=True, data=True):   # normalise list tags so simplification can compare them
        d["highway"] = first(d.get("highway"))
        d["ref"] = ";".join(as_list(d.get("ref")))
        d["toll"] = "yes" if "yes" in as_list(d.get("toll")) else "no"
    G = ox.simplify_graph(G, node_attrs_include=["junction_split"], edge_attrs_differ=["highway", "ref", "toll"])

    # main-lane route names at each node, so a ramp can be labeled by the freeway it serves
    node_route = {}
    for u, v, d in G.edges(data=True):
        if first(d.get("highway")) == "motorway":
            lab = route_label(as_list(d.get("ref")))
            for n in (u, v):
                if lab:
                    node_route.setdefault(n, set()).add(lab)

    e = ox.graph_to_gdfs(G, nodes=False).reset_index().to_crs(2278)
    e["hw"] = e["highway"].apply(first)
    e["refs"] = e["ref"].apply(as_list)
    e["toll"] = e["toll"].apply(lambda v: "yes" in as_list(v))
    e["oneway"] = e["oneway"].apply(first).fillna(True).astype(bool)
    e = e[e["oneway"] | (e["u"] < e["v"])].copy()     # a two-way ramp appears once
    e["geometry"] = e.geometry.intersection(boundary)
    e = e[~e.geometry.is_empty & e.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    e = e.explode(index_parts=False)      # pieces split by the city line become separate sections
    e["length_ft"] = e.geometry.length
    e = e[e["length_ft"] >= MIN_FT].copy().reset_index(drop=True)

    # managed lanes (HOV/HOT, the I-10 express toll lanes) run between the carriageways;
    # leaving them out keeps main-lane crashes from snapping to them
    label_txt = e["refs"].apply(";".join) + " " + e["name"].apply(lambda v: " ".join(as_list(v)))
    managed = e["hw"].eq("motorway") & label_txt.str.contains(MANAGED)
    print(f"Managed-lane pieces left out: {int(managed.sum()):,}")
    e = e[~managed].copy().reset_index(drop=True)
    label_txt = label_txt[~managed].reset_index(drop=True)
    e["toll"] = e["toll"] | label_txt.str.contains(TOLLNAME)

    names, classes, kinds_, hwys, dirs = [], [], [], [], []
    for _, r in e.iterrows():
        nums = route_numbers(r["refs"])
        d = direction(r.geometry, r["refs"])
        nm = first(r.get("name")) if isinstance(first(r.get("name")), str) else None
        if r["hw"] == "motorway":
            lab = route_label(r["refs"])
            names.append(" ".join(x for x in (lab, nm, d) if x) or f"Freeway {d}")
            classes.append("Toll road" if r["toll"] else "Freeway")
            kinds_.append("main")
            hwys.append(nums)
        else:
            ends = sorted((node_route.get(r["u"], set()) | node_route.get(r["v"], set())))
            names.append(("Ramp, " + " to ".join(ends)) if ends else (nm or "Ramp"))
            classes.append("Ramp")
            kinds_.append("ramp")
            hwys.append(" ".join(sorted({n for lab in ends for n in re.findall(r"\d+", lab)})))
        dirs.append(d)
    e["name"], e["road_class"], e["kind"], e["hwy"], e["direction"] = names, classes, kinds_, hwys, dirs
    e["seg_id"] = [f"H-{SEG_ID0 + i}" for i in range(len(e))]
    out = e[["seg_id", "name", "kind", "road_class", "toll", "hwy", "direction", "length_ft", "geometry"]]
    dst = cfg.processed("freeway_sections.gpkg")
    out.to_file(dst, layer="sections", driver="GPKG")
    m = out["kind"].eq("main")
    print(f"Wrote {int(m.sum()):,} main-lane sections ({out.loc[m, 'length_ft'].sum()/5280:,.0f} mi, "
          f"median {out.loc[m, 'length_ft'].median()/5280:.2f} mi) and {int((~m).sum()):,} ramps/connectors -> {dst.name}")
    print("Routes:", out.loc[m, "hwy"].value_counts().head(15).to_dict())


if __name__ == "__main__":
    main()
