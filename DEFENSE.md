# DEFENSE.md: methodology defense notes

Purpose: one entry per methodological choice in the Part 2 model, each with its
literature anchor, the strongest known attack, and the honest answer. Compiled
from the 2026-07-03 three-panel adversarial methodology audit (statistics,
causal inference, data and computer vision), in which every contested choice
was checked against the published literature.

How to use this file: read one layer at a time. For each entry, produce the
answer in your own words before reading the written one. Anything that cannot
be answered cold goes on the study list. The suggested spoken answers are
starting points, not scripts.

Status codes: SOUND (audit-cleared), CAVEAT (defensible with the stated
hedge), FIX QUEUED (a correction or sensitivity run is pending, see the fix
queue at the bottom).

---

## The project in one paragraph

The project asks whether a street's physical design predicts severe crashes
well enough to identify dangerous streets that Houston's crash-history
screening misses. A negative binomial model fit to 66,922 street segments,
validated on held-out council districts, captures 47 to 49 percent of severe
crashes at the official High Injury Network's mileage without using the judged
streets' crash history (the HIN's in-sample figure is 52 percent, inflated by
selection on the outcome). At the HIN-equivalent threshold, roughly half of
the high-design-risk network is absent from the HIN: about 300 miles, already
carrying 1,399 recorded severe crashes, disproportionately in lower-income
neighborhoods. Street imagery processed with open computer-vision models
sharpened the model and adjudicated individual corridors. Every method is an
established, cited technique; the contribution is the combination, the city,
and the quantified disagreement between the two maps.

## The academic gap

Every individual method is established. The contribution sits at the
application layer, in three parts:

1. **The divergence quantification.** Agencies have begun pairing reactive and
   proactive screening in practice (Alameda CTC's 2024 HIN and Proactive
   Safety Network report; Montgomery County's systemic pedestrian analysis,
   Kumfer et al. 2024). What the peer-reviewed literature does not appear to
   contain: a spatially validated, full-network design model compared head to
   head against a city's adopted HIN, with the disagreement set itself as the
   object of study: sized at matched mileage, tested across thresholds,
   profiled for equity, and (planned) forward-tested on a later crash period.
2. **Free, reproducible imagery (claim narrowed after the 2026-07-03
   novelty sweep).** The sweep found a direct hit on the broad version of
   this claim: Elayan, Karki and Hawkins (TRR 2680(7):261-274, 2025) used
   Mapillary's PRECOMPUTED object detections as covariates in grid-based
   pedestrian crash count and severity models for Lincoln, Nebraska, and
   Costa et al. (AAP 205:107533, 2024) used Mapillary imagery at crash
   sites for Berlin cycling severity. The surviving claim, verified narrow:
   first custom computer-vision pipeline on RAW crowdsourced imagery for a
   full-network, segment-level, all-mode crash-frequency model. The
   distinction is substantive, not cosmetic: this project rejected the
   precomputed detections precisely because their richness is
   vintage-split, which is now a documented design decision in the paper.
   Failure modes (vintage heterogeneity, panorama handling, pedestrian
   counting limits) remain documented honestly.
3. **The site consistency test applied to the disagreement set.** Two-period
   evaluation of screening methods is standard (Cheng and Washington 2008);
   applying it to the set where the two maps disagree, to ask whether the
   overlooked streets' bill came due, is a small but genuine methodological
   twist.

A full systematic novelty review has not been performed; before any journal
submission, the positioning must be checked against 2024 to 2026 literature.

---

## Layer 1: Data

### Crash-to-segment assignment (nearest segment within 200 ft)
- **Anchor:** distance allowance from Dumbaugh, Rae and Wunneburger (2011);
  nearest-feature snapping with a cap is standard GIS practice.
- **Attack:** "The 2011 paper used 200 ft to buffer census block groups, not
  to snap crashes to segments. You cited a convention from a different unit of
  analysis. And 200 ft in a gridded city can snap a parking-lot crash onto the
  arterial."
- **Answer:** Correct on the citation, and the phrasing has been corrected:
  the paper supplies the geolocation-error allowance, not the snapping
  procedure. The operative defense is empirical: median snap distance is 4 ft,
  p90 is 15 ft, p99 is 106 ft, so the cap almost never binds. Freeway, ramp,
  and frontage-road crashes are filtered upstream via CRIS road-part codes.
  Sensitivity at 100 and 250 ft is queued.
- **Status:** SOUND (citation reworded; buffer sensitivity run 2026-07-03:
  severe assignments 9,565/9,711/9,756 at 100/200/250 ft, per-segment count
  correlations 0.995 and 0.999 against the 200 ft baseline).

