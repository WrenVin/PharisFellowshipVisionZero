"""Export segment + boundary GeoJSON for the interactive web map (docs/).

The web app (docs/index.html) loads these and does all styling/filtering live
in the browser. We keep the files lean: simplify geometry, round coordinates,
round attribute values, and carry only display/filter-relevant columns.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

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
    where = "SYSTEM='On' AND RDBD_TYPE IN ('Single Roadbed','Left Roadbed','Right Roadbed')"
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
    "on_hin": None,  # is this segment on the City's official High Injury Network?
}

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

# Drop TxDOT-owned roadways from the displayed network: a segment is excluded if
# >=50% of its length runs within 60 ft of a TxDOT on-system main lane (state/US/
# FM highways like S Main/US-90A, SH 6, FM 1093). Keeps the network to streets the
# City owns/operates, consistent with the crash filter (Road_Cls_ID == 5).
seg["on_txdot"] = False
try:
    tx = fetch_txdot_onsys(seg.crs)
    tbuf = tx.buffer(60).union_all()
    tfrac = seg.geometry.intersection(tbuf).length / seg.geometry.length
    seg["on_txdot"] = (tfrac >= 0.5).fillna(False).values
    print(f"TxDOT-owned segments flagged: {int(seg['on_txdot'].sum()):,} "
          f"({100*seg['on_txdot'].mean():.1f}%) — excluded from the city network + crash points")
except Exception as e:
    print(f"WARNING: TxDOT tagging skipped ({type(e).__name__}: {e})")
# NOTE: seg is kept whole here (with on_txdot) so each crash can be matched to its
# nearest road incl. TxDOT ones; the segment EXPORT and crash points then drop the
# TxDOT-owned ones so crashes and roads use one consistent ownership signal.

keep = seg[~seg["on_txdot"]][[c for c in COLS if c in seg.columns] + ["road_class", "geometry"]].copy()
for c, nd in COLS.items():
    if c in keep.columns and nd is not None:
        keep[c] = keep[c].round(nd)
        if nd == 0:
            keep[c] = keep[c].astype("Int64")  # nullable int -> clean JSON
for c in ("oneway", "merged_dual", "on_hin"):
    if c in keep.columns:
        keep[c] = keep[c].astype("boolean")

# simplify in feet (EPSG:2278) for display, then reproject to WGS84.
# 25 ft keeps streets recognizable while roughly halving the payload at
# city scale (75k segments); tune if the web map needs crisper geometry.
keep["geometry"] = keep.geometry.simplify(25, preserve_topology=False)
keep = keep.to_crs(4326)

DOCS.mkdir(exist_ok=True)
out = DOCS / "segments.geojson"
if out.exists():
    out.unlink()
keep.to_file(out, driver="GeoJSON", COORDINATE_PRECISION=5)

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
# [lat, lon, sev, fatal, ped, bike, year, date, hour, yll, district, inc_tier, on_hin]
cr = gpd.read_file(cfg.processed("crashes.gpkg"), layer="crashes").to_crs(seg.crs)
# nearest segment carries the crash's neighborhood income (-> tier), on-HIN flag,
# and whether its road is TxDOT-owned. Match against the FULL network (incl TxDOT)
# so a crash on a TxDOT road is recognised, then dropped below for consistency
# with the segment export.
nj = gpd.sjoin_nearest(cr[["geometry"]], seg[["median_hh_income", "on_hin", "on_txdot", "geometry"]], how="left")
nj = nj[~nj.index.duplicated()]
cr["inc_tier"] = pd.Series(pd.to_numeric(nj["median_hh_income"].values,
                                         errors="coerce")).map(inc_tier).values
cr["on_hin"] = pd.Series(nj["on_hin"].values).fillna(False).astype(bool).values
cr["near_txdot"] = pd.Series(nj["on_txdot"].values).fillna(False).astype(bool).values
n_before = len(cr)
cr = cr[~cr["near_txdot"]].copy()   # drop crashes whose nearest road is TxDOT-owned
print(f"Crash points: dropped {n_before-len(cr):,} on TxDOT-owned roads -> {len(cr):,} city-street crashes")
cr = cr.to_crs(4326)
if districts_4326 is not None:  # council district per crash, for the per-district filter
    cj = gpd.sjoin(cr[["geometry"]], districts_4326[["DISTRICT", "geometry"]],
                   how="left", predicate="within")
    cj = cj[~cj.index.duplicated()]
    cr["district"] = cj["DISTRICT"].values
else:
    cr["district"] = None
pts = []
for g, sv, ft, pd_, bk, yr, dt, hr, yl, dist, it, oh in zip(
        cr.geometry, cr.severe, cr.fatal, cr.involves_ped, cr.involves_bike,
        cr.year, cr.date, cr.hour, cr.yll, cr.district, cr.inc_tier, cr.on_hin):
    if g is None or g.is_empty:
        continue
    pts.append([round(g.y, 5), round(g.x, 5), int(bool(sv)), int(bool(ft)),
                int(bool(pd_)), int(bool(bk)), int(yr) if pd.notna(yr) else None,
                dt if isinstance(dt, str) else None,
                int(hr) if pd.notna(hr) else None,
                round(float(yl), 1) if pd.notna(yl) and yl else 0,
                dist if isinstance(dist, str) else None,
                int(it) if pd.notna(it) else None,
                1 if oh else 0])
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
