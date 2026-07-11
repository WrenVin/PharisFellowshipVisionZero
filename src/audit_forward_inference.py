"""Formal inference for the forward test and the HIN-2025 absorption result.

External review (2026-07-10) asked that the two most persuasive descriptive
ratios carry uncertainty estimates and matched comparators:

  1. The overlooked set "worsened +17%/+26% vs the citywide trend"
     -> a pre/post negative binomial count model with a set-by-period
        interaction, cluster-robust by Super Neighborhood, run against TWO
        comparators: (a) matched off-HIN arterials and collectors (the honest
        like-for-like set) and (b) all other streets (the published citywide
        framing). Both evaluation windows (2022+, 2023+).

  2. "Overlooked miles were absorbed into the 2025 HIN at 2.1x the arterial
     base rate"
     -> Super Neighborhood block-bootstrap CI for the two length-weighted
        absorption shares and their ratio.

The overlooked set is rebuilt exactly as in the temporal holdout (v2 fit on
pre-2022 crashes only, top HIN-mileage by predicted risk per mile, HIN
segments excluded), so no post-2021 information touches the selection.

Outputs: reports/forward_inference_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as cfg
from model_nb import design_matrix, prepare
from model_temporal_holdout import (HIN_MILES, split_counts, score_from_fit,
                                    topmiles)
from model_v2_imagery import sv_design

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

BOOT = 2000


def interaction_nb(n_pre, n_post, yrs_pre, yrs_post, length, in_set, universe,
                   sn, label):
    """NB2 pre/post panel: severe count ~ set + period + set:period, offset
    log(mile-years), cluster-robust by Super Neighborhood. The interaction
    IRR is the set's post/pre rate ratio divided by the comparator's."""
    u = universe
    n = int(u.sum())
    y = np.concatenate([n_pre[u], n_post[u]])
    post = np.concatenate([np.zeros(n), np.ones(n)])
    s = np.concatenate([in_set[u], in_set[u]]).astype(float)
    off = np.log(np.concatenate([
        length[u] / 5280 * yrs_pre, length[u] / 5280 * yrs_post]))
    X = pd.DataFrame({"const": 1.0, "in_set": s, "post": post,
                      "set_post": s * post})
    groups = np.concatenate([sn[u], sn[u]])
    m = sm.NegativeBinomial(y, X, offset=off, loglike_method="nb2").fit(
        maxiter=200, disp=0, cov_type="cluster", cov_kwds={"groups": groups})
    b, se = m.params["set_post"], m.bse["set_post"]
    irr = float(np.exp(b))
    lo, hi = float(np.exp(b - 1.96 * se)), float(np.exp(b + 1.96 * se))
    p = float(m.pvalues["set_post"])
    print(f"[{label}] interaction IRR {irr:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    return {"label": label, "irr": irr, "lo": lo, "hi": hi, "p": p,
            "events_set_post": int(n_post[u & (in_set)].sum())}


def absorption_boot(length, absorbed, in_set, universe, sn, B=BOOT, seed=42):
    """SN block bootstrap for length-weighted absorption shares and lift."""
    rng = np.random.default_rng(seed)
    u = universe
    L, A, S, G = length[u], absorbed[u].astype(float), in_set[u], sn[u]
    codes, uniq = pd.factorize(G)
    nG = len(uniq)
    stats = np.empty((B, 3))
    for b in range(B):
        w = np.bincount(rng.integers(0, nG, nG), minlength=nG).astype(float)[codes]
        mi_set, mi_base = (L * w * S).sum(), (L * w * ~S).sum()
        ab_set, ab_base = (L * w * A * S).sum(), (L * w * A * ~S).sum()
        ps = ab_set / mi_set if mi_set > 0 else np.nan
        pb = ab_base / mi_base if mi_base > 0 else np.nan
        stats[b] = (ps, pb, ps / pb if pb and pb > 0 else np.nan)
    q = np.nanpercentile(stats, [2.5, 97.5], axis=0)
    obs_ps = (L * A * S).sum() / (L * S).sum()
    obs_pb = (L * A * ~S).sum() / (L * ~S).sum()
    return {"share_set": obs_ps, "ci_set": (q[0, 0], q[1, 0]),
            "share_base": obs_pb, "ci_base": (q[0, 1], q[1, 1]),
            "lift": obs_ps / obs_pb, "ci_lift": (q[0, 2], q[1, 2])}


def absorption_adjusted(seg, length, n_pre, yrs_pre, absorbed, in_set,
                        universe, sn):
    """Does the model flag predict 2025-HIN absorption BEYOND prior crash
    burden? The 2025 HIN is crash-based, so overlooked streets could be
    absorbed merely for having been closer to the count-density threshold
    (external review, 2026-07-11). Logistic within off-HIN arterials and
    collectors: absorbed ~ flag + pre-2022 severe rate + log length +
    class, cluster-robust by Super Neighborhood; plus a stratified table
    by pre-2022 severe-crash count."""
    u = universe
    pre_rate = n_pre[u] / (length[u] / 5280) / yrs_pre
    X = pd.DataFrame({
        "const": 1.0,
        "overlooked": in_set[u].astype(float),
        "pre_rate": pre_rate,
        "log_len": np.log(length[u]),
        "arterial": (seg.road_class[u] == "Arterial").astype(float).to_numpy(),
    })
    m = sm.GLM(absorbed[u].astype(float), X,
               family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": sn[u]})
    b, se = m.params["overlooked"], m.bse["overlooked"]
    res = {"or": float(np.exp(b)), "lo": float(np.exp(b - 1.96 * se)),
           "hi": float(np.exp(b + 1.96 * se)),
           "p": float(m.pvalues["overlooked"])}
    print(f"[absorption-adjusted] OR {res['or']:.2f} [{res['lo']:.2f}, "
          f"{res['hi']:.2f}], p={res['p']:.4f}")

    # robustness (review round 4): burden as categories, since threshold
    # crossing may be nonlinear in the prior rate
    cats = pd.cut(n_pre[u], [-0.5, 0.5, 1.5, 3.5, np.inf],
                  labels=["0", "1", "2-3", "4+"])
    Xc = pd.DataFrame({"const": 1.0, "overlooked": in_set[u].astype(float),
                       "log_len": np.log(length[u]),
                       "arterial": (seg.road_class[u] == "Arterial")
                       .astype(float).to_numpy()})
    for lab in ["1", "2-3", "4+"]:
        Xc[f"pre_{lab}"] = (cats == lab).astype(float)
    mc = sm.GLM(absorbed[u].astype(float), Xc,
                family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": sn[u]})
    bc, sec = mc.params["overlooked"], mc.bse["overlooked"]
    res["or_cat"] = float(np.exp(bc))
    res["lo_cat"] = float(np.exp(bc - 1.96 * sec))
    res["hi_cat"] = float(np.exp(bc + 1.96 * sec))
    print(f"[absorption-adjusted, categorical burden] OR {res['or_cat']:.2f} "
          f"[{res['lo_cat']:.2f}, {res['hi_cat']:.2f}]")

    bins = pd.cut(n_pre[u], [-0.5, 0.5, 1.5, 3.5, np.inf],
                  labels=["0", "1", "2-3", "4+"])
    rows = []
    for b_ in ["0", "1", "2-3", "4+"]:
        for grp, name in [(in_set[u], "Overlooked"), (~in_set[u], "Other")]:
            sel = (bins == b_) & grp
            mi = length[u][sel].sum() / 5280
            ab = (length[u][sel] * absorbed[u][sel]).sum() / 5280
            rows.append({"pre-2022 severe crashes": b_, "set": name,
                         "miles": round(mi, 1),
                         "absorbed share": round(ab / mi, 3) if mi > 0 else np.nan})
    return res, pd.DataFrame(rows).pivot(
        index="pre-2022 severe crashes", columns="set",
        values=["miles", "absorbed share"])


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    counts, yrs, _ = split_counts(seg)
    d = prepare(seg).reset_index(drop=True)
    X1 = design_matrix(d).reset_index(drop=True)
    X2 = pd.concat([X1, sv_design(seg, d)], axis=1)

    length = seg.length_ft.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    hin_mi = length[on_hin].sum() / 5280
    sn = seg["sn"].fillna(-1).to_numpy()
    artcoll = seg.road_class.isin(["Arterial", "Collector"]).to_numpy()

    print("rebuilding pre-2022 v2 score and overlooked set...")
    score2, _ = score_from_fit(counts.n_pre, X2, d, seg)
    off_pre = topmiles(score2, length, hin_mi) & ~on_hin
    print(f"overlooked set: {length[off_pre].sum()/5280:.0f} mi, "
          f"{int(off_pre.sum()):,} segments")

    n_pre = counts.n_pre.to_numpy()
    results = []
    for win, n_post, yrs_post in [("2022+", counts.n_post22.to_numpy(), yrs["post22"]),
                                  ("2023+", counts.n_post23.to_numpy(), yrs["post23"])]:
        results.append(interaction_nb(
            n_pre, n_post, yrs["pre"], yrs_post, length, off_pre,
            artcoll & ~on_hin, sn,
            f"{win}, vs matched off-HIN arterials/collectors"))
        results.append(interaction_nb(
            n_pre, n_post, yrs["pre"], yrs_post, length, off_pre,
            np.ones(len(seg), bool), sn, f"{win}, vs all other streets"))

    print("absorption bootstrap (HIN 2025)...")
    absorbed = seg.on_hin_2025.astype(bool).to_numpy()
    ab = absorption_boot(length, absorbed, off_pre, artcoll & ~on_hin, sn)
    adj, strat = absorption_adjusted(seg, length, n_pre, yrs["pre"], absorbed,
                                     off_pre, artcoll & ~on_hin, sn)

    def pctpt(x):
        return f"{100 * x:.1f}%"

    rows = "\n".join(
        f"| {r['label']} | {r['irr']:.2f} | [{r['lo']:.2f}, {r['hi']:.2f}] "
        f"| {r['p']:.4f} |" for r in results)

    report = f"""# Forward-Test and Absorption Inference Report

