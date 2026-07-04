#!/usr/bin/env python3
"""Export aggregated CSVs for Flourish visualizations (flourish.studio).

Flourish wants small, aggregated tables — not the ~421k raw crash points. This
reads the published docs/crash_points.json + docs/vz_summary.json (so every
number matches the live dashboard exactly) and writes feeder CSVs to flourish/.

Exports (one per Flourish slide in the Vision Zero "Story"):
  mode_severity_sankey.csv  — mode -> severity flows (Sankey)
  toll.csv                  — the toll: people killed vs seriously injured (bar)
  ksi_by_year.csv           — KSI per year + a "zero by 2030" goal line (line)
  concentration.csv         — High Injury Network: 6% of streets, 71% of KSI (stacked bar)
  income_equity.csv         — KSI by neighborhood income band (bar)
  mode_harm.csv             — each mode's share of crashes vs share of deaths (paired bar)
  cost.csv                  — FHWA crash cost by injury severity (bar / treemap)

Every crash is counted once, by its travel mode and its MOST SEVERE outcome
(KABCO max), so totals reconcile with the dashboard (Killed 1,687; KSI 9,923).
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTS = ROOT / "docs" / "crash_points.json"
VZ = ROOT / "docs" / "vz_summary.json"
OUT = ROOT / "flourish"
OUT.mkdir(exist_ok=True)

# crash_points.json row layout (21 fields):
# 0 lat 1 lon 2 sev(KSI flag) 3 fatal 4 ped 5 bike 6 year 7 date 8 hour
# 9 yll 10 district 11 inc_tier 12 on_hin 13 on_txdot 14 seg_id 15 sn
# 16 n_k 17 n_a 18 n_b 19 n_c 20 n_noinj

MODE_ORDER = ["In a vehicle", "Walking", "Biking"]
SEV_ORDER = ["Killed", "Seriously injured", "Minor injury", "Possible injury", "No injury"]
INC_LAB = ["Under $50k", "$50–100k", "$100–150k", "$150k+"]  # indexed by inc_tier; None = Unknown

# FHWA-SA-25-021 per-PERSON KABCO costs, 2024 dollars: [economic, comprehensive].
PERSON_COST = {"Killed": (1606644, 11258495), "Seriously injured": (172179, 1089524),
               "Minor injury": (44490, 224597), "Possible injury": (25933, 111281),
               "No injury": (6269, 10196)}
GOAL_YEAR = 2030  # Vision Zero: zero traffic deaths by 2030 (Houston adopted 2019)


def mode_of(r):
    if r[4]:
        return "Walking"
    if r[5]:
        return "Biking"
    return "In a vehicle"


def severity_of(r):
    if r[3]:
        return "Killed"
    if r[2]:
        return "Seriously injured"
    if r[18]:
        return "Minor injury"
    if r[19]:
        return "Possible injury"
    return "No injury"


def write(name, header, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote flourish/{name}")


def main():
    pts = json.load(open(PTS))
    vz = json.load(open(VZ))

    # one pass: classify every crash by (mode, severity)
    cell = {(m, s): 0 for m in MODE_ORDER for s in SEV_ORDER}
    by_year_ksi, persons = {}, {s: 0 for s in SEV_ORDER}
    inc_ksi = {lab: 0 for lab in INC_LAB + ["Unknown"]}
    for r in pts:
        m, s = mode_of(r), severity_of(r)
        cell[(m, s)] += 1
        if r[2]:  # KSI crash
            by_year_ksi[r[6]] = by_year_ksi.get(r[6], 0) + 1
            inc_ksi[INC_LAB[r[11]] if r[11] is not None else "Unknown"] += 1
        for s2, idx in zip(SEV_ORDER, (16, 17, 18, 19, 20)):
            persons[s2] += r[idx]

    mode_tot = {m: sum(cell[(m, s)] for s in SEV_ORDER) for m in MODE_ORDER}
    killed = {m: cell[(m, "Killed")] for m in MODE_ORDER}
    crashes, deaths = sum(mode_tot.values()), sum(killed.values())
    ksi = sum(v for v in by_year_ksi.values())

    # 1. mode -> severity Sankey
    write("mode_severity_sankey.csv", ["source", "target", "value"],
          [[m, s, cell[(m, s)]] for m in MODE_ORDER for s in SEV_ORDER])

    # 2. the toll (bar)
    write("toll.csv", ["category", "value"],
          [["People killed", deaths],
           ["Seriously injured", sum(cell[(m, "Seriously injured")] for m in MODE_ORDER)]])

    # 3. KSI by year + a glide path to zero by 2030 (line). Full years only;
    #    2026 is partial, so it's left out of the actual line.
    full = sorted(y for y in by_year_ksi if y <= 2025)
    base_y, base_v = 2019, by_year_ksi[2019]
    rows = []
    for y in range(full[0], GOAL_YEAR + 1):
        actual = by_year_ksi[y] if y in full else ""
        goal = round(base_v * (GOAL_YEAR - y) / (GOAL_YEAR - base_y)) if y >= base_y else ""
        rows.append([y, actual, goal])
    write("ksi_by_year.csv", ["year", "KSI", "Goal (zero by 2030)"], rows)

    # 4. concentration — HIN share of streets vs share of KSI (100% stacked bar)
    hin_streets, hin_ksi = vz["hin"]["pct_streets"], vz["hin"]["pct_ksi"]
    write("concentration.csv",
          ["", f"High Injury Network (top {hin_streets}% of streets)", "Rest of the city"],
          [["Share of street-miles", hin_streets, 100 - hin_streets],
           ["Share of KSI", hin_ksi, 100 - hin_ksi]])

    # 5. KSI by neighborhood income band (bar)
    write("income_equity.csv", ["Income band", "KSI"],
          [[lab, inc_ksi[lab]] for lab in INC_LAB] + [["Unknown", inc_ksi["Unknown"]]])

    # 6. mode: share of all crashes vs share of deaths (paired bar)
    write("mode_harm.csv", ["Mode", "Share of all crashes", "Share of deaths"],
          [[m, round(100 * mode_tot[m] / crashes, 1), round(100 * killed[m] / deaths, 1)]
           for m in MODE_ORDER])

    # 7. FHWA crash cost by injury severity (bar / treemap)
    write("cost.csv", ["Severity", "Economic cost", "Comprehensive cost"],
          [[s, persons[s] * PERSON_COST[s][0], persons[s] * PERSON_COST[s][1]] for s in SEV_ORDER])

    # --- verification ---
    econ = sum(persons[s] * PERSON_COST[s][0] for s in SEV_ORDER)
    comp = sum(persons[s] * PERSON_COST[s][1] for s in SEV_ORDER)
    print(f"\nreconciliation: crashes {crashes:,} | killed (crashes) {deaths:,} | KSI {ksi:,}")
    print(f"  under-$100k KSI: {inc_ksi['Under $50k'] + inc_ksi['$50–100k']:,} "
          f"({100*(inc_ksi['Under $50k']+inc_ksi['$50–100k'])/(ksi-inc_ksi['Unknown']):.0f}% of known-income KSI)")
    print(f"  walk+bike share of deaths: {100*(killed['Walking']+killed['Biking'])/deaths:.0f}%")
    print(f"  cost: economic ${econ/1e9:.1f}B | comprehensive ${comp/1e9:.1f}B")


if __name__ == "__main__":
    main()
