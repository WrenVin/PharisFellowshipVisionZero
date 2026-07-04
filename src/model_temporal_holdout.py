"""Modeling step 5: temporal holdout. Fit on 2016-2021, grade on 2022-2026.

Every comparison so far grades the maps on crashes from the same window used
to build them; the HIN in particular is graded on the crashes it was selected
from, which regression to the mean inflates (Hauer; HSM network screening).
This step simulates deployment: freeze every screening map at end-2021 and
measure what share of NEVER-SEEN 2022-2026 severe crashes each map's top
miles capture. Design follows the two-period evaluation framework of Cheng &
Washington (2008) and the temporal-validation tier of TRIPOD (Collins 2015).

Maps frozen at end-2021:
  - design model v1 (features only) and v2 (with imagery), fit on pre-2022
    severe crashes only; imagery (median vintage 2015) precedes both windows
  - Gi* hotspots computed on pre-2022 crashes only (what a crash-based method
    honestly knew in 2021)
  - the official HIN, as published in 2022 from pre-2022 data (its true
    deployment state; unchanged)
  - the no-design null (offset + context), pricing what design adds

Also the forward test of the divergence finding (the site consistency test of
Cheng & Washington applied to the disagreement set): did the pre-fit
overlooked streets accumulate 2022-2026 severe crashes at their quiet
historical rate, or at the elevated rate the model predicted? Rates are
trend-adjusted by the citywide pre-to-post ratio.

Pre-registered reading rules (chat + DEFENSE.md, 2026-07-03, before results):
the model "matches" the HIN if the bootstrapped capture difference interval
covers zero and "beats" only if it excludes zero; the forward test succeeds
only if the overlooked set's trend-adjusted post rate exceeds its pre rate;
nulls are reported as evidence for the quieter-streets reading.

Sensitivities: train on 2016-2019 (excludes the COVID crash anomaly) and on
2018-2021 (single CR-3 injury-definition regime).

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
from model_v2_imagery import sv_design
from model_validate import capture, fit_nb

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

PRE_END = pd.Timestamp("2022-01-01")   # post window starts here
GI_MILES, HIN_MILES = 546.0, 589.0
BOOT = 500

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
        "n_post":     (cr.date >= PRE_END),
        "n_pre_1619": (cr.date < "2020-01-01"),
        "n_pre_1821": (cr.date >= "2018-01-01") & (cr.date < PRE_END),
    }
    out = seg[["seg_id"]].copy()
    for col, mask in windows.items():
        c = cr[mask].groupby("seg_id").size().rename(col)
        out = out.merge(c, on="seg_id", how="left")
    out = out.fillna(0)
    yrs_post = (cr.date.max() - PRE_END).days / 365.25
    total = int(out.n_pre.sum() + out.n_post.sum())
    print(f"[split] pre {int(out.n_pre.sum()):,} + post {int(out.n_post.sum()):,} "
          f"= {total:,} (layer n_severe sum {int(seg.n_severe.sum()):,}); "
          f"post window {yrs_post:.2f} yrs")
    return out, 6.0, yrs_post


def score_from_fit(y, X, d, seg):
    """Fit NB on y (pre-window counts), score ALL segments: risk per mile."""
    keep = (X.std() > 0) | (X.columns == "const")
    m = fit_nb(y, X.loc[:, keep], d.offset)
    params = m.params.drop("alpha", errors="ignore")
    mu = np.exp(np.asarray(X[params.index] @ params) + d.offset.to_numpy())
    return mu / (seg.length_ft.to_numpy() / 5280), m


def topmiles(score, length_ft, miles):
    order = np.argsort(-score)
    cum = np.cumsum(length_ft[order]) / 5280
    k = int(np.searchsorted(cum, miles))
    mask = np.zeros(len(score), bool)
    mask[order[:k + 1]] = True
    return mask


def boot_delta(score, on_hin, length_ft, n_post, miles, B=BOOT, seed=42):
    """Bootstrap CI for (model capture - HIN capture) on post-window crashes."""
    rng = np.random.default_rng(seed)
    order = np.argsort(-score)
    L, Y = length_ft[order], n_post[order]
    hin = on_hin.astype(float)
    n = len(score)
    deltas = np.empty(B)
    for b in range(B):
        cnt = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        co = cnt[order]
        cum_mi = np.cumsum(L * co) / 5280
        cum_sev = np.cumsum(Y * co)
        tot = cum_sev[-1] if cum_sev[-1] > 0 else 1.0
        k = min(int(np.searchsorted(cum_mi, miles)), n - 1)
        cap_model = cum_sev[k] / tot
        cap_hin = float((n_post * hin * cnt).sum()) / float((n_post * cnt).sum())
        deltas[b] = cap_model - cap_hin
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    counts, yrs_pre, yrs_post = split_counts(seg)
    d = prepare(seg).reset_index(drop=True)
    X1 = design_matrix(d).reset_index(drop=True)
    X2 = pd.concat([X1, sv_design(seg, d)], axis=1)
    Xn = X1[[c for c in CTX_COLS if c in X1.columns]]
    length = seg.length_ft.to_numpy()
    n_post = counts.n_post.to_numpy()
    n_pre = counts.n_pre.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    hin_mi = length[on_hin].sum() / 5280

    print("fitting pre-2022 models (v1, v2, null)...")
    score1, m1 = score_from_fit(counts.n_pre, X1, d, seg)
    score2, m2 = score_from_fit(counts.n_pre, X2, d, seg)
    scoren, _ = score_from_fit(counts.n_pre, Xn, d, seg)

    print("Gi* on pre-2022 crashes (ranking by z)...")
    w = w_shared_endpoint(seg)
    w.transform = "r"
    gi = G_Local(n_pre, w, star=True, permutations=99)
    score_gi = np.asarray(gi.Zs, dtype=float)

    # --- capture of 2022-2026 crashes at matched mileage ----------------------
    base = pd.DataFrame({"length_ft": length, "n_severe": n_post})
    caps = {
        "Design model v2 (fit pre-2022)": capture(base, score2, [GI_MILES, HIN_MILES]),
        "Design model v1 (fit pre-2022)": capture(base, score1, [GI_MILES, HIN_MILES]),
        "Gi* hotspots (pre-2022 crashes)": capture(base, score_gi, [GI_MILES, HIN_MILES]),
        "No-design null (fit pre-2022)": capture(base, scoren, [GI_MILES, HIN_MILES]),
    }
    cap_hin = float(n_post[on_hin].sum() / n_post.sum())
    lo2, hi2 = boot_delta(score2, on_hin, length, n_post, HIN_MILES)
    lo1, hi1 = boot_delta(score1, on_hin, length, n_post, HIN_MILES)

    # --- forward test of the disagreement set (site consistency) --------------
    hi_pre = topmiles(score2, length, hin_mi)
    off_pre = hi_pre & ~on_hin
    gi_set = topmiles(score_gi, length, hin_mi)
    city_ratio = (n_post.sum() / yrs_post) / (n_pre.sum() / yrs_pre)

    def rates(mask, name):
        mi = length[mask].sum() / 5280
        pre_r = n_pre[mask].sum() / mi / yrs_pre
        post_r = n_post[mask].sum() / mi / yrs_post
        return {"set": name, "miles": mi, "pre_rate": pre_r, "post_rate": post_r,
                "ratio": post_r / pre_r if pre_r > 0 else np.nan,
                "vs_city": (post_r / pre_r) / city_ratio if pre_r > 0 else np.nan,
                "pre_n": int(n_pre[mask].sum()), "post_n": int(n_post[mask].sum())}

    fwd = pd.DataFrame([
        rates(off_pre, "Overlooked set (pre-fit, off-HIN)"),
        rates(on_hin, "Official HIN"),
        rates(gi_set, "Gi* pre-2022 top miles"),
        rates(np.ones(len(seg), bool), "All streets"),
    ]).set_index("set")

    # --- sensitivities ---------------------------------------------------------
    s1619, _ = score_from_fit(counts.n_pre_1619, X1, d, seg)
    s1821, _ = score_from_fit(counts.n_pre_1821, X1, d, seg)
    sens = {
        "v1 trained 2016-2019 (pre-COVID)": capture(base, s1619, [HIN_MILES]),
        "v1 trained 2018-2021 (single injury definition)": capture(base, s1821, [HIN_MILES]),
    }

    def pct(x):
        return f"{100 * x:.0f}%"

    rows = "\n".join(f"| {k} | {pct(v[GI_MILES])} | {pct(v[HIN_MILES])} |"
                     for k, v in caps.items())
    sens_rows = "\n".join(f"| {k} | {pct(v[HIN_MILES])} |" for k, v in sens.items())
    fwd_tab = fwd.assign(
        pre_rate=fwd.pre_rate.round(2), post_rate=fwd.post_rate.round(2),
        ratio=fwd.ratio.round(2), vs_city=fwd.vs_city.round(2),
        miles=fwd.miles.round(0))[
        ["miles", "pre_n", "post_n", "pre_rate", "post_rate", "ratio", "vs_city"]]

    report = f"""# Temporal Holdout Report (Modeling Step 5)

