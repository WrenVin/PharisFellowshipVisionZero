"""Modeling step 5: temporal holdout. Fit on 2016-2021, grade prospectively.

Every comparison so far grades the maps on crashes from the same window used
to build them; the HIN in particular is graded on the crashes it was selected
from, which regression to the mean inflates (Hauer; HSM network screening).
This step simulates deployment: freeze every screening map at end-2021 and
measure what share of never-seen severe crashes each map's top miles capture.
Design follows the two-period evaluation framework of Cheng & Washington
(2008) and the temporal-validation tier of TRIPOD (Collins 2015).

Two evaluation windows (structure per external review, 2026-07-10):
  PRIMARY   2023 through mid-2026: the common holdout. Every map, including
            the HIN (built on 2018-2022 data), predates this window entirely.
  SECONDARY 2022 through mid-2026: the HIN's actual deployment period. The
            HIN's selection window overlaps one year (2022); the models saw
            none of it. Labeled as partially overlapping for the HIN.

Maps frozen at end-2021:
  - design model v1 (features only) and v2 (with imagery), fit on pre-2022
    severe crashes only
  - v2 imagery-vintage sensitivity: the corpus is overwhelmingly mid-2010s
    (median capture year 2015), but 370 of 18,133 imagery segments (2.0%)
    have a median capture year after 2021, so a photo could postdate the
    freeze. Sensitivity rows mask imagery features (honest-fill: features
    zeroed, sv_missing set) on all segments with median capture year >2021,
    and, stricter, >2019.
  - Gi* hotspots computed on pre-2022 crashes only (what a crash-based method
    honestly knew in 2021)
  - the official HIN as ingested (the City's "High Injury Network 2022,"
    built on 2018-2022 crash data per its service metadata)
  - the no-design null (offset + context), pricing what design adds

Also the forward test of the divergence finding (the site consistency test of
Cheng & Washington applied to the disagreement set): did the pre-fit
overlooked streets accumulate post-freeze severe crashes at their quiet
historical rate, or at the elevated rate the model predicted? Rates are
trend-adjusted by the citywide pre-to-post ratio; reported for both windows.

Pre-registered reading rules (chat + DEFENSE.md, 2026-07-03, before results):
the model "matches" the HIN if the bootstrapped capture difference interval
covers zero and "beats" only if it excludes zero; the forward test succeeds
only if the overlooked set's trend-adjusted post rate exceeds its pre rate;
nulls are reported as evidence for the quieter-streets reading.

Uncertainty: the (model - HIN) capture difference is bootstrapped over
Super Neighborhood blocks (88 clusters), not individual segments, because
neighboring segments and their crashes are spatially dependent; a segment
bootstrap would understate uncertainty.

Sensitivities: train on 2016-2019 (excludes the COVID crash anomaly) and on
2018-2021 (single CR-3 injury-definition regime); graded on the primary
window.

Outputs: reports/temporal_holdout_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

import config as cfg
from esda.getisord import G_Local
from model_nb import design_matrix, prepare
from model_spatial_baseline import w_shared_endpoint
from model_v2_imagery import SV, sv_design
from model_validate import capture, fit_nb

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

PRE_END = pd.Timestamp("2022-01-01")        # freeze: models see nothing after
PRIMARY_START = pd.Timestamp("2023-01-01")  # common holdout: no map has seen it
GI_MILES, HIN_MILES = 546.0, 589.0
BOOT = 500
SV_YEAR_CUTS = [2021, 2019]                 # imagery-vintage masking cutoffs

CTX_COLS = ["const", "log_adt", "adt_missing", "median_hh_income",
            "income_missing", "pct_poverty", "pct_zero_car_hh",
            "pop_density_sqmi"]           # identical to model_validate's null


def split_counts(seg):
    """Per-segment severe counts by time window, joined to the modeling layer."""
    cr = gpd.read_file(cfg.processed("crashes.gpkg"), ignore_geometry=True)
    cr = cr[(cr.severe == 1) & cr.seg_id.notna()].copy()
    cr["date"] = pd.to_datetime(cr["date"])
    windows = {
        "n_pre":      (cr.date < PRE_END),
        "n_post22":   (cr.date >= PRE_END),
        "n_post23":   (cr.date >= PRIMARY_START),
        "n_pre_1619": (cr.date < "2020-01-01"),
        "n_pre_1821": (cr.date >= "2018-01-01") & (cr.date < PRE_END),
    }
    out = seg[["seg_id"]].copy()
    for col, mask in windows.items():
        c = cr[mask].groupby("seg_id").size().rename(col)
        out = out.merge(c, on="seg_id", how="left")
    out = out.fillna(0)
    yrs = {
        "pre": 6.0,
        "post22": (cr.date.max() - PRE_END).days / 365.25,
        "post23": (cr.date.max() - PRIMARY_START).days / 365.25,
    }
    print(f"[split] pre {int(out.n_pre.sum()):,}; post22 {int(out.n_post22.sum()):,} "
          f"({yrs['post22']:.2f} yrs); post23 {int(out.n_post23.sum()):,} "
          f"({yrs['post23']:.2f} yrs); crash data through {cr.date.max():%Y-%m-%d}")
    return out, yrs, cr.date.max()


def score_from_fit(y, X, d, seg):
    """Fit NB on y (pre-window counts), score ALL segments: risk per mile."""
    keep = (X.std() > 0) | (X.columns == "const")
    m = fit_nb(y, X.loc[:, keep], d.offset)
    params = m.params.drop("alpha", errors="ignore")
    mu = np.exp(np.asarray(X[params.index] @ params) + d.offset.to_numpy())
    return mu / (seg.length_ft.to_numpy() / 5280), m


def mask_sv(sv, late, label):
    """Imagery-vintage sensitivity: honest-fill masking of the flagged
    segments (features zeroed = observed-subset mean; sv_missing flag set),
    so nothing that could postdate the freeze informs their scores."""
    out = sv.copy()
    late = np.asarray(late, dtype=bool)
    cols = [c for c in out.columns if c != "sv_missing"]
    out.loc[late, cols] = 0.0
    out.loc[late, "sv_missing"] = 1.0
    print(f"[sv-mask] {label}: masked {int(late.sum()):,} segments")
    return out


def late_radius_flags(seg):
    """Segments with ANY photograph captured after the freeze within the
    25 m (82 ft) matching radius. This is a strict superset of the images
    that could have entered a segment's aggregated features (the extraction
    matched sample points to the nearest image within 25 m), so masking
    these segments guarantees no post-freeze photograph informs the score.
    External review 2026-07-11: median-year masking alone does not rule out
    a late photo inside a pre-2021-median segment; this bound does."""
    pts = pd.read_parquet(cfg.EXTERNAL / f"{cfg.AREA}_mapillary_points.parquet")
    ts = pd.to_numeric(pts["captured_at"], errors="coerce")
    cut_ms = PRE_END.tz_localize("UTC").timestamp() * 1000
    late = pts[ts >= cut_ms]
    g = gpd.GeoSeries(gpd.points_from_xy(late.lon, late.lat), crs=4326).to_crs(seg.crs)
    from shapely import STRtree
    tree = STRtree(g.values)
    hits = tree.query(seg.geometry.buffer(82.0).values, predicate="intersects")
    mask = np.zeros(len(seg), bool)
    mask[np.unique(hits[0])] = True
    print(f"[sv-radius] {len(late):,} post-freeze photos; {int(mask.sum()):,} "
          f"segments have one within the 25 m matching radius")
    return mask


def topmiles(score, length_ft, miles):
    order = np.argsort(-score)
    cum = np.cumsum(length_ft[order]) / 5280
    k = int(np.searchsorted(cum, miles))
    mask = np.zeros(len(score), bool)
    mask[order[:k + 1]] = True
    return mask


def boot_delta(score, on_hin, length_ft, n_post, miles, sn_codes, B=BOOT, seed=42):
    """Spatial block bootstrap CI for (model capture - HIN capture): resample
    Super Neighborhoods with replacement; every segment inherits its block's
    weight. Blocks, not segments, are the exchangeable unit because
    neighboring segments and their crashes are spatially dependent."""
    rng = np.random.default_rng(seed)
    order = np.argsort(-score)
    L, Y = length_ft[order], n_post[order]
    g = sn_codes[order]
    hin = on_hin[order].astype(float)
    nG = int(sn_codes.max()) + 1
    deltas = np.empty(B)
    for b in range(B):
        gcnt = np.bincount(rng.integers(0, nG, nG), minlength=nG).astype(float)
        co = gcnt[g]
        cum_mi = np.cumsum(L * co) / 5280
        cum_sev = np.cumsum(Y * co)
        tot = cum_sev[-1] if cum_sev[-1] > 0 else 1.0
        k = min(int(np.searchsorted(cum_mi, miles)), len(L) - 1)
        cap_model = cum_sev[k] / tot
        cap_hin = float((Y * hin * co).sum()) / tot
        deltas[b] = cap_model - cap_hin
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    counts, yrs, max_date = split_counts(seg)
    d = prepare(seg).reset_index(drop=True)
    X1 = design_matrix(d).reset_index(drop=True)
    sv = sv_design(seg, d)
    X2 = pd.concat([X1, sv], axis=1)

    svp = pd.read_parquet(SV)
    year_med = seg[["seg_id"]].merge(
        svp[["seg_id", "sv_year_med"]], on="seg_id", how="left")["sv_year_med"]
    radius_late = late_radius_flags(seg)
    n_radius = int((radius_late & (sv["sv_missing"].to_numpy() == 0.0)).sum())
    X2m = {c: pd.concat([X1, mask_sv(sv, (year_med > c).fillna(False).to_numpy(),
                                     f"median year > {c}")], axis=1)
           for c in SV_YEAR_CUTS}
    X2m["radius"] = pd.concat(
        [X1, mask_sv(sv, radius_late, "any post-freeze photo within 25 m")], axis=1)
    Xn = X1[[c for c in CTX_COLS if c in X1.columns]]

    length = seg.length_ft.to_numpy()
    n_pre = counts.n_pre.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    hin_mi = length[on_hin].sum() / 5280
    sn_codes = d["sn_group"].to_numpy()

    print("fitting pre-2022 models (v1, v2, v2-masked x2, null)...")
    score1, m1 = score_from_fit(counts.n_pre, X1, d, seg)
    score2, m2 = score_from_fit(counts.n_pre, X2, d, seg)
    score2m = {c: score_from_fit(counts.n_pre, X, d, seg)[0]
               for c, X in X2m.items()}
    scoren, _ = score_from_fit(counts.n_pre, Xn, d, seg)

    print("Gi* on pre-2022 crashes (ranking by z)...")
    w = w_shared_endpoint(seg)
    w.transform = "r"
    gi = G_Local(n_pre, w, star=True, permutations=99)
    score_gi = np.asarray(gi.Zs, dtype=float)

    # --- capture at matched mileage, both windows ------------------------------
    def cap_table(n_post):
        base = pd.DataFrame({"length_ft": length, "n_severe": n_post})
        rows = {
            "Design model v2 (fit pre-2022)": capture(base, score2, [GI_MILES, HIN_MILES]),
            "v2, imagery masked: any post-freeze photo within 25 m (strict bound)":
                capture(base, score2m["radius"], [GI_MILES, HIN_MILES]),
            "v2, imagery masked where median capture year >2021":
                capture(base, score2m[2021], [GI_MILES, HIN_MILES]),
            "v2, imagery masked where median capture year >2019":
                capture(base, score2m[2019], [GI_MILES, HIN_MILES]),
            "Design model v1 (fit pre-2022)": capture(base, score1, [GI_MILES, HIN_MILES]),
            "Gi* hotspots (pre-2022 crashes)": capture(base, score_gi, [GI_MILES, HIN_MILES]),
            "No-design null (fit pre-2022)": capture(base, scoren, [GI_MILES, HIN_MILES]),
        }
        cap_hin = float(n_post[on_hin].sum() / n_post.sum())
        return rows, cap_hin

    n_p23 = counts.n_post23.to_numpy()
    n_p22 = counts.n_post22.to_numpy()
    caps23, hin23 = cap_table(n_p23)
    caps22, hin22 = cap_table(n_p22)

    print("block bootstrap (Super Neighborhoods)...")
    ci = {
        ("v2", 23): boot_delta(score2, on_hin, length, n_p23, HIN_MILES, sn_codes),
        ("v1", 23): boot_delta(score1, on_hin, length, n_p23, HIN_MILES, sn_codes),
        ("v2", 22): boot_delta(score2, on_hin, length, n_p22, HIN_MILES, sn_codes),
        ("v1", 22): boot_delta(score1, on_hin, length, n_p22, HIN_MILES, sn_codes),
    }

    # --- forward test of the disagreement set (site consistency), both windows -
    hi_pre = topmiles(score2, length, hin_mi)
    off_pre = hi_pre & ~on_hin
    gi_set = topmiles(score_gi, length, hin_mi)

    def fwd_table(n_post, yrs_post):
        city_ratio = (n_post.sum() / yrs_post) / (n_pre.sum() / yrs["pre"])

        def rates(mask, name):
            mi = length[mask].sum() / 5280
            pre_r = n_pre[mask].sum() / mi / yrs["pre"]
            post_r = n_post[mask].sum() / mi / yrs_post
            return {"set": name, "miles": mi, "pre_rate": pre_r, "post_rate": post_r,
                    "ratio": post_r / pre_r if pre_r > 0 else np.nan,
                    "vs_city": (post_r / pre_r) / city_ratio if pre_r > 0 else np.nan,
                    "pre_n": int(n_pre[mask].sum()), "post_n": int(n_post[mask].sum())}

        t = pd.DataFrame([
            rates(off_pre, "Overlooked set (pre-fit, off-HIN)"),
            rates(on_hin, "Official HIN"),
            rates(gi_set, "Gi* pre-2022 top miles"),
            rates(np.ones(len(seg), bool), "All streets"),
        ]).set_index("set")
        return t, city_ratio

    fwd23, ratio23 = fwd_table(n_p23, yrs["post23"])
    fwd22, ratio22 = fwd_table(n_p22, yrs["post22"])

    # --- sensitivities (training window), graded on the primary window ---------
    base23 = pd.DataFrame({"length_ft": length, "n_severe": n_p23})
    s1619, _ = score_from_fit(counts.n_pre_1619, X1, d, seg)
    s1821, _ = score_from_fit(counts.n_pre_1821, X1, d, seg)
    sens = {
        "v1 trained 2016-2019 (pre-COVID)": capture(base23, s1619, [HIN_MILES]),
        "v1 trained 2018-2021 (single injury definition)": capture(base23, s1821, [HIN_MILES]),
    }

    def pct(x):
        return f"{100 * x:.0f}%"

    def pct1(x):
        return f"{100 * x:.1f}"

    def cap_rows(caps):
        return "\n".join(f"| {k} | {pct(v[GI_MILES])} | {pct(v[HIN_MILES])} |"
                         for k, v in caps.items())

    def fmt_fwd(t):
        return t.assign(
            pre_rate=t.pre_rate.round(2), post_rate=t.post_rate.round(2),
            ratio=t.ratio.round(2), vs_city=t.vs_city.round(2),
            miles=t.miles.round(0))[
            ["miles", "pre_n", "post_n", "pre_rate", "post_rate", "ratio",
             "vs_city"]].to_markdown()

    sens_rows = "\n".join(f"| {k} | {pct(v[HIN_MILES])} |" for k, v in sens.items())
    n_img_seg = int(svp.shape[0])
    late21 = int((svp.sv_year_med > 2021).sum())
    late19 = int((svp.sv_year_med > 2019).sum())

    report = f"""# Temporal Holdout Report (Modeling Step 5)

