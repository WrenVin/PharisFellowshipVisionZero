#!/usr/bin/env python3
"""Independent verification of the Vision Zero dashboard's displayed numbers.

Re-implements, in Python, every computation the dashboard's JavaScript performs
(tally, YLL, FHWA cost, concentration/Gini, mode/income/ownership splits,
worst streets, per-year series) straight from the published docs/ files.
The dashboard's rendered values must match these. Two independent
implementations agreeing = high confidence the displayed data is correct.

Usage: python3 verify_dashboard.py <repo_docs_dir> [--mode ped|bike|veh] [--district C]
Prints a labeled report; also emits PYTHON_KPIS=<json> for machine comparison.
"""
import json
import sys
from collections import defaultdict

DOCS = sys.argv[1]
mode = None
district = None
for i, a in enumerate(sys.argv):
    if a == "--mode":
        mode = sys.argv[i + 1]
    if a == "--district":
        district = sys.argv[i + 1]

pts = json.load(open(f"{DOCS}/crash_points.json"))
seg = json.load(open(f"{DOCS}/segments_vz.geojson"))["features"]

# row: 0 lat 1 lon 2 sev 3 fatal 4 ped 5 bike 6 year 7 date 8 hour 9 yll
#      10 district 11 inc_tier 12 on_hin 13 on_txdot 14 seg_id 15 sn
#      16 n_k 17 n_a 18 n_b 19 n_c 20 n_noinj
PERSON_COST = {16: (1606644, 11258495), 17: (172179, 1089524),
               18: (44490, 224597), 19: (25933, 111281), 20: (6269, 10196)}


def mode_match(p):
    if mode is None or mode == "all":
        return True
    if mode == "ped":
        return bool(p[4])
    if mode == "bike":
        return bool(p[5])
    if mode == "veh":
        return not p[4] and not p[5]


def in_view(p):
    if district and p[10] != district:
        return False
    return True


# ---- tally (mirrors dashboard tally() + drawKPIs mode arithmetic) ----
killed = ksi = crashes = pk = bk = pksi = bksi = 0
yll = 0.0
econ = comp = 0
people_killed = people_serious = 0     # person-level truth (n_k / n_a sums)
by_year_f = defaultdict(int)
by_year_s = defaultdict(int)
inc = defaultdict(int)
own = {"city": 0, "txdot": 0}
seg_ksi = defaultdict(int)

for p in pts:
    if not in_view(p):
        continue
    mm = mode_match(p)
    if mm:
        yll += p[9] or 0
        for idx, (e, c) in PERSON_COST.items():
            econ += p[idx] * e
            comp += p[idx] * c
        crashes += 1
        if p[3]:
            killed += 1
        if p[2]:
            ksi += 1
            inc[p[11]] += 1
            own["txdot" if p[13] else "city"] += 1
            if p[14]:
                seg_ksi[p[14]] += 1
            by_year_f[p[6]] += p[3]
            by_year_s[p[6]] += (1 - p[3])
        people_killed += p[16]
        people_serious += p[17]
    # mode sub-splits use the unfiltered-mode tally (dashboard KPI arithmetic)
    if p[3] and p[4]:
        pk += 1
    if p[3] and p[5]:
        bk += 1
    if p[2] and p[4]:
        pksi += 1
    if p[2] and p[5]:
        bksi += 1

serious = ksi - killed

# ---- concentration (mirrors concentration(): rank street-miles by KSI density) ----
rows = []
totK = totM = 0.0
for f in seg:
    pr = f["properties"]
    if district and pr.get("district") != district:
        continue
    k = seg_ksi.get(pr["seg_id"], 0)
    m = (pr.get("length_ft") or 0) / 5280
    if m > 0:
        rows.append((k, m))
        totK += k
        totM += m
gini = pct_half = hin6 = None
if totK > 0:
    rows.sort(key=lambda r: r[0] / r[1], reverse=True)
    cumM = cumK = area = 0.0
    px = py = 0.0
    for k, m in rows:
        cumM += m
        cumK += k
        x, y = cumM / totM, cumK / totK
        area += (x - px) * (y + py) / 2
        if pct_half is None and y >= 0.5:
            pct_half = x
        if hin6 is None and x >= 0.06:
            hin6 = y
        px, py = x, y
    gini = max(0, min(1, 2 * area - 1))

# ---- worst streets: aggregate segment KSI by street name (city/txdot split) ----
name_ksi = defaultdict(int)
for f in seg:
    pr = f["properties"]
    if district and pr.get("district") != district:
        continue
    k = seg_ksi.get(pr["seg_id"], 0)
    if k and pr.get("name"):
        name_ksi[pr["name"]] += k
top5 = sorted(name_ksi.items(), key=lambda kv: -kv[1])[:5]

out = {
    "filter": {"mode": mode or "all", "district": district},
    "crashes": crashes, "fatal_crashes": killed, "ksi_crashes": ksi,
    "serious_kpi": serious, "yll": round(yll),
    "people_killed_nk": people_killed, "people_serious_na": people_serious,
    "econ_cost_B": round(econ / 1e9, 1), "comp_cost_B": round(comp / 1e9, 1),
    "gini": round(gini, 2) if gini is not None else None,
    "pct_half": round(100 * pct_half, 1) if pct_half else None,
    "hin6_ksi_pct": round(100 * hin6) if hin6 else None,
    "mode_split": {"ped_killed": pk, "bike_killed": bk, "ped_ksi": pksi, "bike_ksi": bksi},
    "income_ksi": {str(k): v for k, v in sorted(inc.items(), key=lambda kv: (kv[0] is None, kv[0]))},
    "ownership_ksi": own,
    "top5_streets": top5,
    "ksi_by_year": {str(y): by_year_f[y] + by_year_s[y] for y in sorted(by_year_f | by_year_s)},
}
print(json.dumps(out, indent=2))
print("PYTHON_KPIS=" + json.dumps(out, separators=(",", ":")))
