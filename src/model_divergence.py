"""Modeling step 4: the divergence analysis (baseline, pre-imagery v1).

Crosses the validated design-risk scores (step 2, validated in step 3) with
the City's official 2022 High Injury Network. The finding is the top-right
cell of the 2x2: streets with high predicted design risk that are NOT on the
HIN. Reported at multiple thresholds so the result does not hinge on one
cutoff, with a descriptive equity overlay (race enters here only, per the
2026-07-03 rulings).

Framing note: the HIN is crash-history screening and does its job; this list
is COMPLEMENTARY, proactive screening. The report language reflects that.

This is the BASELINE divergence. The imagery phase (pedestrian and vehicle
counts, sidewalk quality from Mapillary) refits the model and re-runs this
analysis as v2; the v1-vs-v2 comparison is a headline result of its own.

Outputs:
  reports/divergence_report.md
  reports/divergence_map.png
  data/processed/houston_segments_model.gpkg  (+ offhin_highrisk flags)
"""

from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

import config as cfg

REPORTS = cfg.REPORTS
INC_EDGES = [50000, 100000, 150000]


def topmiles_mask(seg, miles):
    """True for segments in the top `miles` of predicted risk per mile."""
    order = seg.sort_values("risk_per_mile", ascending=False).index
    cum = seg.loc[order, "length_ft"].cumsum() / 5280
    keep = order[cum.to_numpy() <= miles]
    m = pd.Series(False, index=seg.index)
    m.loc[keep] = True
    return m


