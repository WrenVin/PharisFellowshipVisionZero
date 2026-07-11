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
    changed_ways = set()
    absent_2021 = set()
    for oid, row in wide.iterrows():
        diffs = [k for k in TAGS
                 if str(row.get((k, "2021"), "")) != str(row.get((k, "2026"), ""))]
        present_2021 = any(str(row.get((k, "2021"), "")) != ""
                           for k in TAGS) or (oid in tags[tags.when == "2021"].osmid.values)
        if not present_2021:
            absent_2021.add(oid)
            changed_ways.add(oid)
        elif diffs:
            changed_ways.add(oid)

    seg_changed_local = id_lists.map(lambda lst: any(i in changed_ways for i in lst))
    seg_changed = pd.Series(False, index=seg.index)
    seg_changed.loc[seg_changed_local.index] = seg_changed_local
    seg_changed = seg_changed.to_numpy()

    def share(mask):
        mi = length[mask].sum() / 5280
        ch = length[mask & seg_changed].sum() / 5280
        return mi, ch, ch / mi if mi else np.nan

    mi_top, ch_top, sh_top = share(top)
    mi_hin, ch_hin, sh_hin = share(on_hin)

    # sensitivity: primary-window capture with changed segments ineligible
    counts, yrs, _ = split_counts(seg)
    d = prepare(seg).reset_index(drop=True)
    X2 = pd.concat([design_matrix(d).reset_index(drop=True),
                    sv_design(seg, d)], axis=1)
    score2, _ = score_from_fit(counts.n_pre, X2, d, seg)
    n_p23 = counts.n_post23.to_numpy()
    base = pd.DataFrame({"length_ft": length, "n_severe": n_p23})
    cap_full = capture(base, score2, [HIN_MILES])[HIN_MILES]
    score_x = score2.copy()
    score_x[seg_changed] = -np.inf
    cap_excl = capture(base, score_x, [HIN_MILES])[HIN_MILES]
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

## Changed shares (length-weighted; upper bounds on physical change)

| Set | Miles | Changed miles | Share |
|---|---|---|---|
| Model top {HIN_MILES:.0f} mi (v2) | {mi_top:.0f} | {ch_top:.0f} | {100*sh_top:.1f}% |
| Adopted HIN | {mi_hin:.0f} | {ch_hin:.0f} | {100*sh_hin:.1f}% |

Ways absent from OSM in 2021 (new or re-cut geometries): {len(absent_2021):,}
of {len(all_ids):,}.

OSM tag differences overstate physical change: much of the churn is mapping
enrichment (an attribute tagged on an unchanged road) rather than
construction, so these shares are upper bounds on mapped physical change.
City-sourced layers (speed/lane overrides) have no public archive; OSM is
the auditable core of the design inventory.

## Sensitivity: primary-window capture with changed segments ineligible

Temporal v2 (crash information frozen at end-2021), capture of 2023 to
mid-2026 severe crashes at {HIN_MILES:.0f} mi, changed segments excluded
from selection (their crashes still count in the denominator):

- Full selection: {100*cap_full:.0f}%
- Changed segments ineligible: {100*cap_excl:.0f}%
- Adopted HIN (reference): {100*hin23:.0f}%

## Reading

If the exclusion row remains at or above the HIN reference, post-freeze
design change cannot explain the headline comparison: the model maintains
its capture even when every corridor whose OSM representation changed
after 2021 is barred from selection.
"""
    (REPORTS / "design_vintage_audit.md").write_text(report)
    print(f"Wrote {REPORTS / 'design_vintage_audit.md'}")
    print(report)


if __name__ == "__main__":
    main()