### Severity definition (KABCO K plus A, from CRIS)
- **Anchor:** matches the City's own HIN definition, keeping the comparison
  apples to apples; MMUCC 4th edition defines suspected serious injury.
- **Attack:** "Texas revised the CR-3 form on 2018-01-01 to the MMUCC 4
  serious-injury definition; statewide serious injuries stepped down about 15
  percent. Two of your ten outcome years use the old definition. And police
  A-ratings show roughly 50 percent sensitivity against hospital records."
- **Answer:** The break is real and disclosed. It shifts the level of a pooled
  ten-year count roughly uniformly; it biases spatial coefficients only if
  reclassification correlated with street type. The 2018-and-later
  sensitivity (2026-07-03): max design-IRR drift 12.2 percent, on a
  statistically insignificant median-type dummy, and the overlooked set is
  85 percent stable (Jaccard); the definitional break does not drive
  results. The temporal test window (2022 to 2026) sits entirely under the
  new definition. KABCO misclassification is a field-wide
  limitation carried by every study using police data, including the HIN
  itself, and both maps inherit it equally.
- **Status:** CAVEAT, 2018-plus sensitivity queued.

### Boundary exclusion (8,338 segments outside the full-purpose area)
- **Anchor:** selection on data coverage, not on outcome.
- **Attack:** "You dropped 11 percent of the network. Convenient."
- **Answer:** Outside the boundary the recorded rate is 0.25 severe crashes
  per mile versus 64 inside, a 256 to 1 ratio that is diagnostic of CRIS
  jurisdictional coding, not of safety. Including those false zeros would
  teach the model that those designs are safe. The exclusion rule is
  observable (boundary membership), not outcome-based.
- **Status:** SOUND.

### Missing traffic counts (74 percent of segments; imputed plus flag)
- **Anchor:** missing-indicator method; Groenwold et al. (2012) for its limits
  in observational estimation, Sisk, Sperrin et al. (2023) for its validity in
  prediction models when missingness persists at deployment.
- **Attack:** "Groenwold says the missing-indicator method yields partial
  confounder adjustment outside randomized trials. ADT is the central
  confounder and is missing on three quarters of the network, demonstrably not
  at random. Every design coefficient carries residual traffic confounding."
- **Answer:** Split by use. For the screening product the indicator approach
  is the recommended practice, because the City will never have counters on
  most local streets and the model must score them anyway. For the causal
  table the concern is real: imputation is within road class (so residual
  confounding operates only within class strata), the pre-registered
  measured-subset refit produced zero direction flips among significant
  effects, and the large magnitude drifts on that subset are consistent with
  its arterial-heavy composition. The reweighting check (2026-07-03)
  explains only part of the drift (max road-class IRR drift 108 percent
  unweighted, 83 percent reweighted to the full class mix), so composition
  is a partial explanation and the remainder is disclosed as unexplained;
  the pre-registered pass criterion, direction stability, holds. A
  multiple-imputation sensitivity remains queued for the causal table.
- **Status:** CAVEAT (reweighting run 2026-07-03, partial; MI queued;
  magnitude instability on the measured subset is a stated limitation).

---

## Layer 2: Spatial baseline

### Getis-Ord Gi* hotspots with false-discovery-rate control
- **Anchor:** Getis and Ord (1992); Benjamini and Hochberg (1995); FDR on
  local spatial statistics per Caldas de Castro and Singer (2006), the GeoDa
  default practice; 999 conditional permutations.
- **Attack:** "Gi* on raw counts over variable-length segments partly maps
  segment length, not risk. You length-adjusted the global statistic and not
  the local one."
- **Answer:** The layer's purpose is to reconstruct count-based reactive
  screening from raw public data, so count logic is the design requirement,
  and ArcGIS guidance endorses counts when the question is where incidents
  concentrate. Segment lengths are partly regularized by the network build.
  The per-mile sensitivity (2026-07-03): 95.3 percent of segments classify
  identically, but the top-589-mile sets overlap at Jaccard 0.56, so the
  hotspot map's exact membership is genuinely sensitive to the
  counts-versus-rates choice. Reported as a finding in its own right: it
  echoes the 43 percent Gi*-to-HIN overlap, and both support the point that
  crash-based maps are method-sensitive, while no model comparison depends
  on Gi* membership.
- **Status:** CAVEAT with the sensitivity reported (2026-07-03).

### Spatial weights (shared-endpoint adjacency, distance band as check)
- **Anchor:** network-true adjacency from graph topology; both specifications
  reported, 93 percent classification agreement.
