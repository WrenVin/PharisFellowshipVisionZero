"""Crash concentration vs. exposure: is the High-Injury concentration just traffic?

Reads the served segment file (docs/segments_vz.geojson) and measures how
concentrated severe-crash harm (KSI = killed or seriously injured) is across the
street network, using a Lorenz/concentration curve and a Gini coefficient, then
asks whether that concentration survives normalizing by exposure (vehicle-miles
traveled, VMT = ADT x length). Writes the numbers used in
reports/concentration_exposure_note.md.

Run: .venv/bin/python src/analyze_concentration.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEG = ROOT / "docs" / "segments_vz.geojson"


def gini(pairs):
    """Gini of `value` distributed across `weight`, for a list of (weight, value).
    Ranks by value/weight (density), descending; returns 2*area - 1."""
    rows = sorted(pairs, key=lambda t: (t[1] / t[0]) if t[0] > 0 else 0, reverse=True)
    tw = sum(w for w, v in rows)
    tv = sum(v for w, v in rows)
    if tw <= 0 or tv <= 0:
        return None
    cw = cv = area = px = py = 0.0
    for w, v in rows:
        cw += w / tw
        cv += v / tv
        area += (cw - px) * (cv + py) / 2
        px, py = cw, cv
    return 2 * area - 1


def main():
    feats = json.load(open(SEG))["features"]
    tot_ksi_all = 0
    rows = []  # (ksi, miles, adt) for segments that have traffic volume
    for f in feats:
        p = f["properties"]
        ksi = p.get("n_severe") or 0
        mi = (p.get("length_ft") or 0) / 5280.0
        adt = p.get("adt")
        tot_ksi_all += ksi
        if mi > 0 and adt not in (None, "") and float(adt) > 0:
            rows.append((ksi, mi, float(adt)))

    cov_ksi = sum(r[0] for r in rows)
    print(f"Total segments: {len(feats):,} | total KSI: {tot_ksi_all:,}")
    print(f"Segments with ADT (traffic volume): {len(rows):,} | "
          f"KSI on them: {cov_ksi:,.0f} ({100*cov_ksi/tot_ksi_all:.0f}% of all KSI)\n")

    V = [(ksi, mi, adt, adt * mi) for ksi, mi, adt in rows]  # vmt = adt * miles (daily)
    g_miles = gini([(mi, ksi) for ksi, mi, a, v in V])
    g_traffic = gini([(mi, v) for ksi, mi, a, v in V])
    g_vmt = gini([(v, ksi) for ksi, mi, a, v in V])
    print("On the ADT-covered arterials:")
    print(f"  Gini(KSI across street-miles) = {g_miles:.3f}   (the dashboard's count basis)")
    print(f"  Gini(VMT across street-miles) = {g_traffic:.3f}   (how concentrated traffic itself is)")
    print(f"  Gini(KSI across VMT)          = {g_vmt:.3f}   (concentration AFTER removing exposure)")

    # share of harm on the busiest half of VMT
    vs = sorted(V, key=lambda t: t[3], reverse=True)
    tv = sum(t[3] for t in V)
    tk = sum(t[0] for t in V)
    cumv = cumk = 0.0
    busy_half_ksi = None
    for ksi, mi, a, v in vs:
        cumv += v
        cumk += ksi
        if cumv / tv >= 0.5 and busy_half_ksi is None:
            busy_half_ksi = 100 * cumk / tk
            break
    print(f"\nThe busiest 50% of VMT carries {busy_half_ksi:.0f}% of the KSI "
          f"(proportional would be ~50%).")

    # rate-ranking instability: the 'most dangerous per VMT' list is dominated by noise
    rate = sorted(V, key=lambda t: (t[0] / t[3]) if t[3] > 0 else 0, reverse=True)
    print("\nTop segments by KSI-per-VMT (a naive rate ranking) -- note the tiny traffic:")
    for ksi, mi, a, v in rate[:6]:
        print(f"  KSI={ksi:.0f}  ADT={a:,.0f}  ({mi:.2f} mi)")

    # citywide count Gini (all segments, incl. quiet residential) for context
    g_all = gini([((p.get("length_ft") or 0) / 5280.0, p.get("n_severe") or 0)
                  for p in (f["properties"] for f in feats)
                  if (p.get("length_ft") or 0) > 0])
    print(f"\nFor context, citywide Gini(KSI across all street-miles) = {g_all:.3f} "
          f"(includes the many zero-crash residential streets).")


if __name__ == "__main__":
    main()