Generated by `src/audit_forward_inference.py`, {date.today()}. Formal
uncertainty for the two headline descriptive ratios, per external review.
The overlooked set ({length[off_pre].sum()/5280:.0f} mi) is rebuilt exactly as
in the temporal holdout; no post-2021 information touches the selection.

## Did the overlooked streets worsen relative to comparators?

NB2 pre/post panel per segment: severe count ~ set + period + set x period,
offset log(mile-years), cluster-robust SEs by Super Neighborhood. The
interaction IRR is the overlooked set's post/pre rate ratio divided by the
comparator's; above 1.00 means the overlooked streets worsened relative to
the comparator, and the CI/p-value test that formally.

| Window and comparator | Interaction IRR | 95% CI | p |
|---|---|---|---|
{rows}

The matched comparator (off-HIN arterials and collectors) is the honest
like-for-like test: it asks whether the flagged streets diverged from
streets of the same functional classes that the model did NOT flag.

## Absorption into the City's 2025 HIN (block-bootstrap, {BOOT:,} resamples)

Universe: off-HIN-2022 arterials and collectors. Length-weighted share of
miles absorbed into the 2025 HIN:

- Overlooked set: {pctpt(ab['share_set'])} [{pctpt(ab['ci_set'][0])}, {pctpt(ab['ci_set'][1])}]
- Other off-HIN arterials/collectors: {pctpt(ab['share_base'])} [{pctpt(ab['ci_base'][0])}, {pctpt(ab['ci_base'][1])}]
- Lift: {ab['lift']:.2f}x [{ab['ci_lift'][0]:.2f}, {ab['ci_lift'][1]:.2f}]

