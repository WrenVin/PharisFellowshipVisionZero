"""Export segment + boundary GeoJSON for the Vision Zero dashboard (docs/).

The dashboard (docs/vision-zero.html) loads these and does all styling/filtering live
in the browser. We keep the files lean: simplify geometry, round coordinates,
round attribute values, and carry only display/filter-relevant columns.
"""

import glob
from collections import defaultdict
import json
import math

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point, LineString

import config as cfg
ROOT, PROCESSED, DOCS, EXTERNAL = cfg.ROOT, cfg.PROCESSED, cfg.DOCS, cfg.EXTERNAL

# TxDOT on-system main lanes (state-owned roads: IH/US/SH/FM/tollway/etc.) — used
# to drop TxDOT-owned roadways from the "city streets" network so we only show
# what the City owns/operates (matches the crash filter Road_Cls_ID==5).
TXDOT_URL = ("https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/"
             "TxDOT_Roadways/FeatureServer/0")

# TxDOT main roadbeds with mileposts (DFO, miles along the route) stored as M values on
# every vertex; used to place freeway crashes at the milepost on their crash report.
TXDOT_DFO_WHERE = "RTE_PRFX IN ('IH','US','SH','SL') AND RDBD_TYPE IN ('Single Roadbed','Right Roadbed','Left Roadbed')"


def fetch_txdot_dfo():
    """{(prefix, number): [(xs, ys, ms), ...]} in EPSG:2278, Single/Right roadbeds first."""
    cache = cfg.external("txdot_routes_dfo.json")
    if not cache.exists():
        bb = cfg.bbox_4326()
        r = requests.get(TXDOT_URL + "/query", params={
            "where": TXDOT_DFO_WHERE, "geometry": f"{bb[0]},{bb[1]},{bb[2]},{bb[3]}",
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 2278, "returnM": "true",
            "outFields": "RTE_PRFX,RTE_NBR,RDBD_TYPE", "resultRecordCount": 2000, "f": "json"}, timeout=300)
        cache.write_text(r.text)
    feats = json.loads(cache.read_text()).get("features", [])
    routes = {}
    order = {"Single Roadbed": 0, "Right Roadbed": 1, "Left Roadbed": 2}
    for f in sorted(feats, key=lambda f: order.get(f["attributes"]["RDBD_TYPE"], 3)):
        a = f["attributes"]
        key = (a["RTE_PRFX"], int(a["RTE_NBR"]) if str(a["RTE_NBR"]).isdigit() else a["RTE_NBR"])
        for path in f["geometry"]["paths"]:
            if len(path[0]) < 3:
                continue
            routes.setdefault(key, []).append(tuple(map(list, zip(*path))))
    return routes


def dfo_point(routes, key, dfo):
    """The (x, y) at milepost dfo on route key, or None."""
    for xs, ys, ms in routes.get(key, []):
        lo, hi = min(ms[0], ms[-1]), max(ms[0], ms[-1])
        if not (lo <= dfo <= hi):
            continue
        for i in range(len(ms) - 1):
            m0, m1 = ms[i], ms[i + 1]
            if (m0 <= dfo <= m1) or (m1 <= dfo <= m0):
                t = 0 if m1 == m0 else (dfo - m0) / (m1 - m0)
                return xs[i] + t * (xs[i + 1] - xs[i]), ys[i] + t * (ys[i + 1] - ys[i])
    return None


def fetch_txdot_onsys(crs):
    cache = cfg.external("txdot_onsys.gpkg")
    if cache.exists():
        return gpd.read_file(cache).to_crs(crs)
    bb = cfg.bbox_4326()
    env = {"xmin": bb[0], "ymin": bb[1], "xmax": bb[2], "ymax": bb[3],
           "spatialReference": {"wkid": 4326}}
    # exclude interstates (RTE_PRFX='IH'): limited-access freeways, not in our
    # surface-street network; matching streets that run under them mislabels them.
    where = ("SYSTEM='On' AND RTE_PRFX<>'IH' AND "
             "RDBD_TYPE IN ('Single Roadbed','Left Roadbed','Right Roadbed')")
    frames, off = [], 0
    while True:
        r = requests.get(TXDOT_URL + "/query", params={
            "where": where, "geometry": json.dumps(env),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "outFields": "RTE_PRFX", "outSR": 2278,
            "resultOffset": off, "resultRecordCount": 1000, "f": "geojson"}, timeout=120)
        feats = r.json().get("features", [])
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs=2278))
        off += len(feats)
        if len(feats) < 1000:
            break
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=2278)
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    out.to_file(cache, driver="GPKG")
    return out.to_crs(crs)

# column -> rounding (None = keep as-is / string)
COLS = {
    "seg_id": None, "name": None, "highway": None, "district": None,
    "lanes_final": 0, "lanes_source": None,
    "roadway_width_ft": 0,
    "posted_speed_mph": 0, "speed_source": None,
    "op_speed_85_mph": 0,
    "adt": 0, "adt_source": None,
    "median_type": None,
    "sidewalk_presence": None,
    "landuse_dominant": None, "pct_commercial": 0, "pct_industrial": 0,
    "median_hh_income": 0, "pct_poverty": 1, "pct_hispanic": 1,
    "pct_black_nh": 1, "pct_white_nh": 1, "pct_zero_car_hh": 1,
    "pop_density_sqmi": 0,
    # crash outcomes (per segment, from CRIS)
    "n_crash": 0, "n_injury": 0, "n_severe": 0, "n_fatal": 0,
    "n_ped": 0, "n_bike": 0, "n_ped_severe": 0, "n_bike_severe": 0,
    "n_signals": 0, "oneway": None, "merged_dual": None, "length_ft": 0,
    "mid_ft": 0,       # length outside intersection polygons (dashboard concentration measure)
    "trim_a": 0, "trim_b": 0,   # thousandths of the line inside an intersection at its start / end (drawn trimmed when zoomed in)
    "on_hin": None,    # on the City's official High Injury Network?
    "on_txdot": None,  # TxDOT-owned (state) road vs city-owned?
}

# Only these fields are read by the dashboard (docs/vision-zero.html). Everything
# else in COLS stays out of segments_vz.geojson to keep the browser payload small:
# the full property set is ~52 MB at city scale (vs ~6 MB of geometry) and was
# crashing low-memory tabs. The richer per-segment data lives in the CSV/GPKG.
WEB_KEEP = [
    "seg_id", "name", "road_class", "district", "sn", "on_txdot", "on_hin",
    "n_crash", "n_severe", "n_fatal", "n_ped", "n_ped_severe",
    "n_bike", "n_bike_severe", "length_ft", "mid_ft", "trim_a", "trim_b",
    "lanes_final", "roadway_width_ft", "posted_speed_mph",
    "sidewalk_presence", "adt",
]

