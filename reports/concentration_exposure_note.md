# Crash concentration vs. exposure (counts vs. VMT)

Reproduce: `.venv/bin/python src/analyze_concentration.py` (reads `docs/segments_vz.geojson`).

## Question

The dashboard reports that severe-crash harm (KSI = killed or seriously injured) is
extremely concentrated across the street network — a **Gini of 0.94** citywide, i.e.
half of all KSI sits on ~2.3% of street-miles. A fair objection: most of Houston's
street-miles are quiet, low-traffic residential streets with zero crashes, so is this
concentration just a restatement of where the traffic is? Should "most dangerous
streets" be measured by a **rate per exposure** (crashes per vehicle-miles traveled)
rather than by **counts**?

## Method

The concentration is measured with a **Lorenz / concentration curve** and its **Gini
coefficient** (0 = harm spread evenly across street-miles; 1 = all harm on one street).
Exposure is proxied by **VMT = ADT x segment length** (ADT = average daily traffic,
conflated from City count stations). Three Ginis are computed on the 17,517 segments
that have a traffic count (these carry **76% of all KSI** — essentially the arterials):

| Measure | Gini |
|---|---|
| KSI across street-miles (the dashboard's count basis) | **0.829** |
| Traffic (VMT) across street-miles — how concentrated traffic *itself* is | **0.366** |
| **KSI across VMT — concentration after removing exposure** | **0.822** |

(Citywide, including the zero-crash residential streets, KSI across all street-miles is
**0.937**; restricting to arterials with traffic data lowers it to 0.829, confirming
part of the citywide figure is the quiet-streets effect.)

## Result

The harm is concentrated **far beyond what traffic explains**:

- Traffic itself is only mildly concentrated (Gini 0.37), but KSI is highly concentrated
  (0.83) — so harm does **not** simply track traffic volume.
- After dividing by VMT, KSI is **still** about as concentrated (0.822 vs 0.829). If every
  vehicle-mile were equally risky this number would be near 0; it is not. Specific roads
  carry far more KSI **per vehicle-mile** than others — a road-design signal, not an
  exposure artifact.
- The busiest 50% of VMT carries only **34%** of the KSI (proportional would be ~50%), so
  the highest-volume roads are *relatively* safer per trip; mid-volume roads over-index.

## Why the dashboard uses counts, not a VMT rate

1. **Goal alignment.** Vision Zero targets the *absolute* number of deaths, so attention
   goes where people are actually killed. A per-VMT rate would de-prioritize busy
   arterials that account for the most deaths because they "look safe per mile."
2. **Small-numbers instability.** A naive crash-rate ranking is dominated by noise: the
   top segments by KSI-per-VMT are 0.06-mile streets with ADT ~160-370 and a single
   crash. This is the regression-to-the-mean problem, and it is why HIN practice
   (San Francisco onward) uses severity-weighted counts, not raw rates.

## Implication for the modeling phase

Exposure belongs in the systemic risk model as a **control**, not as the ranking metric.
The right question is not "crashes per VMT" (noisy) but **"which roads have more KSI than
their traffic volume and design would predict?"** — estimated with proper shrinkage
(e.g. empirical Bayes / a negative-binomial model with a VMT offset) so a single crash on
a quiet street does not dominate. The 0.82 figure above is quantitative support that such
a model has real signal to find: Houston's harm is driven by specific dangerous roads,
not by traffic density alone.

## Caveats

- ADT covers ~25% of segments (dense on arterials, sparse on local streets); the per-VMT
  analysis is therefore on the arterials, which is where 76% of KSI is, but excludes the
  residential network.
- ADT is conflated and propagated along corridors, so VMT is approximate.
- KSI counts span 2016-2025 (+ partial 2026); the rate uses daily VMT as a proportional
  exposure proxy, which is adequate for ranking and Gini but not an annualized rate.
