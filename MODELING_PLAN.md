# Modeling Plan — Systemic Risk vs. the High Injury Network

A concrete, executable spec for the modeling phase. Written to be handed to Claude Code
running locally in this repo (uses the local `.venv`, the real data in `data/processed/`,
and commits new `src/model_*.py` scripts + `reports/` outputs).

**Research question (from README):** Does a feature-based (systemic) risk model identify
dangerous Houston streets that the City's crash-based High Injury Network (HIN) misses — and
how much risk lies "off the HIN"? The **divergence** between the two maps is the headline output.

**Methodology is already fixed (LOG.md, prospectus):** negative binomial on segment-level
severe-crash counts, segment length as an exposure offset, Moran's I / Getis-Ord Gi* as the
HIN-reconstruction baseline, unsupervised street typologies, spatially blocked cross-validation,
divergence analysis as the headline. DAG identification: adjust land use / exposure /
demographics; do **NOT** adjust operating speed (it is the design→severity mediator); crash
reporting is a collider (the formal basis of the underreporting concern).

---

## 0. Inputs (do not re-derive)

- **Analysis network:** `data/processed/houston_segments_enriched.gpkg`, layer `segments`
  (75,260 segments, EPSG:2278). One row = one undirected intersection-to-intersection segment.
- **Outcome:** `n_severe` (K+A crashes per segment). 6,169 segments (8.2%) have ≥1; max 16;
  91.8% are zero — the overdispersed, zero-heavy pattern NB is built for.
- **Official HIN baseline:** `docs/hin.geojson` (City of Houston 2022, 1,261 segments) and the
  per-segment `on_hin` flag (computed in `src/export_webmap_data.py`).
- Variable definitions: **CODEBOOK.md** is canonical. Keep it in sync with any new column.

### Predictors, grouped by causal role (CODEBOOK + the DAG)

