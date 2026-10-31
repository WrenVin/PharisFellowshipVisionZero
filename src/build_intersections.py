"""Intersection polygons for the dashboard (dashboard only; not the model network).

Follows the Vision Zero Austin method (ATD Geospatial, "Vision Zero Polygon
Maintenance"): each intersection reaches a set distance down every street that
meets it, each leg is buffered to a width set by the street's type, legs stop
halfway when the next intersection is closer than twice the leg, and where two
polygons still overlap the larger one keeps the shared area. A crash that falls
inside a polygon belongs to the intersection (export_webmap_data.py); every other
crash stays with its block.

Leg lengths are Houston's, from src/check_intersection_distance.py (2026-10-31):
police stop coding crashes as intersection crashes 50 to 75 ft from the crossing,
and arterial crossings are physically larger, so legs are 75 ft on local streets
and collectors and 125 ft on arterials and frontage roads. Widths are Austin's.

An intersection is a node where 3+ streets meet, counting streets in the analysis
network plus frontage roads (build_frontage.py). Freeway ramps are not included, and
neither are *_link slip lanes, so a slip lane joining an arterial does not make a
separate intersection. Nodes joined by a street piece shorter than MERGE_FT (the two
or four nodes OpenStreetMap draws where divided roads cross) are one intersection.

Writes data/processed/houston_intersections.gpkg (EPSG:2278) with
    ix_id (H-700000 and up), name ("Westheimer Road & Fondren Road"),
    streets (leg street names joined with "|"), top_class, leg_ft, geometry.

    .venv/bin/python src/build_intersections.py
"""

import ast
from collections import defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree

import config as cfg

IX_ID0 = 700000
MERGE_FT = 100
MAX_SPAN_FT = 160                 # a merged intersection spans at most this, east-west or north-south
# street type -> (leg length ft, buffer ft, rank for naming/size)
CLASS = {
    "local": (75, 40, 0), "collector": (75, 40, 1),
    "minor_art": (125, 50, 2), "frontage": (125, 50, 2), "major_art": (125, 75, 3),
}
HWY = {"residential": "local", "unclassified": "local", "living_street": "local", "road": "local",
       "tertiary": "collector", "secondary": "minor_art", "primary": "major_art", "trunk": "major_art"}
TOP_LABEL = {"local": "Local streets", "collector": "Collector", "minor_art": "Arterial",
             "frontage": "Frontage road", "major_art": "Major arterial"}


def first(v):
    if isinstance(v, str) and v.startswith("["):
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            pass
    return v[0] if isinstance(v, list) else v


def key(xy):
    return (round(xy[0], 1), round(xy[1], 1))


def load_pieces():
    """Undirected street pieces: geometry (ft), class, name, is_link."""
    e = gpd.read_file(cfg.raw("edges_raw.gpkg"), layer="edges", columns=["u", "v", "highway", "name"]).to_crs(cfg.CRS_FT)
    e["hwy"] = e["highway"].map(first).astype(str)
    e["is_link"] = e["hwy"].str.endswith("_link")
    e["cls"] = e["hwy"].str.replace("_link", "", regex=False).map(HWY)
    e = e[e["cls"].notna()].copy()
    e["name"] = e["name"].map(first)
    a, b = np.minimum(e["u"], e["v"]), np.maximum(e["u"], e["v"])
    e["_k"] = list(zip(a, b, e.geometry.length.round(0)))
    e = e.drop_duplicates("_k")                       # two-way streets are stored once per direction
    e = e.explode(index_parts=False)
    f = gpd.read_file(cfg.processed("frontage_segments.gpkg"), layer="segments").to_crs(cfg.CRS_FT)
    f = f.explode(index_parts=False)
    f["cls"], f["is_link"] = "frontage", False
    p = pd.concat([e[["geometry", "cls", "name", "is_link"]], f[["geometry", "cls", "name", "is_link"]]], ignore_index=True)
    p = gpd.GeoDataFrame(p, crs=cfg.CRS_FT)
    return p[p.geometry.length > 1].reset_index(drop=True)


