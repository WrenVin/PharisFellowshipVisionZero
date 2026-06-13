"""Reusable fetcher for ArcGIS REST feature layers, paged + clipped to a bbox.

Used to pull City of Houston / Houston Public Works layers (speed limits,
ADT, etc.) into GeoDataFrames. Handles the 2000-record page cap via
resultOffset paging.
"""

import time
from urllib.parse import urlencode

import geopandas as gpd
import requests


def fetch_layer(base_url, out_fields="*", bbox_4326=None, out_sr=2278, page=2000,
                pause=0.2, max_pages=200):
    """Page through an ArcGIS REST layer query and return a GeoDataFrame.

    base_url : .../MapServer/<id>  (no trailing /query)
    bbox_4326 : (minx, miny, maxx, maxy) in lon/lat to clip the pull, or None
    out_sr : EPSG of returned geometry (default 2278, TX State Plane ft)
    """
    params = {
        "where": "1=1",
        "outFields": out_fields,
        "outSR": out_sr,
        "f": "geojson",
        "resultRecordCount": page,
    }
    if bbox_4326 is not None:
        params.update(
            geometry=",".join(map(str, bbox_4326)),
            geometryType="esriGeometryEnvelope",
            inSR=4326,
            spatialRel="esriSpatialRelIntersects",
        )
    frames, offset = [], 0
    for _ in range(max_pages):
        url = f"{base_url}/query?{urlencode({**params, 'resultOffset': offset})}"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        gj = r.json()
        feats = gj.get("features", [])
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs=out_sr))
        if len(feats) < page:
            break
        offset += page
        time.sleep(pause)
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs=out_sr)
    import pandas as pd

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=out_sr)


def fetch_table(base_url, where="1=1", out_fields="*", page=2000, pause=0.2,
                max_pages=200):
    """Page through a non-spatial ArcGIS REST table and return a DataFrame."""
    import pandas as pd

    params = {"where": where, "outFields": out_fields, "returnGeometry": "false",
              "f": "json", "resultRecordCount": page}
    rows, offset = [], 0
    for _ in range(max_pages):
        url = f"{base_url}/query?{urlencode({**params, 'resultOffset': offset})}"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if not feats:
            break
        rows.extend(f["attributes"] for f in feats)
        if len(feats) < page:
            break
        offset += page
        time.sleep(pause)
    return pd.DataFrame(rows)
