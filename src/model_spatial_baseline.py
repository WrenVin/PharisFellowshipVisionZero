"""Modeling step 1: the spatial baseline — reconstruct the HIN from crashes alone.

Builds the *crash-only* hotspot map that stands in for the City's reactive
screening, so the feature model (step 2) has something to diverge from, and
tests whether severe crashes cluster spatially at all (the justification for
spatial methods downstream).

Modeled universe: the full-purpose subset (the segments published to the
dashboard). Segments outside the full-purpose boundary carry ~0.25 crashes/mi
vs 64 inside — CRIS does not code those areas to Houston, so their zeros are
data coverage, not safety, and including them would poison the model.

Methodology is PROVISIONAL (being nailed down): everything here runs under two
spatial-weights definitions so the choice is made on evidence, not by default —
  W1 (primary):    shared-endpoint adjacency — segments touching the same
                   intersection node (u/v) are neighbors. Network-true.
  W2 (alternative): 1,000-ft distance band between segment midpoints. Captures
                   across-the-freeway proximity that network adjacency misses.
Statistics:
  - Global Moran's I on severe-crash counts, and Moran's I on the
    length-adjusted rate (Moran_Rate, base = length_ft): does harm cluster?
  - Local Getis-Ord Gi* (999 conditional permutations) -> per-segment z-scores;
    hotspot = significantly HIGH after FDR correction (alpha = 0.05).
  - Cross-check: hotspot map vs the City's official 2022 HIN (on_hin).

Outputs:
  data/processed/houston_segments_model.gpkg  (modeling layer + hotspot cols)
  reports/spatial_baseline_report.md
  reports/spatial_baseline_map.png
"""

import json
import time
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
from esda.getisord import G_Local
from esda.moran import Moran, Moran_Rate
from libpysal import weights

import config as cfg

PROCESSED, REPORTS, DOCS = cfg.PROCESSED, cfg.REPORTS, cfg.DOCS
BAND_FT = 1000.0     # W2 distance band between segment midpoints
PERMS = 999
ALPHA = 0.05
np.random.seed(42)   # permutation reproducibility


def fdr_threshold(pvals, alpha=ALPHA):
    """Benjamini-Hochberg cutoff: largest p(i) <= alpha * i / n (0 if none)."""
    p = np.sort(np.asarray(pvals))
    n = len(p)
    ok = p <= alpha * (np.arange(1, n + 1) / n)
    return p[ok].max() if ok.any() else 0.0


def load_universe():
    seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")
    vz = json.load(open(DOCS / "segments_vz.geojson"))
    # carry the published layer's flags + display fields (road_class is the
    # friendly class derived at export; sn/district feed cluster-robust SEs
    # and blocked CV downstream)
    pub = {f["properties"]["seg_id"]: f["properties"] for f in vz["features"]}
    seg = seg[seg["seg_id"].isin(pub)].copy()            # full-purpose universe
    for col, cast in [("on_hin", bool), ("on_txdot", bool),
                      ("road_class", str), ("district", str), ("sn", None)]:
        seg[col] = seg["seg_id"].map(
            lambda s, c=col, k=cast: (k(pub[s][c]) if k and pub[s].get(c) is not None
                                      else pub[s].get(c)))
    seg = seg.reset_index(drop=True)
    print(f"Modeling universe: {len(seg):,} segments "
          f"({seg['n_severe'].sum():,} severe crashes; {seg['on_hin'].sum():,} on the official HIN)")
    return seg


def w_shared_endpoint(seg):
    """W1: segments sharing an intersection node (u or v) are neighbors."""
    node2segs = {}
    for i, (u, v) in enumerate(zip(seg["u"], seg["v"])):
        node2segs.setdefault(u, []).append(i)
        node2segs.setdefault(v, []).append(i)
    nbrs = {i: set() for i in range(len(seg))}
    for members in node2segs.values():
        for a in members:
            for b in members:
                if a != b:
                    nbrs[a].add(b)
    w = weights.W({i: sorted(s) for i, s in nbrs.items()}, silence_warnings=True)
    return w


def w_distance_band(seg):
    """W2: midpoints within BAND_FT are neighbors."""
    mids = seg.geometry.interpolate(0.5, normalized=True)
    pts = np.c_[mids.x, mids.y]
    return weights.DistanceBand(pts, threshold=BAND_FT, binary=True,
                                silence_warnings=True)


def analyze(seg, w, label):
    """Global Moran (count + rate) and local Gi* hotspots under one W."""
    w.transform = "r"
    y = seg["n_severe"].to_numpy(dtype=float)
    t0 = time.time()
    mi = Moran(y, w, permutations=PERMS)
    mr = Moran_Rate(seg["n_severe"].to_numpy(), seg["length_ft"].to_numpy(),
                    w, permutations=PERMS)
    gi = G_Local(y, w, star=True, permutations=PERMS)
    thr = fdr_threshold(gi.p_sim)
    hot = (gi.Zs > 0) & (gi.p_sim <= thr)
    print(f"[{label}] Moran I={mi.I:.3f} (p={mi.p_sim:.3f}) | "
          f"rate I={mr.I:.3f} (p={mr.p_sim:.3f}) | "
          f"hotspots={hot.sum():,} (FDR p<={thr:.4f}) | {time.time()-t0:.0f}s")
    return {"label": label, "moran": mi, "moran_rate": mr, "gi_z": gi.Zs,
            "gi_p": gi.p_sim, "fdr": thr, "hot": hot,
            "islands": len(w.islands), "mean_nbrs": float(w.mean_neighbors)}