- **Attack:** "Weights choice drives local statistics."
- **Answer:** Both specifications were run before results were interpreted;
  the distance band over-smooths (23.6 mean neighbors); agreement is 93
  percent. The choice was made on evidence and both results are published.
- **Status:** SOUND.

---

## Layer 3: The count model

### Negative binomial (NB2) with a length offset
- **Anchor:** the standard family of the crash-frequency literature (Lord and
  Mannering 2010); offsets encode exposure.
- **Attack:** "Your overdispersion evidence is a heuristic, chi-square over
  degrees of freedom equal to 1.57, and 1.57 is modest."
- **Answer:** The formal evidence is the likelihood-ratio test of alpha equals
  zero: statistic 3,193, boundary-corrected p effectively zero (alpha 1.79).
  The model report now cites the test; the chi2/df statistic (1.57) is
  labeled a descriptive check.
- **Status:** SOUND (LR test reported, 2026-07-03).

### Zero-inflated challenger rejected on information criteria
- **Anchor:** Wilson (2015, Economics Letters): the Vuong test is invalid for
  NB versus ZINB because the null sits on the parameter boundary; information
  criteria are the recommended comparison.
- **Attack:** "You compared one ZINB specification, got a tie, and kept the
  model you preferred."
- **Answer:** The ruling was pre-registered: adopt ZINB only if clearly
  better. Delta AIC of 3 is a tie broken by parsimony, and skipping Vuong is
  the literature's recommendation, not a shortcut. Now complete in the
  report: BIC favors NB outright (43,986 vs 44,008), and the zero-share
  calibration ends the argument: the offset NB predicts 90.9 percent zero
  segments against 90.8 observed, so there is no excess zero mass for
  inflation machinery to explain.
- **Status:** SOUND (BIC and zero calibration reported, 2026-07-03).

### Cluster-robust standard errors (88 Super Neighborhood clusters)
- **Anchor:** Cameron and Miller (2015); 88 clusters is well above common
  adequacy thresholds.
- **Attack:** none surviving; residual Moran's I of 0.021 shows the spatial
  correlation concern is largely resolved by the covariates themselves.
- **Status:** SOUND.

### Calibration and the top tail
- **Attack:** "The model over-predicts the top decile by 13 to 20 percent and
  the citywide total by about 10 percent (10,649 predicted versus 9,720
  observed), and your headline corridors live in exactly that tail."
- **Answer:** Correct, disclosed, and contained: every product claim (capture,
  the divergence sets, corridor lists) is rank-based, and monotone
  miscalibration does not reorder a ranking. Corridor tables now lead with
  ranks and rounded estimates, and the aggregate over-prediction is disclosed.
  Out-of-fold tail calibration (13 percent) is better than in-sample (20).
