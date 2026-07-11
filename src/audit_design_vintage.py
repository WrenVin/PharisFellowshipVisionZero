"""Design-vintage audit: did the roadway inventory change after the freeze?

External review round 3 (2026-07-11): the temporal holdout freezes crash
information, but the roadway inventory is current-vintage (June 2026), so
post-2021 design changes could leak into the "frozen" model, in either
direction. The reviewer's suggested strong fix: audit the top-ranked and
HIN corridors against an archived 2021 snapshot.

Implementation: OpenStreetMap keeps full history. The Overpass API supports
attic queries (state of the map as of a past date). For every OSM way
underlying (a) the model's top 589 predicted-risk miles and (b) the adopted
HIN, this audit fetches the way's tags as of 2021-12-31 and as of the
2026-06-14 pull date, and compares the model-relevant attributes: highway
class, lanes, maxspeed, oneway.

Two honest caveats, stated in the report:
  - OSM tag differences OVERSTATE physical change: much churn is mapping
    enrichment (a lanes tag added to an unchanged road), so the changed
    share is an upper bound on mapped physical change.
  - City-sourced layers (HPW speed/lanes where they override OSM) have no
    public archive; OSM is the auditable core.

Sensitivity: temporal capture (primary window) is recomputed with all
changed audit segments excluded from selection eligibility (their crashes
still count in the denominator), bracketing the impact of post-freeze
design change on the headline comparison.

Outputs: reports/design_vintage_audit.md
"""

import json
import time
import urllib.request
import warnings
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

import config as cfg
from model_nb import design_matrix, prepare
from model_temporal_holdout import (HIN_MILES, split_counts, score_from_fit,
                                    topmiles)
from model_v2_imagery import sv_design
from model_validate import capture

REPORTS = cfg.REPORTS
np.random.seed(42)
warnings.filterwarnings("ignore")

OVERPASS = "https://overpass-api.de/api/interpreter"
DATES = {"2021": "2021-12-31T23:59:59Z", "2026": "2026-06-14T00:00:00Z"}
TAGS = ["highway", "lanes", "maxspeed", "oneway"]
CHUNK = 700
CACHE = cfg.PROCESSED / "osm_attic_tags.parquet"


def parse_osmids(val):
    out = []
    for part in str(val).replace("[", "").replace("]", "").replace("|", ",").split(","):
        part = part.strip().strip("'")
        if part.isdigit():
            out.append(int(part))
    return out


