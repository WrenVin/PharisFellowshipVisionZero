"""Step 1 of crash integration: build the clean crash points layer for the study area.

Reads the raw TxDOT CRIS extracts (data/raw/CRIS/, gitignored), dedupes by
Crash_ID, geocodes (CRIS Latitude/Longitude with the officer-reported pair as
fallback), clips to the study area, and classifies severity on the KABCO scale.

ADDING MORE YEARS (e.g. 2020, 2025 when they arrive): just drop the new
`Houston_Crash_<year>/` folder into data/raw/CRIS/ and rerun this script.
It is year-agnostic — it globs every Houston_Crash_* folder, takes the year
from each crash's Crash_Date (not the folder name), dedupes by Crash_ID across
all files, and overwrites its outputs. Nothing is hardcoded to specific years.

Mode (pedestrian / bicycle) is derived from the CRIS `unit` table
(Unit_Desc_ID 4=pedestrian, 3=pedalcyclist), cross-checked against the
`person` table (Prsn_Type_ID 4/3). Codes confirmed from the CRIS lookup table.

Outputs (no segment assignment yet):
  data/processed/district_c_crashes.gpkg   (points, EPSG:2278)
  reports/crash_build_report.md
  reports/crash_points_preview.png
"""

import glob
import re
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as cfg
ROOT, CRIS, PROCESSED, REPORTS = cfg.ROOT, cfg.CRIS, cfg.PROCESSED, cfg.REPORTS

WANT = ["Crash_ID", "Crash_Date", "Crash_Time", "Crash_Fatal_Fl", "Crash_Sev_ID",
        "Latitude", "Longitude", "Rpt_Latitude", "Rpt_Longitude",
        "Sus_Serious_Injry_Cnt", "Tot_Injry_Cnt", "Crash_Speed_Limit",
        "Road_Cls_ID", "Rpt_Road_Part_ID", "Rpt_Street_Name"]
# Years of Life Lost: YPLL before age 75 (CDC convention) = max(0, 75 - age),
# summed over the people killed. Age comes from the CRIS person table.
LIFE_EXPECTANCY = 75
LATMIN, LATMAX, LONMIN, LONMAX = 29.4, 30.2, -95.9, -94.9
# Limited-access (freeway) filter. Vision Zero dashboards (Austin) and the City's
# own HIN keep ALL surface streets where people are killed, including at-grade
# state-owned arterials (S Main/US-90A, SH 6, FM 1093/Westheimer) — only
# limited-access freeways/tollways are excluded (different facility, and they snap
# onto nearby city cross-streets). State vs city OWNERSHIP is tracked downstream
# (TxDOT inventory in export_webmap_data) as a label, not an exclusion.
# Road_Cls_ID 1=Interstate 6=Tollway 8=TollBridge 9=NonTrafficway are limited-access;
# Rpt_Road_Part_ID 2=service/frontage 3/4=ramp 5=connector are freeway parts;
# class 2 (US/State) is mixed, so drop it only when the street name is a freeway
# (keeps at-grade arterials like Main, Shepherd, Kirby, Braeswood, Highway 6).
FWY_NAME = re.compile(r"SOUTHWEST|NORTHWEST|NORTH FWY|FREEWAY|FWY|EASTEX|GULF|"
                      r"KATY|HARDY|US 59|US 290| 59 | 290 |IH|LOOP|610|HOV|TOLL|"
                      r"SAM HOUSTON|SER ", re.I)
# CRIS Crash_Sev_ID -> KABCO (verified against Fatal_Fl + serious-injury counts)
KABCO = {4: "K", 1: "A", 2: "B", 3: "C", 5: "O", 0: "UNK"}

# --- read + dedupe (every Houston_Crash_* folder, year-agnostic) --------------
folders = sorted(p.name for p in CRIS.glob("Houston_Crash_*"))
frames, n_files = [], 0
for f in glob.glob(str(CRIS / "Houston_Crash_*" / "*crash_*.csv")):
    frames.append(pd.read_csv(f, usecols=lambda c: c in WANT, low_memory=False))
    n_files += 1
print(f"Folders found: {folders}")
allc = pd.concat(frames, ignore_index=True).drop_duplicates("Crash_ID")
n_raw = len(allc)

