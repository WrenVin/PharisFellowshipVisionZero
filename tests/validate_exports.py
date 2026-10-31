#!/usr/bin/env python3
"""Validate the published dashboard data files before they reach the live site.

The dashboard at docs/vision-zero.html is driven entirely by a handful of static
JSON / GeoJSON files in docs/. Because the site auto-deploys from docs/ on every
push (GitHub Pages), a malformed, empty, or internally-inconsistent export would
go live with no human in the loop. This script is the safety net: it asserts a
"data contract" on those files and exits non-zero if anything looks broken, so the
GitHub Action (.github/workflows/validate.yml) turns red instead of publishing bad
numbers.

Standard library only (no pandas/geopandas) so it runs in seconds with no install.
Run locally after an export, or let CI run it on every push / PR:

    python tests/validate_exports.py
"""

import json
import re
import sys
from pathlib import Path

# Defaults to the repo's docs/, but accepts an alternate directory as argv[1]
# (used by the negative tests and handy for validating a build dir).
DOCS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs"

# Generous Houston-area bounding box (city proper is ~29.5-30.1, -95.8 to -95.0).
LAT_MIN, LAT_MAX = 29.3, 30.4
LON_MIN, LON_MAX = -96.2, -94.6

# crash_points.json row layout (24 fields). Index -> meaning, for reference:
# 0 lat, 1 lon, 2 sev(KSI flag), 3 fatal, 4 ped, 5 bike, 6 year, 7 date, 8 hour,
# 9 yll, 10 district, 11 inc_tier, 12 on_hin, 13 on_txdot, 14 seg_id, 15 sn,
# 16 n_k, 17 n_a, 18 n_b, 19 n_c, 20 n_noinj, 21 light (0-5), 22 factor bits (0-31),
# 23 people killed/seriously injured (comma-joined codes 0-191, or null), 24 road type
# (0 street, 3 frontage road; freeway file: 1 freeway, 2 toll road)
CRASH_ROW_LEN = 25
PEOPLE_RE = re.compile(r"^\d{1,3}(,\d{1,3})*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Properties the dashboard logic depends on for every segment feature.
REQUIRED_SEG_PROPS = [
    "seg_id", "length_ft", "district", "on_txdot", "on_hin",
    "n_crash", "n_severe", "n_fatal", "road_class",
]

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load(name):
    """Load a docs/ JSON file, recording an error (and returning None) on failure."""
    path = DOCS / name
    if not path.exists():
        err(f"{name}: file is missing from docs/")
        return None
    if path.stat().st_size == 0:
        err(f"{name}: file is empty (0 bytes)")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        err(f"{name}: not valid JSON ({e})")
        return None


def within(value, lo, hi):
    return value is not None and lo <= value <= hi


# ---------------------------------------------------------------------------
# 1. crash_points.json
# ---------------------------------------------------------------------------
def check_crashes(pts):
    if not isinstance(pts, list):
        err("crash_points.json: expected a top-level JSON array")
        return None
    n = len(pts)
    if not 300_000 <= n <= 550_000:
        err(f"crash_points.json: {n:,} rows is outside the expected 300k-550k "
            "(pipeline may have produced a truncated or bloated file)")
    elif n == 0:
        err("crash_points.json: zero crashes")

    bad_len = ksi = fatal = 0
    null_latlon = oob_latlon = bad_year = bad_date = bad_flag = 0
    seg_ids = set()
    years = []
    for r in pts:
        if not isinstance(r, list) or len(r) != CRASH_ROW_LEN:
            bad_len += 1
            continue
        lat, lon, sev, fat = r[0], r[1], r[2], r[3]
        if lat is None or lon is None:
            null_latlon += 1
        elif not (within(lat, LAT_MIN, LAT_MAX) and within(lon, LON_MIN, LON_MAX)):
            oob_latlon += 1
        if r[6] is None or not within(r[6], 2000, 2100):
            bad_year += 1
        else:
            years.append(r[6])
        if r[7] and not DATE_RE.match(str(r[7])):
            bad_date += 1
        if sev not in (0, 1) or fat not in (0, 1):
            bad_flag += 1
        if r[21] not in (0, 1, 2, 3, 4, 5) or not (isinstance(r[22], int) and 0 <= r[22] < 32):
            bad_flag += 1
        if r[24] not in (0, 3):
            bad_flag += 1
        if r[23] is not None and (not PEOPLE_RE.match(r[23]) or any(int(x) > 191 for x in r[23].split(","))):
            bad_flag += 1
        if sev == 1:
            ksi += 1
        if fat == 1:
            fatal += 1
        if r[14]:
            seg_ids.add(r[14])

    if bad_len:
        err(f"crash_points.json: {bad_len:,} rows are not {CRASH_ROW_LEN}-field arrays")
    if null_latlon:
        err(f"crash_points.json: {null_latlon:,} rows have null lat/lon")
    if oob_latlon:
        err(f"crash_points.json: {oob_latlon:,} rows fall outside the Houston bbox")
    if bad_year:
        err(f"crash_points.json: {bad_year:,} rows have a missing/implausible year")
    if bad_flag:
        err(f"crash_points.json: {bad_flag:,} rows have a bad sev/fatal flag, light code, factor bits or people codes")
    if bad_date:
        warn(f"crash_points.json: {bad_date:,} rows have a malformed date string")

    if years:
        print(f"  crash_points: {n:,} rows | years {min(years)}-{max(years)} | "
              f"{ksi:,} KSI crashes | {fatal:,} fatal crashes")
    return {"n": n, "ksi": ksi, "fatal": fatal, "seg_ids": seg_ids}


# ---------------------------------------------------------------------------
# 2. segments_vz.geojson
# ---------------------------------------------------------------------------
def check_segments(seg):
    if not isinstance(seg, dict) or seg.get("type") != "FeatureCollection":
        err("segments_vz.geojson: expected a GeoJSON FeatureCollection")
        return None
    feats = seg.get("features") or []
    n = len(feats)
    if not 55_000 <= n <= 85_000:
        err(f"segments_vz.geojson: {n:,} features is outside the expected 55k-85k")

    ids = set()
    missing_props = bad_geom = bad_len = dup = 0
    for f in feats:
        props = f.get("properties") or {}
        if any(k not in props for k in REQUIRED_SEG_PROPS):
            missing_props += 1
        sid = props.get("seg_id")
        if sid in ids:
            dup += 1
        elif sid:
            ids.add(sid)
        geom = f.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            bad_geom += 1
        lf = props.get("length_ft")
        if lf is None or lf <= 0:
            bad_len += 1

    if missing_props:
        err(f"segments_vz.geojson: {missing_props:,} features missing a required property "
            f"({', '.join(REQUIRED_SEG_PROPS)})")
    if dup:
        err(f"segments_vz.geojson: {dup:,} duplicate seg_id values")
    if bad_geom:
        err(f"segments_vz.geojson: {bad_geom:,} features have non-line geometry")
    if bad_len:
        err(f"segments_vz.geojson: {bad_len:,} features have null/zero length_ft")

    print(f"  segments_vz: {n:,} features | {len(ids):,} unique seg_id")
    return {"n": n, "ids": ids}


# ---------------------------------------------------------------------------
# 3. vz_summary.json  (internal consistency + cross-file reconciliation)
# ---------------------------------------------------------------------------
def check_summary(vz, crashes):
    for key in ("generated", "years", "toll", "mode", "ksi_by_year", "hin", "equity"):
        if key not in vz:
            err(f"vz_summary.json: missing top-level key '{key}'")

    years = vz.get("years") or []
    if not years:
        err("vz_summary.json: 'years' is empty")
    elif years != sorted(years):
        err("vz_summary.json: 'years' is not in ascending order")

    toll = vz.get("toll") or {}
    for k in ("killed", "serious", "ksi", "crashes"):
        v = toll.get(k)
        if not isinstance(v, int) or v <= 0:
            err(f"vz_summary.json: toll.{k} is missing or not a positive integer")

    # Internal: KSI must equal killed + serious.
    if all(k in toll for k in ("killed", "serious", "ksi")):
        if toll["killed"] + toll["serious"] != toll["ksi"]:
            err(f"vz_summary.json: toll.ksi ({toll['ksi']}) != killed+serious "
                f"({toll['killed']}+{toll['serious']})")

    # Internal: ksi_by_year must sum to toll.ksi.
    kby = vz.get("ksi_by_year") or {}
    if kby and "ksi" in toll:
        s = sum(kby.values())
        if s != toll["ksi"]:
            err(f"vz_summary.json: ksi_by_year sums to {s} != toll.ksi ({toll['ksi']})")

    # Cross-file: the per-crash file should reconcile with the headline numbers.
    if crashes:
        reconcile("crash count", crashes["n"], toll.get("crashes"), tol=0.01)
        reconcile("KSI count", crashes["ksi"], toll.get("ksi"), tol=0.02)
        reconcile("fatal count", crashes["fatal"], toll.get("killed"), tol=0.02)

    print(f"  vz_summary: years {years[0]}-{years[-1]} | toll {toll}")


def reconcile(label, from_crashes, from_summary, tol):
    """Flag if crash_points-derived total drifts from vz_summary by more than tol."""
    if from_summary is None or not from_summary:
        return
    diff = abs(from_crashes - from_summary) / from_summary
    if diff > tol:
        err(f"reconciliation: {label} differs by {diff:.1%} "
            f"(crash_points={from_crashes:,} vs vz_summary={from_summary:,}, tol={tol:.0%})")


# ---------------------------------------------------------------------------
# 4. Cross-file referential integrity + the other GeoJSON layers
# ---------------------------------------------------------------------------
def check_integrity(crashes, segments):
    if not (crashes and segments):
        return
    orphan = crashes["seg_ids"] - segments["ids"]
    if crashes["seg_ids"]:
        frac = len(orphan) / len(crashes["seg_ids"])
        msg = (f"{len(orphan):,} of {len(crashes['seg_ids']):,} crash seg_ids "
               f"({frac:.2%}) are not in segments_vz.geojson")
        if frac > 0.01:
            err("referential integrity: " + msg)
        elif orphan:
            warn("referential integrity: " + msg + " (clicking these crashes won't resolve a street)")


def check_equity(pts):
    """inc_tier (index 11) domain + a sanity band on the under-$100k KSI share,
    so a broken neighborhood-income assignment can't silently skew the equity panel."""
    if not isinstance(pts, list):
        return
    bad = known = ksi_known = ksi_under = 0
    for r in pts:
        if not isinstance(r, list) or len(r) < 12:
            continue
        t = r[11]
        if t not in (None, 0, 1, 2, 3):
            bad += 1
            continue
        if t is not None:
            known += 1
            if r[2] == 1:                 # KSI crash
                ksi_known += 1
                if t in (0, 1):           # tiers 0,1 = under $100k
                    ksi_under += 1
    n = len(pts)
    if bad:
        err(f"crash_points.json: {bad:,} rows have an inc_tier outside {{None,0,1,2,3}}")
    if n and known / n < 0.80:
        err(f"crash_points.json: only {100*known/n:.0f}% of crashes have a known income tier (<80%)")
    if ksi_known:
        share = 100 * ksi_under / ksi_known
        if not 70 <= share <= 90:
            err(f"equity: under-$100k KSI share is {share:.0f}% (outside the expected 70-90% band)")
        print(f"  equity: under-$100k KSI share {share:.1f}% ({ksi_known:,} KSI with known income)")


def check_aux_geojson():
    # Required by the dashboard's initial Promise.all (no .catch fallback).
    for name in ("boundary.geojson", "hin.geojson"):
        g = load(name)
        if g is not None and not (g.get("features") or g.get("type") == "Feature"):
            err(f"{name}: GeoJSON has no features")
    # Area-filter layers the page fetches on demand: each feature needs an id + name.
    for name in ("areas_tirz.geojson", "areas_mgmt.geojson", "areas_hpd.geojson",
                 "areas_zip.geojson", "areas_tract.geojson"):
        g = load(name)
        if g is not None:
            fs = g.get("features") or []
            if not fs:
                err(f"{name}: GeoJSON has no features")
            elif any(not (f.get("properties") or {}).get("id") or not (f.get("properties") or {}).get("name") for f in fs):
                err(f"{name}: every feature needs an id and a name (the Area filter keys on them)")
            elif len({f["properties"]["id"] for f in fs}) != len(fs):
                err(f"{name}: duplicate area ids")
    # Optional (city build only) — validate if present, don't require.
    for name in ("districts.geojson", "superneighborhoods.geojson"):
        path = DOCS / name
        if path.exists():
            g = load(name)
            if g is not None and not g.get("features"):
                warn(f"{name}: present but has no features")


# ---------------------------------------------------------------------------
# Packed files (what the page actually loads; see src/pack_webmap_data.py)
# ---------------------------------------------------------------------------
def _undelta(a):
    out, acc = [], 0
    for v in a:
        acc += v
        out.append(acc)
    return out


def decode_crashes(pk):
    """Mirror of the decoder in vision-zero.html: rebuild the 24-field rows."""
    import datetime as dt
    c, n = pk["cols"], pk["n"]
    lat, lon, day, seg = (_undelta(c[k]) for k in ("lat", "lon", "day", "seg"))
    d0 = dt.date.fromisoformat(pk["day0"])
    rows = []
    for i in range(n):
        date = (d0 + dt.timedelta(days=day[i])).isoformat()
        r = [lat[i] / 1e5, lon[i] / 1e5, 0, 0, 0, 0, int(date[:4]), date,
             None if c["hour"][i] == -1 else c["hour"][i], c["yll"][i],
             None if c["dist"][i] == -1 else pk["districts"][c["dist"][i]],
             None if c["inc"][i] == -1 else c["inc"][i], 0, 0,
             None if seg[i] == -1 else f"H-{seg[i]:05d}",
             None if c["sn"][i] == -1 else c["sn"][i],
             c["k"][i], c["a"][i], c["b"][i], c["c"][i], c["o"][i],
             c["light"][i], c["fac"][i], None if c["ppl"][i] == -1 else pk["people"][c["ppl"][i]]]
        if "road" in c:
            r.append(c["road"][i])
        for b, f in enumerate(pk["flagFields"]):
            r[f] = (c["flags"][i] >> b) & 1
        rows.append(r)
    return rows


def decode_segments(pk):
    """Mirror of the decoder in vision-zero.html: rebuild GeoJSON features."""
    c, xy = pk["cols"], _undelta_xy(pk["xy"])
    sid = _undelta(c["seg_id"])
    feats, j = [], 0
    for i in range(pk["n"]):
        props = {}
        for k in pk["keys"]:
            v = c[k][i]
            if k == "seg_id":
                v = f"H-{sid[i]:05d}"
            elif k in pk["dicts"]:
                v = None if v == -1 else pk["dicts"][k][v]
            elif k in ("on_txdot", "on_hin"):
                v = bool(v)
            props[k] = v
        m = pk["npts"][i]
        coords = [[xy[2 * (j + t)] / 1e5, xy[2 * (j + t) + 1] / 1e5] for t in range(m)]
        j += m
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": coords}})
    return feats


def _undelta_xy(a):
    out, x, y = [], 0, 0
    for i in range(0, len(a), 2):
        x += a[i]; y += a[i + 1]
        out += [x, y]
    return out


def check_freeway_sections():
    """Freeway sections: decodable, unique ids, and every freeway crash's section exists."""
    sk, fk = load("freeway_sections.packed.json"), load("freeway_crashes.packed.json")
    if sk is None or fk is None:
        return
    ids = [f["properties"]["seg_id"] for f in decode_segments(sk)]
    if len(ids) != len(set(ids)):
        err("freeway_sections.packed.json: duplicate seg_id")
    rows = decode_crashes(fk)
    used = {r[14] for r in rows if r[14] is not None}
    missing = used - set(ids)
    if missing:
        err(f"freeway crashes: {len(missing)} section ids not in freeway_sections.packed.json")
    print(f"  freeway_sections.packed.json: {len(ids):,} sections and ramps; "
          f"{sum(1 for r in rows if r[14] is not None):,} of {len(rows):,} freeway crashes on one ({100*sum(1 for r in rows if r[14] is not None)/max(1,len(rows)):.1f}%)")


def check_blockgroups():
    """Block groups for the income rate panel: positive population, plausible city total."""
    bg = load("blockgroups.json")
    if bg is None:
        return
    rows = bg["rows"]
    bad = [r for r in rows if len(r) != 6 or not r[2] or r[2] < 0
           or not (within(r[0], LAT_MIN, LAT_MAX) and within(r[1], LON_MIN, LON_MAX))
           or r[3] not in (None, 0, 1, 2, 3)]
    if bad:
        err(f"blockgroups.json: {len(bad)} rows malformed")
    tot = sum(r[2] for r in rows)
    if not 1_500_000 <= tot <= 3_000_000:
        err(f"blockgroups.json: total population {tot:,} is implausible for Houston")
    else:
        print(f"  blockgroups.json: {len(rows):,} block groups, {tot:,} residents")


def check_packed(pts, seg):
    """The packed files must decode to exactly the canonical exports."""
    pk = load("crashes.packed.json")
    if pk is not None and pts is not None:
        key = lambda r: json.dumps(r)
        got = sorted(map(key, decode_crashes(pk)))
        want = sorted(map(key, pts))
        if got != want:
            diff = len(set(got) ^ set(want))
            err(f"crashes.packed.json: does not decode to crash_points.json ({diff} rows differ); rerun src/pack_webmap_data.py")
        else:
            print(f"  crashes.packed.json: decodes to all {len(pts):,} crash rows exactly")
    fw = load("freeway_crash_points.json")
    fk = load("freeway_crashes.packed.json")
    if fw is not None and fk is not None:
        bad = [r for r in fw if len(r) != 25 or r[12] != 0
               or r[24] not in (1, 2) or r[13] != (1 if r[24] == 1 else 0)]
        if bad:
            err(f"freeway_crash_points.json: {len(bad)} rows break the freeway contract (25 fields, not on HIN, road_type 1/2 with matching TxDOT flag)")
        key = lambda r: json.dumps(r)
        if sorted(map(key, decode_crashes(fk))) != sorted(map(key, fw)):
            err("freeway_crashes.packed.json: does not decode to freeway_crash_points.json; rerun src/pack_webmap_data.py")
        else:
            print(f"  freeway_crashes.packed.json: decodes to all {len(fw):,} freeway crash rows exactly "
                  f"({sum(r[3] for r in fw):,} fatal crashes)")
    ps = load("segments.packed.json")
    if ps is not None and seg is not None:
        got = decode_segments(ps)
        want = [{"type": "Feature", "properties": f["properties"],
                 "geometry": f["geometry"]} for f in seg["features"]]
        if got != want:
            bad = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
            err(f"segments.packed.json: does not decode to segments_vz.geojson ({bad} features differ); rerun src/pack_webmap_data.py")
        else:
            print(f"  segments.packed.json: decodes to all {len(got):,} segments exactly")


# ---------------------------------------------------------------------------
def main():
    print(f"Validating dashboard exports in {DOCS} ...")
    # The readable exports (crash_points.json, segments_vz.geojson, freeway_crash_points.json)
    # are built locally but not committed (size). Where they are missing, as in CI, every
    # check runs on the rows decoded from the packed files the page actually loads; locally
    # the packed files are also round-tripped against them.
    canonical = (DOCS / "crash_points.json").exists() and (DOCS / "segments_vz.geojson").exists()
    if canonical:
        pts = load("crash_points.json")
        seg = load("segments_vz.geojson")
    else:
        print("  (readable exports not present; checking the decoded packed files)")
        pk, sk = load("crashes.packed.json"), load("segments.packed.json")
        pts = decode_crashes(pk) if pk is not None else None
        seg = {"type": "FeatureCollection", "features": decode_segments(sk)} if sk is not None else None
    vz = load("vz_summary.json")

    crashes = check_crashes(pts) if pts is not None else None
    segments = check_segments(seg) if seg is not None else None
    if vz is not None:
        check_summary(vz, crashes)
    check_integrity(crashes, segments)
    if pts is not None:
        check_equity(pts)
    check_aux_geojson()
    if canonical:
        check_packed(pts, seg)
    check_blockgroups()
    check_freeway_sections()

    print()
    for w in warnings:
        print(f"  WARN  {w}")
    if errors:
        for e in errors:
            print(f"  FAIL  {e}")
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s) — data contract VIOLATED.")
        return 1
    print(f"All checks passed ({len(warnings)} warning(s)). Data contract OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