FRIENDLY_CLASS = {
    "primary": "Major arterial", "secondary": "Arterial", "tertiary": "Collector",
    "residential": "Local street", "unclassified": "Minor street",
}

# neighborhood median-household-income tier per crash (for the equity panel):
# 0 = <$50k, 1 = $50-100k, 2 = $100-150k, 3 = $150k+
INC_EDGES = [50000, 100000, 150000]
def inc_tier(v):
    if pd.isna(v):
        return None
    for i, e in enumerate(INC_EDGES):
        if v < e:
            return i
    return len(INC_EDGES)

seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")

# clip the served network to the study-area boundary (full-purpose City of Houston; see
# src/fetch_boundary.py). The enriched gpkg keeps the comprehensive network, but the
# dashboard shows only full-service streets — drops the limited-purpose annexation slivers.
_bnd = cfg.boundary_geom(seg.crs)
_n0 = len(seg)
seg = seg[seg.intersects(_bnd)].copy()
print(f"Segments within full-purpose boundary: {len(seg):,} of {_n0:,}")

# friendly road class (collapse *_link to Minor)
base = seg["highway"].str.replace("_link", "", regex=False)
seg["road_class"] = base.map(FRIENDLY_CLASS).fillna("Minor street")
seg.loc[seg["highway"].str.endswith("_link"), "road_class"] = "Minor street"

# Frontage roads (dashboard only; decision 2026-10-31). The analysis network leaves them
# out (pull_osm.py), so the model is unchanged; build_frontage.py makes blocks from OSM.
# Crashes police code as frontage road (road_part 2) leave the Freeways toggle and join
# the default view, each assigned to its nearest frontage block within 200 ft (the same
# rule as assign_crashes.py). Frontage blocks are TxDOT-owned "Frontage road" streets.
front_cr = None
_fseg = cfg.processed("frontage_segments.gpkg")
_fwy_all = cfg.processed("freeway_crashes.gpkg")
if _fseg.exists() and _fwy_all.exists():
    fseg = gpd.read_file(_fseg, layer="segments").to_crs(seg.crs)
    fseg = fseg[fseg.intersects(_bnd)].copy()
    fw_all = gpd.read_file(_fwy_all, layer="crashes").to_crs(seg.crs)
    front_cr = fw_all[fw_all["road_part"].eq(2)].copy()
    j = gpd.sjoin_nearest(front_cr[["geometry"]], fseg[["seg_id", "geometry"]], how="left",
                          max_distance=200, distance_col="_d")
    j = j[~j.index.duplicated(keep="first")]
    front_cr["seg_id"] = j["seg_id"].reindex(front_cr.index).values
    print(f"Frontage-road crashes: {len(front_cr):,}; assigned to a frontage block within 200 ft: "
          f"{int(front_cr['seg_id'].notna().sum()):,} ({100*front_cr['seg_id'].notna().mean():.1f}%)")
    a = front_cr[front_cr["seg_id"].notna()]
    grp = a.groupby("seg_id")
    cnt = pd.DataFrame({
        "n_crash": grp.size(), "n_injury": grp["any_injury"].sum(), "n_severe": grp["severe"].sum(),
        "n_fatal": grp["fatal"].sum(), "n_ped": grp["involves_ped"].sum(), "n_bike": grp["involves_bike"].sum(),
        "n_ped_severe": a[a["severe"]].groupby("seg_id")["involves_ped"].sum(),
        "n_bike_severe": a[a["severe"]].groupby("seg_id")["involves_bike"].sum()})
    fseg = fseg.join(cnt, on="seg_id")
    for c_ in cnt.columns:
        fseg[c_] = fseg[c_].fillna(0).astype(int)
    fseg["highway"], fseg["road_class"] = "frontage", "Frontage road"
    seg = gpd.GeoDataFrame(pd.concat([seg, fseg], ignore_index=True), crs=seg.crs)
    print(f"Added {len(fseg):,} frontage blocks ({fseg['length_ft'].sum()/5280:,.0f} mi) to the published network")

# council district per segment (for the dashboard's per-district filter), if the
# area has sub-districts to filter by (city build); skipped for single-district builds.
districts_4326 = None
_dpath = cfg.raw("districts.geojson")
if _dpath.exists():
    districts_4326 = gpd.read_file(_dpath)
    d_ft = districts_4326.to_crs(seg.crs)[["DISTRICT", "geometry"]]
    mids = gpd.GeoDataFrame(geometry=seg.geometry.representative_point(), crs=seg.crs)
    # nearest district (not within) so segments in thin inter-district gaps still
    # get assigned — the whole network is inside the city, so nearest is correct.
    sj = gpd.sjoin_nearest(mids, d_ft, how="left")
    sj = sj[~sj.index.duplicated()]
    seg["district"] = sj["DISTRICT"].values
    print(f"Tagged segments by district: {seg['district'].notna().sum():,}/{len(seg):,}")

# Super Neighborhood per segment (City planning geography; 88 named areas like
# Downtown / Montrose / Second Ward), for the dashboard's per-SN filter. We use
# point-in-polygon on the segment's representative point (NOT nearest): unlike
# council districts, Super Neighborhoods don't tile the whole city, so a segment
# in no SN is left unlabeled (sn = NA) rather than snapped to a far one.
sn_4326 = None
_snpath = cfg.raw("superneighborhoods.geojson")
if _snpath.exists():
    sn_4326 = gpd.read_file(_snpath)
    sn_ft = sn_4326.to_crs(seg.crs)[["POLYID", "geometry"]]
    smids = gpd.GeoDataFrame(geometry=seg.geometry.representative_point(), crs=seg.crs)
    ssj = gpd.sjoin(smids, sn_ft, how="left", predicate="within")
    ssj = ssj[~ssj.index.duplicated()]
    seg["sn"] = pd.array(pd.to_numeric(ssj["POLYID"].values, errors="coerce"), dtype="Int64")
    print(f"Tagged segments by Super Neighborhood: {seg['sn'].notna().sum():,}/{len(seg):,}")

# on-HIN flag: a segment counts as "on the City's official High Injury Network"
# if at least half its length runs within 50 ft of an HIN line (so a cross-street
# merely crossing an HIN arterial isn't falsely flagged).
seg["on_hin"] = False
_hpath = DOCS / "hin.geojson"
if _hpath.exists():
    hin = gpd.read_file(_hpath).to_crs(seg.crs)
    hin_buf = hin.buffer(50).union_all()
    frac = seg.geometry.intersection(hin_buf).length / seg.geometry.length
    seg["on_hin"] = (frac >= 0.5).fillna(False).values
    print(f"on-HIN segments: {int(seg['on_hin'].sum()):,} "
          f"({100*seg['on_hin'].mean():.1f}%)")