def group_profile(seg, mask, label):
    g = seg[mask]
    return {
        "group": label,
        "segments": int(mask.sum()),
        "miles": g.length_ft.sum() / 5280,
        "median_income": g.median_hh_income.median(),
        "pct_under_100k": 100 * (g.median_hh_income < 100000).mean(),
        "mean_poverty": g.pct_poverty.mean(),
        "mean_zero_car": g.pct_zero_car_hh.mean(),
        "mean_black_nh": g.pct_black_nh.mean(),
        "mean_hispanic": g.pct_hispanic.mean(),
    }


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    hin_miles = seg.loc[seg.on_hin, "length_ft"].sum() / 5280
    tot_pred = seg.pred_severe.sum()
    tot_mi = seg.length_ft.sum() / 5280

    # --- the 2x2 at three thresholds -----------------------------------------
    thresholds = {
        f"HIN-equivalent mileage ({hin_miles:,.0f} mi)": hin_miles,
        "Top 5% of street-miles": 0.05 * tot_mi,
        "Top 10% of street-miles": 0.10 * tot_mi,
    }
    rows = []
    masks = {}
    for name, mi in thresholds.items():
        hi = topmiles_mask(seg, mi)
        masks[name] = hi
        off = hi & ~seg.on_hin
        rows.append({
            "threshold": name,
            "high_risk_segments": int(hi.sum()),
            "off_hin_segments": int(off.sum()),
            "off_hin_miles": seg.loc[off, "length_ft"].sum() / 5280,
            "off_hin_share": off.sum() / hi.sum(),
            "pred_risk_off_hin": seg.loc[off, "pred_severe"].sum() / seg.loc[hi, "pred_severe"].sum(),
            "observed_sev_off": int(seg.loc[off, "n_severe"].sum()),
        })
    tab = pd.DataFrame(rows)

    # how much of ALL predicted risk lies off the HIN entirely
    off_all = seg.loc[~seg.on_hin, "pred_severe"].sum() / tot_pred

    # --- named corridors (primary threshold: HIN-equivalent) ------------------
    hi = masks[list(thresholds)[0]]
    off = hi & ~seg.on_hin
    seg["offhin_highrisk"] = off
    corr = (seg[off & seg.name.notna()]
            .groupby("name")
            .agg(pred=("pred_severe", "sum"), obs=("n_severe", "sum"),
                 miles=("length_ft", lambda s: s.sum() / 5280),
                 cls=("road_class", lambda s: s.mode().iat[0]),
                 lanes=("lanes_final", "median"), speed=("posted_speed_mph", "median"),
                 district=("district", lambda s: "/".join(sorted(set(s.dropna())))))
            .sort_values("pred", ascending=False).head(15))

    # --- equity overlay (descriptive; race enters here only) ------------------
    prof = pd.DataFrame([
        group_profile(seg, off, "Overlooked (high risk, off HIN)"),
        group_profile(seg, seg.on_hin.astype(bool), "Official HIN"),
        group_profile(seg, pd.Series(True, index=seg.index), "All streets"),
    ]).set_index("group")

    out = cfg.processed("segments_model.gpkg")
    seg.to_file(out, layer="segments", driver="GPKG")

    # --- report ----------------------------------------------------------------
    def p(x):
        return f"{100 * x:.0f}%"

    trows = "\n".join(
        f"| {r.threshold} | {r.high_risk_segments:,} | {r.off_hin_segments:,} "
        f"({p(r.off_hin_share)}) | {r.off_hin_miles:,.0f} | {p(r.pred_risk_off_hin)} | {r.observed_sev_off:,} |"
        for r in tab.itertuples())
    crows = "\n".join(
        f"| {n} | {r.pred:.0f} | {r.obs:.0f} | {r.miles:.1f} | {r.cls} | "
        f"{r.lanes:.0f} | {r.speed:.0f} | {r.district} |"
        for n, r in corr.iterrows())
    erows = "\n".join(
        f"| {n} | ${r.median_income:,.0f} | {r.pct_under_100k:.0f}% | {r.mean_poverty:.1f}% | "
        f"{r.mean_zero_car:.1f}% | {r.mean_black_nh:.1f}% | {r.mean_hispanic:.1f}% |"
        for n, r in prof.iterrows())

    report = f"""# Divergence Report (Modeling Step 4, baseline v1)

Generated by `src/model_divergence.py`, {date.today()}. Design-risk scores from
the validated feature model (steps 2-3); official HIN 2022 as the crash-based
reference. This is the pre-imagery baseline; the imagery phase re-runs this
analysis (v2) after adding pedestrian/vehicle counts and sidewalk quality.

The HIN is crash-history screening and performs as designed. The list below is
complementary, proactive screening: streets whose design profile matches the
deadliest corridors but whose crash history has not (yet) placed them on the
reactive list.

## The 2x2 at three thresholds

"High risk" = the top-ranked street-miles by predicted severe crashes per mile.

| High-risk threshold | segments | of which OFF the HIN | off-HIN miles | share of the set's predicted risk off HIN | observed severe on those |
|---|---|---|---|---|---|
{trows}

Across all streets, {p(off_all)} of total predicted severe-crash risk lies off
the HIN entirely.

## Overlooked corridors (named; HIN-equivalent threshold)

Streets ranked by total predicted severe crashes on their off-HIN, high-risk
segments. "obs" = severe crashes actually recorded there 2016-2026.

| Street | predicted severe | obs | miles | class | lanes | speed | district(s) |
|---|---|---|---|---|---|---|---|
{crows}

## Equity overlay (descriptive)

Neighborhood profile of the overlooked set vs the official HIN and the city.
Race shares are descriptive only (not model inputs), per the project rulings.

| Group | median HH income | % segs under $100k | mean poverty | mean zero-car HH | mean Black (NH) | mean Hispanic |
|---|---|---|---|---|---|---|
{erows}

## Notes

- Scores are from the full-data model; step 3 established that the ranking
  generalizes to unseen areas (45-47% capture at these mileages, out of fold).
- The `offhin_highrisk` flag (HIN-equivalent threshold) is saved on the
  modeling layer for mapping and the future dashboard overlay.
- Streets appear in the corridor table with their design profile so each row
  answers "why does the model flag this street."
"""
    (REPORTS / "divergence_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'divergence_report.md'}")

    # --- map -------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 10))
        seg.plot(ax=ax, color="#e3e0d6", linewidth=0.25)
        seg[seg.on_hin & ~off].plot(ax=ax, color="#8a6bbf", linewidth=1.0)
        seg[hi & seg.on_hin].plot(ax=ax, color="#4a1486", linewidth=1.2)
        seg[off].plot(ax=ax, color="#d7301f", linewidth=1.4)
        ax.set_axis_off()
        ax.set_title("Red = high design risk, NOT on the HIN (the overlooked set) · "
                     "purple = official HIN")
        fig.savefig(REPORTS / "divergence_map.png", dpi=150, bbox_inches="tight")
        print(f"Wrote {REPORTS / 'divergence_map.png'}")
    except Exception as e:
        print(f"(map skipped: {e})")

    print(report[:2400])


if __name__ == "__main__":
    main()