## Absorption conditional on prior crash burden

The 2025 HIN is itself crash-based, so the raw lift could reflect the
overlooked streets' higher pre-2022 crash burden (closer to the
count-density threshold) rather than the model flag. Logistic model within
off-HIN arterials and collectors, absorbed ~ overlooked flag + pre-2022
severe rate + log length + arterial class, cluster-robust by Super
Neighborhood:

- Adjusted odds ratio for the model flag: {adj['or']:.2f}
  [{adj['lo']:.2f}, {adj['hi']:.2f}], p = {adj['p']:.4f}
- Robustness, burden entered as categories (0 / 1 / 2-3 / 4+) instead of
  a linear rate: OR {adj['or_cat']:.2f} [{adj['lo_cat']:.2f}, {adj['hi_cat']:.2f}]

Length-weighted absorption shares stratified by pre-2022 severe-crash
count:

{strat.to_markdown()}

Reading: if the adjusted OR stays above 1 with the interval excluding 1,
the City's update tracked the model flag beyond what prior crash burden
predicts; if it attenuates toward 1, the convergence is reported as
descriptive, not as independent validation of the design score.

## Reading

- An interaction IRR above 1 with a CI excluding 1 upgrades the forward-test
  claim from a descriptive ratio to a formal result: the overlooked streets
  worsened relative to the comparator by more than chance and spatial
  clustering explain.
- A lift CI excluding 1 means the City's own 2025 update moved toward the
  model's earlier picks at a rate not explained by chance assignment of
  update miles across neighborhoods.
"""
    (REPORTS / "forward_inference_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'forward_inference_report.md'}")
    print(report)


if __name__ == "__main__":
    main()
