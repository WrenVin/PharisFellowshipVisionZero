"""Cut Houston's crashes out of statewide TxDOT CRIS public extracts.

CRIS can be pulled for all of Texas as dated chunk zips (CRIS/<year>/*Texas.zip,
each holding crash, unit, person, primaryperson, ... CSVs). This script keeps
only Houston crashes, using the same filter as the City = Houston extracts the
pipeline was built on (City_ID == 208, Houston's full-purpose city code), and
writes them in the layout build_crashes.py already reads:

    <out>/Houston_Crash_<year>/statewide_crash_<year>.csv
                               statewide_unit_<year>.csv
                               statewide_person_<year>.csv
                               statewide_primaryperson_<year>.csv

All values are copied as text, unchanged. Writes to a staging folder by default
so the current extracts in data/raw/CRIS/ are never overwritten in place.

    .venv/bin/python src/extract_cris_houston.py ~/Desktop/FarmandCity/CRIS
    .venv/bin/python src/extract_cris_houston.py <statewide CRIS dir> --years 2025 2026
"""

import argparse
import re
import zipfile
from pathlib import Path

import pandas as pd

import config as cfg

HOUSTON_CITY_ID = "208"
TABLES = ("unit", "person", "primaryperson")   # child tables, joined on Crash_ID


def table_members(zf, kind):
    """Zip members for one table, keyed by CRIS schema version (the year after
    extract_public_). A chunk spanning TxDOT's 2023 format change holds the table
    in both the 2018 and 2023 layouts; both are kept, as in the City = Houston
    extracts. person and primaryperson stay distinct."""
    pat = re.compile(rf"extract_public_(\d{{4}})_\d+_{kind}_\d{{8}}-\d{{8}}.*\.csv$", re.I)
    out = {}
    for n in zf.namelist():
        m = pat.search(n)
        if m:
            out[m.group(1)] = n
    if not out:
        raise RuntimeError(f"{zf.filename}: no {kind} table")
    return out


def read(zf, member):
    with zf.open(member) as fh:
        return pd.read_csv(fh, dtype=str, keep_default_na=False, low_memory=False)


def extract_year(year_dir, out_root):
    year = year_dir.name
    zips = sorted(year_dir.glob("*.zip"))
    if not zips:
        print(f"{year}: no zips, skipped")
        return
    parts = {}   # (schema, table) -> list of frames
    for zp in zips:
        with zipfile.ZipFile(zp) as zf:
            n_zip = 0
            for schema, member in table_members(zf, "crash").items():
                crash = read(zf, member)
                crash = crash[crash["City_ID"] == HOUSTON_CITY_ID]
                ids = set(crash["Crash_ID"])
                n_zip += len(ids)
                parts.setdefault((schema, "crash"), []).append(crash)
                for kind in TABLES:
                    t = read(zf, table_members(zf, kind)[schema])
                    parts.setdefault((schema, kind), []).append(t[t["Crash_ID"].isin(ids)])
        print(f"  {zp.name}: {n_zip:,} Houston crash rows")
    dest = out_root / f"Houston_Crash_{year}"
    dest.mkdir(parents=True, exist_ok=True)
    schemas = sorted({sc for sc, _ in parts})
    for (schema, kind), frames in parts.items():
        df = pd.concat(frames, ignore_index=True)
        if kind == "crash":
            df = df.drop_duplicates("Crash_ID")
        tag = f"v{schema}_" if len(schemas) > 1 else ""
        df.to_csv(dest / f"statewide_{tag}{kind}_{year}.csv", index=False)
    n = len(set().union(*(set(f["Crash_ID"]) for (sc, k), fr in parts.items() if k == "crash" for f in fr)))
    print(f"{year}: {n:,} Houston crashes ({', '.join(schemas)} layout) -> {dest}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("statewide_dir", type=Path, help="folder holding <year>/ subfolders of chunk zips")
    ap.add_argument("--out", type=Path, default=cfg.RAW / "CRIS_staging")
    ap.add_argument("--years", nargs="*", help="only these years (default: all)")
    a = ap.parse_args()
    years = sorted(p for p in a.statewide_dir.expanduser().iterdir()
                   if p.is_dir() and p.name.isdigit() and (not a.years or p.name in a.years))
    for y in years:
        extract_year(y, a.out)


if __name__ == "__main__":
    main()
