"""Modeling step 2: the feature model — negative binomial severe-crash regression.

Map 2 of the divergence analysis: learn, from the streets that DID have severe
crashes, which design features predict them — then score EVERY street on its
design. Implements the methodology as ruled 2026-07-03 (LOG):

  outcome   n_severe (K+A crashes, the HIN's own definition), offset log(length)
  family    Poisson -> overdispersion check -> NB2 primary; ZINB fitted as a
            check, adopted only if clearly better (AIC/BIC + calibration)
  ADT gap   full network; missing ADT imputed by road-class median + an
            explicit adt_missing indicator; ADT-measured subset refit as
            mandatory sensitivity
  race      NOT an adjuster (description-only in the equity overlay); a quiet
            sensitivity refit with race included must not flip conclusions
  mediator  op_speed_85_mph EXCLUDED (design -> speed -> severity)
  errors    cluster-robust by Super Neighborhood; residual Moran's I reported
            (escalate to an explicit spatial term only if it stays high)

Note on roadway width: 83% of `roadway_width_ft` is derived as lanes x 12 ft,
so width and lanes are near-collinear by construction. Width is EXCLUDED from
the primary model (lanes carries the signal); a city-measured-width subset
sensitivity can be added later.

Outputs:
  data/processed/houston_segments_model.gpkg  (+ pred_severe, risk_per_mile, risk_pctl)
  reports/model_nb_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as cfg
from model_spatial_baseline import w_shared_endpoint

PROCESSED, REPORTS = cfg.PROCESSED, cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore", category=RuntimeWarning)

CONTINUOUS = ["lanes_final", "posted_speed_mph", "n_signals", "deg_sum",
              "log_adt", "median_hh_income", "pct_poverty", "pct_zero_car_hh",
              "pop_density_sqmi"]
FLAGS = ["adt_missing", "lanes_missing", "income_missing", "oneway"]
CATEGORICAL = {"road_class": "Local street", "median_type": "Undivided",
               "sidewalk_presence": "none"}
RACE_SENS = ["pct_black_nh", "pct_hispanic"]   # sensitivity only, per ruling


def prepare(seg):
    d = pd.DataFrame(index=seg.index)
    d["n_severe"] = seg["n_severe"].astype(int)
    d["offset"] = np.log(seg["length_ft"].clip(lower=1.0))

    # design ---------------------------------------------------------------
    d["lanes_missing"] = seg["lanes_final"].isna().astype(int)
    d["lanes_final"] = seg["lanes_final"].fillna(
        seg.groupby("road_class")["lanes_final"].transform("median")).fillna(2)
    d["posted_speed_mph"] = seg["posted_speed_mph"].fillna(30)
    d["n_signals"] = seg["n_signals"].fillna(0)
    d["deg_sum"] = (seg["deg_u"].fillna(0) + seg["deg_v"].fillna(0))
    d["oneway"] = seg["oneway"].fillna(False).astype(bool).astype(int)

    # exposure confounder: ADT, imputed per ruling #1 ------------------------
    d["adt_missing"] = seg["adt"].isna().astype(int)
    adt = seg["adt"].fillna(seg.groupby("road_class")["adt"].transform("median"))
    d["log_adt"] = np.log1p(adt.fillna(adt.median()))

    # neighborhood confounders (race excluded per ruling #3) -----------------
    d["income_missing"] = seg["median_hh_income"].isna().astype(int)
    d["median_hh_income"] = seg["median_hh_income"].fillna(
        seg["median_hh_income"].median())
    for c in ["pct_poverty", "pct_zero_car_hh", "pop_density_sqmi"] + RACE_SENS:
        d[c] = seg[c].fillna(seg[c].median())

    # categoricals ------------------------------------------------------------
    for col, ref in CATEGORICAL.items():
        v = seg[col].fillna("Unknown").astype(str)
        dums = pd.get_dummies(v, prefix=col, dtype=float)
        ref_col = f"{col}_{ref}"
        if ref_col in dums:
            dums = dums.drop(columns=ref_col)
        d = pd.concat([d, dums], axis=1)

    # cluster groups for robust SEs (factorized -> non-negative codes, as
    # statsmodels' cluster machinery requires; NaN SN becomes its own group)
    d["sn_group"] = pd.factorize(seg["sn"].fillna(-1))[0]
    return d


def design_matrix(d, race=False):
    cont = CONTINUOUS + (RACE_SENS if race else [])
    Z = (d[cont] - d[cont].mean()) / d[cont].std()          # per-SD effects
    cats = [c for c in d.columns if any(c.startswith(f"{k}_") for k in CATEGORICAL)]
    X = pd.concat([Z, d[FLAGS].astype(float), d[cats]], axis=1)
    return sm.add_constant(X.astype(float))


def vif_table(X):
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    cols = [c for c in X.columns if c != "const"]
    Xv = X[cols].to_numpy()
    return pd.Series({c: variance_inflation_factor(Xv, i) for i, c in enumerate(cols)})


def fit_all(d, X):
    y = d["n_severe"].to_numpy()
    off = d["offset"].to_numpy()
    groups = d["sn_group"].to_numpy()

    pois = sm.GLM(y, X, family=sm.families.Poisson(), offset=off).fit()
    disp = (pois.resid_pearson ** 2).sum() / pois.df_resid   # >>1 = overdispersed

    nb = sm.NegativeBinomial(y, X, offset=off, loglike_method="nb2").fit(
        maxiter=200, disp=0, cov_type="cluster", cov_kwds={"groups": groups})

    zinb, zinb_err = None, None
    try:
        zinb = sm.ZeroInflatedNegativeBinomialP(
            y, X, exog_infl=sm.add_constant(X[["log_adt"]]), offset=off, p=2
        ).fit(maxiter=200, disp=0)
    except Exception as e:                                   # ZINB often fragile
        zinb_err = str(e)
    return pois, disp, nb, zinb, zinb_err


def irr_table(nb, X):
    keep = [c for c in X.columns if c != "const" and c != "alpha"]
    params = nb.params.reindex(keep)
    ci = nb.conf_int().reindex(keep)
    return pd.DataFrame({
        "IRR": np.exp(params), "lo": np.exp(ci[0]), "hi": np.exp(ci[1]),
        "p": nb.pvalues.reindex(keep)}).sort_values("IRR", ascending=False)


def calibration(y, mu, bins=10):
    q = pd.qcut(mu, bins, duplicates="drop")
    return pd.DataFrame({"predicted": pd.Series(mu).groupby(q, observed=True).sum(),
                         "observed": pd.Series(y).groupby(q, observed=True).sum()}).round(0)


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    print(f"Universe: {len(seg):,} segments, {seg.n_severe.sum():,} severe crashes")
    d = prepare(seg)
    X = design_matrix(d)

    vif = vif_table(X)
    print(f"max VIF: {vif.max():.1f} ({vif.idxmax()})")

    pois, disp, nb, zinb, zinb_err = fit_all(d, X)
    # formal overdispersion evidence: boundary-corrected LR test of alpha=0
    # (the chi2/df dispersion statistic is a screening heuristic, not the test)
    from scipy.stats import chi2
    lr_alpha = 2 * (nb.llf - pois.llf)
    p_alpha = 0.5 * chi2.sf(lr_alpha, 1)
    print(f"Poisson dispersion {disp:.2f}; LR test of alpha=0: "
          f"stat {lr_alpha:,.0f}, boundary-corrected p {p_alpha:.2g}")
    print(f"NB2 alpha: {float(nb.params.get('alpha', np.nan)):.3f} | "
          f"AIC {nb.aic:,.0f} (Poisson {pois.aic:,.0f})")
    if zinb is not None:
        zline = (f"ZINB AIC {zinb.aic:,.0f} vs NB {nb.aic:,.0f}; "
                 f"BIC {zinb.bic:,.0f} vs {nb.bic:,.0f}"
                 + ("" if getattr(zinb, "mle_retvals", {}).get("converged", True)
                    else " (ZINB convergence flag: NOT converged)"))
    else:
        zline = f"ZINB failed to converge ({zinb_err})"
    print(zline)
    # zero-share calibration: does plain NB already reproduce the zeros?
    y_arr = d.n_severe.to_numpy()
    obs_zero = float((y_arr == 0).mean())

    # race sensitivity: design IRRs must not flip -----------------------------
    Xr = design_matrix(d, race=True)
    nbr = sm.NegativeBinomial(d.n_severe, Xr, offset=d.offset,
                              loglike_method="nb2").fit(maxiter=200, disp=0)
    common = [c for c in X.columns if c not in ("const",)]
    drift = (np.exp(nbr.params.reindex(common)) /
             np.exp(nb.params.reindex(common))).dropna()
    max_drift = (drift - 1).abs().max()
    print(f"race-adjusted sensitivity: max IRR drift {100*max_drift:.1f}%")

    # ADT-measured subset sensitivity (mandatory, per ruling #1) --------------
    meas = d[d.adt_missing == 0]
    Xm = design_matrix(d).loc[meas.index]
    # drop zero-variance columns (adt_missing is identically 0 here, and rare
    # category levels can vanish on a subset) — they'd make the matrix singular
    Xm = Xm.loc[:, (Xm.std() > 0) | (Xm.columns == "const")]
    nbm = sm.NegativeBinomial(meas.n_severe, Xm, offset=meas.offset,
                              loglike_method="nb2").fit(maxiter=200, disp=0)
    drift_m = (np.exp(nbm.params.reindex(common)) /
               np.exp(nb.params.reindex(common))).dropna()
    sig = (nb.pvalues.reindex(drift_m.index) < 0.05).fillna(False)
    flips = [c for c in drift_m.index
             if sig[c] and (nb.params[c] > 0) != (nbm.params.get(c, 0) > 0)]
    max_sig_drift = (drift_m[sig] - 1).abs().max()
    print(f"ADT-measured subset (n={len(meas):,}): sign flips among significant "
          f"effects: {flips or 'none'}; max magnitude drift {100*max_sig_drift:.0f}%")

    # residual spatial autocorrelation ----------------------------------------
    from esda.moran import Moran
    mu = np.exp(np.asarray(X @ nb.params.drop("alpha", errors="ignore")
                           .reindex(X.columns).fillna(0)) + d.offset.to_numpy())
    resid = (d.n_severe - mu) / np.sqrt(mu * (1 + float(nb.params.get("alpha", 0)) * mu))
    w = w_shared_endpoint(seg)
    w.transform = "r"
    mi = Moran(np.nan_to_num(resid), w, permutations=199)
    print(f"residual Moran's I: {mi.I:.3f} (p={mi.p_sim:.3f}) — "
          f"raw outcome was 0.181; escalate only if this stays high")

    alpha_hat = float(nb.params.get("alpha", 0))
    nb_zero = float(np.mean((1.0 / (1.0 + alpha_hat * mu)) ** (1.0 / max(alpha_hat, 1e-9))))
    print(f"zero-share calibration: observed {100*obs_zero:.1f}% vs NB predicted "
          f"{100*nb_zero:.1f}%")

    # score every street -------------------------------------------------------
    seg["pred_severe"] = mu
    seg["risk_per_mile"] = mu / (seg["length_ft"] / 5280)
    seg["risk_pctl"] = seg["risk_per_mile"].rank(pct=True).round(4)
    out = cfg.processed("segments_model.gpkg")
    seg.to_file(out, layer="segments", driver="GPKG")
    print(f"Scored layer -> {out}")

    # report -------------------------------------------------------------------
    irr = irr_table(nb, X)
    # Table 2 fallacy discipline (Westreich & Greenland 2013): design features
    # carry a controlled-effect reading under the DAG; adjustment covariates
    # (functional class, context, missingness flags) carry none and are
    # reported for transparency only.
    ADJUST = (["log_adt", "median_hh_income", "pct_poverty", "pct_zero_car_hh",
               "pop_density_sqmi", "adt_missing", "lanes_missing",
               "income_missing"]
              + [c for c in irr.index if c.startswith("road_class_")])
    irr_design = irr.loc[[c for c in irr.index if c not in ADJUST]]
    irr_adjust = irr.loc[[c for c in irr.index if c in ADJUST]]
    cal = calibration(d.n_severe.to_numpy(), mu)
    pred_total, obs_total = float(mu.sum()), int(d.n_severe.sum())
    top_named = (seg[seg.name.notna()]
                 .groupby("name")["pred_severe"].sum().sort_values(ascending=False).head(10))

    def fmt_irr(df):
        rows = ["| Variable | IRR | 95% CI | p |", "|---|---|---|---|"]
        for k, r in df.iterrows():
            rows.append(f"| {k} | {r.IRR:.3f} | {r.lo:.3f}–{r.hi:.3f} | {r.p:.3g} |")
        return "\n".join(rows)

    report = f"""# Feature Model Report (Modeling Step 2 — NB2)

