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
from shapely.geometry import Point

import config as cfg

SEG_ID0 = 500000
MIN_FT = 30
FILTER = '["highway"~"^(motorway|motorway_link)$"]'
CROSS_SKIP = re.compile(r"freeway|frontage|feeder|service road|tollway|expressway|turnpike", re.I)


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
    ox.settings.useful_tags_node = ["ref", "highway"]   # exit numbers live on motorway_junction nodes
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
            refs_ = as_list(d.get("ref"))
            if MANAGED.search(";".join(refs_) + " " + " ".join(as_list(d.get("name")))):
                continue              # express/managed lanes are not a second freeway
            lab = route_label(refs_)
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

    # exits: OSM motorway_junction nodes with an exit number (about half are numbered)
    exit_ref = {n: str(d["ref"]) for n, d in G.nodes(data=True)
                if d.get("highway") == "motorway_junction" and d.get("ref")}
    xn = [(n, d) for n, d in G.nodes(data=True) if n in exit_ref]
    exits = gpd.GeoDataFrame({"ref": [exit_ref[n] for n, _ in xn]},
                             geometry=gpd.points_from_xy([d["x"] for _, d in xn], [d["y"] for _, d in xn]),
                             crs=4326).to_crs(2278)
    print(f"Numbered exits: {len(exits):,}")

    # cross streets: named streets of the analysis network (no freeways or frontage roads)
    st = gpd.read_file(cfg.raw("edges_raw.gpkg"), layer="edges", columns=["name"]).to_crs(2278)
    st["name"] = st["name"].astype(str).str.split("|").str[0]
    st = st[~st["name"].isin(["None", "nan", ""]) & ~st["name"].str.contains(CROSS_SKIP, na=True)].copy()

    is_main = e["hw"].eq("motorway")
    base_name, dirs, hwys = [], [], []
    for _, r in e.iterrows():
        dirs.append(direction(r.geometry, r["refs"]))
        hwys.append(route_numbers(r["refs"]))
        nm = first(r.get("name")) if isinstance(first(r.get("name")), str) else None
        base_name.append(" ".join(x for x in (route_label(r["refs"]), nm, dirs[-1]) if x) or f"Freeway {dirs[-1]}")
    e["direction"], e["hwy"] = dirs, hwys

    # ---- main lanes: one direction of one route; labeled by the streets crossing the section
    main = e[is_main]
    jx = gpd.sjoin(st[["name", "geometry"]], main[["geometry"]], predicate="intersects", how="inner")
    crossing = {}
    for idx, grp in jx.groupby("index_right"):
        line = main.geometry.loc[idx]
        hits = []
        own = base_name[idx].lower()
        for nm_, g in zip(grp["name"], grp.geometry):
            if nm_.lower() in own or "sam houston" in nm_.lower():   # the freeway's own frontage, not a cross street
                continue
            ip = line.intersection(g)
            if not ip.is_empty:
                hits.append((line.project(ip.centroid), nm_))
        order = []
        for _, nm_ in sorted(hits):
            if nm_ not in order:
                order.append(nm_)
        crossing[idx] = order

    def main_label(i, r):
        xs = crossing.get(i, [])
        where = (f"{xs[0]} to {xs[-1]}" if len(xs) > 1 else f"at {xs[0]}") if xs else ""
        ex = [exit_ref[n] for n in (r["u"], r["v"]) if n in exit_ref]
        exs = (f"exit {ex[0]}" if len(ex) == 1 else f"exits {ex[0]} to {ex[1]}") if ex else ""
        tail = ", ".join(x for x in (where, exs) if x)
        return base_name[i] + (", " + tail if tail else "")

    # ---- ramps: a connector between two freeways belongs to that interchange; an ordinary
    # on/off ramp to its exit (number when known, else the nearest cross street)
    def end_point(geom, at_start):
        cs = geom.coords
        return Point(cs[0] if at_start else cs[-1])

    grp_name, labels = [None] * len(e), [None] * len(e)
    for i in range(len(e)):              # main lanes: grouped by route and direction, labeled by place
        if is_main.iloc[i]:
            grp_name[i], labels[i] = base_name[i], main_label(i, e.iloc[i])
    # chain ramp pieces that meet anywhere except on a freeway's main lanes: one chain is one
    # connector or one ramp, even when OSM splits it where a ramp forks
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    ramp_rows = [i for i in range(len(e)) if not is_main[i]]
    for i in ramp_rows:
        r = e.iloc[i]
        a_, b_ = ("n", r["u"]), ("n", r["v"])
        find(("r", i))
        for node in (a_, b_):
            if node[1] not in node_route:            # a ramp-to-ramp node joins the pieces
                parent[find(("r", i))] = find(node)
    chains = {}
    for i in ramp_rows:
        chains.setdefault(find(("r", i)), []).append(i)

    def nums(lab):
        return set(re.findall(r"\d+", lab))
    pair_rows = {}
    for rows in chains.values():
        routes = set()
        for i in rows:
            routes |= node_route.get(e.iloc[i]["u"], set()) | node_route.get(e.iloc[i]["v"], set())
        distinct = []                                 # routes sharing a number are one freeway
        for lab in sorted(routes, key=lambda x: (-len(nums(x)), x)):
            if not any(nums(lab) & nums(d) for d in distinct):
                distinct.append(lab)
        chain_nums = " ".join(sorted({n for lab in distinct for n in nums(lab)}))
        for i in rows:                                # a ramp carries the route numbers it connects
            e.at[e.index[i], "hwy"] = chain_nums
        if len(distinct) >= 2:
            pair_rows.setdefault(tuple(sorted(distinct[:2])), []).extend(rows)
            continue
        for i in rows:
            r = e.iloc[i]
            if not distinct:
                continue                              # named from a neighbor below
            route = distinct[0]
            exit_side = r["u"] in node_route          # leaves the freeway at its start: an exit ramp
            ref = exit_ref.get(r["u"]) or exit_ref.get(r["v"])
            if not ref:
                near = exits.distance(end_point(r.geometry, True)).sort_values()
                ref = exits.loc[near.index[0], "ref"] if len(near) and near.iloc[0] < 2500 else None
            street = None
            far = end_point(r.geometry, not exit_side)   # the end away from the freeway
            d = st.distance(far)
            if len(d) and d.min() < 1000:
                street = st.loc[d.idxmin(), "name"]
            if ref:
                grp_name[i] = f"{route} exit {ref} ramps" + (f" ({street})" if street else "")
            elif street:
                grp_name[i] = f"{route} ramps at {street}"
            else:
                grp_name[i] = f"{route} ramps"
            labels[i] = (f"{route} exit ramp" if exit_side else f"{route} entrance ramp") + (f", {street}" if street else "")
    # interchanges: connector chains for the same pair of freeways, clustered by distance
    # (two freeways can meet twice, e.g. I-610 and I-69/US 59)
    for (a, b), rows in pair_rows.items():
        cents = e.geometry.iloc[rows].centroid
        cents.index = rows
        cluster = {rows[0]: 0}
        k = 0
        for i in rows[1:]:
            near = [cluster[j] for j in cluster if cents[i].distance(cents[j]) < 8000]
            if near:
                cluster[i] = near[0]
            else:
                k += 1
                cluster[i] = k
        allc = Point(cents.x.mean(), cents.y.mean())
        for i in rows:
            name = f"{a} at {b} interchange"
            if k:
                c = [j for j in rows if cluster[j] == cluster[i]]
                cx, cy = cents[c].x.mean() - allc.x, cents[c].y.mean() - allc.y
                name += " (" + (("north" if cy > 0 else "south") if abs(cy) >= abs(cx) else ("east" if cx > 0 else "west")) + ")"
            grp_name[i], labels[i] = name, name
    # ramp pieces that touch no freeway (one ramp splitting into two) join the nearest named ramp
    named = [i for i in range(len(e)) if grp_name[i]]
    ng = gpd.GeoDataFrame({"g": [grp_name[i] for i in named], "l": [labels[i] for i in named]},
                          geometry=e.geometry.iloc[named].values, crs=e.crs)
    for i in range(len(e)):
        if grp_name[i] is None:
            d = ng.distance(e.geometry.iloc[i])
            j = d.idxmin()
            grp_name[i], labels[i] = ng.loc[j, "g"], ng.loc[j, "l"]

    e["name"], e["label"] = grp_name, labels
    e["kind"] = is_main.map({True: "main", False: "ramp"})
    e["road_class"] = [("Toll road" if t else "Freeway") if m_ else "Ramp" for m_, t in zip(is_main, e["toll"])]
    e["seg_id"] = [f"H-{SEG_ID0 + i}" for i in range(len(e))]
    out = e[["seg_id", "name", "label", "kind", "road_class", "toll", "hwy", "direction", "length_ft", "geometry"]]
    dst = cfg.processed("freeway_sections.gpkg")
    out.to_file(dst, layer="sections", driver="GPKG")
    m = out["kind"].eq("main")
    print(f"Wrote {int(m.sum()):,} main-lane sections ({out.loc[m, 'length_ft'].sum()/5280:,.0f} mi, "
          f"median {out.loc[m, 'length_ft'].median()/5280:.2f} mi) and {int((~m).sum()):,} ramps/connectors -> {dst.name}")
    ix = out.loc[~m, "name"]
    print(f"Interchanges: {ix[ix.str.endswith(('interchange', ')'))].str.contains('interchange').sum() and ix[ix.str.contains('interchange')].nunique()}; "
          f"ramp groups: {ix[~ix.str.contains('interchange')].nunique()}")
    print("Sample main labels:", out.loc[m, "label"].sample(6, random_state=2).tolist())
    print("Sample ramp groups:", out.loc[~m, "name"].drop_duplicates().sample(6, random_state=2).tolist())



if __name__ == "__main__":
    main()
