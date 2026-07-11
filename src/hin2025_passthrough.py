"""HIN 2025 passthrough: conflate the new vintages, run the convergence test,
measure HIN drift, and re-cut the divergence against the current network.

The City's HIN genealogy (see DEFENSE.md): 2018 vintage (2014-2018 data),
2022 vintage (2018-2022 data; this project's standing comparator `on_hin`),
2025 vintage (2021-2025 data; published methodology). The 2022 vintage stays
the temporal test's comparator permanently (the 2025 network was drawn from
crashes inside that test window). This script answers three new questions:

  1. CONVERGENCE: of the streets the pre-2022 model flagged that the 2022
     HIN missed (the overlooked set, selected with zero post-2021 data), how
     many did the City's own 2021-2025 data force onto the 2025 HIN? The
     base rate for comparison is the add rate among ALL streets off the 2022
     HIN (reported for all streets and for arterials/collectors only, the
     fairer base). Framing rule: corroboration through the City's own
     adopted instrument, not an independent confirmation (the 2025 HIN is
     built from the same crashes as the forward test).
  2. DRIFT: how much does the HIN itself move between vintages (segment
     Jaccard, mile churn)? Instability of count-based screening, measured on
     the City's own products.
  3. THE CURRENT DIVERGENCE: at the 2025 HIN's own mileage, how much of the
     current model's high-design-risk network is off the NEW list (the
     persistent blind spot), and which corridors.

Conflation rule for all vintages, identical to the 2022 ingest: a segment is
on a network if at least half its length runs within 50 ft of that network's
lines.

Outputs: on_hin_2018 / on_hin_2025 columns on the modeling layer;
reports/hin2025_report.md
"""

import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

import config as cfg
from model_nb import design_matrix, prepare
from model_temporal_holdout import score_from_fit, split_counts, topmiles
from model_v2_imagery import sv_design

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")


def conflate(seg, path):
    net = gpd.read_file(path).to_crs(seg.crs)
    buf = net.buffer(50).union_all()
    frac = seg.geometry.intersection(buf).length / seg.geometry.length
    return (frac >= 0.5).fillna(False).to_numpy()