# Label each segment as TxDOT-owned (state) vs city-owned. A segment is on_txdot
# only if it runs ALONG a TxDOT on-system main lane (S Main/US-90A, SH 6, FM 1093,
# etc.) for >=50% of its length. We break both networks into straight 2-point
# pieces with a compass bearing, then a city piece "matches" a TxDOT piece only
# when it is within 60 ft AND roughly parallel (bearing within 30 deg). The
# parallel test is the fix for a real bug: a plain city street that BRIDGES OVER an
# interstate runs directly above the (wide) freeway corridor, so the old distance-
# only test flagged the overpass as state-owned even though it crosses the freeway
# perpendicularly. These at-grade state arterials are KEPT in the network (like the
# City's HIN and Austin's dashboard); only limited-access freeways are excluded
# upstream (pull_osm + build_crashes).
#
# We also DROP interstates (RTE_PRFX 'IH') from the match set: they are limited-
# access freeways that aren't in our network, and a surface street running parallel
# directly UNDER an elevated interstate (e.g. Pierce St below the Pierce Elevated /
# I-45) would otherwise pass the parallel test and be mislabeled state-owned. At-
# grade state arterials are US/SH/FM/etc., which stay.
FREEWAY_PRFX = {"IH"}

# Hand-curated false positives: short, isolated city-street stubs that the
# parallel-match test still flags because they run beside/under a non-interstate
# freeway (US 59, SH 288, the downtown freeway tangle) or a toll road. The TxDOT
# network is static, so we just list the offending seg_ids and force them
# city-owned. These are ordinary city streets (Pierce under the Pierce Elevated,
# Bagby/Milam/Chartres/Burlington downtown, etc.) plus unnamed disconnected stubs;
# genuine short state routes (Highway 6, La Porte Fwy, FM 1960/Cypress Creek,
# FM 528/NASA Pkwy, Spur 5, Hempstead Hwy, Wayside, Cullen, Westheimer) are kept.
TXDOT_FALSE_POSITIVES = {
    # downtown / midtown city streets in the freeway tangle
    "H-81534", "H-84475",                                  # Pierce Street
    "H-103300", "H-103301",                               # Bagby Street
    "H-90087", "H-90088", "H-96804", "H-96805",          # Milam Street
    "H-65518",                                            # Chartres Street
    "H-87413", "H-87414",                                 # Burlington Street
    "H-15093",                                            # West Alabama Street
    "H-99811",                                            # Zephyr Street
    "H-81685",                                            # Calhoun Road
    # other city streets running parallel to a freeway/toll road
    "H-66525",                                            # Hardy Street
    "H-77927", "H-77928",                                 # Sue Barnett Drive
    "H-102029", "H-102031", "H-99579",                   # Monroe Road
    "H-63149", "H-63153", "H-88549", "H-88551", "H-88552",  # North Durham Drive
    "H-56555",                                            # West Montgomery Road
    # unnamed disconnected stubs
    "H-109435", "H-109437", "H-13968", "H-18124", "H-25436", "H-25437",
    "H-26041", "H-26043", "H-26434", "H-26438", "H-31125", "H-32165",
    "H-55510", "H-59157", "H-59648", "H-76591",
}
def _bearing_pieces(gdf, id_col=None):
    """Explode lines into straight 2-point pieces with a 0-180 bearing + length."""
    recs = []
    ids = gdf[id_col].values if id_col else [None] * len(gdf)
    for gid, geom in zip(ids, gdf.geometry.values):
        if geom is None or geom.is_empty:
            continue
        parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for part in parts:
            cs = list(part.coords)
            for i in range(len(cs) - 1):
                (x0, y0), (x1, y1) = cs[i], cs[i + 1]
                ln = LineString([(x0, y0), (x1, y1)])
                rec = {"brg": math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180,
                       "plen": ln.length, "geometry": ln}
                if id_col:
                    rec[id_col] = gid
                recs.append(rec)
    return gpd.GeoDataFrame(recs, crs=gdf.crs)

seg["on_txdot"] = False
try:
    tx = fetch_txdot_onsys(seg.crs)
    if "RTE_PRFX" in tx.columns:   # drop interstates (limited-access freeways)
        tx = tx[~tx["RTE_PRFX"].isin(FREEWAY_PRFX)].copy()
    cpieces = _bearing_pieces(seg, "seg_id")
    tpieces = _bearing_pieces(tx)[["brg", "geometry"]].rename(columns={"brg": "tx_brg"})
    j = gpd.sjoin_nearest(cpieces, tpieces, how="left", max_distance=60, distance_col="d")
    j = j[~j.index.duplicated(keep="first")]
    db = (j["brg"] - j["tx_brg"]).abs()
    db = db.where(db <= 90, 180 - db)          # circular bearing diff on 0-180
    j["match"] = j["tx_brg"].notna() & (db <= 30)
    matched = j[j["match"]].groupby("seg_id")["plen"].sum()
    total = cpieces.groupby("seg_id")["plen"].sum()
    frac = (matched / total).reindex(seg["seg_id"].values).fillna(0).values
    seg["on_txdot"] = frac >= 0.5
    # force the hand-curated false positives back to city-owned (see above)
    n_fp = int(seg["seg_id"].isin(TXDOT_FALSE_POSITIVES).sum())
    seg.loc[seg["seg_id"].isin(TXDOT_FALSE_POSITIVES), "on_txdot"] = False
    print(f"TxDOT-owned (state) segments labeled: {int(seg['on_txdot'].sum()):,} "
          f"({100*seg['on_txdot'].mean():.1f}%) — parallel-aligned, interstates dropped, "
          f"{n_fp} curated false positives removed")
except Exception as e:
    print(f"WARNING: TxDOT tagging skipped ({type(e).__name__}: {e})")

seg.loc[seg["highway"].eq("frontage"), "on_txdot"] = True   # frontage roads are part of the state highway

# Intersections (dashboard only; decision 2026-10-31). build_intersections.py draws a
# polygon around every intersection on the Vision Zero Austin method; a street or
# frontage-road crash inside one belongs to the intersection, not to a block. The
# blocks' crash counts drop by the crashes that moved, so block + intersection
# counts still add up to the same total. ix_of maps Crash_ID -> intersection id and
# is applied to the crash points below.
_city_all = gpd.read_file(cfg.processed("crashes.gpkg"), layer="crashes")
if front_cr is not None:   # frontage-road crashes join the default view
    _fc = front_cr.to_crs(_city_all.crs)
    _city_all = gpd.GeoDataFrame(pd.concat([_city_all, _fc[[c for c in _city_all.columns if c in _fc.columns] + (["seg_id"] if "seg_id" not in _city_all.columns else [])]],
                                           ignore_index=True), crs=_city_all.crs)
