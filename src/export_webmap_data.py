"""Export segment + boundary GeoJSON for the interactive web map (docs/).

The web app (docs/index.html) loads these and does all styling/filtering live
in the browser. We keep the files lean: simplify geometry, round coordinates,
round attribute values, and carry only display/filter-relevant columns.
"""

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString

import config as cfg
ROOT, PROCESSED, DOCS, EXTERNAL = cfg.ROOT, cfg.PROCESSED, cfg.DOCS, cfg.EXTERNAL

# TxDOT on-system main lanes (state-owned roads: IH/US/SH/FM/tollway/etc.) — used
# to drop TxDOT-owned roadways from the "city streets" network so we only show
# what the City owns/operates (matches the crash filter Road_Cls_ID==5).
TXDOT_URL = ("https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/"
             "TxDOT_Roadways/FeatureServer/0")

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
    "on_hin": None,    # on the City's official High Injury Network?
    "on_txdot": None,  # TxDOT-owned (state) road vs city-owned?
}

# Only these fields are read by the dashboard (docs/vision-zero.html). Everything
# else in COLS stays out of segments.geojson to keep the browser payload small:
# the full property set is ~52 MB at city scale (vs ~6 MB of geometry) and was
# crashing low-memory tabs. The richer per-segment data lives in the CSV/GPKG.
WEB_KEEP = [
    "seg_id", "name", "road_class", "district", "sn", "on_txdot", "on_hin",
    "n_crash", "n_severe", "n_fatal", "n_ped", "n_ped_severe",
    "n_bike", "n_bike_severe", "length_ft",
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

# friendly road class (collapse *_link to Minor)
base = seg["highway"].str.replace("_link", "", regex=False)
seg["road_class"] = base.map(FRIENDLY_CLASS).fillna("Minor street")
seg.loc[seg["highway"].str.endswith("_link"), "road_class"] = "Minor street"

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
# Full property set -> segments.geojson, used by the Street Explorer (index.html),
# which surfaces every design + demographic field.
out = DOCS / "segments.geojson"
if out.exists():
    out.unlink()
keep.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)
# Super Neighborhood id is added to the SLIM file only (the dashboard filters by
# it); the full Street Explorer file above doesn't use it, so we skip it there.
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

print(f"Wrote {len(keep):,} segments -> {out} ({out.stat().st_size/1e6:.1f} MB)")
print(f"Wrote boundary -> {bpath}")

# crash points for the VZ dashboard "Crash locations" view + the by-month,
# by-time-of-day, years-of-life-lost, and by-neighborhood-income panels:
# [lat, lon, sev, fatal, ped, bike, year, date, hour, yll, district, inc_tier, on_hin, on_txdot, seg_id, sn]
cr = gpd.read_file(cfg.processed("crashes.gpkg"), layer="crashes").to_crs(seg.crs)
# nearest segment carries the crash's neighborhood income (-> tier), on-HIN flag,
# whether its road is TxDOT-owned (state), and the segment id itself (so the
# dashboard can cross-filter every panel to a clicked street/segment). on_txdot
# is a LABEL (for the ownership view), not an exclusion; at-grade arterials stay.
nj = gpd.sjoin_nearest(cr[["geometry"]], seg[["seg_id", "median_hh_income", "on_hin", "on_txdot", "geometry"]], how="left")
nj = nj[~nj.index.duplicated()]
cr["seg_id"] = nj["seg_id"].values
cr["inc_tier"] = pd.Series(pd.to_numeric(nj["median_hh_income"].values,
                                         errors="coerce")).map(inc_tier).values
cr["on_hin"] = pd.Series(nj["on_hin"].values).fillna(False).astype(bool).values
cr["on_txdot"] = pd.Series(nj["on_txdot"].values).fillna(False).astype(bool).values
print(f"Crash points: {int(cr['on_txdot'].sum()):,} on TxDOT-owned (state) roads (kept, labeled)")
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
for g, sv, ft, pd_, bk, yr, dt, hr, yl, dist, it, oh, otx, sid, snv in zip(
        cr.geometry, cr.severe, cr.fatal, cr.involves_ped, cr.involves_bike,
        cr.year, cr.date, cr.hour, cr.yll, cr.district, cr.inc_tier, cr.on_hin, cr.on_txdot, cr.seg_id, cr.sn):
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
                int(snv) if pd.notna(snv) else None])
cpath = DOCS / "crash_points.json"
cpath.write_text(json.dumps(pts, separators=(",", ":")))
print(f"Wrote {len(pts):,} crash points -> {cpath} ({cpath.stat().st_size/1e6:.1f} MB)")

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