Generated by `src/model_temporal_holdout.py`, {date.today()}. Models fit on
2016-2021 severe crashes only; Gi* on pre-2022 crashes; the HIN as published
in 2022 (2018-2022 crash data). Crash data through {max_date:%B %Y}.
Pre-registered reading rules in the module docstring and DEFENSE.md Layer 8.

## Primary: common holdout, 2023 through {max_date:%B %Y} ({yrs['post23']:.1f} yrs)

Every map, including the HIN, predates this window entirely. No map has seen
any of these {int(n_p23.sum()):,} severe crashes.

| Map (frozen at end-2021) | top 546 mi | top 589 mi |
|---|---|---|
{cap_rows(caps23)}
| Official HIN (as published; {hin_mi:.0f} mi) | | {pct(hin23)} |

Block-bootstrap 95% interval for (model - HIN) capture at {HIN_MILES:.0f} mi,
{BOOT} Super Neighborhood resamples: v2 [{pct1(ci[('v2', 23)][0])}, {pct1(ci[('v2', 23)][1])}] points;
v1 [{pct1(ci[('v1', 23)][0])}, {pct1(ci[('v1', 23)][1])}].

## Secondary: deployment window, 2022 through {max_date:%B %Y} ({yrs['post22']:.1f} yrs)

The HIN's actual deployment period. The HIN's 2018-2022 selection window
overlaps the first year; the models saw none of the window, an asymmetry in
the HIN's favor.

