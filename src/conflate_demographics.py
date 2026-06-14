"""Conflate neighborhood demographics (ACS) onto District C segments.

Demographics are a CONFOUNDER in the project DAG and the basis of the equity
overlay. They come from the U.S. Census American Community Survey (ACS) 5-year
estimates at the **block group** level (polygons), so each segment inherits the
numbers of the block group its midpoint falls in. This is a neighborhood
attribute attached to a street, NOT a street-level measurement.

Sources:
  - Block-group geometry: Census TIGERweb (no key).
  - ACS attributes: Census Data API (FREE key required; get one at
    https://api.census.gov/data/key_signup.html). Provide it via env var
    CENSUS_API_KEY or a gitignored file data/external/.census_api_key.

Variables pulled (ACS 5-year):
  B01003_001E total population
  B19013_001E median household income
  B03002_001E/003E/004E/012E  total / white-NH / Black-NH / Hispanic
  B17001_001E/002E            poverty universe / below poverty
  B08201_001E/002E            households / households with no vehicle

Derived per block group: pct_white_nh, pct_black_nh, pct_hispanic,
median_hh_income, pct_poverty, pct_zero_car_hh, pop_density_sqmi.
"""

import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from arcgis_fetch import fetch_layer

import config as cfg
ROOT, PROCESSED, EXTERNAL, REPORTS = cfg.ROOT, cfg.PROCESSED, cfg.EXTERNAL, cfg.REPORTS

ACS_YEAR = 2023            # ACS 5-year (2019–2023); falls back to 2022
STATE, COUNTY = "48", "201"  # Texas, Harris County (Houston is ~99% Harris;
                             # expand to a county list if going beyond Harris)
BG_LAYER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2023/MapServer/10"
BBOX = cfg.bbox_4326()

# Note: at BLOCK GROUP level the poverty (B17001) and vehicle (B08201) detail
# tables return null, so we use the equivalents that ARE published at BG:
#   poverty  -> C17002 (income-to-poverty ratio): below = _002E + _003E
#   vehicles -> B25044 (tenure by vehicles available): no-veh = _003E + _010E
VARS = {
    "B01003_001E": "pop",
    "B19013_001E": "median_hh_income",
    "B03002_001E": "race_total",
    "B03002_003E": "white_nh",
    "B03002_004E": "black_nh",
    "B03002_012E": "hispanic",
    "C17002_001E": "pov_universe",
    "C17002_002E": "pov_lt050",
    "C17002_003E": "pov_050_099",
    "B25044_001E": "hh_total",
    "B25044_003E": "owner_no_veh",
    "B25044_010E": "renter_no_veh",
}
OWNED = ["bg_geoid", "pop", "median_hh_income", "pct_white_nh", "pct_black_nh",
         "pct_hispanic", "pct_poverty", "pct_zero_car_hh", "pop_density_sqmi"]


def get_key():
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        f = EXTERNAL / ".census_api_key"
        if f.exists():
            key = f.read_text().strip()
    if not key:
        raise SystemExit(
            "No Census API key. Get a free one at "
            "https://api.census.gov/data/key_signup.html and either set "
            "CENSUS_API_KEY or save it to data/external/.census_api_key"
        )
    return key


def fetch_acs(year, key):
    url = (
        f"https://api.census.gov/data/{year}/acs/acs5"
        f"?get={','.join(VARS)}&for=block%20group:*"
        f"&in=state:{STATE}%20county:{COUNTY}&key={key}"
    )
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df = df.rename(columns=VARS)
    for c in VARS.values():
        df[c] = pd.to_numeric(df[c], errors="coerce")
        # Census uses large negative sentinels (e.g. -666666666) for "not
        # available" — treat any negative count/income as missing.
        df.loc[df[c] < 0, c] = np.nan
    df["pov_below"] = df["pov_lt050"] + df["pov_050_099"]
    df["hh_no_vehicle"] = df["owner_no_veh"] + df["renter_no_veh"]
    df["bg_geoid"] = df["state"] + df["county"] + df["tract"] + df["block group"]
    return df