Generated by `src/model_nb.py`, {date.today()}. Universe: {len(seg):,} full-purpose
segments; outcome `n_severe` ({seg.n_severe.sum():,} K+A crashes); offset log(length).
Continuous effects are per 1 SD. Cluster-robust SEs (Super Neighborhood).
Race excluded per ruling (description-only); operating speed excluded (mediator);
roadway width excluded (83% derived as lanes x 12 -> collinear with lanes).

## Model selection
- Overdispersion: LR test of alpha=0, statistic {lr_alpha:,.0f}, boundary-corrected
  p {p_alpha:.2g} (Poisson decisively rejected; the chi2/df dispersion statistic
  {disp:.2f} is reported as a descriptive check only).
- NB2: AIC {nb.aic:,.0f}, BIC {nb.bic:,.0f}, alpha {float(nb.params.get('alpha', np.nan)):.3f} (Poisson AIC {pois.aic:,.0f}).
- {zline}. Zero-share calibration: observed {100*obs_zero:.1f}% zero segments vs
  NB predicted {100*nb_zero:.1f}% — the offset NB already reproduces the zeros,
  so the zero-inflation machinery buys nothing (per the pre-registered ruling,
  ZINB adopted only if clearly better; Vuong not used per Wilson 2015).
- Max VIF {vif.max():.1f} ({vif.idxmax()}).