- **Design (the systemic risk features — the model's point):** `lanes_final`,
  `roadway_width_ft`, `posted_speed_mph`, `median_type`, `sidewalk_presence`, `oneway`,
  `road_class`/`highway`, intersection context (`deg_u`, `deg_v`, `n_signals`).
- **Exposure (confounder, must adjust):** `length_ft` (as the offset), `adt`.
- **Neighborhood confounders (adjust):** `median_hh_income`, `pct_poverty`, `pop_density_sqmi`,
  `pct_zero_car_hh` (and race shares for equity description, not necessarily as adjusters —
  decide explicitly).
- **Mediator — DO NOT adjust:** `op_speed_85_mph` (85th-pct operating speed). Model it as the
  mechanism in a separate sub-analysis; including it as a covariate would block the design
  effect we want to estimate.
- **Deferred / absent at city scale:** `landuse_*` (HCAD, 1.5M parcels). The DAG wants land use
  as a confounder, so note its absence as a limitation and, if time allows, run the District C
  subset (which *has* land use) as a robustness check.

---

## 1. Pre-modeling fixes (do these first)

1. **Fold the TxDOT exclusion/labeling upstream.** Per LOG (line ~424), `on_txdot` and the
   freeway exclusion are currently applied at *export*, not baked into the enriched analysis
   gpkg. Confirm the enriched gpkg matches the modeled universe (surface streets; state arterials
   kept + labeled). Add `on_txdot` and `on_hin` to the enriched gpkg if not present, so modeling
   reads one canonical file.
2. **Decide the ADT-missingness strategy explicitly** (`adt` is ~25% coverage, dense on
   arterials, blank on most locals — deliberately not class-imputed). Pick one and document it:
   (a) model on the arterial/collector subset where ADT is observed; (b) multiple imputation /
   missing-indicator; (c) a no-ADT model + an ADT-subset model as sensitivity. Recommended:
   primary model = missing-indicator or imputation on the full network, plus an ADT-observed
   subset as robustness. Whatever you choose, sensitivity-test it.
3. **Build the spatial weights once** and reuse. Queen contiguity is awkward for a line network;
   use a **shared-endpoint adjacency** (segments sharing a `u`/`v` node are neighbors) as the
   primary W, with a distance-band W on segment centroids as an alternative. Row-standardize.

---

## 2. Step 1 — Spatial baseline (reconstruct the HIN from crashes alone)

Goal: build the *crash-only* hotspot map that stands in for the City's reactive screening, so
the feature model has something to diverge from.

- **Global Moran's I** on `n_severe` (and a rate version, `n_severe` with `length_ft` exposure)
  to confirm spatial autocorrelation exists and justify the spatial framing.
- **Local Getis-Ord Gi\*** to flag statistically significant severe-crash hot spots → a
  reconstructed, data-driven HIN. Use FDR correction for multiple testing.
- **Cross-check against the official HIN:** overlap / agreement between Gi* hotspots and
  `on_hin`. This both validates the approach and previews the divergence theme.
- Output: `reports/spatial_baseline_report.md` + a hotspot column on the segments.

Library: `esda` + `libpysal` (PySAL stack).

---

## 3. Step 2 — Feature model (negative binomial)

The core systemic-risk model: predict severe-crash counts from **design + context**, adjusting
confounders, so it can score every street whether or not it has a crash history.

- **Outcome:** `n_severe` (count). **Offset:** `log(length_ft)` (variable segment length →
  exposure offset, per the prospectus). Optionally also offset/covariate on `adt` exposure.
- **Family:** Negative Binomial (NB2). First fit Poisson, then **test overdispersion** (e.g.
  the dispersion statistic / Cameron-Trivedi); confirm NB is warranted (it will be — 91.8% zeros,
  max 16). **Consider zero-inflation** (ZINB) and compare to NB by AIC/BIC and a Vuong test, but
  prefer plain NB unless ZI clearly wins (interpretability for a council audience).
- **Predictors:** the design set from §0, plus the neighborhood confounders. **Exclude the
  operating-speed mediator.** Standardize continuous predictors; treat `median_type`,
  `road_class`, `sidewalk_presence` as categoricals with sensible reference levels.
- **Spatial dependence:** residuals will be autocorrelated. Address it with one of:
  (a) cluster-robust SEs by a spatial block (e.g. Super Neighborhood `sn` or district),
  (b) a spatial-lag/SAR-style term, or (c) an ICAR/BYM random effect if you go Bayesian.
  Start simple (cluster-robust by `sn`); escalate only if residual Moran's I stays high.
- **Report:** incidence-rate ratios with CIs for each design feature, the overdispersion result,
  and residual spatial autocorrelation before/after the spatial term.

Libraries: `statsmodels` (`GLM` / `NegativeBinomial`, `ZeroInflatedNegativeBinomialP`) for the
core; `spreg` (PySAL) if you add a spatial regression term.

---

## 4. Step 3 — Validation (spatially blocked CV)

Random k-fold leaks spatial structure and inflates performance. Use **spatially blocked CV**:
hold out whole spatial blocks (council districts or Super Neighborhoods, or a spatial grid) so
the model is scored on streets it hasn't "seen the neighborhood of."

- Metrics for count/ranking: predictive log-likelihood / deviance, and a ranking metric
  appropriate to screening (e.g. recall of true high-severe segments in the top-k predicted —
  this mirrors how a city would use the list).
- Calibration check: predicted vs observed severe counts by decile.
- Output: `reports/model_validation_report.md`.

---

## 5. Step 4 — Divergence analysis (the headline)

Quantify what proactive screening adds over reactive screening.

- Score every segment with the feature model → a **predicted systemic-risk rank**.
- Compare to the crash-based map (official `on_hin` and/or the Gi* reconstruction). Build the
  2×2: high-predicted-risk × on/off the HIN.
- **Headline numbers:** how many high-risk-by-design segments are **off** the HIN (dangerous by
  design, not yet bloody — the streets reactive screening misses), how much predicted risk lies
  off-HIN, and concrete example corridors. Tie back to the README framing (Texas's enforcement
  ban → design-led safety).
- Equity overlay: are off-HIN high-risk streets disproportionately in lower-income / higher
  `pct_zero_car_hh` neighborhoods?
- Outputs: `reports/divergence_report.md`, a scored segments layer
  (`data/processed/houston_segments_scored.gpkg`), and figures for the writeup / a future
  "predicted risk" dashboard layer.

---

## 6. Optional — Unsupervised street typologies

Cluster segments on the design features (k-means / HDBSCAN on standardized predictors) to
produce interpretable street "types" (e.g. wide fast undivided arterial vs. narrow local). Useful
as a descriptive lens and a robustness cross-check on the regression. Lower priority than 1–5.

---

## 7. Deliverables & conventions

- **Scripts** (mirror the existing `src/` style — idempotent, config-driven via `src/config.py`,
  area-agnostic where possible):
  - `src/model_spatial_baseline.py` (Moran's I, Gi*)
  - `src/model_nb.py` (Poisson→NB→[ZINB] fit, IRRs, diagnostics)
  - `src/model_validate.py` (spatially blocked CV)
  - `src/model_divergence.py` (scoring + divergence + equity)
- **Reports** to `reports/` (markdown, like the existing conflation reports), figures alongside.
- **Update CODEBOOK.md** with any new columns (hotspot flag, predicted risk score, typology).
- **Update LOG.md** with dated decisions (ADT strategy, NB vs ZINB, weights choice, CV blocking).
- Keep results out of the public dashboards until demonstrated (LOG line ~602: the dashboard
  stays descriptive; the divergence claim lives in the analysis until proven).

## 8. Libraries (add to requirements.txt / .venv)

`statsmodels`, `libpysal`, `esda`, `spreg`, `geopandas` (already present), `scikit-learn`
(for typologies + blocked CV splitting), optionally `pymc`/`numpyro` if you go Bayesian ICAR.

## 9. Decisions to make explicitly (and sensitivity-test)

1. ADT missingness handling (§1.2).
2. NB vs ZINB.
3. Spatial-weights definition (shared-endpoint vs distance band).
4. How spatial dependence enters the model (robust SEs vs spatial term vs random effect).
5. Whether race shares are adjusters or description-only (equity framing).
6. The off-HIN "high risk" threshold (top-k vs predicted-rate cutoff) — report the headline
   across a couple of thresholds so it isn't cherry-picked.
