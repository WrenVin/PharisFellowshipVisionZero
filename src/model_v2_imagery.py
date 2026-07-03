"""Modeling v2: refit the feature model with street-imagery features.

The imagery phase's payoff. Adds the extracted street-view features to the
validated v1 model and answers three questions:

  1. THE SIDEWALK TEST: with pedestrian exposure measured (person counts),
     does the sidewalk coefficient fall toward or below 1? (v1's 1.4-1.7x is
     an exposure artifact; measuring the exposure should absorb it.)
  2. FIT AND TRANSFER: does imagery improve the model, in-sample (AIC) and on
     unseen districts (blocked-CV capture, same protocol as step 3)?
  3. DIVERGENCE V2: how does the overlooked-streets list change once exposure
     is measured? Streets whose risk survives are dangerous by design; streets
     whose risk deflates were explained by low exposure (the Bay Area Blvd
     question).

Estimand note (per the DAG): pedestrian exposure is both a confounder-path
node and a mediator of design (sidewalks attract walkers). Adjusting for it
makes v2 coefficients DIRECT design effects, separating "dangerous street"
from "busy sidewalk". That is the intended reading and is stated in the report.

Imagery features enter with the honest-fill pattern (same as ADT): observed
values standardized on the observed subset; segments without imagery get the
mean (0 after centering) plus an explicit sv_missing flag.

Outputs:
  reports/model_v2_report.md
  data/processed/houston_segments_model.gpkg  (+ pred_severe_v2, risk_pctl_v2, offhin_highrisk_v2)
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as cfg
from model_divergence import group_profile, topmiles_mask
from model_nb import CATEGORICAL, design_matrix, prepare

PROCESSED, REPORTS = cfg.PROCESSED, cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

SV = PROCESSED / f"{cfg.AREA}_streetview_features.parquet"
SV_FEATURES = {                      # column -> transform
    "sv_n_person": "log1p",          # pedestrian exposure (the headline variable)
    "sv_n_vehicle": "log1p",         # traffic proxy where no counter exists
    "sv_sidewalk": "raw",            # sidewalk pixel share (quality, not presence)
    "sv_vegetation": "raw",          # greenery / canopy
    "sv_building": "raw",            # enclosure
}
SV_CONTROLS = ["sv_pano_share"]      # measurement covariate (pano vs flat imagery)


def sv_design(seg, d):
    """Imagery columns for the design matrix: observed-subset standardization,
    mean-fill (0 after centering) + explicit missing flag."""
    sv = pd.read_parquet(SV)
    m = seg[["seg_id"]].merge(sv, on="seg_id", how="left")
    obs = m["sv_n_img"].fillna(0) > 0
    out = pd.DataFrame(index=seg.index)
    out["sv_missing"] = (~obs).astype(float)
    for col, tf in list(SV_FEATURES.items()) + [(c, "raw") for c in SV_CONTROLS]:
        v = m[col].astype(float)
        if tf == "log1p":
            v = np.log1p(v)
        mu, sd = v[obs].mean(), v[obs].std()
        z = (v - mu) / (sd if sd > 0 else 1.0)
        z[~obs] = 0.0
        out[col] = z.fillna(0.0)
    print(f"[sv] {obs.sum():,} of {len(seg):,} segments carry imagery features "
          f"({100*obs.mean():.0f}%)")
    return out


def fit_nb(y, X, off):
    return sm.NegativeBinomial(y, X, offset=off, loglike_method="nb2").fit(
        maxiter=200, disp=0)


def blocked_capture(d, X, seg, groups, miles_at):
    """OOF NB predictions with whole groups held out -> capture at mileages."""
    mu = np.full(len(d), np.nan)
    for g in pd.unique(groups):
        tr, te = groups != g, groups == g
        Xtr = X.loc[tr]
        keep = (Xtr.std() > 0) | (Xtr.columns == "const")
        try:
            m = fit_nb(d.n_severe[tr], Xtr.loc[:, keep], d.offset[tr])
            params = m.params.drop("alpha", errors="ignore")
            mu[te.to_numpy()] = np.exp(X.loc[te, params.index] @ params
                                       + d.offset[te])
        except Exception as e:
            print(f"  fold {g} failed: {str(e)[:60]}")
    ok = np.isfinite(mu)
    s = (seg[["length_ft"]].assign(n_severe=d.n_severe, mu=mu)[ok]
         .assign(score=lambda t: t.mu / (t.length_ft / 5280))
         .sort_values("score", ascending=False))
    cum_mi = s.length_ft.cumsum() / 5280
    cum_sev = s.n_severe.cumsum()
    tot = s.n_severe.sum()
    return {mi: float(cum_sev.iloc[min(int(np.searchsorted(cum_mi.to_numpy(), mi)),
                                       len(s) - 1)] / tot) for mi in miles_at}, ok.mean()


def irr_row(model, name):
    if name not in model.params.index:
        return None
    ci = model.conf_int().loc[name]
    return (float(np.exp(model.params[name])), float(np.exp(ci[0])),
            float(np.exp(ci[1])), float(model.pvalues[name]))


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    d = prepare(seg).reset_index(drop=True)
    X1 = design_matrix(d).reset_index(drop=True)
    Xsv = sv_design(seg, d)
    X2 = pd.concat([X1, Xsv], axis=1)

    print("fitting v1 (baseline) and v2 (with imagery)...")
    m1 = fit_nb(d.n_severe, X1, d.offset)
    m2 = fit_nb(d.n_severe, X2, d.offset)
    print(f"v1 AIC {m1.aic:,.0f} | v2 AIC {m2.aic:,.0f} | delta {m1.aic - m2.aic:,.0f}")

    # --- the sidewalk test ----------------------------------------------------
    sw_cols = [c for c in X1.columns if c.startswith("sidewalk_presence_")]
    sw_tab = []
    for c in sw_cols:
        r1, r2 = irr_row(m1, c), irr_row(m2, c)
        sw_tab.append((c.replace("sidewalk_presence_", "sidewalk "), r1, r2))
    person = irr_row(m2, "sv_n_person")
    vehicle = irr_row(m2, "sv_n_vehicle")

    # --- blocked CV comparison (district folds, same protocol as step 3) ------
    groups = seg["district"].fillna("none")
    print("blocked CV, v1...")
    cap1, cov1 = blocked_capture(d, X1, seg, groups, [546.0, 589.0])
    print("blocked CV, v2...")
    cap2, cov2 = blocked_capture(d, X2, seg, groups, [546.0, 589.0])

    # --- score v2 + divergence v2 ---------------------------------------------
    params2 = m2.params.drop("alpha", errors="ignore")
    mu2 = np.exp(np.asarray(X2[params2.index] @ params2) + d.offset.to_numpy())
    seg["pred_severe_v2"] = mu2
    seg["risk_per_mile_v2"] = mu2 / (seg.length_ft / 5280)
    seg["risk_pctl_v2"] = seg.risk_per_mile_v2.rank(pct=True).round(4)

    hin_miles = seg.loc[seg.on_hin.astype(bool), "length_ft"].sum() / 5280
    seg_r = seg.drop(columns=["risk_per_mile"], errors="ignore").rename(
        columns={"risk_per_mile_v2": "risk_per_mile"})  # reuse helper
    hi2 = topmiles_mask(seg_r, hin_miles)
    off2 = hi2 & ~seg.on_hin.astype(bool)
    seg["offhin_highrisk_v2"] = off2
    off1 = seg.offhin_highrisk.astype(bool)
    stay = (off1 & off2).sum()
    dropped = (off1 & ~off2).sum()
    added = (off2 & ~off1).sum()

    corr2 = (seg[off2 & seg.name.notna()]
             .groupby("name")
             .agg(pred=("pred_severe_v2", "sum"), obs=("n_severe", "sum"),
                  miles=("length_ft", lambda s: s.sum() / 5280))
             .sort_values("pred", ascending=False).head(10))
    # the adjudication list: v1-overlooked streets whose v2 risk deflated
    deflated = (seg[off1 & ~off2 & seg.name.notna()]
                .groupby("name")["pred_severe"].sum()
                .sort_values(ascending=False).head(8))

    prof2 = pd.DataFrame([
        group_profile(seg, off2, "Overlooked v2"),
        group_profile(seg, pd.Series(True, index=seg.index), "All streets"),
    ]).set_index("group")

    out = cfg.processed("segments_model.gpkg")
    seg.to_file(out, layer="segments", driver="GPKG")

    # --- report ----------------------------------------------------------------
    def fmt(r):
        return f"x{r[0]:.2f} ({r[1]:.2f} to {r[2]:.2f}, p={r[3]:.2g})" if r else "n/a"

    sw_lines = "\n".join(
        f"| {name} | {fmt(r1)} | {fmt(r2)} |" for name, r1, r2 in sw_tab)
    report = f"""# Imagery Refit Report (v2)

