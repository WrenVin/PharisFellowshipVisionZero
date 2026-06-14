"""Conflate adjacent land use onto District C segments — a DAG confounder.

Land use shapes both how a street is built and how much harm occurs there
(commercial/industrial frontage -> more driveways, turning, deliveries, foot
traffic). Source: City of Houston "Land Use (Grouped)" parcel layer (HCAD-
derived). For each segment we summarize the land-use MIX of parcels whose
centroid lies within BUFFER_FT, area-weighted (a big tract outweighs small lots).

Output per segment:
  landuse_dominant   - category with the largest adjacent land area
  pct_residential / pct_commercial / pct_industrial - area shares nearby
  n_parcels_nearby   - parcels contributing
  landuse_source     - 'hcad_parcels' / 'none'
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

import config as cfg
ROOT, PROCESSED, EXTERNAL, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.EXTERNAL, cfg.REPORTS

LU_URL = "https://mycity2.houstontx.gov/pubgis02/rest/services/HoustonMap/Landuse/MapServer/0"
BUFFER_FT = 100
OWNED = ["landuse_dominant", "pct_residential", "pct_commercial",
         "pct_industrial", "n_parcels_nearby", "landuse_source"]

# HCAD group_dscr -> simplified land-use category
GROUP_MAP = {
    "Single-Family Residential": "Residential",
    "Multi-Family Residential": "Residential",
    "Commercial": "Commercial",
    "Office": "Commercial",
    "Industrial": "Industrial",
    "Public & Institutional": "Institutional",
    "Park & Open Spaces": "Parks/Open",
    "Undeveloped": "Undeveloped",
    "Transportation & Utility": "Other",
    "Agriculture Production": "Other",
}


def fetch_parcels(boundary_4326):
    """Page the parcel layer via an OBJECTID cursor (robust to the server's
    transfer-size capping, which breaks resultOffset paging)."""
    geom = json.loads(boundary_4326.to_json())["features"][0]["geometry"]
    rings = {"rings": geom["coordinates"], "spatialReference": {"wkid": 4326}}
    frames, last_oid, total = [], 0, 0
    while True:
        r = requests.post(
            f"{LU_URL}/query",
            data={
                "where": f"OBJECTID > {last_oid}",
                "geometry": json.dumps(rings), "geometryType": "esriGeometryPolygon",
                "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                "outFields": "group_dscr,OBJECTID", "outSR": "2278",
                "orderByFields": "OBJECTID",
                "maxAllowableOffset": "8",  # generalize -> smaller payload
                "resultRecordCount": "4000",
                "f": "geojson",
            }, timeout=120,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
        if not feats:
            break
        g = gpd.GeoDataFrame.from_features(feats, crs=2278)
        frames.append(g)
        last_oid = int(g["OBJECTID"].max())
        total += len(g)
        if total // 20000 != (total - len(g)) // 20000:
            print(f"  ...{total:,} parcels")
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=2278)
    return out.drop_duplicates("OBJECTID").reset_index(drop=True)


seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")
seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])
print(f"Segments: {len(seg):,}")

EXTERNAL.mkdir(parents=True, exist_ok=True)
cache = cfg.external("parcels_landuse.gpkg")
if cache.exists():
    parcels = gpd.read_file(cache)
else:
    boundary = cfg.boundary(4326)
    parcels = fetch_parcels(boundary)
    parcels.to_file(cache, driver="GPKG")
print(f"Parcels: {len(parcels):,}")

# geojson/gpkg round-trip can change field case — find the group column
gcol = next(c for c in parcels.columns if c.lower() == "group_dscr")
parcels["lu"] = parcels[gcol].map(GROUP_MAP).fillna("Unknown")
parcels["area"] = parcels.geometry.area

# A parcel is "adjacent" if its POLYGON comes within BUFFER_FT of the segment
# (centroids miss deep lots whose centroid sits >100 ft back from the street).
seg_buf = seg[["seg_id", "geometry"]].copy()
seg_buf["geometry"] = seg.geometry.buffer(BUFFER_FT)
hit = gpd.sjoin(parcels[["lu", "area", "geometry"]], seg_buf, how="inner",
                predicate="intersects")

# area by land-use category per segment
known = hit[hit["lu"] != "Unknown"]
area_by = known.groupby(["seg_id", "lu"])["area"].sum().unstack(fill_value=0.0)
tot = area_by.sum(axis=1)
shares = area_by.div(tot, axis=0)

res = pd.DataFrame(index=seg["seg_id"])
res["landuse_dominant"] = area_by.idxmax(axis=1).reindex(res.index)
for cat, col in [("Residential", "pct_residential"),
                 ("Commercial", "pct_commercial"),
                 ("Industrial", "pct_industrial")]:
    res[col] = (shares[cat] * 100).round(1).reindex(res.index) if cat in shares else np.nan
res["n_parcels_nearby"] = hit.groupby("seg_id").size().reindex(res.index).fillna(0).astype(int)

seg = seg.merge(res.reset_index(), on="seg_id", how="left")
seg["landuse_source"] = np.where(seg["landuse_dominant"].notna(), "hcad_parcels", "none")

out = cfg.processed("segments_enriched.gpkg")
seg.to_file(out, layer="segments", driver="GPKG")
print(f"Saved {out}")

# --- report -------------------------------------------------------------------
def pct(m):
    return round(100 * m.mean(), 1)

dist = seg["landuse_dominant"].value_counts(dropna=False)
report = f"""# Land Use Conflation Report

Generated by `src/conflate_landuse.py`. Source: City of Houston "Land Use
(Grouped)" parcel layer (HCAD). For each segment, parcels with a centroid
within {BUFFER_FT} ft are summarized area-weighted by category.

## Coverage

- Segments with adjacent land use: **{pct(seg.landuse_source.eq('hcad_parcels'))}%**
  ({int(seg.landuse_source.eq('hcad_parcels').sum()):,} of {len(seg):,});
  {pct(seg.loc[seg.highway.isin(['primary','secondary','tertiary']),'landuse_source'].eq('hcad_parcels'))}% of arterials/collectors.
- Unique parcels used (in-district): {len(parcels):,} (HCAD "stacked" condo
  records, which share a footprint, are de-duplicated — redundant for land use).
- The ~21% with no adjacent parcel are roads through large NON-parceled areas
  (Hermann Park, Rice University, the Texas Medical Center, cemeteries, bayou
  greenways) — nearest parcel a median ~340 ft away. Left as `none`, not
  mislabeled.

## Dominant adjacent land use

{dist.to_string()}

## Adjacent-mix summary (median share where present)

- % residential: median {seg['pct_residential'].median():.0f}%
- % commercial: median {seg['pct_commercial'].median():.0f}%
- % industrial: median {seg['pct_industrial'].median():.0f}%

## Notes

- "Dominant" = land-use category with the largest adjacent land AREA within
  {BUFFER_FT} ft (area-weighted, so a single big tract outweighs many small lots).
- Categories collapse HCAD groups: Residential = single+multi-family;
  Commercial = commercial+office; plus Industrial, Institutional, Parks/Open,
  Undeveloped, Other. Parcels with no HCAD group are excluded from shares.
- Confounder, not mediator: land use influences both design and crash counts.
"""
REPORTS.mkdir(exist_ok=True)
(REPORTS / "landuse_conflation_report.md").write_text(report)
print(report)