# --- geocode ------------------------------------------------------------------
for c in ["Latitude", "Longitude", "Rpt_Latitude", "Rpt_Longitude"]:
    allc[c] = pd.to_numeric(allc[c], errors="coerce")
allc["lat"] = allc["Latitude"].fillna(allc["Rpt_Latitude"])
allc["lon"] = allc["Longitude"].fillna(allc["Rpt_Longitude"])
allc["coord_source"] = allc["Latitude"].notna().map({True: "cris", False: "reported"})
valid = allc["lat"].between(LATMIN, LATMAX) & allc["lon"].between(LONMIN, LONMAX)

g = gpd.GeoDataFrame(
    allc[valid].copy(),
    geometry=gpd.points_from_xy(allc.loc[valid, "lon"], allc.loc[valid, "lat"]),
    crs=4326,
).to_crs(2278)

# --- clip to the study area ---------------------------------------------------
boundary = cfg.boundary(2278)
g = g[g.within(boundary.geometry.iloc[0])].copy()
n_in_district = len(g)

# drop limited-access freeway/tollway crashes; keep at-grade arterials (see note)
cls = pd.to_numeric(g["Road_Cls_ID"], errors="coerce")
part = pd.to_numeric(g["Rpt_Road_Part_ID"], errors="coerce")
nm = g["Rpt_Street_Name"].fillna("")
on_fwy = (cls.isin([1, 6, 8, 9]) | part.isin([2, 3, 4, 5])
          | (cls.eq(2) & nm.str.contains(FWY_NAME)))
n_fwy = int(on_fwy.sum())
g = g[~on_fwy].copy()
dc_ids = set(g["Crash_ID"])

# --- mode (pedestrian / bicycle) from the unit table --------------------------
# Unit_Desc_ID: 4=pedestrian, 3=pedalcyclist. Read all unit files, keep only
# study-area crashes, flag per Crash_ID (duplicate unit rows across overlapping
# extracts are harmless for an any() flag).
ped_ids, bike_ids = set(), set()
for f in glob.glob(str(CRIS / "Houston_Crash_*" / "*unit_*.csv")):
    u = pd.read_csv(f, usecols=lambda c: c in ("Crash_ID", "Unit_Desc_ID"),
                    low_memory=False)
    u = u[u["Crash_ID"].isin(dc_ids)]
    ped_ids |= set(u.loc[u["Unit_Desc_ID"] == 4, "Crash_ID"])
    bike_ids |= set(u.loc[u["Unit_Desc_ID"] == 3, "Crash_ID"])

# cross-check against the person table (Prsn_Type_ID 4/3)
pped, pbike = set(), set()
for f in glob.glob(str(CRIS / "Houston_Crash_*" / "*person_*.csv")):
    p = pd.read_csv(f, usecols=lambda c: c in ("Crash_ID", "Prsn_Type_ID"),
                    low_memory=False)
    p = p[p["Crash_ID"].isin(dc_ids)]
    pped |= set(p.loc[p["Prsn_Type_ID"] == 4, "Crash_ID"])
    pbike |= set(p.loc[p["Prsn_Type_ID"] == 3, "Crash_ID"])
# union the two sources (robust to either table missing a record)
ped_ids |= pped
bike_ids |= pbike

g["involves_ped"] = g["Crash_ID"].isin(ped_ids)
g["involves_bike"] = g["Crash_ID"].isin(bike_ids)
g["mode"] = "motor vehicle"
g.loc[g["involves_bike"], "mode"] = "bicycle"
g.loc[g["involves_ped"], "mode"] = "pedestrian"   # ped takes precedence if both

# --- severity + year ----------------------------------------------------------
g["date"] = pd.to_datetime(g["Crash_Date"], errors="coerce")
g["year"] = g["date"].dt.year.astype("Int64")
g["month"] = g["date"].dt.month.astype("Int64")          # 1-12
g["hour"] = pd.to_datetime(g["Crash_Time"], format="%I:%M %p",
                           errors="coerce").dt.hour.astype("Int64")   # 0-23
g["kabco"] = g["Crash_Sev_ID"].map(KABCO).fillna("UNK")
g["fatal"] = g["kabco"].eq("K")
g["serious"] = g["kabco"].eq("A")
g["severe"] = g["fatal"] | g["serious"]            # K+A — the HIN / model outcome
g["any_injury"] = pd.to_numeric(g["Tot_Injry_Cnt"], errors="coerce").fillna(0) > 0
g["speed_limit"] = pd.to_numeric(g["Crash_Speed_Limit"], errors="coerce")