- **Status:** SOUND (aggregate over-prediction disclosed in the model
  report's calibration section with the rank-based reading rule, 2026-07-03).

---

## Layer 4: Causal framework

### The DAG and the composite exposure
- **Anchor:** Pearl (2009); Textor et al. (2016, DAGitty); VanderWeele (2022)
  on constructed measures.
- **Attack:** "A composite road-design node is an ill-defined intervention,
  and DAGitty confirming your own adjusted set is circular."
- **Answer:** The identified estimand is the joint effect of the measured
  design features; individual coefficients are conditional associations, and
  for features downstream of functional class they carry a controlled-effect
  reading only under the drawn assumptions. The DAGitty result is verification
  that the fitted covariate set is sufficient under the stated graph, not a
  discovery procedure. The write-ups use this language.
- **Status:** CAVEAT, language enforced.

### Operating speed excluded as a mediator
- **Anchor:** mediator adjustment blocks the causal path under study
  (VanderWeele 2016); the DAG states design causes speed causes severity.
- **Attack:** "So your design effects include speed-mediated harm."
- **Answer:** Yes, by construction: the estimand is the total design effect,
  which is the policy-relevant quantity, since redesigns change speeds. The
  IRRs must never be described as independent of speed. Footnote: posted
  limits partly follow historical operating speed (85th percentile practice),
  so the posted-speed coefficient partly reflects existing behavior.
- **Status:** SOUND with the stated reading.

### Functional class: adjusted covariate, not a design effect
- **Anchor:** Westreich and Greenland (2013), the Table 2 fallacy.
- **Attack:** "You adjusted class as a confounder and then headlined its
  coefficient as your largest design effect."
- **Answer:** The audit found this committed in early write-ups and it is
  corrected: the IRR table is split into design features versus adjustment
  covariates, and the class coefficient is presented as a stratification
  pattern (arterials carry 2.4 to 2.9 times the rate of comparable locals),
  never as a reclassification effect. By the DAG, class is the one coefficient
  with no causal reading, and income inherits the same rule.
- **Status:** SOUND (report table partitioned into design and adjustment
  panels with the Westreich-Greenland note, 2026-07-03; deck done).

### The v2 estimand (imagery-adjusted coefficients)
- **Anchor:** controlled direct effects require no unmeasured
  mediator-outcome confounding (Cole and Hernan 2002; VanderWeele 2016);
  mediator measurement error biases direct effects (le Cessie et al. 2012).
- **Attack:** "You wrote that v2 coefficients are direct design effects. Your
  pedestrian proxy came out exactly null, so no adjustment occurred, and the
  latent land-use node breaks the identification anyway."
- **Answer:** The audit sustained this attack in full. The corrected reading:
  v2 was intended to move coefficients toward direct effects; the available
  proxy proved too weak (person counts null at 1.00, from sparse 2015-vintage
  low-resolution imagery), so v2 coefficients remain total design effects with
  the exposure artifact only partially attenuated. The sidewalk coefficients
  moving in the predicted direction (1.71 to 1.53 and similar) is directional
  evidence for the artifact hypothesis and is claimed as exactly that.
- **Status:** SOUND (docstring and report header rewritten to the corrected
  estimand, 2026-07-03).

### Underreporting
- **Anchor:** nondifferential outcome underascertainment with high specificity
  leaves ratio measures approximately unbiased; linkage studies document 30 to
  56 percent pedestrian and cyclist underreporting with racial gradients.
- **Attack:** "You drew the reporting bias in the DAG and then modeled
  recorded crashes anyway. Drawing a bias is not addressing it."
- **Answer:** Stronger than disclosure, and now stated affirmatively: in a
  log-linear count model, reporting that is a multiplicative thinning
  conditionally independent of design given the adjusted neighborhood
  covariates is absorbed by the intercept and the income coefficient, leaving
  design IRRs unbiased. Corollaries: the income coefficient is contaminated by
  reporting and is never interpreted; absolute counts and cross-neighborhood
  comparisons of observed burdens inherit the bias; and the design-based score
  is less vulnerable to local underreporting than the crash-count HIN, because
  coefficients pool citywide. The race-sensitivity refit (max IRR drift 14.5
  percent) partially checks the income-only assumption.
- **Status:** SOUND with the stated scope.

### The land-use latent
- **Attack:** "Your identification hangs on land use touching design only
  through class and traffic. Commercial strips get sidewalks. Add that arrow
  and identification fails. Worse, your own sidewalk caveat requires the arrow
  your DAG omits."
- **Answer:** The audit's sharpest finding, conceded: the drawn graph and the
  sidewalk-artifact story are inconsistent, and the operative beliefs are the
  artifact story's. The DAG is being redrawn with the land-use-to-sidewalks
  arrow and the honest identification loss reported. The durable fix is
  measuring land use citywide from county parcel records (a pilot conflation
  exists at 79 percent coverage); that work is the highest-value remaining
  modeling investment. The divergence deliverable does not depend on this
  identification.
- **Status:** FIX QUEUED (DAG redraw; citywide conflation on the roadmap).

### What needs causal identification and what does not
- **Anchor:** the prediction versus causation task distinction (Hernan, Hsu
  and Healy 2019).
- **The clean split:** the overlooked-streets list is a prediction product and
  needs predictive validity, which the blocked validation establishes. The IRR
  sentences are causal claims and carry every assumption above. The equity
  overlay is description. Keeping these three registers separate is the single
  most important discipline in presenting this work.
- **Status:** SOUND when the language holds the line.

---

## Layer 5: Validation

### Spatially blocked cross-validation
- **Anchor:** Roberts et al. (2017): hold out along the dimension of
  dependence you generalize across. Random folds leak spatial structure.
- **Attack:** "Small folds failed to converge and you originally ranked
  unpredicted segments last."
- **Answer:** Caught and corrected during the work: capture is computed on the
  predicted subset with out-of-fold coverage reported (100 percent for the
  district blocking). District and Super Neighborhood blockings agree (45 and
  47 percent).
- **Status:** SOUND.

### The comparator itself: the City's HIN genealogy (corrected 2026-07-03)
- **Three vintages exist**, per the City's own web map and service metadata,
  all archived in `data/external/`:
  1. **HIN 2018** (2014 to 2018 data): the VZAP-era original. The VZAP
     publishes no formula or mileage, only "nearly 60% of traffic deaths and
     serious injuries occur on just 6% of Houston's streets" (VZAP p. 14).
     Measured here: 906 features, 426 raw miles. The VZAP equity statistic
     (Socially Vulnerable Communities: 33 percent of streets, 52 percent of
     HIN streets) describes THIS vintage.
  2. **HIN 2022** (2018 to 2022 data): THE COMPARATOR THIS PROJECT INGESTED
     as `on_hin` (service: HoustonMap/Transportation/MapServer/20). Its
     metadata states the method: CRIS crashes geocoded, streets segmented
     into half-mile lengths, crashes joined within 50 ft. 589 miles as
     measured on this project's network. The earlier note dating the
     comparator to 2014-2018 was wrong and is superseded by this entry.
  3. **HIN 2025** (2021 to 2025 data): published 2026 with a full public
     methodology (half-mile segmentation, 50 ft join, minimum 4.5 severe
     crashes per half-mile, freeways excluded; 6.81 percent of streets,
     52.67 percent of deaths and serious injuries). 1,080 features, 509 raw
     miles, plus Priority (48 mi), Bike (75 mi), Ped (280 mi) sublayers.
     Integration pending (the comprehensive passthrough).
- **Method characterization now rests on the City's own words:** all
  vintages are count-density screening on half-mile windows with no
  exposure, design, or empirical-Bayes adjustment; exactly the reactive
  method this project's two-period test evaluates.
- **The policy hook, from the City's own plan:** VZAP Action 2.3 commits to
  systemic analysis ("Identify high-risk roadway features correlated with
  specific, recurring severe crash types for each mode... Address multiple
  corridors and intersections with similar characteristics of streets
  identified in the High Injury Network"), status "Underway" in the 2022
  Annual Report. The Concept PSN is an open implementation of that committed
  action, not an external critique.
- **Why the capture numbers differ across documents:** the City reports
  "nearly 60% on 6%" (2018 vintage, 2014-2018 window) and "52.67% on 6.81%"
  (2025 vintage, 2021-2025 window); this project measures 52 percent for
  the 2022 vintage on its own 2016-2026 window and network. Different
  windows, vintages, and network measurements; all correct.

### Capture at matched mileage, and the HIN comparison
- **Anchor:** capture at fixed mileage is the standard screening-efficiency
  metric; regression to the mean inflates evaluations of sites selected on
  observed counts (Hauer; Highway Safety Manual network screening).
- **Attack:** "Your three reference numbers are not on a common footing:
  model out-of-fold, Gi* in-sample, HIN selected on the graded outcome."
- **Answer, with vintage precision (corrected):** the asymmetry runs against
  the model, making the parity claim conservative. The ingested HIN (2022
  vintage) was selected on 2018-2022 crashes, so five of the ten grading
  years overlap its selection window: substantially in-sample. The Gi*
  reference is fully in-sample. The precise sentence: "the references are
  graded substantially (HIN) or fully (Gi*) on the crashes that selected
  them; the model is graded on districts it never saw." In the temporal test
  (Layer 8), note one further asymmetry in the HIN's favor: its 2018-2022
  selection window overlaps one year of the 2022-2026 test window, while
  the model saw none of it; the model's 51 versus the HIN's 49 is therefore
  conservative on that axis too.
- **Status:** SOUND (temporal test run; bootstrap intervals reported;
  vintage corrected 2026-07-03).

### The black-box benchmark
- **Attack:** "An untuned default gradient-boosting model is a floor on the
  machine-learning ceiling, so the interpretability price is at least 2 to 3
  points, not at most."
- **Answer:** Conceded and reworded everywhere: the claim is now "about 3
  points against a default-configuration benchmark under identical folds." A
  modestly tuned benchmark run is queued to test whether the ceiling moves.
- **Status:** FIX QUEUED (tuned benchmark sensitivity).

---

## Layer 6: Divergence and equity

### The divergence result
- **Answer shape:** 49 percent of the high-design-risk network absent from
  the HIN at matched mileage, robust at 42 to 51 percent across thresholds,
  already carrying 1,399 recorded severe crashes. Framing rule: the HIN
  performs as crash-history screening should; the list is complementary
  proactive screening, not a criticism of Public Works.
- **Status:** SOUND (rank-based, threshold-robust, validated model).

### The equity overlay
- **Attack:** "Income is in the model, so poorer streets get mechanically
  higher predicted risk, and your equity finding is partly baked into the
  selection rule. Also, blind spots falling somewhere is a claim about the
  screening process you have not established."
- **Answer, revised after the check RAN AND SUSTAINED THE ATTACK
  (2026-07-03):** under a design-only score (all demographic covariates
  removed) the income skew of the overlooked set disappears and mildly
  reverses (design-only median income $80,313 vs citywide $69,625; sub-$100k
  62 vs 64 percent), against the full model's $61,405 and 78 percent. The
  skew is therefore substantially produced by the model's income and poverty
  coefficients, which steer predicted risk toward poorer areas. The
  defensible claims: (1) the deployed score's overlooked set IS
  lower-income, as a description of the product, with the mechanism
  disclosed; (2) the model's context adjustment is legitimate (it is a
  validated confounder set and improves prediction), so the deployed score
  is the right product, but its equity profile is partly its own
  construction; (3) the DANGER finding is independent of this: the
  overlooked set's forward worsening (temporal holdout, 17 percent above
  trend) holds regardless of why its income profile arises. What may no
  longer be said, anywhere: that reactive screening's blind spots fall in
  poor neighborhoods as a finding about design or process.
