"""Shared geometry-conflation helper.

Match a value-carrying line layer (e.g. a City of Houston Traffic_gx layer)
onto our segments when geometries don't align exactly: sample points along
each segment, snap each to the nearest source line within a tolerance, and
aggregate the source attributes per segment.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

DEFAULT_FRACS = (0.1, 0.3, 0.5, 0.7, 0.9)


def snap_match(seg, lines, fields, tol_ft=60, min_frac=0.4, fracs=DEFAULT_FRACS):
    """Aggregate `lines` attributes onto `seg` via point-snapping.

    seg, lines : GeoDataFrames in the same projected CRS (feet).
    fields : dict {source_col: "mode" | "mean" | "median"} to aggregate.
    Returns a DataFrame indexed by seg["seg_id"] with one column per field
    plus `match_frac` (share of the segment's sample points that matched).
    A segment is only given values when match_frac >= min_frac.
    """
    n = len(fracs)
    rows, pid = [], 0
    for sid, geom in zip(seg["seg_id"], seg.geometry):
        for f in fracs:
            p = geom.interpolate(f, normalized=True)
            rows.append({"pid": pid, "seg_id": sid, "geometry": Point(p.x, p.y)})
            pid += 1
    pts = gpd.GeoDataFrame(rows, crs=seg.crs)

    cols = list(fields) + ["geometry"]
    joined = gpd.sjoin_nearest(
        pts, lines[cols], how="left", max_distance=tol_ft, distance_col="_d"
    )
    joined = joined.sort_values("_d").drop_duplicates("pid")

    out = {}
    for sid, g in joined.groupby("seg_id"):
        matched = g[list(fields)].notna().any(axis=1)
        frac = matched.sum() / n
        rec = {"match_frac": round(frac, 3)}
        if frac >= min_frac:
            gm = g[matched]
            for col, how in fields.items():
                vals = gm[col].dropna()
                if vals.empty:
                    rec[col] = np.nan
                elif how == "mode":
                    m = vals.mode()
                    rec[col] = m.iloc[0] if len(m) else np.nan
                elif how == "mean":
                    rec[col] = float(vals.mean())
                elif how == "median":
                    rec[col] = float(vals.median())
                else:
                    raise ValueError(how)
        else:
            for col in fields:
                rec[col] = np.nan
        out[sid] = rec
    return pd.DataFrame.from_dict(out, orient="index").rename_axis("seg_id")