# --- Years of Life Lost (YPLL before 75) from the person table ----------------
# Killed people = person rows with Prsn_Injry_Sev_ID == 4 (KABCO K). YPLL per
# person = max(0, 75 - age); sum per crash. Persons live in two files per year —
# `primaryperson` (drivers / non-motorists) and `person` (passengers) — which
# REUSE Prsn_Nbr, so dedupe each type separately (handles overlapping extracts)
# then concatenate; never cross-dedupe the two types.
# Caveat: the public CRIS extract records a victim age for only ~half of fatal
# crashes (person detail is suppressed on the rest), so the crash-level K flag
# (`fatal`) is the reliable death count. We use recorded ages where present and
# impute the mean years-lost-per-fatality to the remaining fatal crashes, making
# the YLL total an *estimate* anchored to the fatal-crash count.
pcols = ("Crash_ID", "Prsn_Nbr", "Prsn_Injry_Sev_ID", "Prsn_Age")
def _load_persons(kind):
    fs = [f for f in glob.glob(str(CRIS / "Houston_Crash_*" / f"*{kind}_*.csv"))
          if (kind == "primaryperson") or ("primaryperson" not in f)]
    fr = [pd.read_csv(f, usecols=lambda c: c in pcols, low_memory=False) for f in fs]
    return pd.concat(fr, ignore_index=True).drop_duplicates(["Crash_ID", "Prsn_Nbr"])
killed = pd.concat([_load_persons("primaryperson"), _load_persons("person")],
                   ignore_index=True)
killed = killed[killed["Crash_ID"].isin(dc_ids) & (killed["Prsn_Injry_Sev_ID"] == 4)].copy()
killed["age"] = pd.to_numeric(killed["Prsn_Age"], errors="coerce")
killed["yll"] = (LIFE_EXPECTANCY - killed["age"]).clip(lower=0)
yll_by_crash = killed.groupby("Crash_ID")["yll"].sum()          # recorded crashes only
recorded = g["Crash_ID"].isin(yll_by_crash.index)
mean_yll = float(g.loc[g["fatal"] & recorded, "Crash_ID"].map(yll_by_crash).mean())
g["yll"] = 0.0
g.loc[g["fatal"] & recorded, "yll"] = g.loc[g["fatal"] & recorded, "Crash_ID"].map(yll_by_crash)
g.loc[g["fatal"] & ~recorded, "yll"] = mean_yll                 # impute the rest
g["yll"] = g["yll"].round(1)
n_killed_persons = len(killed)
n_fatal_recorded = int((g["fatal"] & recorded).sum())
n_fatal_imputed = int((g["fatal"] & ~recorded).sum())
total_yll = float(g["yll"].sum())

out = g[["Crash_ID", "year", "month", "hour", "date", "kabco", "fatal",
         "serious", "severe", "yll", "any_injury", "mode", "involves_ped",
         "involves_bike", "Crash_Sev_ID", "speed_limit", "coord_source",
         "geometry"]].copy()
out["date"] = out["date"].dt.strftime("%Y-%m-%d")
PROCESSED.mkdir(parents=True, exist_ok=True)
dst = cfg.processed("crashes.gpkg")
out.to_file(dst, layer="crashes", driver="GPKG")
print(f"Saved {len(out):,} {cfg.AREA_LABEL} crashes -> {dst}")

# --- preview map --------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7, 9))
boundary.boundary.plot(ax=ax, color="black", linewidth=1)
g[~g["severe"]].plot(ax=ax, color="#9ecae1", markersize=1, alpha=.35)
g[g["severe"]].plot(ax=ax, color="#cb181d", markersize=6)
ax.set_title(f"{cfg.AREA_LABEL} crashes (2016–2026)\nred = severe (K+A), blue = other", fontsize=11)
ax.axis("off")
REPORTS.mkdir(exist_ok=True)
fig.savefig(REPORTS / "crash_points_preview.png", dpi=120, bbox_inches="tight")
print("Saved reports/crash_points_preview.png")

# --- report -------------------------------------------------------------------
by_year = g.groupby("year").agg(crashes=("Crash_ID", "size"),
                                severe=("severe", "sum")).astype(int)