- **Spoken answer:** "The overlooked streets under our deployed score skew
  lower-income, and we report exactly why: the model adjusts for
  neighborhood context, and that adjustment contributes to the skew. A
  design-only score does not show it. We ran that check ourselves and
  publish it. What does not depend on any of this is that those streets went
  on to get worse."
- **Status:** SOUND only in the revised language (check run 2026-07-03; all
  project text updated the same day).

---

## Layer 7: Imagery

### Coverage audit before commitment
- **Anchor:** coverage rule follows Yue (2025); Mapillary GPS error of 2 to 6
  m sits well inside the 25 m match radius.
- **Answer shape:** 94 to 100 percent of arterial miles covered in every
  district, no income bias in coverage (62 to 69 percent across tiers), and
  the richness scan corrected the audit's own optimism (2019-plus imagery
  covers only 23 percent of arterials), which drove the decision to run
  open models over all vintages rather than rely on Mapillary's precomputed
  detections.
- **Status:** SOUND.

### Panorama handling
- **Anchor:** four 90-degree gnomonic views is the literature-standard
  treatment of equirectangular panoramas.
- **Attack:** "You sliced 1024-pixel thumbnails, so each view holds about 256
  by 256 real pixels. A pedestrian at 20 m is 14 pixels tall. Your pedestrian
  instrument was physically near-blind, and you reported its null as a
  finding."