ixg, ix_of = None, {}
_ixpath = cfg.processed("intersections.gpkg")
if _ixpath.exists():
    ixg = gpd.read_file(_ixpath, layer="intersections").to_crs(seg.crs).rename(columns={"ix_id": "seg_id"})
    _cc = _city_all.to_crs(seg.crs)
    hit = gpd.sjoin(_cc[["Crash_ID", "seg_id", "severe", "fatal", "any_injury", "involves_ped", "involves_bike", "geometry"]],
                    ixg[["seg_id", "geometry"]].rename(columns={"seg_id": "ix"}), predicate="within")
    hit = hit[~hit.index.duplicated(keep="first")]
    ix_of = dict(zip(hit["Crash_ID"], hit["ix"]))
    _ksi_all = _cc["severe"].sum()
    print(f"Intersections: {len(ixg):,}; crashes inside one: {len(hit):,} of {len(_cc):,} ({100*len(hit)/len(_cc):.1f}%); "
          f"killed or seriously injured crashes: {100*hit['severe'].sum()/_ksi_all:.1f}%")

    def _counts(a, by):
        g = a.groupby(by)
        return pd.DataFrame({
            "n_crash": g.size(), "n_injury": g["any_injury"].sum(), "n_severe": g["severe"].sum(),
            "n_fatal": g["fatal"].sum(), "n_ped": g["involves_ped"].sum(), "n_bike": g["involves_bike"].sum(),
            "n_ped_severe": a[a["severe"]].groupby(by)["involves_ped"].sum(),
            "n_bike_severe": a[a["severe"]].groupby(by)["involves_bike"].sum()}).fillna(0).astype(int)
    moved = _counts(hit[hit["seg_id"].notna()], "seg_id")          # leave their blocks
    _m = moved.reindex(seg["seg_id"].values).fillna(0).astype(int)
    for c_ in moved.columns:
        seg[c_] = (seg[c_].fillna(0).astype(int).values - _m[c_].values).clip(min=0)
    ixc = _counts(hit, "ix")
    ixg = ixg.join(ixc, on="seg_id")
    for c_ in ixc.columns:
        ixg[c_] = ixg[c_].fillna(0).astype(int)

    # an intersection is on a TxDOT road or the HIN when 60+ ft of such a street runs inside it
    pairs = gpd.sjoin(seg[["on_txdot", "on_hin", "geometry"]], ixg[["geometry"]], predicate="intersects")
    pairs["_ft"] = [g.intersection(ixg.geometry.iat[j]).length for g, j in zip(pairs.geometry, pairs["index_right"])]
    for flag in ("on_txdot", "on_hin"):
        ft = pairs[pairs[flag].fillna(False).astype(bool)].groupby("index_right")["_ft"].sum()
        ixg[flag] = (ft.reindex(ixg.index).fillna(0) >= 60).values
    # street length inside intersections moves with their crashes, so block miles plus
    # intersection miles add up to the network's miles (the "share of street miles" KPI)
    covered = pairs.groupby(level=0)["_ft"].sum()
    seg["mid_ft"] = (seg["length_ft"] - covered.reindex(seg.index).fillna(0)).clip(lower=0)
    ixg["leg_ft"] = pairs.groupby("index_right")["_ft"].sum().reindex(ixg.index).fillna(0).round()
    # how far each block runs into an intersection at either end, so the page can stop
    # the line at the intersection's edge when the polygons are drawn
    ivs = defaultdict(list)
    for si, g, j in zip(pairs.index, pairs.geometry, pairs["index_right"]):
        x = g.intersection(ixg.geometry.iat[j])
        for part in getattr(x, "geoms", [x]):
            if part.geom_type == "LineString" and not part.is_empty:
                a_, b_ = sorted((g.project(Point(part.coords[0])), g.project(Point(part.coords[-1]))))
                ivs[si].append((a_, b_))
    ta, tb = {}, {}
    for si, iv in ivs.items():
        L_ = seg.geometry.at[si].length
        a_ = 0.0
        for lo, hi in sorted(iv):
            if lo <= a_ + 3:
                a_ = max(a_, hi)
        b_ = L_
        for lo, hi in sorted(iv, key=lambda t: -t[1]):
            if hi >= b_ - 3:
                b_ = min(b_, lo)
        if L_ > 0:
            ta[si], tb[si] = round(1000 * a_ / L_), round(1000 * (L_ - b_) / L_)
    seg["trim_a"] = pd.Series(ta).reindex(seg.index).fillna(0).astype(int)
    seg["trim_b"] = pd.Series(tb).reindex(seg.index).fillna(0).astype(int)
    print(f"Blocks trimmed at an intersection: {(seg['trim_a'] > 0).sum() + (seg['trim_b'] > 0).sum():,} ends; "
          f"wholly inside one: {((seg['trim_a'] + seg['trim_b']) >= 1000).sum():,}")
    ctr = gpd.GeoDataFrame(geometry=ixg.geometry.representative_point(), crs=seg.crs)
    if districts_4326 is not None:
        j = gpd.sjoin_nearest(ctr, districts_4326.to_crs(seg.crs)[["DISTRICT", "geometry"]], how="left")
        ixg["district"] = j[~j.index.duplicated()]["DISTRICT"].values
    if sn_4326 is not None:
        j = gpd.sjoin(ctr, sn_4326.to_crs(seg.crs)[["POLYID", "geometry"]], how="left", predicate="within")
        ixg["sn"] = pd.array(pd.to_numeric(j[~j.index.duplicated()]["POLYID"].values, errors="coerce"), dtype="Int64")
    ixg["road_class"] = "Intersection"
    ixg["length_ft"] = ixg["leg_ft"]
    print(f"Intersections on TxDOT roads: {int(ixg['on_txdot'].sum()):,}; on the HIN: {int(ixg['on_hin'].sum()):,}")
    iw = ixg[["seg_id", "name", "streets", "top_class", "road_class", "district", "sn", "on_txdot", "on_hin",
              "n_crash", "n_severe", "n_fatal", "n_ped", "n_ped_severe", "n_bike", "n_bike_severe", "length_ft", "geometry"]].copy()
    _simp = iw.geometry.simplify(5)   # keep the original where simplifying breaks a small polygon
    iw["geometry"] = [b if b.geom_type == "Polygon" and not b.is_empty else a for a, b in zip(iw.geometry, _simp)]
    iw = iw.to_crs(4326)
    ipath = DOCS / "intersections_vz.geojson"
    if ipath.exists():
        ipath.unlink()
    iw.to_file(ipath, driver="GeoJSON", COORDINATE_PRECISION=5)
    ipath.write_text(json.dumps(json.loads(ipath.read_text()), separators=(",", ":")))
    print(f"Wrote {len(iw):,} intersections -> {ipath.name} ({ipath.stat().st_size/1e6:.1f} MB)")
