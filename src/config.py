"""Central study-area configuration — the one place that knows *where* we study.

Retarget the entire pipeline to a different area (another council district, or
the full City of Houston) in two steps:

  1. Drop the new outline at  data/raw/<AREA>_boundary.geojson
  2. Change AREA below to that slug

…then rerun the pipeline. The clip polygon, the query bounding box, and every
output filename all follow from here, so nothing else needs editing. Output
files are prefixed with AREA, so several areas can be built side by side without
colliding (e.g. district_c_segments.gpkg vs district_h_segments.gpkg).

Published web-app files in docs/ keep fixed names (segments.geojson, etc.) —
one built site per area; that's a deployment choice, not a pipeline one.
"""

from pathlib import Path

import geopandas as gpd

# --- the study area -----------------------------------------------------------
AREA = "houston"             # slug -> output filenames + boundary file
AREA_LABEL = "Houston"       # human-readable, for report/title text
SEG_PREFIX = "H"             # stable segment-id prefix (e.g. H-00001)

# --- coordinate reference systems ---------------------------------------------
CRS_FT = 2278     # EPSG:2278 Texas State Plane South-Central (US ft) — distance work
CRS_WGS = 4326    # lon/lat (WGS84) — web maps, source data

# --- directories --------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
EXTERNAL = ROOT / "data" / "external"
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
CRIS = RAW / "CRIS"          # raw TxDOT crash extracts (city-wide, gitignored)

# --- study-area boundary ------------------------------------------------------
BOUNDARY = RAW / f"{AREA}_boundary.geojson"


def boundary(crs=CRS_WGS):
    """The study-area polygon as a GeoDataFrame in the requested CRS."""
    return gpd.read_file(BOUNDARY).to_crs(crs)


def boundary_geom(crs=CRS_WGS):
    """The study-area polygon geometry (first feature) in the requested CRS."""
    return boundary(crs).geometry.iloc[0]


def bbox_4326(pad=0.005):
    """(minx, miny, maxx, maxy) lon/lat envelope of the study area.

    Derived from the boundary (no longer hand-coded per district), with a small
    pad (~0.005° ≈ 500 m) so city-data pulls catch features sitting right on the
    edge before the precise spatial clip. Replaces the old per-district BBOX.
    """
    minx, miny, maxx, maxy = (float(v) for v in boundary(CRS_WGS).total_bounds)
    return (round(minx - pad, 4), round(miny - pad, 4),
            round(maxx + pad, 4), round(maxy + pad, 4))


# --- area-scoped output paths -------------------------------------------------
def processed(name):
    """data/processed/<AREA>_<name>  (e.g. processed('segments.gpkg'))."""
    return PROCESSED / f"{AREA}_{name}"


def external(name):
    """data/external/<AREA>_<name> — area-scoped cache so areas don't collide."""
    return EXTERNAL / f"{AREA}_{name}"


def raw(name):
    """data/raw/<AREA>_<name>  (area-scoped raw artifacts, e.g. OSM edge dumps)."""
    return RAW / f"{AREA}_{name}"
