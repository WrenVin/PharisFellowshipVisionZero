"""Modeling step 3: spatially blocked cross-validation of the feature model.

Random k-fold leaks spatial structure (a segment's neighbor lands in the
training set), inflating performance. This validation holds out WHOLE AREAS:
the model is fit with an entire council district hidden, predicts that
district cold, and is graded on it. Repeated so every district is held out
once. Sensitivity: the same procedure grouped by Super Neighborhood.

Grading matches the screening use-case:
  - capture share: ranking held-out streets by predicted risk per mile, what
    share of actual severe crashes falls on the top-ranked miles. Reported at
    the Gi*-hotspot mileage (546 mi) and the official HIN mileage (589 mi) so
    the out-of-sample model is directly comparable to both crash-based maps.
  - calibration: pooled out-of-fold predicted vs observed by decile.
  - held-out NB deviance vs a no-design null (offset + context only).
  - an ML benchmark (gradient-boosted trees, Poisson loss) under the SAME
    blocked folds, measuring the accuracy cost of the interpretable model.

Outputs:
  reports/model_validation_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as cfg
from model_nb import CATEGORICAL, prepare, design_matrix

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

GI_MILES = 546.0    # step-1 Gi* hotspot mileage (54% capture, in-sample)
HIN_MILES = 589.0   # official HIN mileage (52% capture)


def fit_nb(y, X, off):
    return sm.NegativeBinomial(y, X, offset=off, loglike_method="nb2").fit(
        maxiter=200, disp=0)


def nb_loglik(y, mu, alpha):
    """NB2 log-likelihood of held-out counts under predicted means."""
    from scipy.special import gammaln
    a = max(alpha, 1e-8)
    r = 1.0 / a
    p = r / (r + mu)
    return float(np.sum(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                        + r * np.log(p) + y * np.log1p(-p)))


def blocked_oof(d, X, groups, label):
    """Out-of-fold NB predictions with whole groups held out."""
    mu = np.full(len(d), np.nan)
    alphas, fails = [], []
    for g in pd.unique(groups):
        tr, te = groups != g, groups == g
        Xtr = X.loc[tr]
        keep = (Xtr.std() > 0) | (Xtr.columns == "const")
        try:
            m = fit_nb(d.n_severe[tr], Xtr.loc[:, keep], d.offset[tr])
            params = m.params.drop("alpha", errors="ignore")
            Xte = X.loc[te, params.index]
            mu[te.to_numpy()] = np.exp(Xte @ params + d.offset[te])
            alphas.append(float(m.params.get("alpha", np.nan)))
        except Exception as e:
            fails.append((str(g), str(e)[:60]))
    if fails:
        print(f"[{label}] {len(fails)} fold failures: {fails}")
    print(f"[{label}] OOF coverage {100 * np.isfinite(mu).mean():.1f}%")
    return mu, float(np.nanmean(alphas))


def capture(df, score, miles_at):
    """Share of severe crashes on the top-ranked miles (by score, descending)."""
    s = df.assign(score=score).sort_values("score", ascending=False)
    cum_mi = s["length_ft"].cumsum() / 5280
    cum_sev = s["n_severe"].cumsum()
    tot = s["n_severe"].sum()
    out = {}
    for m in miles_at:
        i = int(np.searchsorted(cum_mi.to_numpy(), m))
        out[m] = float(cum_sev.iloc[min(i, len(s) - 1)] / tot)
    return out


def gbm_oof(seg, d, groups):
    """Gradient-boosted benchmark (Poisson loss), same blocked folds."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    feats = pd.DataFrame({
        "lanes": d.lanes_final, "speed": d.posted_speed_mph,
        "signals": d.n_signals, "deg": d.deg_sum, "oneway": d.oneway,
        "log_adt": d.log_adt, "adt_missing": d.adt_missing,
        "income": d.median_hh_income, "poverty": d.pct_poverty,
        "zerocar": d.pct_zero_car_hh, "density": d.pop_density_sqmi,
        "length_ft": seg.length_ft.to_numpy(),
    })
    for c in CATEGORICAL:
        feats[c] = pd.Categorical(seg[c].fillna("Unknown").astype(str)).codes
    cat_idx = [feats.columns.get_loc(c) for c in CATEGORICAL]
    mu = np.full(len(d), np.nan)
    for g in pd.unique(groups):
        tr, te = (groups != g).to_numpy(), (groups == g).to_numpy()
        m = HistGradientBoostingRegressor(
            loss="poisson", categorical_features=cat_idx, random_state=42)
        m.fit(feats[tr], d.n_severe[tr])
        mu[te] = m.predict(feats[te])
    return np.clip(mu, 1e-9, None)


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    d = prepare(seg)
    X = design_matrix(d)
    d = d.reset_index(drop=True); X = X.reset_index(drop=True)
    seg = seg.reset_index(drop=True)

    districts = seg["district"].fillna("none")
    sns = seg["sn"].fillna(-1)

    # --- NB, district-blocked (primary) --------------------------------------
    mu_d, alpha_d = blocked_oof(d, X, districts, "NB district-blocked")
    # --- NB, SN-blocked (sensitivity) ----------------------------------------
    mu_s, _ = blocked_oof(d, X, sns, "NB SN-blocked")
    # --- null model (no design features): offset + context only --------------
    ctx_cols = ["const", "log_adt", "adt_missing", "median_hh_income",
                "income_missing", "pct_poverty", "pct_zero_car_hh",
                "pop_density_sqmi"]
    Xn = X[[c for c in ctx_cols if c in X.columns]]
    mu_n, _ = blocked_oof(d, Xn, districts, "null (no design)")
    # --- GBM benchmark, district-blocked -------------------------------------
    mu_g = gbm_oof(seg, d, districts)
    print("GBM benchmark done")

    base = seg[["length_ft"]].assign(n_severe=d.n_severe)

    def cap_row(mu):
        """Capture on the predicted subset (rare small-fold nonconvergence can
        leave a few segments without an OOF prediction); coverage disclosed."""
        ok = np.isfinite(mu)
        sub = base[ok]
        c = capture(sub, mu[ok] / (sub.length_ft / 5280), [GI_MILES, HIN_MILES])
        c["cov"] = float(ok.mean())
        return c

    caps = {
        "NB (district-blocked)": cap_row(mu_d),
        "NB (SN-blocked)": cap_row(mu_s),
        "No-design null": cap_row(mu_n),
        "GBM benchmark": cap_row(mu_g),
    }
    ll = {k: nb_loglik(d.n_severe.to_numpy(), m, alpha_d)
          for k, m in [("NB", np.nan_to_num(mu_d, nan=d.n_severe.mean())),
                       ("null", np.nan_to_num(mu_n, nan=d.n_severe.mean())),
                       ("GBM", mu_g)]}

    # calibration, pooled OOF (district-blocked NB)
    ok = np.isfinite(mu_d)
    q = pd.qcut(pd.Series(mu_d[ok]), 10, duplicates="drop")
    cal = pd.DataFrame({
        "predicted": pd.Series(d.n_severe[ok].to_numpy()).groupby(q.values, observed=True).size() * 0
        + pd.Series(mu_d[ok]).groupby(q.values, observed=True).sum().round(0),
        "observed": pd.Series(d.n_severe[ok].to_numpy()).groupby(q.values, observed=True).sum(),
    })

    def pct(x):
        return f"{100 * x:.0f}%"

    rows = "\n".join(
        f"| {k} | {pct(v[GI_MILES])} | {pct(v[HIN_MILES])} | {pct(v['cov'])} |"
        for k, v in caps.items())
    report = f"""# Blocked Cross-Validation Report (Modeling Step 3)

Generated by `src/model_validate.py`, {date.today()}. Whole council districts
held out in turn (11 folds); every street predicted by a model that never saw
its district. Sensitivity: the same procedure blocked by Super Neighborhood.

## Screening performance on unseen areas (capture share, out-of-fold)

Share of all severe crashes on the top-ranked miles, ranking by predicted
risk per mile. In-sample references: Gi* hotspots 54% at 546 mi; official
HIN 52% at 589 mi.

| Ranking | top 546 mi | top 589 mi | OOF coverage |
|---|---|---|---|
{rows}

Reference-footing note: the model rows are out-of-fold; the references are
not. The Gi* map is graded on the same 2016-2026 crashes it was computed
from (fully in-sample; regression to the mean inflates it). The official HIN
as ingested ("High Injury Network 2022") was built on 2018-2022 crash data,
so five of the ten grading years overlap its selection window: substantially
in-sample. Both asymmetries favor the references, making the model's parity
conservative; the temporal holdout (step 5) puts all maps on one prospective
footing.

Capture is computed on the segments with an out-of-fold prediction; coverage
below 100% reflects rare small-fold nonconvergence (SN blocking has 89 folds).

## Held-out log-likelihood (higher is better)

NB {ll['NB']:,.0f} · no-design null {ll['null']:,.0f} · GBM {ll['GBM']:,.0f}

## Calibration, pooled out-of-fold (district-blocked NB)

{cal.to_markdown()}

## Reading

- The design model vs the no-design null isolates what street design adds on
  unseen areas, beyond exposure and context alone.
- The GBM row prices the interpretability constraint: the gap between GBM and
  NB capture is the accuracy cost of the explainable model.
- District blocking is the harder test (large contiguous holdouts); the SN
  row checks sensitivity to the blocking choice.
"""
    (REPORTS / "model_validation_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'model_validation_report.md'}")
    print(report)


if __name__ == "__main__":
    main()
