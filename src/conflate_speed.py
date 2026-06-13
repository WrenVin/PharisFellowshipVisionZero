"""Conflate City of Houston posted speed limits onto District C segments.

Source: Houston Public Works "Speed Limit" layer (TDO/Traffic_gx/2), a street
centerline network with POSTED_SPEED. Published via the city GeoHub from a
staging host (geogimstest); production host was unreachable on 2026-06-12.

Match method (geometry differs between OSM and the city network, so no exact
join): sample 5 points along each of our segments, snap each to the nearest
city speed line within TOL_FT, take the modal POSTED_SPEED among matched
points. Require >= MIN_FRAC of points to match before trusting it.

Speed fill priority (recorded in `speed_source`):
  city                 - matched to the city Speed Limit layer (authoritative)
  osm                  - no city match, but OSM had a posted maxspeed
  default_30_local     - no match, residential/local class -> Texas urban
                         prima facie default (30 mph)
  default_30_unposted  - no match, higher OSM class but NOT on the city's
                         posted-thoroughfare network (median ~1100 ft from any
                         city speed line) -> legally also 30 mph by default,
                         flagged separately for sensitivity testing

Diagnostic (2026-06-12): unmatched higher-class segments are not near any city
speed line (median 1111 ft), i.e. genuinely unposted, not a match failure.
Under TX Transportation Code 545.352 an unposted urban street is 30 mph.

Enrichment model: reads the enriched file if it exists, else the clean file,
adds columns, writes data/processed/district_c_segments_enriched.gpkg. This
is the canonical analysis file once conflation has begun.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from arcgis_fetch import fetch_layer

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "external"
REPORTS = ROOT / "reports"

SPEED_URL = "https://geogimstest.houstontx.gov/arcgis/rest/services/TDO/Traffic_gx/MapServer/2"
BBOX = (-95.51, 29.66, -95.37, 29.85)  # District C envelope, lon/lat
TOL_FT = 60          # max snap distance, segment sample point -> city line
MIN_FRAC = 0.4       # >= this share of a segment's 5 points must match
LOCAL_CLASSES = {"residential", "unclassified", "living_street"}
TX_DEFAULT_MPH = 30  # Texas urban prima facie limit where unposted

# --- load network (enriched if present, else clean) ---------------------------
enriched = PROCESSED / "district_c_segments_enriched.gpkg"
src = enriched if enriched.exists() else PROCESSED / "district_c_segments_clean.gpkg"
seg = gpd.read_file(src, layer="segments")
# idempotent: drop any columns from a previous run of this script
OWNED = ["maxspeed_city", "match_frac", "city_name", "posted_speed_mph",
         "speed_source", "speed_name_match"]
seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])
print(f"Segments: {len(seg):,} (from {src.name})")

# --- fetch + cache the city speed layer ---------------------------------------
EXTERNAL.mkdir(parents=True, exist_ok=True)
cache = EXTERNAL / "houston_speed_limit_districtC.gpkg"
if cache.exists():
    speed = gpd.read_file(cache)
else:
    speed = fetch_layer(
        SPEED_URL,
        out_fields="STREETNAME,POSTED_SPEED,NO_OF_LANES,AVG_LANE_WIDTH,MEDIAN_TYPE,MTFP_CLASSIFICATION",
        bbox_4326=BBOX,
        out_sr=2278,
    )
    speed.to_file(cache, driver="GPKG")
speed = speed[speed["POSTED_SPEED"].notna() & (speed["POSTED_SPEED"] > 0)].copy()
speed = speed.reset_index(drop=True)
print(f"City speed lines (District C, posted>0): {len(speed):,}")

# --- sample points along each segment, snap to nearest city line --------------
FRACS = [0.1, 0.3, 0.5, 0.7, 0.9]
pts = []
pid = 0
for sid, geom in zip(seg["seg_id"], seg.geometry):
    for f in FRACS:
        p = geom.interpolate(f, normalized=True)
        pts.append({"pid": pid, "seg_id": sid, "geometry": Point(p.x, p.y)})
        pid += 1
pts = gpd.GeoDataFrame(pts, crs=seg.crs)

joined = gpd.sjoin_nearest(
    pts, speed[["POSTED_SPEED", "STREETNAME", "geometry"]],
    how="left", max_distance=TOL_FT, distance_col="dist_ft",
)
# a sample point may tie-match >1 line; keep the nearest per point
joined = joined.sort_values("dist_ft").drop_duplicates("pid")
joined = joined.groupby("seg_id")

def _agg(g):
    matched = g["POSTED_SPEED"].notna()
    frac = matched.mean()
    if frac < MIN_FRAC:
        return pd.Series({"maxspeed_city": np.nan, "match_frac": frac,
                          "city_name": None})
    modal = g.loc[matched, "POSTED_SPEED"].mode()
    name = g.loc[matched, "STREETNAME"].mode()
    return pd.Series({
        "maxspeed_city": float(modal.iloc[0]),
        "match_frac": frac,
        "city_name": name.iloc[0] if len(name) else None,
    })

agg = joined.apply(_agg)
seg = seg.merge(agg, on="seg_id", how="left")

# --- fill priority + provenance -----------------------------------------------
is_local = seg["highway"].isin(LOCAL_CLASSES)
posted, source = [], []
for city, osm, loc in zip(seg["maxspeed_city"], seg["maxspeed_mph"], is_local):
    if pd.notna(city):
        posted.append(city); source.append("city")
    elif pd.notna(osm):
        posted.append(float(osm)); source.append("osm")
    elif loc:
        posted.append(float(TX_DEFAULT_MPH)); source.append("default_30_local")
    else:
        # unposted higher-class street -> TX prima facie 30 mph (flagged)
        posted.append(float(TX_DEFAULT_MPH)); source.append("default_30_unposted")
seg["posted_speed_mph"] = posted
seg["speed_source"] = source

# name-agreement confidence flag (normalize: upper, strip common suffixes)
def _norm(n):
    if not isinstance(n, str):
        return ""
    n = n.upper()
    for suf in (" ROAD", " RD", " STREET", " ST", " DRIVE", " DR", " BOULEVARD",
                " BLVD", " AVENUE", " AVE", " LANE", " LN", " PARKWAY", " PKWY"):
        n = n.replace(suf, "")
    return n.strip()
seg["speed_name_match"] = [
    bool(a) and bool(b) and (_norm(a) in _norm(b) or _norm(b) in _norm(a))
    for a, b in zip(seg["name"], seg["city_name"])
]

out = PROCESSED / "district_c_segments_enriched.gpkg"
seg.to_file(out, layer="segments", driver="GPKG")
print(f"Saved {out}")

# --- report -------------------------------------------------------------------
sc = seg["speed_source"].value_counts()
mi = lambda mask: seg.loc[mask, "length_ft"].sum() / 5280
def cov_by(mask_name, mask):
    s = seg[mask]
    return {
        "n": len(s), "miles": round(s["length_ft"].sum() / 5280, 1),
        "city_pct": round(100 * (s["speed_source"] == "city").mean(), 1),
    }
arterial = seg["highway"].isin(["primary", "secondary", "tertiary"])
dist = seg.loc[seg["speed_source"] == "city", "posted_speed_mph"].value_counts().sort_index()
namechk = seg[seg["speed_source"] == "city"]["speed_name_match"].mean()

report = f"""# Speed Limit Conflation Report