| Map (frozen at end-2021) | top 546 mi | top 589 mi |
|---|---|---|
{cap_rows(caps22)}
| Official HIN (selection overlaps 2022; {hin_mi:.0f} mi) | | {pct(hin22)} |

Block-bootstrap 95% interval, {HIN_MILES:.0f} mi: v2 [{pct1(ci[('v2', 22)][0])},
{pct1(ci[('v2', 22)][1])}] points; v1 [{pct1(ci[('v1', 22)][0])}, {pct1(ci[('v1', 22)][1])}].

## Imagery vintage (freeze integrity)

The Mapillary corpus is overwhelmingly mid-2010s (median capture year 2015
across the {n_img_seg:,} imagery segments), but median-year masking alone
cannot rule out a late photograph inside an early-median segment (external
review, 2026-07-11). The strict bound: {n_radius:,} imagery segments
({100*n_radius/n_img_seg:.1f}%) have at least one post-freeze photograph
anywhere within the 25 m matching radius; the "strict bound" row above
withholds imagery features from ALL of them (honest-fill). Because the
extraction only ever matched images within 25 m, no post-freeze photograph
can inform that row's scores, by construction. Secondary rows mask on
median capture year ({late21:,} segments > 2021; {late19:,} > 2019).
Image-level re-aggregation from the extraction manifest (PC) remains
available as a refinement but cannot change the bound's conclusion.

