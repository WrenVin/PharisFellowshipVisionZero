"""Export the concept Proactive Safety Network for the dashboard overlay
(docs/psn.geojson).

The PSN is this project's design-based counterpart to the City's HIN: streets
flagged by the risk model for how they are built, not for their crash history
(built by src/build_psn.py on the trb-revisions branch; the network itself is
committed at data/processed/houston_concept_psn.geojson). "Concept" follows the
Alameda CTC (2024) labeling convention: a screening product for review, not an
engineering determination.

Geometry-only, like docs/hin.geojson: the dashboard tags each segment with its
district / super neighborhood client-side, so no properties are needed.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "houston_concept_psn.geojson"
OUT = ROOT / "docs" / "psn.geojson"

with open(SRC) as f:
    psn = json.load(f)


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 5), round(coords[1], 5)]
    return [_round(c) for c in coords]


miles = sum(f["properties"].get("length_ft", 0) for f in psn["features"]) / 5280
feats = [{"type": "Feature", "properties": {},
          "geometry": {"type": f["geometry"]["type"],
                       "coordinates": _round(f["geometry"]["coordinates"])}}
         for f in psn["features"]]

OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                          separators=(",", ":")))
print(f"Wrote {len(feats):,} PSN segments ({miles:.0f} mi) -> {OUT} "
      f"({OUT.stat().st_size/1e6:.2f} MB)")