else:
    print("WARNING: houston_intersections.gpkg missing (run build_intersections.py); crashes stay on blocks")

keep = seg[[c for c in COLS if c in seg.columns] + ["road_class", "geometry"]].copy()
for c, nd in COLS.items():
    if c in keep.columns and nd is not None:
        keep[c] = keep[c].round(nd)
        if nd == 0:
            keep[c] = keep[c].astype("Int64")  # nullable int -> clean JSON
for c in ("oneway", "merged_dual", "on_hin", "on_txdot"):
    if c in keep.columns:
        keep[c] = keep[c].astype("boolean")

# simplify in feet (EPSG:2278) for display, then reproject to WGS84.
# 25 ft keeps streets recognizable while roughly halving the payload at
# city scale (75k segments); tune if the web map needs crisper geometry.
keep["geometry"] = keep.geometry.simplify(25, preserve_topology=False)
keep = keep.to_crs(4326)

DOCS.mkdir(exist_ok=True)
# The full-property segments.geojson is retired with the Street Explorer; only the
# slim segments_vz.geojson (below) is published now. Delete any stale copy.
_full = DOCS / "segments.geojson"
if _full.exists():
    _full.unlink()
# Super Neighborhood id (the dashboard filters by it) is added to the slim file.
if sn_4326 is not None and "sn" in seg.columns:
    keep["sn"] = seg["sn"].values
# Slim copy -> segments_vz.geojson for the Vision Zero dashboard, which only reads
# WEB_KEEP. Dropping the ~17 unused fields ~halves the payload (52 MB of props
# becomes ~18 MB) and keeps low-memory tabs from crashing.
vz_out = DOCS / "segments_vz.geojson"
if vz_out.exists():
    vz_out.unlink()
web = keep[[c for c in WEB_KEEP if c in keep.columns] + ["geometry"]].copy()
web.to_file(vz_out, driver="GeoJSON", COORDINATE_PRECISION=5)
# GDAL writes pretty-printed JSON; re-dump compact to shave the download further
# (parsed memory is unchanged, but it trims a few MB off the wire).
vz_out.write_text(json.dumps(json.loads(vz_out.read_text()), separators=(",", ":")))
print(f"Wrote slim VZ segments -> {vz_out} ({vz_out.stat().st_size/1e6:.1f} MB)")

# boundary: simplify hard (outline only, not measured) to keep it light
boundary = cfg.boundary(2278)
boundary["geometry"] = boundary.geometry.simplify(100, preserve_topology=True)
boundary = boundary.to_crs(4326)
bpath = DOCS / "boundary.geojson"
if bpath.exists():
    bpath.unlink()
boundary[["geometry"]].to_file(bpath, driver="GeoJSON", COORDINATE_PRECISION=5)

print(f"Wrote boundary -> {bpath}")