## Forward test of the disagreement set (site consistency)

Overlooked set = top {hin_mi:.0f} predicted-risk miles from the PRE-2022 fit,
excluding HIN segments (no post-2021 data touched the selection). Rates are
severe crashes per mile per year; `vs_city` divides each set's post/pre ratio
by the citywide ratio, so 1.00 means the set moved with the city, above 1.00
means it worsened relative to trend.

### Primary window, 2023+ (citywide ratio {ratio23:.2f})

{fmt_fwd(fwd23)}

### Deployment window, 2022+ (citywide ratio {ratio22:.2f})

{fmt_fwd(fwd22)}

## Sensitivities (training window; capture of primary-window crashes, {HIN_MILES:.0f} mi)

| Training window | top 589 mi |
|---|---|
{sens_rows}

## Reading

- Every number is prospective for the models: they were built without any
  post-2021 information. The primary table is the deployment question asked
  cleanly: with data through 2021, which map best anticipated crashes that
  NO map, including the HIN, had seen?
- The secondary table is retained because 2022-2026 is the HIN's actual
  deployment period; its overlap with the HIN's selection window is labeled,
  not hidden. Regression to the mean predicts count-selected screening loses
  capture out of window; the raw Gi* map shows the full effect, while the
  HIN's half-mile corridor aggregation (and, in the secondary window, its
  partial overlap) buffer it.
- The forward-test tables adjudicate the divergence finding: `vs_city` above
  1.00 for the overlooked set means the streets the model flagged, and the
  HIN missed, worsened relative to the citywide trend after selection.
"""
    (REPORTS / "temporal_holdout_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'temporal_holdout_report.md'}")
    print(report)


if __name__ == "__main__":
    main()
