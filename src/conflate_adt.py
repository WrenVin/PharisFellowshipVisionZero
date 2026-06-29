"""Conflate traffic volume (ADT) onto the study area's segments — the exposure confounder.

Source: Houston Public Works Traffic_gx service.
  - Count stations: layer 4 (Major Thoroughfare ADT) + layer 5 (Local Street ADT),
    point features with a GlobalID.
  - Counts: table 22 (Traffic Count Assignments), joined to stations by
    LocationID = station GlobalID. Carries ADT, reading Date, and (bonus)
    PercentileSpeed85 = 85th-percentile OPERATING speed (the design->severity
    mediator in the project DAG).

Pipeline:
  1. Fetch the study area's stations (both layers) + all ADT-bearing assignments.
  2. Per station: keep the MOST RECENT valid reading (Status Complete,
     Outcome Success) -> current ADT, plus most recent non-null op speed.
  3. Assign each station to its nearest segment within STATION_TOL_FT; a
     segment's measured ADT = mean of stations on it. (`adt_source = measured`)
  4. Propagate along corridors: segments with no station but sharing a street
     NAME with measured segments inherit that street's median ADT.
     (`adt_source = street_median`)
  5. Leave the rest NaN (no class-imputation here — ADT is a confounder;
     imputation is a modeling decision, kept explicit and separate).

Operating speed (op_speed_85_mph) is carried the same way but is sparser; it
is the mediator, NOT a predictor to adjust for — flagged in the codebook.
"""


import geopandas as gpd
import numpy as np
import pandas as pd

from arcgis_fetch import fetch_layer, fetch_table
from conflate_util import snap_match  # noqa: F401  (kept for parity / future use)

import config as cfg
ROOT, PROCESSED, EXTERNAL, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.EXTERNAL, cfg.REPORTS

BASE = "https://geogimstest.houstontx.gov/arcgis/rest/services/TDO/Traffic_gx/MapServer"
BBOX = cfg.bbox_4326()
STATION_TOL_FT = 150  # max distance station point -> segment centerline

OWNED = ["adt", "adt_source", "adt_year", "n_adt_stations",
         "op_speed_85_mph", "op_speed_source"]

seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")
seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])
print(f"Segments: {len(seg):,}")

# --- 1. fetch + cache stations and ADT readings -------------------------------
EXTERNAL.mkdir(parents=True, exist_ok=True)
st_cache = cfg.external("adt_stations.gpkg")
a_cache = cfg.external("adt_assignments.parquet")
if st_cache.exists() and a_cache.exists():
    stations = gpd.read_file(st_cache)
    assign = pd.read_parquet(a_cache)
else:
    sf = "StationID,GlobalID,ADDRESS,SEGMENT,COLLECTIONTYPE"
    major = fetch_layer(f"{BASE}/4", out_fields=sf, bbox_4326=BBOX, out_sr=2278)
    local = fetch_layer(f"{BASE}/5", out_fields=sf, bbox_4326=BBOX, out_sr=2278)
    stations = gpd.GeoDataFrame(pd.concat([major, local], ignore_index=True),
                                crs=2278)
    assign = fetch_table(
        f"{BASE}/22", where="ADT IS NOT NULL",
        out_fields="LocationID,ADT,Date,Status,Outcome,PercentileSpeed85",
    )
    stations.to_file(st_cache, driver="GPKG")
    assign.to_parquet(a_cache)
# clip stations to the actual district polygon (+200 ft for boundary roads);
# the bbox pull included many out-of-district stations
boundary = cfg.boundary(2278)
poly = boundary.geometry.iloc[0].buffer(200)
stations = stations[stations.within(poly)].copy()
print(f"Stations in {cfg.AREA_LABEL}: {len(stations):,} | ADT readings (citywide): {len(assign):,}")

# --- 2. most recent valid reading per station --------------------------------
a = assign[(assign["Status"] == "Complete") & (assign["Outcome"] == "Success")].copy()
a = a[a["ADT"].notna() & (a["ADT"] > 0)]
a["year"] = pd.to_datetime(a["Date"], unit="ms", errors="coerce").dt.year
a = a.sort_values("Date")
latest = a.groupby("LocationID").tail(1).set_index("LocationID")
# most recent op-speed reading (may be a different, newer row than ADT)
ops = a[a["PercentileSpeed85"].notna()].groupby("LocationID").tail(1)
ops = ops.set_index("LocationID")["PercentileSpeed85"]