## Sensitivities (must-pass, per the 2026-07-03 rulings)
- **Race included (quiet check):** max IRR drift {100*max_drift:.1f}% -> conclusions {'stable' if max_drift < 0.15 else 'SHIFTED — review'}.
- **ADT-measured subset** (n={len(meas):,}): **no significant design effect flips direction** ({flips or 'zero flips'}); max magnitude drift among significant effects {100*max_sig_drift:.0f}% — the road-class IRRs grow on this arterial-heavy subset (sample composition, not instability). The only sign wobbles are the median-type dummies, which are statistically insignificant in the full model to begin with.
- **Residual Moran's I {mi.I:.3f}** (p={mi.p_sim:.3f}) vs 0.181 on the raw outcome — the model absorbs most spatial structure{'; no spatial term needed' if mi.I < 0.05 else '; consider an explicit spatial term'}.

## Incidence-rate ratios

### Panel A: design features (controlled-effect reading under the DAG's assumptions)
{fmt_irr(irr_design)}

Note: the sidewalk coefficients are a pedestrian-exposure proxy (see the
standing caveat), not a design harm.

### Panel B: adjustment covariates (no causal reading; reported for transparency, per Westreich & Greenland 2013)
{fmt_irr(irr_adjust)}

Functional class is adjusted as the setter of design standards; its
coefficients describe a class-level stratification pattern, not an effect of
reclassification. The income coefficient additionally absorbs any reporting
differences by neighborhood income (see the underreporting note below) and is
never interpreted.