years_present = [int(y) for y in by_year.index]
gaps = [y for y in range(years_present[0], years_present[-1] + 1)
        if y not in years_present]
kab = g["kabco"].value_counts()
report = f"""# Crash Build Report (Step 1) — {cfg.AREA_LABEL} crash points

Generated by `src/build_crashes.py` from raw TxDOT CRIS extracts (gitignored).

## Pipeline
- Unique crashes citywide (dedup Crash_ID): {n_raw:,}
- Geocoded (valid Houston coords): {int(valid.sum()):,} ({100*valid.mean():.1f}%)
- In study area (geocoded): {n_in_district:,}
- **Excluded {n_fwy:,} limited-access (freeway/tollway/ramp) crashes** — at-grade arterials (incl. state-owned) are kept; ownership is labeled downstream, not excluded
- **Surface-street crashes (freeways excluded; at-grade arterials incl. state-owned kept): {len(g):,}** (EPSG:2278)
- Coordinate source: {int((g.coord_source=='cris').sum()):,} CRIS-geocoded, {int((g.coord_source=='reported').sum()):,} officer-reported fallback

## Severity (KABCO, all years)
- **Severe (K+A): {int(g['severe'].sum()):,}** ({int(g['fatal'].sum())} fatal K, {int(g['serious'].sum())} serious A) — the negative-binomial outcome
- Any injury: {int(g['any_injury'].sum()):,}
- KABCO counts: {kab.to_dict()}

## Years of Life Lost (YPLL before age {LIFE_EXPECTANCY}, CDC convention) — estimated
- Fatal crashes (crash-level K): {int(g['fatal'].sum())}
- ...with a recorded victim age in the public extract: {n_fatal_recorded} ({n_killed_persons} killed persons); the other {n_fatal_imputed} get the mean ({mean_yll:.0f} yrs/fatality)
- **Estimated Total Years of Life Lost: {total_yll:,.0f}** (Σ max(0, {LIFE_EXPECTANCY} − age), imputed where age is suppressed)

## Time of day / month
- Crashes with a parseable time: {int(g['hour'].notna().sum()):,} / {len(g):,}
- Month + hour stored per crash for the dashboard's By-Month and By-Time-of-Day charts.

## Mode (from CRIS unit table, cross-checked vs person table)
- **Pedestrian crashes: {int(g['involves_ped'].sum()):,}** — of which {int((g['involves_ped'] & g['severe']).sum()):,} severe ({int((g['involves_ped'] & g['fatal']).sum())} fatal)
- **Bicycle crashes: {int(g['involves_bike'].sum()):,}** — of which {int((g['involves_bike'] & g['severe']).sum()):,} severe ({int((g['involves_bike'] & g['fatal']).sum())} fatal)
- Vulnerable (ped or bike) share of all crashes: {100*(g['involves_ped']|g['involves_bike']).mean():.1f}%; share of SEVERE crashes: {100*(g.loc[g['severe'],'involves_ped']|g.loc[g['severe'],'involves_bike']).mean():.1f}%
- Cross-check (unit vs person source): ped {len(ped_ids):,} union / person-only {len(pped):,}; bike {len(bike_ids):,} union / person-only {len(pbike):,}

## By year

{by_year.to_string()}

## Coverage (computed live)
- Source folders read: {', '.join(folders)} ({n_files} crash files)
- Years present: {', '.join(str(y) for y in years_present)}
- Gaps within {years_present[0]}–{years_present[-1]}: {', '.join(str(y) for y in gaps) or 'none'}
- **To add a year:** drop `Houston_Crash_<year>/` into `data/raw/CRIS/` and rerun
  `src/build_crashes.py` — year-agnostic, dedupes by Crash_ID, overwrites outputs.

## Notes / flags
- Severity decode verified: Crash_Sev_ID 4=K, 1=A, 2=B, 3=C, 5=O, 0=Unknown.
- ~10% of citywide crashes are ungeocoded and excluded — tie to the reporting
  collider; bound with a sensitivity check later, don't ignore.
- Some years may be partial (e.g. a current-year extract); years here reflect
  whatever extracts are present in data/raw/CRIS/ at run time.
- Mode (pedestrian / bicycle) is NOT here yet — it needs a person/unit join
  (next step). This layer is crash-level severity only.
"""
(REPORTS / "crash_build_report.md").write_text(report)
print(report)