- **Answer:** Sustained by the audit and adopted: pixel shares (road,
  vegetation, building) are area-integrated and robust to the resolution
  budget; object counts are not, and the person-count null is reported as
  uninformative about walking, an instrument limitation, not a conclusion.
  The fixes are concrete: re-download panoramas at 2048 pixels (the API
  offers it), re-run detection, hand-label roughly 200 images for detector
  recall, and report a threshold sensitivity. Until then, no claim rests on
  the person counts.
- **Status:** FIX QUEUED (high-resolution re-run, labeled validation set).

### Model transfer (Cityscapes and COCO to Houston)
- **Attack:** "German-trained segmentation, zero local validation."
- **Answer:** Partially conceded: no hand-labeled Houston validation set
  exists yet (queued, and Mapillary's own detections on 2019-plus imagery
  provide a free comparison set). Mitigations: coarse pixel shares are the
  most transfer-robust segmenter outputs; the features carrying the v2 result
  involve large objects (vehicles); and the vehicle-count finding (1.24 per
  SD) independently replicates the strongest result in Yue (2025), which is
  itself a form of external validation.
- **Status:** FIX QUEUED (labeled validation, detection comparison).

### Temporal alignment (2015-vintage imagery, 2016 to 2026 crashes)
- **Answer shape:** exposure measured at or before the outcome window start
  is the correct ordering (no reverse causation); drift attenuates toward the
  null; stable design features drift slowly. The mismatch inverts into a
  strength under the temporal test, where imagery fully precedes the 2022 to
  2026 evaluation window. The vintage-control refit (2026-07-03): adding
  median capture year moves AIC by 5 points and no coefficient by more than
  4.5 percent; the vehicle IRR is unchanged at 1.24. Vintage is not driving
  the imagery results. Separately, the v2 gain is fold-consistent: v2 beats
  v1 in 10 of 11 district folds (sign test p = 0.012, mean +2.6 points).
- **Status:** SOUND (vintage control and fold consistency run 2026-07-03).

---

## Layer 8: Temporal holdout (run 2026-07-03)

- **Design:** fit on 2016 to 2021 severe crashes, freeze all maps as of
  end-2021 (model, Gi* on pre-2022 crashes only, the HIN as published in
  2022), grade everything on the 4.4 years of 2022 to 2026 crashes; forward
  test of the overlooked set (site consistency applied to the disagreement
  set); sensitivities for the COVID years (train 2016 to 2019) and the injury
  definition (train 2018 to 2021). Report:
  `reports/temporal_holdout_report.md`.
