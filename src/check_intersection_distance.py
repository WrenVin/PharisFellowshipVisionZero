"""How far from an intersection do police still code a crash as an intersection crash?

Calibration check for intersection polygons (Austin Vision Zero method: each
intersection reaches a fixed distance down every street that meets it, 150 ft on
local/collector streets and 250 ft on arterials). For every city-street crash this
measures the straight-line distance to the nearest intersection (a network node
where 3+ streets meet) and the type of street the crash is on (its nearest block),
then plots the share the police coded as "intersection" or "intersection related"
(CRIS Intrsct_Relat_ID 1 or 2) against that distance.

Nodes closer than MERGE_FT are merged first, so the two or four nodes OpenStreetMap
draws where divided roads cross count as one intersection.

Writes reports/intersection_distance_check.png and .csv.

    .venv/bin/python src/check_intersection_distance.py
"""

import glob

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Point

import config as cfg

MERGE_FT = 80             # nodes this close are one intersection (divided roads)
BIN_FT = 25
MAX_FT = 600
CLASSES = {               # OSM highway -> street type, roughly Austin's ASMP levels
    "residential": "Local street", "unclassified": "Local street", "living_street": "Local street",
    "tertiary": "Collector (tertiary)",
    "secondary": "Minor arterial (secondary)",
    "primary": "Major arterial (primary/trunk)", "trunk": "Major arterial (primary/trunk)",
}
ORDER = list(dict.fromkeys(CLASSES.values()))


def street_type(h):
    h = str(h).split("|")[0].replace("_link", "")
    return CLASSES.get(h)


def main():
    e = gpd.read_file(cfg.raw("edges_raw.gpkg"), layer="edges", columns=["u", "v", "highway"]).to_crs(cfg.CRS_FT)
    e["stype"] = e["highway"].map(street_type)
    e = e[e["stype"].notna()].copy()

    # intersections: nodes with 3+ distinct neighbouring nodes
    pairs = pd.DataFrame({"a": e["u"].astype("int64"), "b": e["v"].astype("int64")})
    pairs = pairs[pairs.a != pairs.b]
    und = pd.DataFrame(np.sort(pairs.values, axis=1), columns=["a", "b"]).drop_duplicates()
    deg = pd.concat([und.a, und.b]).value_counts()
    xy = {}
    for u, v, g in zip(e["u"], e["v"], e.geometry):
        cs = list(g.coords) if g.geom_type == "LineString" else list(g.geoms[0].coords)
        xy.setdefault(int(u), cs[0]); xy.setdefault(int(v), cs[-1])
    ids = [n for n, d in deg.items() if d >= 3 and n in xy]
    nodes = gpd.GeoDataFrame({"node": ids}, geometry=[Point(xy[n]) for n in ids], crs=cfg.CRS_FT)

    # merge nearby nodes (divided roads) into one point per intersection
    blobs = nodes.buffer(MERGE_FT / 2).union_all()
    blobs = gpd.GeoDataFrame(geometry=list(getattr(blobs, "geoms", [blobs])), crs=cfg.CRS_FT)
    blobs["ix"] = range(len(blobs))
    j = gpd.sjoin(nodes, blobs, predicate="within")
    cent = j.dissolve("ix").centroid
    ix = gpd.GeoDataFrame(geometry=cent.values, crs=cfg.CRS_FT)
    print(f"Intersection nodes: {len(nodes):,}; after merging within {MERGE_FT} ft: {len(ix):,}")

    # crashes + police intersection code
    c = gpd.read_file(cfg.processed("crashes.gpkg"), columns=["Crash_ID", "severe", "seg_id"])
    c = c[c["seg_id"].notna()].copy()
    codes = []
    for f in glob.glob(str(cfg.CRIS / "Houston_Crash_*" / "*crash_*.csv")):
        codes.append(pd.read_csv(f, usecols=["Crash_ID", "Intrsct_Relat_ID"], low_memory=False))
    codes = pd.concat(codes).drop_duplicates("Crash_ID")
    c = c.merge(codes, on="Crash_ID", how="left")
    c = c[c["Intrsct_Relat_ID"].isin([1, 2, 3, 4])].copy()

    near_e = gpd.sjoin_nearest(c[["geometry"]], e[["stype", "geometry"]], how="left")
    c["stype"] = near_e[~near_e.index.duplicated()]["stype"]
    near_n = gpd.sjoin_nearest(c[["geometry"]], ix, how="left", distance_col="d")
    c["dist_ft"] = near_n[~near_n.index.duplicated()]["d"]
    c = c[c["stype"].notna()]
    c["intx"] = c["Intrsct_Relat_ID"].isin([1, 2])
    print(f"Crashes checked: {len(c):,}; coded intersection or related: {c['intx'].mean():.1%}")

    edges = np.arange(0, MAX_FT + BIN_FT, BIN_FT)
    c["bin"] = pd.cut(c["dist_ft"], edges, right=False, labels=edges[:-1])
    t = (c.groupby(["stype", "bin"], observed=True)
           .agg(n=("intx", "size"), share=("intx", "mean"), n_ksi=("severe", "sum"))
           .reset_index())
    t.to_csv(cfg.REPORTS / "intersection_distance_check.csv", index=False)

    # summary: far-field baseline and where the share gets close to it
    rows = []
    for s in ORDER:
        d = c[c.stype == s]
        far = d[(d.dist_ft >= 400) & (d.dist_ft < 600)]["intx"].mean()
        tt = t[t.stype == s].set_index("bin")
        peak = tt["share"].iloc[0]
        cut = next((b for b, r in tt.iterrows() if r["share"] <= far + 0.1 * (peak - far)), None)
        within = {r: d[d.dist_ft < r]["intx"].sum() / d["intx"].sum() for r in (150, 250, 300)}
        rows.append(dict(stype=s, crashes=len(d), at_0_25=peak, far_400_600=far, settles_at_ft=cut,
                         **{f"intx_within_{k}": v for k, v in within.items()},
                         snapped_within_10ft=(d.dist_ft < 10).mean()))
    summ = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(summ.round(3).to_string(index=False))

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for s, col in zip(ORDER, ["#7a9cc6", "#4a7bb7", "#c0703a", "#9b2d20"]):
        tt = t[(t.stype == s) & (t.n >= 50)]
        ax.plot(tt["bin"].astype(float) + BIN_FT / 2, tt["share"] * 100, color=col, lw=2, label=s)
    for x, y, lab in ((150, 96, "150 ft: Austin, local and collector"), (250, 90, "250 ft: Austin, arterial")):
        ax.axvline(x, color="#888", ls="--", lw=1)
        ax.text(x + 4, y, lab, fontsize=8, color="#555", va="top")
    ax.set_xlim(0, MAX_FT); ax.set_ylim(0, 100)
    ax.set_xlabel("Distance from the nearest intersection (feet)")
    ax.set_ylabel("Crashes police coded as intersection\nor intersection related (%)")
    ax.set_title("Where police stop calling a crash an intersection crash\nHouston city streets, 2016 to 2025, by type of street the crash was on")
    ax.legend(title="Street the crash was on", frameon=False, loc="center right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(cfg.REPORTS / "intersection_distance_check.png", dpi=150)
    print("Wrote reports/intersection_distance_check.png")


if __name__ == "__main__":
    main()