def main():
    bnd = cfg.boundary(cfg.CRS_FT).geometry.union_all()
    pc = load_pieces()
    geoms, cls, names, link = list(pc.geometry), list(pc["cls"]), list(pc["name"]), list(pc["is_link"])
    ends = []                                   # (start key, end key) per piece
    inc = defaultdict(list)                     # node -> [(piece, at_start)]
    for i, g in enumerate(geoms):
        s, t = key(g.coords[0]), key(g.coords[-1])
        ends.append((s, t))
        if s == t:
            continue                            # loops (cul-de-sacs) are not legs
        inc[s].append((i, True)); inc[t].append((i, False))
    deg = {n: sum(1 for i, _ in v if not link[i]) for n, v in inc.items()}
    ixn = {n for n, d in deg.items() if d >= 3}
    print(f"Street pieces: {len(geoms):,}; intersection nodes (3+ streets, slip lanes not counted): {len(ixn):,}")

    def oriented(i, at_start):
        g = geoms[i]
        return g if at_start else LineString(g.coords[::-1])

    def trace(n, i, at_start, cap):
        """Follow a street away from node n through pass-through nodes; returns
        (line, length, ends at an intersection?, far node)."""
        coords, total, node, cur, st = [], 0.0, n, i, at_start
        seen = {i}
        while True:
            g = oriented(cur, st)
            coords.extend(g.coords if not coords else list(g.coords)[1:])
            total += g.length
            far = ends[cur][1] if st else ends[cur][0]
            if far in ixn or total >= cap:
                return LineString(coords), total, far in ixn, far
            nxt = [(j, s) for j, s in inc.get(far, []) if j not in seen and not link[j]]
            if len(nxt) != 1:                   # dead end, or a node made of slip lanes
                return LineString(coords), total, False, far
            cur, st = nxt[0]
            seen.add(cur)

    # merge intersection nodes joined by a short street piece (divided roads)
    parent = {n: n for n in ixn}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    pts = {n: [n] for n in ixn}                 # member nodes per root, to cap a merged group's size
    short = sorted((geoms[i].length, s, t) for i, (s, t) in enumerate(ends)
                   if s in ixn and t in ixn and s != t and geoms[i].length < MERGE_FT)
    for _, s, t in short:
        a, b = find(s), find(t)
        if a == b:
            continue
        both = pts[a] + pts[b]
        xs, ys = [q[0] for q in both], [q[1] for q in both]
        if max(max(xs) - min(xs), max(ys) - min(ys)) > MAX_SPAN_FT:
            continue                            # chains of short pieces (subdivision loops) stay separate
        parent[a] = b
        pts[b] = both
    groups = defaultdict(list)
    for n in ixn:
        groups[find(n)].append(n)
    print(f"Intersections after merging nodes joined by pieces under {MERGE_FT} ft: {len(groups):,}")

    recs = []
    for members in groups.values():
        mset = set(members)
        parts, legs_ft, leg_names, top = [], 0.0, defaultdict(float), -1
        top_cls, maxw, unnamed_leg = None, 0, False
        for n in members:
            for i, at_start in inc[n]:
                if link[i]:
                    continue
                L, W, rank = CLASS[cls[i]]
                line, total, to_ix, far = trace(n, i, at_start, 2 * L)
                if far in mset and far != n and total < 2 * MERGE_FT:   # internal piece between merged nodes: all of it
                    leg = line
                else:
                    leg_len = min(L, total / 2) if to_ix else min(L, total)
                    leg = substring(line, 0, leg_len)
                if leg.length <= 0:
                    continue
                parts.append(leg.buffer(W, cap_style="flat", quad_segs=3))
                legs_ft += leg.length / (2 if far in mset and far != n and total < 2 * MERGE_FT else 1)   # internal pieces are traced from both ends
                nm = names[i]
                if isinstance(nm, str) and nm.strip():
                    for part in nm.split("|"):  # a piece merged from several OSM ways lists each name
                        part = part.strip()
                        if part:
                            leg_names[part] = max(leg_names[part], rank * 1e6 + total)
                else:
                    unnamed_leg = True
                maxw = max(maxw, W)
                if rank > top:
                    top, top_cls = rank, cls[i]
            parts.append(Point(n).buffer(max(maxw, 40), quad_segs=4))
        if not parts:
            continue
        poly = unary_union(parts)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda q: q.area)
        poly = poly.__class__(poly.exterior)    # fill holes
        streets = sorted(leg_names, key=lambda s: -leg_names[s])
        if len(streets) == 1 and not unnamed_leg:
            continue                            # one street splitting or rejoining (divided road ends): not a crossing
        if len(streets) >= 2:
            name = " & ".join(streets[:3])
        elif streets:
            name = streets[0] + " (unnamed cross street)"
        else:
            name = "Unnamed intersection"
        cx, cy = np.mean([m[0] for m in members]), np.mean([m[1] for m in members])
        recs.append(dict(name=name, streets="|".join(streets), top_class=TOP_LABEL.get(top_cls, "Local streets"),
                         leg_ft=round(legs_ft), cx=cx, cy=cy, geometry=poly))
    ix = gpd.GeoDataFrame(recs, crs=cfg.CRS_FT)
    ix = ix[ix.geometry.representative_point().within(bnd)].reset_index(drop=True)

    # overlaps: the larger polygon keeps the shared area (Austin's rule)
    order = np.argsort(-ix.geometry.area.values)
    tree = STRtree(list(ix.geometry))
    final = list(ix.geometry)
    done = np.zeros(len(ix), bool)
    for i in order:
        g = final[i]
        for j in tree.query(g):
            if done[j] and j != i and final[j].intersects(g):
                g = g.difference(final[j])
        if g.geom_type == "GeometryCollection":   # keep only the area left over
            g = unary_union([q for q in g.geoms if q.geom_type in ("Polygon", "MultiPolygon")])
        if g.geom_type == "MultiPolygon":
            c = Point(ix.at[i, "cx"], ix.at[i, "cy"])
            g = min(g.geoms, key=lambda q: q.distance(c))   # the part at the intersection itself
        final[i] = g
        done[i] = True
    ix["geometry"] = final
    ix = ix[(ix.geom_type == "Polygon") & ~ix.geometry.is_empty & (ix.geometry.area > 100)].reset_index(drop=True)
    ix.insert(0, "ix_id", [f"H-{IX_ID0 + i}" for i in range(len(ix))])
    out = ix[["ix_id", "name", "streets", "top_class", "leg_ft", "geometry"]]
    dst = cfg.processed("intersections.gpkg")
    out.to_file(dst, layer="intersections", driver="GPKG")
    a = out.geometry.area
    print(f"Wrote {len(out):,} intersections -> {dst.name}; area median {a.median():,.0f} sq ft, "
          f"p95 {a.quantile(.95):,.0f}, max {a.max():,.0f}")
    print(out["top_class"].value_counts().to_dict())


if __name__ == "__main__":
    main()