- **Anchors:** Cheng and Washington (2008) two-period evaluation framework;
  TRIPOD temporal-validation hierarchy (Collins et al. 2015); Roberts et al.
  (2017) blocking logic applied to time; Hauer and the Highway Safety Manual
  on regression to the mean.
- **Results, against the pre-registered rules:** prospective capture of
  2022 to 2026 severe crashes at 589 matched miles: design model v2 51
  percent, v1 49, official HIN 49, no-design null 42, and the Gi* map built
  on pre-2022 crashes 40 (a collapse from its 54 percent in-sample: the
  regression-to-the-mean prediction, confirmed; the HIN's corridor
  aggregation evidently buffers it, falling only 52 to 49). Bootstrap 95
  percent interval for v2 minus HIN is -0 to +4 points, so by the
  pre-registered rule the model MATCHES the HIN prospectively (point
  estimate above it) and the claim of beating it is not made. The forward
  test succeeds: the pre-fit overlooked set worsened from 0.41 to 0.52
  severe crashes per mile per year (ratio 1.27 against a citywide 1.08;
  trend-adjusted 1.17), recording 691 severe crashes in the post window,
  while the HIN set improved relative to trend (0.90) as regression to the
  mean and treatments predict. Training-window sensitivities: 48 percent
  capture under both the pre-COVID and single-definition windows.
- **Spoken answer:** "Frozen at the end of 2021, the design model
  anticipated the next four and a half years of severe crashes as well as
  the City's own High Injury Network, without using the judged streets'
  crash history, and the streets it flagged that the HIN missed went on to
  worsen 17 percent relative to the citywide trend. A raw crash-hotspot map
  built the same way collapsed to 40 percent, which is what regression to
  the mean does to screening that selects on observed counts."

---

## Parameter judgment calls (convention plus disclosed choice)

| Parameter | Value | Basis |
|---|---|---|
| Crash snap cap | 200 ft | Error allowance per Dumbaugh et al.; binds for under 1 percent (p99 = 106 ft) |
| Imagery sampling interval | 50 m | Follows Yue (2025) |
| Photo match radius | 25 m | Conservative given 2 to 6 m Mapillary GPS error |
| Images per segment cap | 12 | Cost control; median achieved is 3 |
| Detection threshold | 0.5 | Torchvision convention; sensitivity queued |
| Self-capture area rule | 15 percent of frame | Visual inspection of walking panoramas; tallied separately |
| Pano slicing | 4 views at 90 degrees | Literature standard |
| Severe outcome | K plus A | The City's HIN definition |
| High-risk threshold | 589 mi (plus 546 and top 5/10 percent) | Matched to the HIN's size; multi-threshold by design |

## Known limitations (the honest ledger)

1. Pedestrian exposure remains effectively unmeasured; the sidewalk artifact
   is only partially attenuated in v2.
2. Land use is unmeasured citywide; the DAG identification for causal IRRs
   depends on a disputed exclusion restriction until parcel conflation lands.
3. 74 percent of traffic volumes are imputed (with flags); causal IRRs lean
   on the measured-subset sensitivity.
4. Police-reported severity is noisily graded and under-ascertained, with
   documented inequities; ratio estimates are protected under stated
   assumptions, absolute counts are not.
5. Top-tail point predictions run 13 to 20 percent high; rankings, not
   counts, are the supported claim.
6. Features describe today's streets, not the streets as of each crash.
7. No hand-labeled validation of the CV models yet (queued for the PC).
8. Findings are Houston, 2016 to 2026; transfer elsewhere is untested.
9. The overlooked set's lower-income profile is partly produced by the
   model's own context adjustment (design-only score shows no skew); it is
   a description of the deployed score, never a design or process finding.

## Fix queue (from the 2026-07-03 audit)

Tier 1, language: COMPLETE 2026-07-03 (v2 estimand rewritten in docstring
and report; IRR table partitioned; person-null phrasing; RTM and
underreporting paragraphs; tail hedges and aggregate disclosure; HIN vintage
precision after the VZAP primary-document read).

Tier 2, cheap runs: COMPLETE 2026-07-03 except two, see
`reports/audit_sensitivities_report.md`. Passed: 2018-plus refit, buffer
sensitivity, vintage control, fold-level v2 consistency, LR test plus BIC
and zero calibration. Mixed, reported honestly: Gi* per-mile (top-set
Jaccard 0.56), measured-subset reweighting (partial explanation). SUSTAINED
the audit's attack: design-only equity overlay (income skew is
score-mechanical; all language revised). Remaining: off-street image filter
(needs the per-image table on the PC); multiple-imputation ADT sensitivity.

Tier 3, upgrades: temporal holdout COMPLETE (Layer 8). Remaining: 2048-pixel
pano re-run plus roughly 200 labeled images (PC); citywide parcel land-use
conflation; DAG redraw with the land-use arrow; modestly tuned benchmark.

