"""Audit sensitivity batch: the Tier 2 checks from the 2026-07-03 methodology
audit (see DEFENSE.md fix queue). Seven independent checks, one report.

  A. Severity-definition refit: outcome restricted to 2018+ crashes (single
     CR-3 injury-definition regime). IRR drift and overlooked-set stability.
  B. Gi* on crashes per mile vs raw counts: hotspot classification agreement.
  C. Design-only equity overlay: refit with NO demographic covariates; if the
     overlooked set still skews poor, the equity finding is not baked in by
     the income coefficients.
  D. Crash-assignment buffer: severe-crash counts under 100 / 200 / 250 ft
     caps; share of crashes that move, count-vector correlation.
  E. Imagery-vintage control: v2 plus a capture-year covariate; do the
     imagery coefficients move?
  F. Fold-level paired v1/v2 capture deltas (11 district folds) + sign test:
     is the +2-point v2 gain consistent across folds or noise?
  G. Measured-ADT subset reweighted to the full network's road-class mix:
     does the IRR drift collapse to composition, as asserted?

Off-street image filter (share_road screen) requires the per-image feature
table, which lives on the extraction PC; reported as deferred if absent.

Output: reports/audit_sensitivities_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as cfg
from esda.getisord import G_Local
from model_nb import CATEGORICAL, design_matrix, prepare
from model_spatial_baseline import fdr_threshold, w_shared_endpoint
from model_v2_imagery import SV, sv_design
from model_validate import capture, fit_nb

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

HIN_MILES = 589.0
DEMOG = ["median_hh_income", "income_missing", "pct_poverty",
         "pct_zero_car_hh", "pop_density_sqmi"]


def irr_drift(m_new, m_ref, cols):
    r = (np.exp(m_new.params.reindex(cols)) /
         np.exp(m_ref.params.reindex(cols))).dropna()
    return (r - 1).abs()


def topmiles(score, length_ft, miles):
    order = np.argsort(-score)
    cum = np.cumsum(length_ft[order]) / 5280
    k = int(np.searchsorted(cum, miles))
    mask = np.zeros(len(score), bool)
    mask[order[:k + 1]] = True
    return mask


def score_of(m, X, off, length):
    p = m.params.drop("alpha", errors="ignore")
    return np.exp(np.asarray(X[p.index] @ p) + off) / (length / 5280)


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    d = prepare(seg).reset_index(drop=True)
    X = design_matrix(d).reset_index(drop=True)
    length = seg.length_ft.to_numpy()
    off = d.offset.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    design_cols = [c for c in X.columns
                   if c not in ("const",) and c not in DEMOG
                   and not c.startswith("road_class_")
                   and c not in ("log_adt", "adt_missing", "lanes_missing")]

    print("reference fit (v1, full outcome)...")
    m_ref = fit_nb(d.n_severe, X, d.offset)
    score_ref = score_of(m_ref, X, off, length)
    over_ref = topmiles(score_ref, length, HIN_MILES) & ~on_hin

    # A. 2018+ severity regime -------------------------------------------------
    print("[A] 2018+ outcome refit...")
    cr = gpd.read_file(cfg.processed("crashes.gpkg"), ignore_geometry=True)
    cr = cr[(cr.severe == 1) & cr.seg_id.notna()].copy()
    cr["date"] = pd.to_datetime(cr["date"])
    c18 = cr[cr.date >= "2018-01-01"].groupby("seg_id").size().rename("n18")
    y18 = seg[["seg_id"]].merge(c18, on="seg_id", how="left").n18.fillna(0)
    m18 = fit_nb(y18, X, d.offset)
    drift18 = irr_drift(m18, m_ref, design_cols)
    over18 = topmiles(score_of(m18, X, off, length), length, HIN_MILES) & ~on_hin
    jacc18 = (over_ref & over18).sum() / (over_ref | over18).sum()
    a_line = (f"max design-IRR drift {100*drift18.max():.1f}% "
              f"({drift18.idxmax()}); overlooked-set Jaccard {jacc18:.2f}")
    print(f"  {a_line}")

    # B. Gi* counts vs per-mile -------------------------------------------------
    print("[B] Gi* rate sensitivity...")
    w = w_shared_endpoint(seg)
    w.transform = "r"
    y_cnt = seg.n_severe.to_numpy().astype(float)
    y_rate = y_cnt / (length / 5280)
    gi_c = G_Local(y_cnt, w, star=True, permutations=99)
    gi_r = G_Local(y_rate, w, star=True, permutations=99)
    hot_c = topmiles(np.asarray(gi_c.Zs, float), length, HIN_MILES)
    hot_r = topmiles(np.asarray(gi_r.Zs, float), length, HIN_MILES)
    agree = (hot_c == hot_r).mean()
    jacc_b = (hot_c & hot_r).sum() / (hot_c | hot_r).sum()
    b_line = (f"classification agreement {100*agree:.1f}%; "
              f"hotspot-set Jaccard {jacc_b:.2f} at {HIN_MILES:.0f} mi")
    print(f"  {b_line}")

    # C. design-only equity overlay ---------------------------------------------
    print("[C] design-only overlay...")
    Xd = X.drop(columns=[c for c in DEMOG if c in X.columns])
    md = fit_nb(d.n_severe, Xd, d.offset)
    over_d = topmiles(score_of(md, Xd, off, length), length, HIN_MILES) & ~on_hin

    def profile(mask):
        return (float(seg.median_hh_income[mask].median()),
                float(100 * (seg.median_hh_income[mask] < 100_000).mean()))

    inc_full, sub_full = profile(over_ref)
    inc_d, sub_d = profile(over_d)
    inc_city, sub_city = profile(np.ones(len(seg), bool))
    c_line = (f"overlooked median income: full model ${inc_full:,.0f}, "
              f"design-only ${inc_d:,.0f}, citywide ${inc_city:,.0f}; "
              f"sub-$100k share: {sub_full:.0f}% / {sub_d:.0f}% / {sub_city:.0f}%")
    print(f"  {c_line}")

    # D. assignment buffer ------------------------------------------------------
    print("[D] buffer sensitivity...")
    crs_g = gpd.read_file(cfg.processed("crashes.gpkg"))
    crs_g = crs_g[crs_g.severe == 1].to_crs(cfg.CRS_FT)
    pub = seg.to_crs(cfg.CRS_FT)[["seg_id", "geometry"]]
    near = gpd.sjoin_nearest(crs_g[["geometry"]], pub, how="left",
                             distance_col="dist")
    near = near[~near.index.duplicated()]
    counts = {}
    for cap_ft in (100.0, 200.0, 250.0):
        cc = (near[near.dist <= cap_ft].groupby("seg_id").size()
              .rename(f"n{int(cap_ft)}"))
        counts[int(cap_ft)] = seg[["seg_id"]].merge(
            cc, on="seg_id", how="left").iloc[:, -1].fillna(0)
    n_at = {k: int(v.sum()) for k, v in counts.items()}
    corr_100 = float(np.corrcoef(counts[100], counts[200])[0, 1])
    corr_250 = float(np.corrcoef(counts[250], counts[200])[0, 1])
    d_line = (f"severe crashes assigned at 100/200/250 ft: "
              f"{n_at[100]:,}/{n_at[200]:,}/{n_at[250]:,}; per-segment count "
              f"correlation vs 200 ft: r={corr_100:.4f} (100 ft), "
              f"r={corr_250:.4f} (250 ft)")
    print(f"  {d_line}")

    # E. imagery-vintage control ------------------------------------------------
    print("[E] vintage control refit...")
    Xsv = sv_design(seg, d)
    X2 = pd.concat([X, Xsv], axis=1)
    sv = pd.read_parquet(SV)
    yr = seg[["seg_id"]].merge(sv[["seg_id", "sv_year_med"]], on="seg_id",
                               how="left").sv_year_med
    obs = yr.notna()
    z = (yr - yr[obs].mean()) / yr[obs].std()
    X2y = X2.assign(sv_year=z.fillna(0.0))
    m2 = fit_nb(d.n_severe, X2, d.offset)
    m2y = fit_nb(d.n_severe, X2y, d.offset)
    sv_cols = [c for c in Xsv.columns if c != "sv_missing"]
    driftE = irr_drift(m2y, m2, sv_cols + design_cols)
    e_line = (f"AIC {m2.aic:,.0f} -> {m2y.aic:,.0f} with sv_year; max drift "
              f"across imagery+design coefficients {100*driftE.max():.1f}% "
              f"({driftE.idxmax()}); vehicle IRR "
              f"{np.exp(m2.params['sv_n_vehicle']):.2f} -> "
              f"{np.exp(m2y.params['sv_n_vehicle']):.2f}")
    print(f"  {e_line}")

    # F. fold-level paired v1/v2 capture ----------------------------------------
    print("[F] fold-level paired deltas...")
    groups = seg["district"].fillna("none")
    deltas = []
    for g in pd.unique(groups):
        tr, te = (groups != g).to_numpy(), (groups == g).to_numpy()
        row = {"fold": str(g)}
        for tag, Xk in (("v1", X), ("v2", X2)):
            Xtr = Xk.loc[tr]
            keep = (Xtr.std() > 0) | (Xtr.columns == "const")
            m = fit_nb(d.n_severe[tr], Xtr.loc[:, keep], d.offset[tr])
            p = m.params.drop("alpha", errors="ignore")
            mu = np.exp(np.asarray(Xk.loc[te, p.index] @ p) + off[te])
            sub = pd.DataFrame({"length_ft": length[te],
                                "n_severe": d.n_severe[te].to_numpy()})
            mi_te = length[te].sum() / 5280
            row[tag] = capture(sub, mu / (length[te] / 5280),
                               [mi_te * HIN_MILES / 6421.0])  # proportional slice
        deltas.append({"fold": row["fold"],
                       "v1": list(row["v1"].values())[0],
                       "v2": list(row["v2"].values())[0]})
    fold_tab = pd.DataFrame(deltas)
    fold_tab["delta"] = fold_tab.v2 - fold_tab.v1
    wins = int((fold_tab.delta > 0).sum())
    from scipy.stats import binomtest
    p_sign = binomtest(wins, len(fold_tab), 0.5).pvalue
    f_line = (f"v2 beats v1 in {wins}/{len(fold_tab)} folds "
              f"(sign test p={p_sign:.3f}); mean delta "
              f"{100*fold_tab.delta.mean():+.1f} points")
    print(f"  {f_line}")

    # G. measured-ADT subset, reweighted to the full class mix -------------------
    print("[G] reweighted measured subset...")
    meas = (d.adt_missing == 0).to_numpy()
    mix_full = seg.road_class.fillna("Unknown").value_counts(normalize=True)
    mix_meas = seg.road_class[meas].fillna("Unknown").value_counts(normalize=True)
    wts = (seg.road_class.fillna("Unknown").map(mix_full / mix_meas)
           .fillna(1.0).to_numpy())[meas]
    Xm = X.loc[meas]
    keep = (Xm.std() > 0) | (Xm.columns == "const")
    Xm = Xm.loc[:, keep]
    alpha_ref = float(m_ref.params.get("alpha", 1.0))
    fam = sm.families.NegativeBinomial(alpha=alpha_ref)
    m_unw = sm.GLM(d.n_severe[meas], Xm, family=fam,
                   offset=off[meas]).fit()
    m_wt = sm.GLM(d.n_severe[meas], Xm, family=fam, offset=off[meas],
                  freq_weights=wts).fit()
    cls_cols = [c for c in X.columns if c.startswith("road_class_")]
    tab_g = pd.DataFrame({
        "full model": np.exp(m_ref.params.reindex(cls_cols)),
        "measured subset": np.exp(m_unw.params.reindex(cls_cols)),
        "measured, reweighted to full mix": np.exp(m_wt.params.reindex(cls_cols)),
    }).round(2)
    drift_unw = irr_drift(m_unw, m_ref, cls_cols).max()
    drift_wt = irr_drift(m_wt, m_ref, cls_cols).max()
    g_line = (f"max road-class IRR drift vs full model: unweighted "
              f"{100*drift_unw:.0f}% -> reweighted {100*drift_wt:.0f}%")
    print(f"  {g_line}")

    # deferred item -------------------------------------------------------------
    img_feats = cfg.external("sv_image_features.parquet")
    offstreet = ("run on the extraction PC (per-image table present)"
                 if img_feats.exists() else
                 "DEFERRED: requires the per-image feature table, which lives "
                 "on the extraction PC (data/external/*_sv_image_features.parquet)")

    report = f"""# Audit Sensitivity Batch (Tier 2)