# crash points for the VZ dashboard "Crash locations" view + the by-month,
# by-time-of-day, years-of-life-lost, by-neighborhood-income, and crash-cost panels:
# [lat, lon, sev, fatal, ped, bike, year, date, hour, yll, district, inc_tier, on_hin, on_txdot, seg_id, sn, n_k, n_a, n_b, n_c, n_noinj,
#  light, factors, ksi_people]
# fields 16-20 are the per-crash person counts by KABCO injury severity (killed K, serious A,
# minor B, possible C, no-injury), so the dashboard can apply the FHWA per-PERSON cost table.
# 21 light (0 unknown, 1 daylight, 2 dark with street lights, 3 dawn/dusk, 4 dark without street
# lights, 5 dark with lighting not recorded), 22 contributing-factor bit flags,
# 23 people killed or seriously injured as comma-joined codes or null (64*travel + 32*killed + 4*age group + sex; see build_crashes.py).
def crash_rows(cr, freeway=False):
    """Tag crash points and build dashboard rows (25 fields; field 24 is the road type)."""
    cr = cr.to_crs(seg.crs)
    cr = cr[cr.within(_bnd)].copy()   # clip crashes to the full-purpose boundary (drops limited-purpose slivers)
    # Per-crash person counts by injury severity live in the raw CRIS crash files (the processed
    # gpkg drops them); pull them and match by Crash_ID. CRIS person DETAIL is suppressed on some
    # crashes, but these crash-level COUNT fields are complete. Needs the raw CRIS extracts present.
    _ccols = ["Crash_ID", "Death_Cnt", "Sus_Serious_Injry_Cnt", "Nonincap_Injry_Cnt", "Poss_Injry_Cnt", "Non_Injry_Cnt"]
    _cfiles = glob.glob(str(cfg.CRIS / "Houston_Crash_*" / "*crash_*.csv"))
    if _cfiles:
        _raw = pd.concat([pd.read_csv(f, usecols=lambda c: c in _ccols, low_memory=False) for f in _cfiles],
                         ignore_index=True).drop_duplicates("Crash_ID").set_index("Crash_ID")
        for _c in _ccols[1:]:
            _raw[_c] = pd.to_numeric(_raw[_c], errors="coerce").fillna(0).astype(int)
        for _dst, _src in [("n_k", "Death_Cnt"), ("n_a", "Sus_Serious_Injry_Cnt"), ("n_b", "Nonincap_Injry_Cnt"),
                           ("n_c", "Poss_Injry_Cnt"), ("n_noinj", "Non_Injry_Cnt")]:
            cr[_dst] = cr["Crash_ID"].map(_raw[_src]).fillna(0).astype(int)
    else:
        print("WARNING: no raw CRIS crash files found; crash-cost person counts will be 0")
        for _dst in ("n_k", "n_a", "n_b", "n_c", "n_noinj"):
            cr[_dst] = 0
    # Each crash's street (seg_id, for cross-filtering), on-HIN flag, and road
    # ownership come from the PIPELINE's assignment (assign_crashes.py: single
    # nearest segment within 200 ft, merged-away halves credited to their rep) —
    # not re-derived here — so per-crash counting in the dashboard reconciles
    # exactly with the per-segment n_* columns. Crashes with no street within
    # 200 ft (or whose street isn't in the published subset) get a null seg_id:
    # they still count in KPIs/points, they just don't attach to a street.
    # on_txdot is a LABEL (for the ownership view), not an exclusion.
    if freeway:   # freeway sections (assigned below), never on the HIN; TxDOT unless a toll road
        if "seg_id" not in cr.columns:
            cr["seg_id"] = None
        cr["seg_id"] = cr["seg_id"].where(cr["seg_id"].notna(), None)
        cr["on_hin"] = False
        cr["on_txdot"] = cr["road_type"].eq(1)
    elif "seg_id" in cr.columns:
        _lut = seg.set_index("seg_id")[["on_hin", "on_txdot"]]
        if ixg is not None:   # crashes inside an intersection polygon belong to the intersection
            cr["seg_id"] = cr["Crash_ID"].map(ix_of).fillna(cr["seg_id"])
            _lut = pd.concat([_lut, ixg.set_index("seg_id")[["on_hin", "on_txdot"]]])
        _pub = set(_lut.index)
        cr["seg_id"] = cr["seg_id"].where(cr["seg_id"].isin(_pub))
        cr["on_hin"] = cr["seg_id"].map(_lut["on_hin"]).fillna(False).astype(bool)
        cr["on_txdot"] = cr["seg_id"].map(_lut["on_txdot"]).fillna(False).astype(bool)
        print(f"Crash streets from pipeline assignment: {int(cr['seg_id'].notna().sum()):,} of {len(cr):,} attach to a published street")
    else:  # legacy crashes.gpkg without the persisted assignment: nearest published segment
        print("WARNING: crashes.gpkg has no seg_id (rerun assign_crashes.py); falling back to unbounded nearest-join")
        nj = gpd.sjoin_nearest(cr[["geometry"]], seg[["seg_id", "on_hin", "on_txdot", "geometry"]], how="left")
        nj = nj[~nj.index.duplicated()]
        cr["seg_id"] = nj["seg_id"].values
        cr["on_hin"] = pd.Series(nj["on_hin"].values).fillna(False).astype(bool).values
        cr["on_txdot"] = pd.Series(nj["on_txdot"].values).fillna(False).astype(bool).values
    print(f"Crash points: {int(cr['on_txdot'].sum()):,} on TxDOT-owned (state) roads (kept, labeled)")

    # Neighborhood income (-> inc_tier for the equity panel) comes from the block
    # group the crash POINT falls in, NOT the nearest street. Census draws block-
    # group lines down the middle of major roads, so nearest-street inheritance
    # mislabels ~14% of crashes near a boundary (5% across the $100k line); a crash
    # is a point and sits unambiguously inside one block group. (cr is still in the
    # projected segment CRS here; the to_crs(4326) happens just below.)
    _bgcache = cfg.external("census_bg.gpkg")
    if _bgcache.exists():
        bg_inc = gpd.read_file(_bgcache)[["GEOID", "geometry"]].to_crs(seg.crs)
        bg_inc["GEOID"] = bg_inc["GEOID"].astype(str)
        _bg2inc = (seg.dropna(subset=["bg_geoid"])
                      .assign(bg_geoid=lambda d: d["bg_geoid"].astype(str))
                      .groupby("bg_geoid")["median_hh_income"].first())
        bg_inc["median_hh_income"] = bg_inc["GEOID"].map(_bg2inc)
        ij = gpd.sjoin(cr[["geometry"]], bg_inc[["median_hh_income", "geometry"]],
                       how="left", predicate="within")
        inc_src = ij[~ij.index.duplicated()]["median_hh_income"].values
    else:  # fallback to nearest-street income if the block-group cache is absent
        print("WARNING: block-group cache missing; inc_tier falls back to nearest-street income")
        _ni = gpd.sjoin_nearest(cr[["geometry"]], seg[["median_hh_income", "geometry"]], how="left")
        inc_src = _ni[~_ni.index.duplicated()]["median_hh_income"].values
    cr["inc_tier"] = pd.Series(pd.to_numeric(inc_src, errors="coerce")).map(inc_tier).values
    cr = cr.to_crs(4326)
    if districts_4326 is not None:  # council district per crash, for the per-district filter
        cj = gpd.sjoin(cr[["geometry"]], districts_4326[["DISTRICT", "geometry"]],
                       how="left", predicate="within")
        cj = cj[~cj.index.duplicated()]
        cr["district"] = cj["DISTRICT"].values
    else:
        cr["district"] = None
    if sn_4326 is not None:  # Super Neighborhood per crash (point-in-polygon; NA if in none)
        sj2 = gpd.sjoin(cr[["geometry"]], sn_4326[["POLYID", "geometry"]],
                        how="left", predicate="within")
        sj2 = sj2[~sj2.index.duplicated()]
        cr["sn"] = pd.to_numeric(sj2["POLYID"].values, errors="coerce")
        print(f"Crash points tagged with a Super Neighborhood: {cr['sn'].notna().sum():,}/{len(cr):,}")
    else:
        cr["sn"] = None
    pts = []
    for g, sv, ft, pd_, bk, yr, dt, hr, yl, dist, it, oh, otx, sid, snv, nk, na, nb, nc, nn, rt, lt, fc, kp in zip(
            cr.geometry, cr.severe, cr.fatal, cr.involves_ped, cr.involves_bike,
            cr.year, cr.date, cr.hour, cr.yll, cr.district, cr.inc_tier, cr.on_hin, cr.on_txdot, cr.seg_id, cr.sn,
            cr.n_k, cr.n_a, cr.n_b, cr.n_c, cr.n_noinj, cr.road_type if freeway else (cr["road_part"].eq(2).map({True: 3, False: 0}) if "road_part" in cr.columns else [0] * len(cr)),
            cr.light, cr.factors, cr.ksi_people):
        if g is None or g.is_empty:
            continue
        pts.append([round(g.y, 5), round(g.x, 5), int(bool(sv)), int(bool(ft)),
                    int(bool(pd_)), int(bool(bk)), int(yr) if pd.notna(yr) else None,
                    dt if isinstance(dt, str) else None,
                    int(hr) if pd.notna(hr) else None,
                    round(float(yl), 1) if pd.notna(yl) and yl else 0,
                    dist if isinstance(dist, str) else None,
                    int(it) if pd.notna(it) else None,
                    1 if oh else 0,
                    1 if otx else 0,
                    sid if isinstance(sid, str) else None,
                    int(snv) if pd.notna(snv) else None,
                    int(nk), int(na), int(nb), int(nc), int(nn),
                    int(lt), int(fc), kp if isinstance(kp, str) and kp else None] + [int(rt)])   # 24 road type: 0 street, 3 frontage road, 1 freeway, 2 toll road
    return pts