## Sources

Methods and statistics:
- Lord and Mannering (2010), Transportation Research Part A. Crash-frequency
  methods review.
- Cameron and Trivedi (1990), Journal of Econometrics. Overdispersion tests.
- Wilson (2015), Economics Letters. Vuong invalid for zero-inflation.
  https://ideas.repec.org/a/eee/ecolet/v127y2015icp51-53.html
- Cameron and Miller (2015), Journal of Human Resources. Cluster-robust
  inference. https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf
- Getis and Ord (1992), Geographical Analysis. Gi*.
- Moran (1950), Biometrika. Spatial autocorrelation.
- Benjamini and Hochberg (1995), JRSS-B. False discovery rate.
- Caldas de Castro and Singer (2006). FDR for local spatial statistics.
- Roberts et al. (2017), Ecography. Blocked cross-validation.
- Cheng and Washington (2008), Transportation Research Record 2083. Hotspot
  evaluation criteria. https://journals.sagepub.com/doi/10.3141/2083-09
- Collins et al. (2015), the TRIPOD statement.
  https://pubmed.ncbi.nlm.nih.gov/25627261/
- Hauer et al. (2002), TRR 1784. Empirical Bayes tutorial (regression to the
  mean). https://journals.sagepub.com/doi/10.3141/1784-16
- Groenwold et al. (2012), CMAJ. Missing-indicator limits.
  https://www.cmaj.ca/content/184/11/1265
- Sisk, Sperrin et al. (2023), Statistical Methods in Medical Research.
  Missing indicators in prediction models.
  https://journals.sagepub.com/doi/10.1177/09622802231165001

Causal inference:
- Pearl (2009), Causality, 2nd ed.
- Textor et al. (2016), International Journal of Epidemiology. DAGitty.
- Westreich and Greenland (2013), American Journal of Epidemiology. The Table
  2 fallacy. https://academic.oup.com/aje/article/177/4/292/147738
- VanderWeele and Hernan (2013), Journal of Causal Inference. Multiple
  versions of treatment. https://pmc.ncbi.nlm.nih.gov/articles/PMC4219328/
- VanderWeele (2022), Epidemiology. Constructed measures.
- Cole and Hernan (2002), International Journal of Epidemiology. Direct
  effects. https://academic.oup.com/ije/article/31/1/163/655948
- VanderWeele (2016), Annual Review of Public Health. Mediation.
- le Cessie et al. (2012), Epidemiology. Mediator measurement error.
- Greenland (2001), International Journal of Epidemiology. Ecologic bias.
- Hernan, Hsu and Healy (2019), Chance. Prediction versus causation.
  https://cdn1.sph.harvard.edu/wp-content/uploads/sites/1268/1268/20/hernan_chance19.pdf

Data, imagery, and computer vision:
- Dumbaugh, Rae and Wunneburger (2011), Urban Design International.
- Yue (2025), Accident Analysis and Prevention 210:107851.
  https://www.sciencedirect.com/science/article/abs/pii/S0001457524003968
- Xie et al. (2021), NeurIPS. SegFormer.
- Ren et al. (2015), NeurIPS. Faster R-CNN.
- Cordts et al. (2016), CVPR. Cityscapes.
- Lin et al. (2014), ECCV. COCO.
- Chen et al. (2017). Cross-city segmentation transfer.
  https://arxiv.org/abs/1704.08509
- Zhang et al. (2016). Faster R-CNN on small pedestrians.
  https://arxiv.org/abs/1607.07032
- FHWA, MMUCC 4th edition serious-injury definition.
  https://highways.dot.gov/safety/hsip/spm/national-definition-serious-injuries-mmucc-4th-edition
- Sandt et al. (2024), KABCO versus injury-severity-score linkage.
  https://pubmed.ncbi.nlm.nih.gov/38917362/
- Burdett et al. (2015), TRR. Police A-code accuracy.

Policy and practice:
- FHWA (2013). Systemic Safety Project Selection Tool.
- NCHRP Report 893 (2018). Systemic Pedestrian Safety Analysis.
- City of Houston (2020, 2022). Vision Zero Action Plan; High Injury Network.
- Texas HB 1631 (2019).
- Alameda CTC (2024). High-Injury Network and Proactive Safety Network
  Report. https://www.alamedactc.org/wp-content/uploads/2024/09/HIN_PSN_Report.pdf
- Kumfer et al. (2024), TRR. Systemic pedestrian analysis, Montgomery County.
  https://journals.sagepub.com/doi/10.1177/03611981241247178