Generated by `src/conflate_speed.py`. Source: Houston Public Works Speed Limit
layer (`TDO/Traffic_gx/2`, city GeoHub; staging host `geogimstest`). Matched by
snapping 5 sample points per segment to the nearest city speed line within
{TOL_FT} ft (>= {int(MIN_FRAC*100)}% of points must match).

## Coverage by source

| `speed_source` | segments | miles |
|---|---|---|
| city (authoritative posted) | {sc.get('city',0):,} | {mi(seg.speed_source=='city'):.1f} |
| osm (OSM had a posted value) | {sc.get('osm',0):,} | {mi(seg.speed_source=='osm'):.1f} |
| default_30_local (TX default, local class) | {sc.get('default_30_local',0):,} | {mi(seg.speed_source=='default_30_local'):.1f} |
| default_30_unposted (TX default, unposted collector/arterial) | {sc.get('default_30_unposted',0):,} | {mi(seg.speed_source=='default_30_unposted'):.1f} |

- **`posted_speed_mph` now populated for {100*seg.posted_speed_mph.notna().mean():.1f}% of segments** (was 14% OSM-only).
- Authoritative (city-posted) coverage: {100*(seg.speed_source=='city').mean():.1f}% of segments, {round(100*(seg.loc[arterial,'speed_source']=='city').mean(),1)}% of arterials/collectors.
- Name-agreement on city matches (sanity check on the spatial join): {100*namechk:.1f}%.
- **Diagnostic:** unmatched higher-class segments sit a median ~1,100 ft from any city speed line — genuinely unposted (not a match failure), so they take the TX 30 mph default. `default_30_unposted` is the set to sensitivity-test if posted speed ever feeds a published number.

## Posted speed distribution (city-matched segments, mph)

{dist.to_string()}

## Notes

- `posted_speed_mph` = final value; `speed_source` records where each came from.
- `maxspeed_city` = raw city match; `maxspeed_mph` = original OSM posted speed (kept).
- Local streets default to {TX_DEFAULT_MPH} mph (Texas prima facie urban limit) — this is the legal default, not a measurement.
- Still posted, not OPERATING speed (the model's mediator). Operating speed needs a different source (speed studies / probe data); Traffic_gx layers 16/17 (Pre/Post Speed Study) may help later.
- City layer also carries lanes, lane width, median type — staged for later conflation steps, not used here.
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "speed_conflation_report.md").write_text(report)
print(report)