def miles(seg, mask):
    return seg.length_ft.to_numpy()[mask].sum() / 5280


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    length = seg.length_ft.to_numpy()
    on22 = seg.on_hin.astype(bool).to_numpy()

    print("conflating 2018 and 2025 vintages (50 ft / 50% rule)...")
    on18 = conflate(seg, cfg.EXTERNAL / "hin2018.geojson")
    on25 = conflate(seg, cfg.EXTERNAL / "hin2025.geojson")
    seg["on_hin_2018"] = on18
    seg["on_hin_2025"] = on25
    mi = {v: miles(seg, m) for v, m in
          [("2018", on18), ("2022", on22), ("2025", on25)]}
    print({k: round(v) for k, v in mi.items()})

    # --- drift between vintages ------------------------------------------------
    def jacc(a, b):
        return miles(seg, a & b) / miles(seg, a | b)

    drift = pd.DataFrame([
        {"pair": "2018 vs 2022", "jaccard_mi": jacc(on18, on22),
         "kept_mi": miles(seg, on18 & on22), "dropped_mi": miles(seg, on18 & ~on22),
         "added_mi": miles(seg, ~on18 & on22)},
        {"pair": "2022 vs 2025", "jaccard_mi": jacc(on22, on25),
         "kept_mi": miles(seg, on22 & on25), "dropped_mi": miles(seg, on22 & ~on25),
         "added_mi": miles(seg, ~on22 & on25)},
        {"pair": "2018 vs 2025", "jaccard_mi": jacc(on18, on25),
         "kept_mi": miles(seg, on18 & on25), "dropped_mi": miles(seg, on18 & ~on25),
         "added_mi": miles(seg, ~on18 & on25)},
    ]).set_index("pair").round(2)

    # --- rebuild the pre-2022 overlooked set (exactly as the temporal test) ----
    print("refitting the pre-2022 model for the convergence test...")
    counts, yrs, _ = split_counts(seg)
    yrs_pre, yrs_post = yrs["pre"], yrs["post22"]
    d = prepare(seg).reset_index(drop=True)
    X2 = pd.concat([design_matrix(d).reset_index(drop=True),
                    sv_design(seg, d)], axis=1)
    score2, _ = score_from_fit(counts.n_pre, X2, d, seg)
    hin22_mi = mi["2022"]
    hi_pre = topmiles(score2, length, hin22_mi)
    off_pre = hi_pre & ~on22
    n_post = counts.n_post22.to_numpy()

    # --- convergence: did the City's 2025 update absorb the overlooked set? ----
    arterial = seg.road_class.isin(["Major arterial", "Arterial", "Collector"]).to_numpy()
    conv = {
        "overlooked_mi": miles(seg, off_pre),
        "overlooked_added_mi": miles(seg, off_pre & on25),
        "overlooked_add_rate": miles(seg, off_pre & on25) / miles(seg, off_pre),
        "base_all": miles(seg, ~on22 & on25) / miles(seg, ~on22),
        "base_art": (miles(seg, ~on22 & arterial & on25)
                     / miles(seg, ~on22 & arterial)),
    }
    conv["lift_all"] = conv["overlooked_add_rate"] / conv["base_all"]
    conv["lift_art"] = conv["overlooked_add_rate"] / conv["base_art"]

    # corridor-level adjudication for the overlooked top names
    corr = (seg[off_pre & seg.name.notna()]
            .assign(pred=score2[off_pre & seg.name.notna().to_numpy()]
                    * seg.length_ft[off_pre & seg.name.notna().to_numpy()] / 5280,
                    added=lambda t: t.on_hin_2025)
            .groupby("name")
            .agg(miles_ov=("length_ft", lambda s: s.sum() / 5280),
                 pred=("pred", "sum"),
                 post_severe=("seg_id",
                              lambda s: int(n_post[s.index.to_numpy()].sum())),
                 pct_added_2025=("added", lambda s: 100 * s.mean()))
            .sort_values("pred", ascending=False).head(12).round(1))

    # --- the current divergence vs the NEW list ---------------------------------
    hin25_mi = mi["2025"]
    hi_now = topmiles(seg.risk_per_mile_v2.to_numpy(), length, hin25_mi)
    off_now = hi_now & ~on25
    blind = {
        "mi": miles(seg, off_now),
        "share": miles(seg, off_now) / hin25_mi,
        "severe": int(seg.n_severe[off_now].sum()),
        "post": int(n_post[off_now].sum()),
    }
    blind_corr = (seg[off_now & seg.name.notna()]
                  .groupby("name")
                  .agg(miles_ov=("length_ft", lambda s: s.sum() / 5280),
                       pred=("pred_severe_v2", "sum"),
                       severe=("n_severe", "sum"))
                  .sort_values("pred", ascending=False).head(10).round(1))

    # capture references for the 2025 HIN (labeled: substantially in-sample)
    cap25_all = 100 * seg.n_severe[on25].sum() / seg.n_severe.sum()
    cap25_post = 100 * n_post[on25].sum() / n_post.sum()

    seg.to_file(cfg.processed("segments_model.gpkg"), layer="segments",
                driver="GPKG")

    report = f"""# HIN 2025 Passthrough Report

Generated by `src/hin2025_passthrough.py`, {date.today()}. Vintages conflated
with the identical rule used for the standing comparator (segment on-network
if at least half its length runs within 50 ft). Mileage on this project's
network: 2018 vintage {mi['2018']:.0f} mi, 2022 vintage {mi['2022']:.0f} mi,
2025 vintage {mi['2025']:.0f} mi. The 2025 HIN carries {cap25_all:.0f}% of
2016-2026 severe crashes and {cap25_post:.0f}% of 2022-2026 severe crashes
(both substantially in-sample for it: it was drawn from 2021-2025 crashes).

## 1. Convergence: the City's own update versus the model's 2021 predictions

The overlooked set below was selected by the model fit on 2016-2021 crashes
only, at the 2022 HIN's mileage, excluding 2022-HIN segments: zero post-2021
information. The 2025 HIN was drawn by the City from 2021-2025 crashes.

- Overlooked set: {conv['overlooked_mi']:.0f} miles. Newly on the 2025 HIN:
  {conv['overlooked_added_mi']:.0f} miles (**{100*conv['overlooked_add_rate']:.0f}%**).
- Base rates for comparison: among ALL streets off the 2022 HIN, the City
  added {100*conv['base_all']:.1f}% of miles; among off-2022
  arterials/collectors, {100*conv['base_art']:.1f}%.
- **Lift: {conv['lift_all']:.1f}x over the all-streets base,
  {conv['lift_art']:.1f}x over the arterial/collector base.**

Framing rule: this is corroboration through the City's own adopted
instrument, not an independent confirmation; the 2025 HIN is built from the
same 2021-2025 crashes that the temporal forward test used.

### Overlooked corridors: which did the City's update absorb?

`pct_added_2025` = share of the corridor's overlooked miles now on the 2025
HIN; `post_severe` = severe crashes 2022-2026.

{corr.to_markdown()}

## 2. HIN drift between the City's own vintages

Miles measured on this project's network; Jaccard = kept / (kept+dropped+added).

{drift.to_markdown()}

Reading: count-density screening reshuffles substantially between vintages;
this instability is the within-product signature of the regression-to-the-mean
result in the temporal holdout (the Gi* map's 54 to 40 collapse), now visible
in the City's own products.

## 3. The current divergence (persistent blind spot vs the NEW list)

At the 2025 HIN's own mileage on this network ({hin25_mi:.0f} mi), ranking by
the current v2 model:

- **{100*blind['share']:.0f}% of the high-design-risk network is not on the
  2025 HIN**: {blind['mi']:.0f} miles, {blind['severe']:,} severe crashes
  2016-2026 ({blind['post']:,} in 2022-2026).

### Top persistent blind-spot corridors (by predicted severe crashes)

{blind_corr.to_markdown()}

## Columns added to the modeling layer

`on_hin_2018`, `on_hin_2025` (the standing comparator `on_hin` remains the
2022 vintage; the temporal holdout keeps it permanently).
"""
    (REPORTS / "hin2025_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'hin2025_report.md'}")
    print(report[:2200])


if __name__ == "__main__":
    main()
