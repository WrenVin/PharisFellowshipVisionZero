"""Export headline Vision Zero stats to docs/vz_summary.json for the VZ dashboard.

Small JSON of district-wide numbers the per-segment GeoJSON can't carry: the
toll (killed / seriously injured), per-year KSI trend, mode breakdown, the
High Injury Network concentration, and the income equity split.
"""

import json
from datetime import date
from pathlib import Path

import geopandas as gpd

import config as cfg
ROOT, PROCESSED, DOCS = cfg.ROOT, cfg.PROCESSED, cfg.DOCS

cr = gpd.read_file(cfg.processed("crashes.gpkg"), layer="crashes")
seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"), layer="segments")

ksi = cr["severe"]
out = {
    "generated": date.today().isoformat(),
    "years": sorted(int(y) for y in cr["year"].dropna().unique()),
    "toll": {
        "killed": int(cr["fatal"].sum()),
        "serious": int(cr["serious"].sum()),
        "ksi": int(ksi.sum()),
        "crashes": int(len(cr)),
    },
    "mode": {
        "ped_killed": int((cr["involves_ped"] & cr["fatal"]).sum()),
        "bike_killed": int((cr["involves_bike"] & cr["fatal"]).sum()),
        "ped_ksi": int((cr["involves_ped"] & ksi).sum()),
        "bike_ksi": int((cr["involves_bike"] & ksi).sum()),
        "ped_crashes": int(cr["involves_ped"].sum()),
        "bike_crashes": int(cr["involves_bike"].sum()),
    },
    # KSI per year (district), for the trend chart
    "ksi_by_year": {int(y): int(n) for y, n in
                    cr[ksi].groupby("year").size().sort_index().items()},
}
out["mode"]["vuln_killed_share"] = round(
    100 * (out["mode"]["ped_killed"] + out["mode"]["bike_killed"]) / out["toll"]["killed"]
)

# High Injury Network concentration (assigned to city streets)
s = seg.sort_values("n_severe", ascending=False).copy()
s["mi"] = s["length_ft"] / 5280
tot_sev, tot_mi = s["n_severe"].sum(), s["mi"].sum()
s["cum_sev"] = s["n_severe"].cumsum() / tot_sev
s["cum_mi"] = s["mi"].cumsum() / tot_mi
row6 = s[s["cum_mi"] >= 0.06].iloc[0]
out["hin"] = {
    "pct_streets": 6,
    "pct_ksi": int(round(row6["cum_sev"] * 100)),
    "pct_zero_streets": int(round(100 * (seg["n_severe"] == 0).mean())),
    "ksi_on_streets": int(tot_sev),  # assigned (excludes freeway/feeder)
}

# Equity: KSI share by neighbourhood income (within-district lower vs upper half)
s2 = seg[seg["median_hh_income"].notna()].copy()
med = s2["median_hh_income"].median()
below = s2[s2["median_hh_income"] < med]
out["equity"] = {
    "median_income": int(med),
    "ksi_lower_income_pct": int(round(100 * below["n_severe"].sum() / s2["n_severe"].sum())),
}

DOCS.mkdir(exist_ok=True)
(DOCS / "vz_summary.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