def crosstab(seg, hot):
    """Hotspots vs the official HIN: agreement + share of severe crashes captured."""
    on = seg["on_hin"].to_numpy()
    sev = seg["n_severe"].to_numpy()
    both = hot & on
    tot = sev.sum()
    return {
        "n_hot": int(hot.sum()), "n_hin": int(on.sum()), "n_both": int(both.sum()),
        "hin_share_of_hot": float(both.sum() / hot.sum()) if hot.sum() else np.nan,
        "hot_share_of_hin": float(both.sum() / on.sum()) if on.sum() else np.nan,
        "sev_in_hot": float(sev[hot].sum() / tot),
        "sev_in_hin": float(sev[on].sum() / tot),
        "hot_miles": float(seg.loc[hot, "length_ft"].sum() / 5280),
        "hin_miles": float(seg.loc[on, "length_ft"].sum() / 5280),
    }


def main():
    seg = load_universe()

    res1 = analyze(seg, w_shared_endpoint(seg), "W1 shared-endpoint")
    res2 = analyze(seg, w_distance_band(seg), f"W2 {BAND_FT:.0f}-ft band")

    seg["gi_z"] = res1["gi_z"]
    seg["gi_p"] = res1["gi_p"]
    seg["hotspot"] = res1["hot"]
    seg["hotspot_band"] = res2["hot"]

    ct1, ct2 = crosstab(seg, res1["hot"]), crosstab(seg, res2["hot"])
    agree = (res1["hot"] == res2["hot"]).mean()

    out = cfg.processed("segments_model.gpkg")
    seg.to_file(out, layer="segments", driver="GPKG")
    print(f"Saved modeling layer -> {out}")

    top = (seg[seg["hotspot"] & seg["name"].notna()]
           .groupby("name")["n_severe"].sum().sort_values(ascending=False).head(10))

    def pct(x):
        return f"{100*x:.0f}%"

    def wline(r, ct):
        return (f"| {r['label']} | {r['moran'].I:.3f} ({r['moran'].p_sim:.3f}) | "
                f"{r['moran_rate'].I:.3f} ({r['moran_rate'].p_sim:.3f}) | "
                f"{ct['n_hot']:,} ({ct['hot_miles']:,.0f} mi) | {pct(ct['sev_in_hot'])} | "
                f"{r['islands']:,} / {r['mean_nbrs']:.1f} |")

    report = f"""# Spatial Baseline Report (Modeling Step 1)

Generated by `src/model_spatial_baseline.py`, {date.today()}. {PERMS} permutations, seed 42.

**Universe:** {len(seg):,} full-purpose segments ({seg.length_ft.sum()/5280:,.0f} mi,
{seg.n_severe.sum():,} severe crashes). Segments outside the full-purpose boundary are
excluded (0.25 crashes/mi vs 64 inside — CRIS coverage, not safety).

## Is severe harm spatially clustered? (global Moran's I)

| Weights | Moran's I on counts (p) | Moran's I on rate/length (p) | Gi* hotspots | share of severe crashes in hotspots | islands / mean neighbors |
|---|---|---|---|---|---|
{wline(res1, ct1)}
{wline(res2, ct2)}

Hotspot = Gi* z>0, significant after FDR (Benjamini-Hochberg, alpha={ALPHA}).
W1/W2 hotspot agreement: {pct(agree)} of segments classified identically.

## Reconstructed hotspots vs the City's official 2022 HIN (primary W1)

| | count | miles | share of all severe crashes |
|---|---|---|---|
| Gi* hotspots | {ct1['n_hot']:,} | {ct1['hot_miles']:,.0f} | {pct(ct1['sev_in_hot'])} |
| Official HIN | {ct1['n_hin']:,} | {ct1['hin_miles']:,.0f} | {pct(ct1['sev_in_hin'])} |
| Overlap (both) | {ct1['n_both']:,} | — | — |

- {pct(ct1['hin_share_of_hot'])} of hotspot segments are on the official HIN.
- {pct(ct1['hot_share_of_hin'])} of official-HIN segments are Gi* hotspots.

## Top hotspot corridors (sanity check)

{top.to_string()}

## Reading this

- A strongly positive, significant Moran's I justifies the spatial framing and
  warns that regression residuals will be spatially correlated (handle in step 2).
- The Gi*-vs-HIN overlap validates the reconstruction; the mismatch previews the
  divergence theme (hotspots the City's list misses, and vice versa).
- The W1-vs-W2 comparison is evidence for the weights decision (open decision #3):
  if conclusions are stable across both, the choice is low-stakes.

## Columns added to `{out.name}`

`gi_z`, `gi_p` (Gi* z-score / pseudo p, W1), `hotspot` (FDR-significant high, W1),
`hotspot_band` (same under W2), `on_hin`, `on_txdot` (joined from the published layer).
"""
    (REPORTS / "spatial_baseline_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'spatial_baseline_report.md'}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 10))
        base = seg
        base.plot(ax=ax, color="#e3e0d6", linewidth=0.25)
        seg[seg.on_hin & ~seg.hotspot].plot(ax=ax, color="#8a6bbf", linewidth=1.1)
        seg[seg.hotspot & ~seg.on_hin].plot(ax=ax, color="#d7301f", linewidth=1.1)
        seg[seg.hotspot & seg.on_hin].plot(ax=ax, color="#4a1486", linewidth=1.3)
        ax.set_axis_off()
        ax.set_title("Severe-crash hotspots (Gi*, red) vs official HIN (purple); dark = both")
        fig.savefig(REPORTS / "spatial_baseline_map.png", dpi=150, bbox_inches="tight")
        print(f"Wrote {REPORTS / 'spatial_baseline_map.png'}")
    except Exception as e:
        print(f"(map skipped: {e})")

    print(report[:1200])


if __name__ == "__main__":
    main()
