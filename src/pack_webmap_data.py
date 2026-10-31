"""Pack the dashboard's two large exports into compact files the page loads.

crash_points.json (one 24-field row per crash) and segments_vz.geojson stay the
canonical, human-readable exports. This step writes column-oriented versions:

    docs/crashes.packed.json    every crash, same 24 fields, lossless
    docs/segments.packed.json   every street segment, same properties + geometry
    docs/freeway_crashes.packed.json   freeway/tollway/ramp/frontage crashes for the
                                optional toggle (24 fields + road_type), lossless

Compaction: values are stored per column instead of per row; coordinates become
integers (1e-5 degrees, the exports' existing precision) stored as differences
from the previous point; dates become day numbers; yes/no flags share one
bit-packed integer; repeated strings become dictionary indexes. Crashes are
sorted by segment then date (order carries no meaning on the page), which makes
the differences small. vision-zero.html rebuilds the exact original rows and
GeoJSON features on load, so no other dashboard code changes.

tests/validate_exports.py decodes both packed files and checks they match the
canonical exports value for value. Run after export_webmap_data.py:

    .venv/bin/python src/pack_webmap_data.py
"""

import datetime as dt
import json
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
D0 = dt.date(2016, 1, 1)
# crash row field -> bit in the packed flags column
FLAG_FIELDS = (2, 3, 4, 5, 12, 13)          # severe, fatal, ped, bike, on_hin, on_txdot
SEG_STR_DICT = ("name", "road_class", "district", "sidewalk_presence")
SEG_BOOL = ("on_txdot", "on_hin")


def dump(obj, path):
    path.write_text(json.dumps(obj, separators=(",", ":")))
    return path.stat().st_size


def delta(values):
    out, prev = [], 0
    for v in values:
        out.append(v - prev)
        prev = v
    return out


def pack_crashes(rows):
    rows = sorted(rows, key=lambda r: (r[14] is None, r[14] or "", r[7], r[0], r[1]))
    dists = sorted({r[10] for r in rows if r[10] is not None})
    di = {d: i for i, d in enumerate(dists)}
    nn = lambda v: -1 if v is None else v
    c = {
        "lat": delta([round(r[0] * 1e5) for r in rows]),
        "lon": delta([round(r[1] * 1e5) for r in rows]),
        "day": delta([(dt.date.fromisoformat(r[7]) - D0).days for r in rows]),
        "flags": [sum(r[f] << b for b, f in enumerate(FLAG_FIELDS)) for r in rows],
        "hour": [nn(r[8]) for r in rows],
        "yll": [r[9] for r in rows],
        "dist": [-1 if r[10] is None else di[r[10]] for r in rows],
        "inc": [nn(r[11]) for r in rows],
        "seg": delta([-1 if r[14] is None else int(r[14][2:]) for r in rows]),
        "sn": [nn(r[15]) for r in rows],
    }
    for i, k in zip(range(16, 21), ("k", "a", "b", "c", "o")):
        c[k] = [r[i] for r in rows]
    c["light"] = [r[21] for r in rows]
    c["fac"] = [r[22] for r in rows]
    people = sorted({r[23] for r in rows if r[23] is not None})
    pi = {v: i for i, v in enumerate(people)}
    c["ppl"] = [-1 if r[23] is None else pi[r[23]] for r in rows]
    if rows and len(rows[0]) > 24:          # road type, field 24 (0 street, 3 frontage, 1 freeway, 2 toll)
        c["road"] = [r[24] for r in rows]
    return {"format": "vz-crashes", "version": 2, "day0": D0.isoformat(),
            "flagFields": list(FLAG_FIELDS), "districts": dists, "people": people,
            "n": len(rows), "cols": c}


def pack_segments(gj):
    feats = gj["features"]
    keys = list(feats[0]["properties"])
    cols, dicts = {}, {}
    for k in keys:
        vals = [f["properties"][k] for f in feats]
        if k == "seg_id":
            cols[k] = delta([int(v[2:]) for v in vals])
        elif k in SEG_STR_DICT:
            dicts[k] = sorted({v for v in vals if v is not None})
            ix = {v: i for i, v in enumerate(dicts[k])}
            cols[k] = [-1 if v is None else ix[v] for v in vals]
        elif k in SEG_BOOL:
            cols[k] = [int(v) for v in vals]
        else:
            cols[k] = vals
    npts, xy, px, py = [], [], 0, 0
    for f in feats:
        g = f["geometry"]
        assert g["type"] == "LineString", g["type"]
        npts.append(len(g["coordinates"]))
        for x, y in g["coordinates"]:
            X, Y = round(x * 1e5), round(y * 1e5)
            xy += [X - px, Y - py]
            px, py = X, Y
    return {"format": "vz-segments", "version": 1, "keys": keys, "dicts": dicts,
            "n": len(feats), "cols": cols, "npts": npts, "xy": xy}


def main():
    crashes = json.loads((DOCS / "crash_points.json").read_text())
    n = dump(pack_crashes(crashes), DOCS / "crashes.packed.json")
    print(f"Wrote {len(crashes):,} crashes -> crashes.packed.json ({n/1e6:.1f} MB)")
    fp = DOCS / "freeway_crash_points.json"
    if fp.exists():
        fw = json.loads(fp.read_text())
        n = dump(pack_crashes(fw), DOCS / "freeway_crashes.packed.json")
        print(f"Wrote {len(fw):,} freeway crashes -> freeway_crashes.packed.json ({n/1e6:.1f} MB)")
    fsp = DOCS / "freeway_sections.geojson"   # freeway sections and ramps, loaded with the Freeways toggle
    if fsp.exists():
        fs = json.loads(fsp.read_text())
        n = dump(pack_segments(fs), DOCS / "freeway_sections.packed.json")
        print(f"Wrote {len(fs['features']):,} freeway sections -> freeway_sections.packed.json ({n/1e6:.1f} MB)")
    segs = json.loads((DOCS / "segments_vz.geojson").read_text())
    n = dump(pack_segments(segs), DOCS / "segments.packed.json")
    print(f"Wrote {len(segs['features']):,} segments -> segments.packed.json ({n/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