def main():
    key = get_key()
    seg = gpd.read_file(cfg.processed("segments_enriched.gpkg"),
                        layer="segments")
    seg = seg.drop(columns=[c for c in OWNED if c in seg.columns])

    # block-group geometry (cache)
    bg_cache = cfg.external("census_bg.gpkg")
    if bg_cache.exists():
        bg = gpd.read_file(bg_cache)
    else:
        bg = fetch_layer(BG_LAYER, out_fields="GEOID,AREALAND", bbox_4326=BBOX,
                         out_sr=2278)
        bg.to_file(bg_cache, driver="GPKG")
    bg = bg.rename(columns={"GEOID": "bg_geoid"}).to_crs(seg.crs)

    # ACS attributes
    try:
        acs = fetch_acs(ACS_YEAR, key)
        year = ACS_YEAR
    except Exception:
        acs = fetch_acs(2022, key)
        year = 2022
    print(f"ACS {year}: {len(acs):,} Harris County block groups")

    # derived metrics (guard divide-by-zero)
    def safe(n, d):
        return np.where(d > 0, 100 * n / d, np.nan)

    acs["pct_white_nh"] = safe(acs["white_nh"], acs["race_total"]).round(1)
    acs["pct_black_nh"] = safe(acs["black_nh"], acs["race_total"]).round(1)
    acs["pct_hispanic"] = safe(acs["hispanic"], acs["race_total"]).round(1)
    acs["pct_poverty"] = safe(acs["pov_below"], acs["pov_universe"]).round(1)
    acs["pct_zero_car_hh"] = safe(acs["hh_no_vehicle"], acs["hh_total"]).round(1)

    keep = ["bg_geoid", "pop", "median_hh_income", "pct_white_nh", "pct_black_nh",
            "pct_hispanic", "pct_poverty", "pct_zero_car_hh"]
    bg = bg.merge(acs[keep], on="bg_geoid", how="left")
    bg["pop_density_sqmi"] = np.where(
        bg["AREALAND"] > 0, bg["pop"] / (bg["AREALAND"] / 2_589_988.0), np.nan
    ).round(0)

    # assign each segment to the block group containing its midpoint
    mids = seg.copy()
    mids["geometry"] = seg.geometry.interpolate(0.5, normalized=True)
    cols = keep + ["pop_density_sqmi"]
    joined = gpd.sjoin(mids[["seg_id", "geometry"]], bg[cols + ["geometry"]],
                       how="left", predicate="within")
    joined = joined.drop_duplicates("seg_id")
    seg = seg.merge(joined[["seg_id"] + cols], on="seg_id", how="left")

    out = cfg.processed("segments_enriched.gpkg")
    seg.to_file(out, layer="segments", driver="GPKG")
    print(f"Saved {out}")

    # report
    def pct(m):
        return round(100 * m.mean(), 1)

    have = seg["pop"].notna()
    n_bg = seg["bg_geoid"].nunique() if "bg_geoid" in seg else joined["bg_geoid"].nunique() if "bg_geoid" in joined else "?"
    rep = f"""# Demographics (ACS) Conflation Report

Generated by `src/conflate_demographics.py`. Source: U.S. Census ACS {year}
5-year estimates at the **block group** level; each segment inherits the block
group containing its midpoint. Geometry from Census TIGERweb.

## Coverage

- Segments assigned a block group: **{pct(have)}%** ({int(have.sum()):,} of {len(seg):,}).
- District C spans roughly {seg['bg_geoid'].nunique() if 'bg_geoid' in seg.columns else '—'} block groups.

## District C demographic range (block-group values, population-weighted where shown)

| Metric | min | median | max |
|---|---|---|---|
| Median HH income ($) | {seg['median_hh_income'].min():,.0f} | {seg['median_hh_income'].median():,.0f} | {seg['median_hh_income'].max():,.0f} |
| % below poverty | {seg['pct_poverty'].min():.0f} | {seg['pct_poverty'].median():.0f} | {seg['pct_poverty'].max():.0f} |
| % Hispanic | {seg['pct_hispanic'].min():.0f} | {seg['pct_hispanic'].median():.0f} | {seg['pct_hispanic'].max():.0f} |
| % Black (NH) | {seg['pct_black_nh'].min():.0f} | {seg['pct_black_nh'].median():.0f} | {seg['pct_black_nh'].max():.0f} |
| % White (NH) | {seg['pct_white_nh'].min():.0f} | {seg['pct_white_nh'].median():.0f} | {seg['pct_white_nh'].max():.0f} |
| % zero-car households | {seg['pct_zero_car_hh'].min():.0f} | {seg['pct_zero_car_hh'].median():.0f} | {seg['pct_zero_car_hh'].max():.0f} |

## Notes

- **Ecological attribution:** these are neighborhood (block-group) values
  attached to every street in that neighborhood — a confounder/overlay, not a
  street-level measurement. Interpret accordingly.
- Block-group ACS estimates carry non-trivial margins of error (esp. median
  income); fine for a descriptive overlay and adjustment, not for fine
  street-by-street claims.
- `pct_zero_car_hh` is especially relevant: zero-car households walk/transit
  more, tying demographics to pedestrian exposure and the equity question.
"""
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "demographics_conflation_report.md").write_text(rep)
    print(rep)


if __name__ == "__main__":
    main()
