"""Build the interactive District C network map (reports/network_map.html).

Design goal: readable by a non-GIS audience (council staff, fellowship
reviewers). Plain-English road classes, a fixed legend box, and tooltips
with human labels. Variable definitions live in CODEBOOK.md.
"""

from pathlib import Path

import folium
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]

# Plain-English class labels and colors (keep in sync with CODEBOOK.md)
CLASS_LABEL = {
    "primary": "Major arterial",
    "secondary": "Arterial",
    "tertiary": "Collector",
    "residential": "Local street",
    "unclassified": "Minor street",
}
CLASS_COLOR = {
    "Major arterial": "#d62728",
    "Arterial": "#ff7f0e",
    "Collector": "#2ca02c",
    "Local street": "#1f77b4",
    "Minor street": "#9467bd",
}
DUAL_COLOR = "#e377c2"

# prefer the enriched (conflated) file once it exists
_enr = ROOT / "data/processed/district_c_segments_enriched.gpkg"
_clean = ROOT / "data/processed/district_c_segments_clean.gpkg"
seg = gpd.read_file(_enr if _enr.exists() else _clean, layer="segments").to_crs(4326)
boundary = gpd.read_file(ROOT / "data/raw/district_c_boundary.geojson")

# Friendly display columns
base_class = seg["highway"].str.replace("_link", "", regex=False)
seg["road_class"] = base_class.map(CLASS_LABEL).fillna("Minor street")
seg.loc[seg["highway"].str.endswith("_link"), "road_class"] = "Minor street"
seg["street"] = seg["name"].fillna("(unnamed)")
if "posted_speed_mph" in seg.columns:
    _srclabel = {
        "city": "city posted limit", "osm": "OpenStreetMap",
        "default_30_local": "TX default (local, 30)",
        "default_30_unposted": "TX default (unposted, 30)",
    }
    seg["posted_speed"] = [
        f"{v:.0f} mph ({_srclabel.get(s, s)})" if v == v else "unknown"
        for v, s in zip(seg["posted_speed_mph"], seg["speed_source"])
    ]
else:
    seg["posted_speed"] = seg["maxspeed_mph"].map(
        lambda v: f"{v:.0f} mph" if v == v else "not tagged"
    )
# lanes: prefer conflated lanes_final (with source), fall back to OSM lanes
_lanesrc = {"city": "city", "osm": "OpenStreetMap", "default_local_2": "local default",
            "none": "unknown"}
if "lanes_final" in seg.columns:
    seg["lanes_disp"] = [
        f"{v:.0f} ({_lanesrc.get(s, s)})" if v == v else "unknown"
        for v, s in zip(seg["lanes_final"], seg["lanes_source"])
    ]
else:
    seg["lanes_disp"] = seg["lanes"].map(lambda v: f"{v:.0f}" if v == v else "not tagged")

if "roadway_width_ft" in seg.columns:
    seg["width_disp"] = seg["roadway_width_ft"].map(
        lambda v: f"{v:.0f} ft" if v == v else "unknown"
    )
    seg["median_disp"] = seg["median_type"].fillna("unknown")
seg["len_disp"] = seg["length_ft"].map(lambda v: f"{v:,.0f} ft")
seg["oneway_disp"] = seg["oneway"].map({True: "yes", False: "no"})
seg["divided_disp"] = seg["merged_dual"].map(
    {True: "yes - both halves merged into this segment", False: "no"}
)

if "roadway_width_ft" in seg.columns:
    TOOLTIP = ["street", "road_class", "lanes_disp", "width_disp", "posted_speed",
               "median_disp", "oneway_disp", "divided_disp", "len_disp"]
    ALIASES = ["Street", "Road type", "Traffic lanes (total)", "Roadway width",
               "Posted speed", "Median", "One-way", "Divided road (merged)",
               "Segment length"]
else:
    TOOLTIP = ["street", "road_class", "lanes_disp", "posted_speed",
               "oneway_disp", "divided_disp", "len_disp"]
    ALIASES = ["Street", "Road type", "Traffic lanes (total)", "Posted speed",
               "One-way", "Divided road (merged)", "Segment length"]

m = folium.Map(tiles="CartoDB positron")
boundary.explore(
    m=m, color="black", style_kwds={"fill": False, "weight": 2.5},
    name="District C boundary",
)

# One toggleable layer per road type, drawn smallest-to-largest
for label in ["Local street", "Minor street", "Collector", "Arterial", "Major arterial"]:
    sub = seg[seg["road_class"] == label]
    if sub.empty:
        continue
    weight = 1.2 if label in ("Local street", "Minor street") else 2.2
    sub.explore(
        m=m, color=CLASS_COLOR[label], tooltip=TOOLTIP, tooltip_kwds={"aliases": ALIASES},
        style_kwds={"weight": weight, "opacity": 0.8}, name=f"{label}s",
    )

seg[seg["merged_dual"]].explore(
    m=m, color=DUAL_COLOR, tooltip=TOOLTIP, tooltip_kwds={"aliases": ALIASES},
    style_kwds={"weight": 3, "opacity": 0.9},
    name="Divided roads (merged to one line)", show=False,
)

m.fit_bounds(m.get_bounds())
folium.LayerControl(collapsed=False).add_to(m)

legend_rows = "".join(
    f'<div><span style="background:{c};width:18px;height:4px;'
    f'display:inline-block;margin-right:6px;vertical-align:middle"></span>{l}</div>'
    for l, c in CLASS_COLOR.items()
)
legend_html = f"""
<div style="position: fixed; bottom: 24px; left: 12px; z-index: 9999;
            background: white; padding: 12px 14px; border-radius: 6px;
            box-shadow: 0 1px 5px rgba(0,0,0,0.35);
            font: 13px/1.6 Helvetica, Arial, sans-serif; max-width: 290px;">
  <b>District C street network</b><br>
  <span style="color:#555">Every public street in Houston Council District C,
  broken into {len(seg):,} intersection-to-intersection segments
  ({seg['length_ft'].sum() / 5280:,.0f} miles). Freeways excluded —
  the city can't redesign them. Hover any street for its details.</span>
  <hr style="margin:8px 0">
  {legend_rows}
  <div><span style="background:{DUAL_COLOR};width:18px;height:4px;
    display:inline-block;margin-right:6px;vertical-align:middle"></span>
    Divided road, two halves merged (off by default)</div>
  <div><span style="border-top:2.5px solid black;width:18px;
    display:inline-block;margin-right:6px;vertical-align:middle"></span>
    District C boundary</div>
  <hr style="margin:8px 0">
  <span style="color:#555">"Not tagged" = missing in OpenStreetMap, not
  necessarily absent on the ground. Full variable definitions: CODEBOOK.md</span>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

out = ROOT / "reports/network_map.html"
m.save(out)
print(f"saved {out}")