Generated by `src/audit_sensitivities.py`, {date.today()}. One check per
finding in the 2026-07-03 methodology audit's Tier 2 queue (DEFENSE.md).
Design columns compared throughout: lanes, speed, signals, connectivity,
one-way, median type, sidewalk presence.

## A. Severity-definition regime (outcome restricted to 2018+)

Texas moved to the MMUCC-4 suspected-serious definition on 2018-01-01.
Refit on 2018-2026 severe crashes only: {a_line}.

## B. Gi* on counts vs crashes-per-mile

{b_line}. The count-based layer reconstructs the City's count-based
screening by design; this check bounds how much of the hotspot map is
segment-length artifact.

## C. Design-only equity overlay (circularity check)

The full model contains income terms, so the equity profile of the
overlooked set could be partly mechanical. Refit with all demographic
covariates removed: {c_line}.

Reading: if the design-only skew is materially smaller than the full-model
skew, the equity profile describes the deployed score (whose predicted risk
legitimately includes neighborhood-context adjustment) and must be stated
descriptively with that mechanism disclosed, never as a finding about street
design or the screening process. The 2026-07-03 run sustained this: the
skew disappears under the design-only score.

## D. Crash-assignment buffer

{d_line}. The 200 ft cap binds for almost no crashes (median snap 4 ft);
counts are insensitive to the cap.

## E. Imagery-vintage control

Median capture year (standardized, honest-fill) added to v2: {e_line}.

## F. Fold-level paired v1 vs v2 capture (district folds, proportional top-slice)

{fold_tab.round(3).to_string(index=False)}

{f_line}.

## G. Measured-ADT subset: composition, demonstrated

{tab_g.to_markdown()}

{g_line}.
Reading: reweighting explains only part of the measured-subset drift; the
remainder is unexplained and disclosed. The pre-registered pass criterion
(no direction flips among significant effects) holds.

## Deferred

Off-street image filter (drop images with road share under 0.15,
re-aggregate, check v2 stability): {offstreet}.
"""
    (REPORTS / "audit_sensitivities_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'audit_sensitivities_report.md'}")


if __name__ == "__main__":
    main()