pts = crash_rows(_city_all)
cpath = DOCS / "crash_points.json"
cpath.write_text(json.dumps(pts, separators=(",", ":")))
print(f"Wrote {len(pts):,} crash points -> {cpath} ({cpath.stat().st_size/1e6:.1f} MB)")
# freeway / tollway / ramp / frontage crashes for the dashboard's optional toggle
# (off by default; loaded only when a visitor turns it on). Same 21 fields plus
# road_type (1 = TxDOT freeway/ramp/frontage, 2 = toll-road main lanes or ramps).
_fpath = cfg.processed("freeway_crashes.gpkg")
if _fpath.exists():
    _fw = gpd.read_file(_fpath, layer="crashes")
    if "road_part" in _fw.columns:   # frontage roads are in the default view now
        _fw = _fw[~_fw["road_part"].eq(2)].copy()
    # Freeway sections (build_freeway.py; FREEWAY_PLAN.md): main-lane crashes go to main-lane
    # sections, ramp and connector crashes (road part 3, 4, 5) to ramps. A section on the
    # crash's own highway (CRIS Hwy_Nbr vs the section's route numbers) is preferred, so a
    # crash at an interchange lands on its own freeway; otherwise the nearest of the right
    # kind, then the nearest of any kind; all within 250 ft.
    _fsec_path = cfg.processed("freeway_sections.gpkg")
    if _fsec_path.exists():
        sec = gpd.read_file(_fsec_path, layer="sections").to_crs(seg.crs)
        fwc = _fw.to_crs(seg.crs)
        fwc["_kind"] = fwc["road_part"].isin([3, 4, 5]).map({True: "ramp", False: "main"})
        fwc["seg_id"] = None
        sec["_nums"] = sec["hwy"].fillna("").str.split()

        def _nearest(crashes, cands):
            if crashes.empty or cands.empty:
                return pd.Series(dtype=object)
            j = gpd.sjoin_nearest(crashes[["geometry"]], cands[["seg_id", "geometry"]], how="left",
                                  max_distance=250, distance_col="_d")
            j = j[~j.index.duplicated(keep="first")]
            return j["seg_id"].dropna()

        nbr = fwc["hwy_nbr"] if "hwy_nbr" in fwc.columns else pd.Series(0, index=fwc.index)
        for kind in ("main", "ramp"):
            ck = fwc[fwc["_kind"].eq(kind)]
            sk = sec[sec["kind"].eq(kind)]
            for n in sorted(set(nbr[ck.index]) - {0}):            # 1. same highway, same kind
                on_route = sk[sk["_nums"].apply(lambda xs, n=str(n): n in xs)]
                hit = _nearest(ck[nbr[ck.index].eq(n)], on_route)
                fwc.loc[hit.index, "seg_id"] = hit.values
            left = ck[fwc.loc[ck.index, "seg_id"].isna()]          # 2. nearest of the same kind
            hit = _nearest(left, sk)
            fwc.loc[hit.index, "seg_id"] = hit.values
        left = fwc[fwc["seg_id"].isna()]                           # 3. nearest of any kind
        hit = _nearest(left, sec)
        fwc.loc[hit.index, "seg_id"] = hit.values
        # milepost placement: the point at the crash report's DFO on its highway (CRIS Hwy_Sys,
        # Hwy_Nbr, Dfo), then of that highway's main-lane sections within 300 ft of that point,
        # the one nearest the crash's own coordinates (the right direction). Kept only when the
        # milepost point and the coordinates agree within a quarter mile; otherwise the
        # coordinate-based assignment above stands.
        try:
            routes = fetch_txdot_dfo()
            _rc = ["Crash_ID", "Hwy_Sys", "Hwy_Nbr", "Dfo"]
            _rw = pd.concat([pd.read_csv(f, usecols=lambda c: c in _rc, dtype=str, low_memory=False)
                             for f in glob.glob(str(cfg.CRIS / "Houston_Crash_*" / "*crash_*.csv"))],
                            ignore_index=True).drop_duplicates("Crash_ID")
            _rw["Crash_ID"] = pd.to_numeric(_rw["Crash_ID"], errors="coerce")
            _rw = _rw.set_index("Crash_ID")
            main_sec = sec[sec["kind"].eq("main")]
            sidx = main_sec.sindex
            n_try = n_dfo = n_far = n_moved = 0
            for i in fwc.index[fwc["_kind"].eq("main")]:
                cid = fwc.at[i, "Crash_ID"]
                if cid not in _rw.index:
                    continue
                row = _rw.loc[cid]
                try:
                    sys_, nbr_, dfo_ = str(row["Hwy_Sys"]), int(row["Hwy_Nbr"]), float(row["Dfo"])
                except (TypeError, ValueError):
                    continue
                n_try += 1
                pt = dfo_point(routes, (sys_, nbr_), dfo_)
                if pt is None:
                    continue
                P, C = Point(pt), fwc.at[i, "geometry"]
                if P.distance(C) > 1320:
                    n_far += 1
                    continue
                hits = main_sec.iloc[list(sidx.query(P.buffer(300)))]
                hits = hits[hits["_nums"].apply(lambda xs: str(nbr_) in xs)]
                if hits.empty:
                    continue
                best = hits.geometry.distance(C).idxmin()
                sid = hits.at[best, "seg_id"]
                n_dfo += 1
                if fwc.at[i, "seg_id"] != sid:
                    n_moved += 1
                fwc.at[i, "seg_id"] = sid
            print(f"Milepost placement: {n_try:,} main-lane crashes with a milepost; placed by milepost {n_dfo:,}; "
                  f"milepost and coordinates over 1/4 mi apart (kept coordinates) {n_far:,}; section changed {n_moved:,}")
        except Exception as ex:   # no network / no CRIS files: the coordinate-based placement stands
            print(f"WARNING: milepost placement skipped ({type(ex).__name__}: {ex})")
        _fw["seg_id"] = fwc["seg_id"].values
        _secnums = dict(zip(sec["seg_id"], sec["_nums"]))
        print(f"Freeway crashes assigned to a section or ramp: {int(_fw['seg_id'].notna().sum()):,} of {len(_fw):,} "
              f"({100*_fw['seg_id'].notna().mean():.1f}%); on their own highway's section: "
              f"{int(sum(1 for i, sid in _fw['seg_id'].items() if isinstance(sid, str) and str(nbr[i]) in _secnums[sid])):,}")

        # section features for the page (loaded with the Freeways toggle), counts like the streets'
        a = _fw[_fw["seg_id"].notna()]
        grp = a.groupby("seg_id")
        cnt = pd.DataFrame({
            "n_crash": grp.size(), "n_injury": grp["any_injury"].sum(), "n_severe": grp["severe"].sum(),
            "n_fatal": grp["fatal"].sum(), "n_ped": grp["involves_ped"].sum(), "n_bike": grp["involves_bike"].sum(),
            "n_ped_severe": a[a["severe"]].groupby("seg_id")["involves_ped"].sum(),
            "n_bike_severe": a[a["severe"]].groupby("seg_id")["involves_bike"].sum()})
        sec = sec.join(cnt, on="seg_id")
        for c_ in cnt.columns:
            sec[c_] = sec[c_].fillna(0).astype(int)
        sec["on_txdot"] = ~sec["toll"].astype(bool)
        sec["on_hin"] = False
        mids = gpd.GeoDataFrame(geometry=sec.geometry.representative_point(), crs=sec.crs).to_crs(4326)
        sec["district"] = None
        if districts_4326 is not None:
            jj = gpd.sjoin_nearest(mids, districts_4326[["DISTRICT", "geometry"]].to_crs(4326), how="left")
            sec["district"] = jj[~jj.index.duplicated()]["DISTRICT"].values
        sec["sn"] = None
        if sn_4326 is not None:
            jj = gpd.sjoin(mids, sn_4326[["POLYID", "geometry"]], how="left", predicate="within")
            sec["sn"] = pd.array(pd.to_numeric(jj[~jj.index.duplicated()]["POLYID"].values, errors="coerce"), dtype="Int64")
        sec["length_ft"] = sec["length_ft"].round().astype(int)
        for c_ in ("lanes_final", "roadway_width_ft", "posted_speed_mph", "sidewalk_presence", "adt"):
            sec[c_] = None
        sec["geometry"] = sec.geometry.simplify(25, preserve_topology=False)
        fs = sec.to_crs(4326)[[c for c in WEB_KEEP if c not in ("mid_ft", "trim_a", "trim_b")] + ["label", "geometry"]]   # whole sections, no intersections
        fsp = DOCS / "freeway_sections.geojson"
        if fsp.exists():
            fsp.unlink()
        fs.to_file(fsp, driver="GeoJSON", COORDINATE_PRECISION=5)
        print(f"Wrote {len(fs):,} freeway sections and ramps -> {fsp.name} ({fsp.stat().st_size/1e6:.1f} MB)")
    fpts = crash_rows(_fw, freeway=True)
    fcp = DOCS / "freeway_crash_points.json"
    fcp.write_text(json.dumps(fpts, separators=(",", ":")))
    print(f"Wrote {len(fpts):,} freeway crash points -> {fcp} ({fcp.stat().st_size/1e6:.1f} MB)")