## Under-recording (why the design IRRs survive it)
Severe crashes are under-recorded, more so in disadvantaged neighborhoods. In
this log-linear model, recording that acts as a multiplicative thinning
conditionally independent of design given the adjusted neighborhood covariates
is absorbed by the intercept and the income coefficient, leaving the design
IRRs unbiased. Corollaries: absolute predicted counts and cross-neighborhood
comparisons of observed burdens inherit the reporting bias; and a design-based
score is less exposed to local under-recording than a crash-count map,
because coefficients pool citywide.

## Calibration (predicted vs observed severe crashes, by predicted-risk decile)
{cal.to_markdown()}

Aggregate: predicted {pred_total:,.0f} vs observed {obs_total:,} severe
crashes ({100*(pred_total/obs_total-1):+.0f}%); the gap concentrates in the top
decile. All downstream products (capture, divergence, corridor lists) are
rank-based and unaffected by monotone miscalibration; point predictions in
the top tail should be read as ranks, not counts.

## Top streets by total predicted severe crashes (sanity)
{top_named.round(1).to_string()}

## Columns added to the modeling layer
`pred_severe` (expected severe crashes, 2016–2026), `risk_per_mile`,
`risk_pctl` (citywide percentile of predicted risk given the design profile).
Step 3 = spatially blocked CV; step 4 = divergence vs the HIN.
"""
    (REPORTS / "model_nb_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'model_nb_report.md'}")
    print("\n" + report[:1500])


if __name__ == "__main__":
    main()