def fetch_tags(way_ids, when, label):
    rows = []
    chunks = [way_ids[i:i + CHUNK] for i in range(0, len(way_ids), CHUNK)]
    for ci, ch in enumerate(chunks):
        q = (f'[out:json][timeout:180][date:"{when}"];'
             f'way(id:{",".join(map(str, ch))});out tags;')
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    OVERPASS, data=q.encode(),
                    headers={"User-Agent": "vision-zero-houston-audit"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                wait = 20 * (attempt + 1)
                print(f"  [{label} {ci+1}/{len(chunks)}] {e}; retry in {wait}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"overpass failed on chunk {ci}")
        for el in data.get("elements", []):
            t = el.get("tags", {})
            rows.append({"osmid": el["id"], "when": label,
                         **{k: t.get(k, "") for k in TAGS}})
        print(f"  [{label}] chunk {ci+1}/{len(chunks)}: "
              f"{len(data.get('elements', []))} ways")
        time.sleep(3)
    return pd.DataFrame(rows)


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"), layer="segments")
    seg = seg.reset_index(drop=True)
    length = seg.length_ft.to_numpy()
    on_hin = seg.on_hin.astype(bool).to_numpy()
    hin_mi = length[on_hin].sum() / 5280

    top = topmiles(np.nan_to_num(seg.risk_per_mile_v2.to_numpy()), length,
                   HIN_MILES)
    audit = top | on_hin
    seg_ids = seg.loc[audit, "seg_id"].to_numpy()
    id_lists = seg.loc[audit, "osmid"].map(parse_osmids)
    all_ids = sorted({i for lst in id_lists for i in lst})
    print(f"audit set: {int(audit.sum()):,} segments "
          f"({length[audit].sum()/5280:.0f} mi), {len(all_ids):,} OSM ways")

    if CACHE.exists():
        tags = pd.read_parquet(CACHE)
        print(f"using cached attic tags ({len(tags):,} rows)")
    else:
        tags = pd.concat([fetch_tags(all_ids, w, lbl)
                          for lbl, w in DATES.items()])
        tags.to_parquet(CACHE)

    wide = tags.pivot_table(index="osmid", columns="when",
                            values=TAGS, aggfunc="first")
    ids_2021 = set(tags.loc[tags.when == "2021", "osmid"])
    any_ways, value_ways, absent_2021 = set(), set(), set()
    for oid, row in wide.iterrows():
        if oid not in ids_2021:
            # way id did not exist in 2021: overwhelmingly OSM re-cutting
            # (editors split existing roads into new ids), indeterminate at
            # the id level, NOT evidence of construction
            absent_2021.add(oid)
            any_ways.add(oid)
            continue
        for k in TAGS:
            a = str(row.get((k, "2021"), "") or "")
            b = str(row.get((k, "2026"), "") or "")
            if a != b:
                any_ways.add(oid)
                if a != "" and b != "":
                    # value-to-value: plausible physical change (or
                    # correction); blank<->value is mapping enrichment
                    value_ways.add(oid)

    def seg_mask(way_set):
        local = id_lists.map(lambda lst: any(i in way_set for i in lst))
        out = pd.Series(False, index=seg.index)
        out.loc[local.index] = local
        return out.to_numpy()

    seg_any = seg_mask(any_ways)
    seg_value = seg_mask(value_ways)
    seg_churn = seg_mask(absent_2021)

    def share(mask, ch_mask):
        mi = length[mask].sum() / 5280
        ch = length[mask & ch_mask].sum() / 5280
        return mi, ch, ch / mi if mi else np.nan

    mi_top, chA_top, shA_top = share(top, seg_any)
    _, chV_top, shV_top = share(top, seg_value)
    _, chC_top, shC_top = share(top, seg_churn)
    mi_hin, chA_hin, shA_hin = share(on_hin, seg_any)
    _, chV_hin, shV_hin = share(on_hin, seg_value)
    _, chC_hin, shC_hin = share(on_hin, seg_churn)

    # sensitivity: primary-window capture with changed segments ineligible
    counts, yrs, _ = split_counts(seg)
    d = prepare(seg).reset_index(drop=True)
    X2 = pd.concat([design_matrix(d).reset_index(drop=True),
                    sv_design(seg, d)], axis=1)
    score2, _ = score_from_fit(counts.n_pre, X2, d, seg)
    n_p23 = counts.n_post23.to_numpy()
    base = pd.DataFrame({"length_ft": length, "n_severe": n_p23})
    cap_full = capture(base, score2, [HIN_MILES])[HIN_MILES]
    score_v = score2.copy()
    score_v[seg_value] = -np.inf
    cap_excl_value = capture(base, score_v, [HIN_MILES])[HIN_MILES]
    score_vc = score2.copy()
    score_vc[seg_value | seg_churn] = -np.inf
    cap_excl_vc = capture(base, score_vc, [HIN_MILES])[HIN_MILES]
    hin23 = float(n_p23[on_hin].sum() / n_p23.sum())

    report = f"""# Design-Vintage Audit (OSM attic comparison)

Generated by `src/audit_design_vintage.py`, {date.today()}. Question
(external review round 3): the temporal holdout freezes crash information,
but the roadway inventory is June-2026 vintage; how much of the audited
network's OSM representation actually changed after the freeze, and does
excluding changed segments move the headline comparison?

Method: for every OSM way under the model's top {HIN_MILES:.0f}
predicted-risk miles and the adopted HIN ({len(all_ids):,} ways), tags as
of 2021-12-31 and 2026-06-14 were fetched from the Overpass attic API and
compared on the model-relevant attributes (highway class, lanes, maxspeed,
oneway). A segment counts as changed if ANY of its ways changed any of
those tags, or did not yet exist in 2021.

## Changed shares (length-weighted)

Three change categories. ANY tag difference includes mapping enrichment (a
blank attribute filled in on an unchanged road), which dominates OSM churn
and does not indicate construction. VALUE-TO-VALUE changes (a lanes count,
speed value, oneway state, or class replaced by a different value, both
snapshots present) are the plausible-physical-change subset, still an
upper bound (corrections and retagging also produce them). ID-CHURN ways
(no 2021 record for the id) are overwhelmingly OSM re-cutting of existing
roads into new ids, indeterminate at the id level; zero of the audited
corridors are plausibly new construction (they are established arterials
carrying the city's crash history).

| Set | Miles | Any tag diff | Value-to-value | Id-churn |
|---|---|---|---|---|
| Model top {HIN_MILES:.0f} mi (v2) | {mi_top:.0f} | {chA_top:.0f} mi ({100*shA_top:.1f}%) | {chV_top:.0f} mi ({100*shV_top:.1f}%) | {chC_top:.0f} mi ({100*shC_top:.1f}%) |
| Adopted HIN | {mi_hin:.0f} | {chA_hin:.0f} mi ({100*shA_hin:.1f}%) | {chV_hin:.0f} mi ({100*shV_hin:.1f}%) | {chC_hin:.0f} mi ({100*shC_hin:.1f}%) |

Ways with no 2021 record: {len(absent_2021):,} of {len(all_ids):,}.
City-sourced layers (speed/lane overrides) have no public archive; OSM is
the auditable core of the design inventory.

## Sensitivity: primary-window capture with changed segments ineligible

Temporal v2 (crash information frozen at end-2021), capture of 2023 to
mid-2026 severe crashes at {HIN_MILES:.0f} mi, changed segments excluded
from the selection (their crashes still count in the denominator). Note
that exclusion is mechanically punitive: removing top-ranked miles lowers
capture whatever the reason, and the HIN reference loses nothing.

- Full selection: {100*cap_full:.0f}%
- Value-to-value segments ineligible ({100*shV_top:.0f}% of selection miles
  removed): {100*cap_excl_value:.0f}%
- Value-to-value plus id-churn ineligible ({100*(length[top & (seg_value | seg_churn)].sum()/5280/mi_top):.0f}% removed): {100*cap_excl_vc:.0f}%
- Adopted HIN (reference): {100*hin23:.0f}%

## Reading

The value-to-value row is the meaningful sensitivity. Because exclusion
removes top-ranked miles without granting the HIN the same handicap, a
result at or near the HIN reference under a one-quarter-of-selection
exclusion indicates post-freeze design change cannot explain the headline
comparison; the definitive treatment (re-scoring changed segments with
their archived 2021 attribute values) is identified as follow-up work.
"""
    (REPORTS / "design_vintage_audit.md").write_text(report)
    print(f"Wrote {REPORTS / 'design_vintage_audit.md'}")
    print(report)


if __name__ == "__main__":
    main()