stations = stations.merge(
    latest[["ADT", "year"]], left_on="GlobalID", right_index=True, how="left"
)
stations["op_speed"] = stations["GlobalID"].map(ops)
stations = stations[stations["ADT"].notna()].copy()
print(f"Stations with a current ADT reading: {len(stations):,}")

# --- 3. assign stations to nearest segment -----------------------------------
near = gpd.sjoin_nearest(
    stations[["ADT", "op_speed", "year", "geometry"]],
    seg[["seg_id", "geometry"]], how="left", max_distance=STATION_TOL_FT,
    distance_col="_d",
).dropna(subset=["seg_id"])

g = near.groupby("seg_id")
measured = pd.DataFrame({
    "adt": g["ADT"].mean().round(0),
    "adt_year": g["year"].max(),
    "n_adt_stations": g.size(),
    "op_speed_85_mph": g["op_speed"].mean(),
})
seg = seg.merge(measured, on="seg_id", how="left")
seg["adt_source"] = np.where(seg["adt"].notna(), "measured", None)
seg["op_speed_source"] = np.where(seg["op_speed_85_mph"].notna(), "measured", None)

# --- 4. corridor propagation by street name ----------------------------------
named = seg["name"].notna()
street_med = (
    seg[named & seg["adt"].notna()].groupby("name")["adt"].median()
)
fill = seg["adt"].isna() & named & seg["name"].isin(street_med.index)
seg.loc[fill, "adt"] = seg.loc[fill, "name"].map(street_med).round(0)
seg.loc[fill, "adt_source"] = "street_median"

out = cfg.processed("segments_enriched.gpkg")
seg.to_file(out, layer="segments", driver="GPKG")
print(f"Saved {out}")

# --- 5. report ----------------------------------------------------------------
def pct(m):
    return round(100 * m.mean(), 1)

arterial = seg["highway"].isin(["primary", "secondary", "tertiary"])
have = seg["adt"].notna()
q = seg.loc[have, "adt"].quantile([.25, .5, .75, .95]).round(0)
report = f"""# Traffic Volume (ADT) Conflation Report

Generated by `src/conflate_adt.py`. Source: Houston Public Works Traffic_gx
count stations (layers 4 & 5) joined to count readings (table 22) by
LocationID. Most recent valid reading per station; stations snapped to the
nearest segment within {STATION_TOL_FT} ft; then ADT propagated along
same-named corridors.

## Coverage

| `adt_source` | segments | share |
|---|---|---|
| measured (station on the segment) | {int((seg.adt_source=='measured').sum()):,} | {pct(seg.adt_source=='measured')}% |
| street_median (corridor propagation) | {int((seg.adt_source=='street_median').sum()):,} | {pct(seg.adt_source=='street_median')}% |
| none (left blank) | {int(seg.adt.isna().sum()):,} | {pct(seg.adt.isna())}% |

- **ADT present on {pct(have)}% of segments overall.** Coverage *within* each
  road class: primary {pct(have[seg.highway=='primary'])}%,
  secondary {pct(have[seg.highway=='secondary'])}%,
  tertiary {pct(have[seg.highway=='tertiary'])}%,
  residential {pct(have[seg.highway=='residential'])}%
  — counts concentrate on the major roads, as expected.
- {cfg.AREA_LABEL} has ~{len(stations):,} count stations (the genuine measurement density);
  {int(seg.n_adt_stations.fillna(0).sum()):,} station-readings mapped onto segments.
- ADT distribution (segments with a value): p25={q[.25]:,.0f}, median={q[.5]:,.0f}, p75={q[.75]:,.0f}, p95={q[.95]:,.0f} vehicles/day.
- Reading recency: years {int(seg.adt_year.min())}–{int(seg.adt_year.max())}.

## Operating speed (bonus — the DAG mediator, NOT a confounder)

- `op_speed_85_mph` (85th-percentile measured speed) present on {pct(seg.op_speed_85_mph.notna())}% of segments ({int(seg.op_speed_85_mph.notna().sum()):,}).
- This is the design->severity **mediator**: model it as the mechanism, do
  NOT adjust for it. Stored for that purpose, not as a risk predictor.

## Notes

- ADT is measured at sample points; most local streets have no station, hence
  the lower overall coverage. We deliberately do NOT class-impute ADT here —
  imputing a confounder is a modeling decision, kept explicit/separate.
- Station ADT is treated as total (both directions) at the count location.
- Reading is the most recent per station (some stations span 2010–2026).
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "adt_conflation_report.md").write_text(report)
print(report)