Generated by `src/model_temporal_holdout.py`, {date.today()}. All screening
maps frozen at end-2021 (models fit on 2016-2021 severe crashes only; Gi* on
pre-2022 crashes; the HIN as published in 2022) and graded on the {yrs_post:.1f}
years of 2022-2026 severe crashes none of them saw. Pre-registered reading
rules in the module docstring and DEFENSE.md Layer 8.

## Capture of 2022-2026 severe crashes at matched mileage

| Map (frozen at end-2021) | top 546 mi | top 589 mi |
|---|---|---|
{rows}
| Official HIN (as published; {hin_mi:.0f} mi) | | {pct(cap_hin)} |

Bootstrap 95% interval for (model - HIN) capture at {HIN_MILES:.0f} mi,
{BOOT} segment resamples: v2 [{pct(lo2)}, {pct(hi2)}]; v1 [{pct(lo1)}, {pct(hi1)}].

## Forward test of the disagreement set (site consistency)

Overlooked set = top {hin_mi:.0f} predicted-risk miles from the PRE-2022 fit,
excluding HIN segments (no post-2021 data touched the selection). Rates are
severe crashes per mile per year; `vs_city` divides each set's post/pre ratio
by the citywide ratio ({city_ratio:.2f}), so 1.00 means the set moved with the
city, above 1.00 means it worsened relative to trend.

{fwd_tab.to_markdown()}

## Sensitivities (capture of post-window crashes at {HIN_MILES:.0f} mi)

| Training window | top 589 mi |
|---|---|
{sens_rows}

## Reading

- Every number in the capture table is prospective: the maps were built
  without any 2022-2026 information. This is the deployment question: with
  data through 2021, which map best anticipated the next {yrs_post:.1f} years?
- The HIN row measures the City's actual product in its actual deployment
  state; regression to the mean predicts its capture falls relative to its
  in-sample 52%.
- The forward-test table adjudicates the divergence finding: `vs_city` above
  1.00 for the overlooked set means the streets the model flagged, and the
  HIN missed, worsened relative to the citywide trend after selection.
"""
    (REPORTS / "temporal_holdout_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'temporal_holdout_report.md'}")
    print(report)


if __name__ == "__main__":
    main()
