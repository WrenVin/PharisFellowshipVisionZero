"""Build the Houston Concept Proactive Safety Network (PSN).

Packages the validated v2 design-risk model as a named network product, the
proactive counterpart to the City's High Injury Network, following the
presentation conventions of Alameda CTC's 2024 HIN + Concept PSN report but
built on a fitted, spatially and temporally validated model rather than a
factor checklist.

Method:
  1. SELECT: top segments by v2 predicted severe crashes per mile, sized at
     the HIN's own mileage (apples-to-apples selection budget).
  2. SMOOTH into corridors (Alameda convention): bridge gaps where a run of
     unselected same-named segments no longer than 0.25 mi connects two
     selected segments of that street; then drop isolated network fragments
     shorter than 0.5 mi.
  3. TIER: psn_and_hin (dangerous by design and by history), psn_only (the
     proactive additions), hin_only (history without current design signal).

"Concept" labeling per Alameda precedent: the network is a screening
product for review with the District C office and Public Works, not an
engineering determination.

Outputs:
  data/processed/houston_concept_psn.geojson   (PSN + tier columns)
  reports/concept_psn_report.md
  reports/psn_map.png
  psn / psn_tier columns on the modeling layer
"""

import warnings
from datetime import date

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

import config as cfg

REPORTS, PROCESSED, DOCS = cfg.REPORTS, cfg.PROCESSED, cfg.DOCS
warnings.filterwarnings("ignore")

GAP_FT = 1320.0        # bridge same-street gaps up to 0.25 mi
MIN_FRAG_FT = 2640.0   # drop isolated fragments under 0.5 mi
COLORS = {"psn_and_hin": "#8a1538", "psn_only": "#C0392B", "hin_only": "#7a6fb0"}
LABELS = {
    "psn_and_hin": "On both networks: dangerous by design and by history",
    "psn_only": "PSN only: dangerous by design, not on the City's list",
    "hin_only": "HIN only: crash history without current design signal",
}


def adjacency(seg):
    """seg index -> set of touching seg indices (shared intersection node)."""
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
    return nbrs


def components(members, nbrs):
    """Connected components within the boolean member mask."""
    member_idx = set(np.flatnonzero(members))
    seen, comps = set(), []
    for start in member_idx:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            i = stack.pop()
            comp.append(i)
            for j in nbrs[i]:
                if j in member_idx and j not in seen:
                    seen.add(j)
                    stack.append(j)
        comps.append(comp)
    return comps


def topmiles(score, length_ft, miles):
    order = np.argsort(-score)
    cum = np.cumsum(length_ft[order]) / 5280
    k = int(np.searchsorted(cum, miles))
    mask = np.zeros(len(score), bool)
    mask[order[:k + 1]] = True
    return mask