else:
    print("WARNING: freeway_crashes.gpkg missing (rerun build_crashes.py); freeway toggle data not written")

# council district polygons for the dashboard dropdown + outline + zoom (city build)
if districts_4326 is not None:
    dd = districts_4326.to_crs(2278)
    dd["geometry"] = dd.geometry.simplify(150, preserve_topology=True)
    dd = dd.to_crs(4326)
    keep_cols = [c for c in ("DISTRICT", "MEMBER") if c in dd.columns] + ["geometry"]
    dpath = DOCS / "districts.geojson"
    if dpath.exists():
        dpath.unlink()
    dd[keep_cols].to_file(dpath, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"Wrote {len(dd)} districts -> {dpath} ({dpath.stat().st_size/1e3:.0f} KB)")

# Super Neighborhood polygons for the dashboard dropdown + outline + zoom
if sn_4326 is not None:
    ss = sn_4326.to_crs(2278)
    ss["geometry"] = ss.geometry.simplify(150, preserve_topology=True)
    ss = ss.to_crs(4326)
    spath = DOCS / "superneighborhoods.geojson"
    if spath.exists():
        spath.unlink()
    ss[["POLYID", "SNBNAME", "geometry"]].to_file(spath, driver="GeoJSON", COORDINATE_PRECISION=5)
    print(f"Wrote {len(ss)} Super Neighborhoods -> {spath} ({spath.stat().st_size/1e3:.0f} KB)")

# Census block groups for the income panel's rate per resident: one row per block
# group inside the boundary, [lat, lon, pop, inc_tier, district, sn]. A block group
# that crosses the city line keeps the share of its population equal to the share
# of its land inside (area-weighted). Point = a representative point of the inside
# part, tagged to a council district and Super Neighborhood like a crash, so the
# page can total residents for any area filter.
_bgcache = cfg.external("census_bg.gpkg")
if _bgcache.exists() and "pop" in seg.columns:
    bg = gpd.read_file(_bgcache)[["GEOID", "geometry"]].to_crs(seg.crs)
    bg["GEOID"] = bg["GEOID"].astype(str)
    _bgattr = (seg.dropna(subset=["bg_geoid"]).assign(bg_geoid=lambda d: d["bg_geoid"].astype(str))
                  .groupby("bg_geoid")[["pop", "median_hh_income"]].first())
    bg = bg.join(_bgattr, on="GEOID").dropna(subset=["pop"])
    inside = bg.geometry.intersection(_bnd)
    share = inside.area / bg.geometry.area
    bg = bg.assign(geometry=inside, pop=(bg["pop"] * share).round())
    bg = bg[(share > 0.01) & (bg["pop"] > 0)].copy()
    bg["geometry"] = bg.geometry.representative_point()
    bg["inc_tier"] = pd.to_numeric(bg["median_hh_income"], errors="coerce").map(inc_tier)
    bg = bg.to_crs(4326)
    bg["district"] = None
    if districts_4326 is not None:
        j = gpd.sjoin(bg[["geometry"]], districts_4326[["DISTRICT", "geometry"]], how="left", predicate="within")
        bg["district"] = j[~j.index.duplicated()]["DISTRICT"].values
    bg["sn"] = None
    if sn_4326 is not None:
        j = gpd.sjoin(bg[["geometry"]], sn_4326[["POLYID", "geometry"]], how="left", predicate="within")
        bg["sn"] = pd.to_numeric(j[~j.index.duplicated()]["POLYID"].values, errors="coerce")
    rows = [[round(g.y, 5), round(g.x, 5), int(p), int(t) if pd.notna(t) else None,
             d if isinstance(d, str) else None, int(s) if pd.notna(s) else None]
            for g, p, t, d, s in zip(bg.geometry, bg["pop"], bg["inc_tier"], bg["district"], bg["sn"])]
    bpath = DOCS / "blockgroups.json"
    bpath.write_text(json.dumps({"cols": ["lat", "lon", "pop", "inc_tier", "district", "sn"], "rows": rows},
                                separators=(",", ":")))
    print(f"Wrote {len(rows):,} block groups ({int(bg['pop'].sum()):,} residents) -> {bpath.name} "
          f"({bpath.stat().st_size/1e3:.0f} KB)")
else:
    print("WARNING: block-group cache or segment population missing; blockgroups.json not written")