Generated by `src/model_v2_imagery.py`, {date.today()}. Universe: {len(seg):,}
segments; imagery features on 18,133 arterial/collector segments (honest-fill
plus `sv_missing` flag elsewhere). v2 coefficients are DIRECT design effects:
pedestrian exposure is measured and adjusted, separating dangerous streets
from busy sidewalks (see the DAG).

## 1. The sidewalk test

| Variable | v1 (exposure unmeasured) | v2 (exposure measured) |
|---|---|---|
{sw_lines}
| pedestrian exposure (sv_n_person, per SD) | not measurable | {fmt(person)} |
| imagery traffic (sv_n_vehicle, per SD) | not measurable | {fmt(vehicle)} |

## 2. Fit and transfer

- AIC: v1 {m1.aic:,.0f} vs v2 {m2.aic:,.0f} (delta {m1.aic - m2.aic:,.0f}; positive favors v2)
- Blocked-CV capture, top 546 mi: v1 {100*cap1[546.0]:.0f}% vs v2 {100*cap2[546.0]:.0f}%
- Blocked-CV capture, top 589 mi: v1 {100*cap1[589.0]:.0f}% vs v2 {100*cap2[589.0]:.0f}%
  (district folds; OOF coverage v1 {100*cov1:.0f}% / v2 {100*cov2:.0f}%.
  In-sample references: Gi* 54% at 546 mi; official HIN 52% at 589 mi.)

## 3. Divergence v2 (HIN-equivalent threshold)

- Overlooked set: v1 {int(off1.sum()):,} segments -> v2 {int(off2.sum()):,} segments
  ({stay:,} stay, {dropped:,} drop out, {added:,} newly flagged)
- Top overlooked corridors, v2 (by predicted severe on off-HIN portions):

{corr2.round(1).to_string()}

- v1-overlooked corridors whose risk DEFLATED once exposure was measured
  (candidates for "low exposure explained it, not design"):

{deflated.round(1).to_string()}

## Equity overlay, v2 overlooked set

{prof2[['segments','miles','median_income','pct_under_100k','mean_zero_car']].round(1).to_markdown()}

## Columns added to the modeling layer

`pred_severe_v2`, `risk_per_mile_v2`, `risk_pctl_v2`, `offhin_highrisk_v2`.
"""
    (REPORTS / "model_v2_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'model_v2_report.md'}")
    print(report[:2600])


if __name__ == "__main__":
    main()