def post_window_counts(seg):
    cr = gpd.read_file(cfg.processed("crashes.gpkg"), ignore_geometry=True)
    cr = cr[(cr.severe == 1) & cr.seg_id.notna()].copy()
    cr["date"] = pd.to_datetime(cr["date"])
    c = cr[cr.date >= "2022-01-01"].groupby("seg_id").size().rename("n_post")
    return seg[["seg_id"]].merge(c, on="seg_id", how="left").n_post.fillna(0).to_numpy()


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    length = seg.length_ft.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    hin_mi = length[on_hin].sum() / 5280
    n_post = post_window_counts(seg)
    nbrs = adjacency(seg)
    names = seg["name"].fillna("").to_numpy()

    # 1. SELECT at the HIN's mileage
    selected = topmiles(seg.risk_per_mile_v2.to_numpy(), length, hin_mi)
    print(f"[select] {selected.sum():,} segments, "
          f"{length[selected].sum()/5280:,.0f} mi (HIN budget {hin_mi:.0f} mi)")

    # 2a. BRIDGE same-street gaps: an unselected connected run of one street's
    #     segments joins the PSN if it touches >=2 selected segments of that
    #     street and totals <= GAP_FT.
    psn = selected.copy()
    bridged = 0
    for name in pd.unique(names[selected]):
        if not name:
            continue
        in_street = names == name
        gap_pool = in_street & ~psn
        if not gap_pool.any():
            continue
        for comp in components(gap_pool, nbrs):
            total = length[comp].sum()
            if total > GAP_FT:
                continue
            touches = {j for i in comp for j in nbrs[i]
                       if psn[j] and names[j] == name}
            if len(touches) >= 2:
                psn[comp] = True
                bridged += len(comp)
    print(f"[bridge] {bridged:,} gap segments added")

    # 2b. DROP isolated fragments under MIN_FRAG_FT
    dropped = 0
    for comp in components(psn, nbrs):
        if length[comp].sum() < MIN_FRAG_FT:
            psn[comp] = False
            dropped += len(comp)
    print(f"[fragments] {dropped:,} segments dropped in sub-0.5-mi fragments")
    psn_mi = length[psn].sum() / 5280

    # 3. TIERS
    tier = np.where(psn & on_hin, "psn_and_hin",
                    np.where(psn, "psn_only",
                             np.where(on_hin, "hin_only", "")))
    seg["psn"] = psn
    seg["psn_tier"] = tier

    def group_stats(mask, name):
        mi = length[mask].sum() / 5280
        return {"tier": name, "segments": int(mask.sum()), "miles": round(mi, 1),
                "severe_2016_2026": int(seg.n_severe[mask].sum()),
                "severe_2022_2026": int(n_post[mask].sum()),
                "median_income": int(seg.median_hh_income[mask].median()),
                "pred_share_pct": round(100 * seg.pred_severe_v2[mask].sum()
                                        / seg.pred_severe_v2.sum(), 1)}

    tiers = pd.DataFrame([
        group_stats(tier == "psn_and_hin", LABELS["psn_and_hin"]),
        group_stats(tier == "psn_only", LABELS["psn_only"]),
        group_stats(tier == "hin_only", LABELS["hin_only"]),
    ]).set_index("tier")

    # corridor table: name-aggregated within the PSN
    corr = (seg[psn & (seg.name != "")]
            .groupby("name")
            .agg(miles=("length_ft", lambda s: round(s.sum() / 5280, 1)),
                 pred=("pred_severe_v2", lambda s: round(s.sum())),
                 severe=("n_severe", "sum"),
                 tier_new=("psn_tier", lambda s: round(100 * (s == "psn_only").mean())))
            .sort_values("pred", ascending=False).head(25))

    # capture of the final smoothed network
    cap_all = 100 * seg.n_severe[psn].sum() / seg.n_severe.sum()
    cap_post = 100 * n_post[psn].sum() / n_post.sum()

    # exports
    out_cols = ["seg_id", "name", "road_class", "district", "length_ft",
                "pred_severe_v2", "risk_pctl_v2", "n_severe", "on_hin",
                "psn_tier", "geometry"]
    gj = seg.loc[psn, out_cols].to_crs(4326)
    gj_path = PROCESSED / f"{cfg.AREA}_concept_psn.geojson"
    gj.to_file(gj_path, driver="GeoJSON")
    seg.to_file(cfg.processed("segments_model.gpkg"), layer="segments",
                driver="GPKG")

    # map
    boundary = gpd.read_file(DOCS / "boundary.geojson").to_crs(2278)
    s2 = seg.to_crs(2278)
    fig, ax = plt.subplots(figsize=(15, 13), dpi=200)
    boundary.plot(ax=ax, facecolor="none", edgecolor="#999999", linewidth=0.8)
    s2.plot(ax=ax, color="#e2ddce", linewidth=0.25, zorder=1)
    for t, color in COLORS.items():
        sub = s2[s2.psn_tier == t]
        sub.plot(ax=ax, color=color, linewidth=1.0, zorder=2)
    ax.set_axis_off()
    ax.set_title("Houston Concept Proactive Safety Network",
                 fontsize=20, color="#16395B", fontfamily="Georgia", pad=14)
    handles = [Line2D([], [], color=COLORS[t], linewidth=3,
                      label=f"{LABELS[t]} "
                            f"({length[tier == t].sum()/5280:,.0f} mi)")
               for t in COLORS]
    handles.append(Line2D([], [], color="#e2ddce", linewidth=2,
                          label="All other streets"))
    ax.legend(handles=handles, loc="lower left", fontsize=11, frameon=True,
              facecolor="#FBF6E9", edgecolor="#C8A24B")
    plt.tight_layout()
    plt.savefig(REPORTS / "psn_map.png", bbox_inches="tight", facecolor="white")

    report = f"""# Houston Concept Proactive Safety Network

Generated by `src/build_psn.py`, {date.today()}.

## What it is

A network of streets whose physical design carries elevated severe-crash
risk, identified by a statistical model rather than by crash history. It is
the proactive counterpart to the City's High Injury Network (HIN): the HIN
shows where severe crashes have concentrated; the PSN shows where street
design makes them likely, including on streets whose crash history has not
yet accumulated. "Concept" follows the labeling convention of Alameda CTC
(2024): a screening product for agency review, not an engineering
determination.

## Why

Screening by crash history alone is reactive by construction and subject to
regression to the mean. The temporal holdout (step 5) showed that this
model, frozen at end-2021, anticipated 2022 to 2026 severe crashes as well
as the HIN itself (51% vs 49% capture at matched mileage), and that the
streets it flagged off the HIN worsened 17% relative to the citywide trend.
Texas HB 1631 bars automated enforcement, leaving design as the primary
lever; a design-based network shows where that lever applies.

## Methodology

1. Every one of {len(seg):,} street segments is scored by the validated v2
   negative binomial model (design features, context controls, and street
   imagery features; spatially blocked and temporally validated).
2. The top-ranked segments by predicted severe crashes per mile are selected
   at the HIN's own mileage ({hin_mi:.0f} mi), so the two networks are the
   same size by construction.
3. Segments are smoothed into corridors: runs of unselected same-street
   segments totaling 0.25 mi or less that connect selected segments are
   bridged in; isolated fragments under 0.5 mi are dropped.
4. Each PSN or HIN segment carries one of three tiers for prioritization.

Smoothing parameters (0.25 mi gap, 0.5 mi minimum) are stated judgment
calls following the corridor conventions of Alameda CTC (2024).

## Findings

- Final smoothed network: **{psn_mi:,.0f} miles** ({psn.sum():,} segments;
  selection budget {hin_mi:.0f} mi, bridging +{bridged}, fragments -{dropped}).
- The PSN carries **{cap_all:.0f}%** of all 2016 to 2026 severe crashes and
  **{cap_post:.0f}%** of 2022 to 2026 severe crashes.

### The three tiers

{tiers.to_markdown()}

Reading: the first tier is dangerous by both evidence types and is the
natural first-priority set. The second tier is the proactive addition: high
design risk the City's list does not flag. The third tier is crash history
without current design signal, a candidate set for exposure review or for
checking whether past redesigns already addressed the design.

### Top PSN corridors (name-aggregated, by predicted severe crashes)

`tier_new` = share of the corridor's PSN segments that are off the HIN (%).

{corr.to_markdown()}

## Limitations

- Point predictions in the model's top tail run 13 to 20% high; corridor
  ordering, not predicted counts, is the supported claim.
- Name-aggregated corridors can merge distant same-named streets; extent
  splitting is a refinement for the delivery version.
- Pedestrian exposure remains substantially unmeasured (see DEFENSE.md);
  tier assignments inherit the model's stated limitations.
- The network is a screening product; site-level engineering review decides
  treatments.

## Files

- `data/processed/houston_concept_psn.geojson` (PSN segments + tiers)
- `psn`, `psn_tier` columns on the modeling layer
- `reports/psn_map.png`
"""
    (REPORTS / "concept_psn_report.md").write_text(report)
    print(f"Wrote {REPORTS / 'concept_psn_report.md'}")
    print(f"[psn] {psn_mi:,.0f} mi | capture all-years {cap_all:.0f}% "
          f"| post-window {cap_post:.0f}%")
    print(tiers.to_string())


if __name__ == "__main__":
    main()
