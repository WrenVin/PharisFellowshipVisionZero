"""Make the link-preview image (docs/og-image.png, 1200x630) shown when the dashboard
link is shared in messages, email or social posts.

Left: the site name, a one-line description, and the headline counts of people killed
and seriously injured (from docs/crash_points.json person records). Right: city streets
shaded by people killed or seriously injured (docs/segments_vz.geojson), the same red
scale as the dashboard. Rerun after each data refresh:

    .venv/bin/python src/make_og_image.py
"""

import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

DOCS = Path(__file__).resolve().parent.parent / "docs"
NAVY, INK, MUTED = "#162e51", "#1b1b1b", "#c9d3df"
REDS = ["#fdae61", "#f98e52", "#f16d43", "#e0451f", "#c0151a", "#8a0b12"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def font():
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Public Sans", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"):
        if name in have:
            return name
    return "sans-serif"


def main():
    rows = json.loads((DOCS / "crash_points.json").read_text())
    killed = serious = 0
    last = max(r[7] for r in rows if r[7])
    for r in rows:
        for c in map(int, (r[23] or "").split(",")) if r[23] else ():
            if (c >> 5) & 1:
                killed += 1
            else:
                serious += 1
    y, m, d = map(int, last.split("-"))
    if d < 28:                       # data through the last complete month
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    first = min(r[6] for r in rows if r[6])
    span = f"January {first} to {MONTHS[m - 1]} {y}"

    seg = gpd.read_file(DOCS / "segments_vz.geojson")
    seg = seg.to_crs(3857)
    v = seg["n_severe"].fillna(0)

    plt.rcParams["font.family"] = font()
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor("white")

    # left panel
    ax0 = fig.add_axes([0, 0, 0.42, 1])
    ax0.set_axis_off()
    ax0.add_patch(plt.Rectangle((0, 0), 1, 1, color=NAVY, transform=ax0.transAxes))
    ax0.text(0.08, 0.86, "Houston Street\nSafety Dashboard", color="white", fontsize=34, fontweight="bold",
             va="top", linespacing=1.1, transform=ax0.transAxes)
    ax0.text(0.08, 0.60, "Where people are killed and\nseriously injured on city streets", color=MUTED,
             fontsize=17, va="top", linespacing=1.3, transform=ax0.transAxes)
    ax0.text(0.08, 0.36, f"{killed:,}", color="white", fontsize=40, fontweight="bold", va="bottom", transform=ax0.transAxes)
    ax0.text(0.08, 0.345, "people killed", color=MUTED, fontsize=15, va="top", transform=ax0.transAxes)
    ax0.text(0.55, 0.36, f"{serious:,}", color="white", fontsize=40, fontweight="bold", va="bottom", transform=ax0.transAxes)
    ax0.text(0.55, 0.345, "seriously injured", color=MUTED, fontsize=15, va="top", transform=ax0.transAxes)
    ax0.text(0.08, 0.10, span, color=MUTED, fontsize=14, transform=ax0.transAxes)

    # right panel: the street map
    ax = fig.add_axes([0.43, 0.02, 0.56, 0.96])
    ax.set_axis_off()
    cmap = LinearSegmentedColormap.from_list("reds", REDS)
    seg[v == 0].plot(ax=ax, color="#c9cdd2", linewidth=0.45)
    hot = seg[v > 0].assign(v=v[v > 0]).sort_values("v")
    hot.plot(ax=ax, column="v", cmap=cmap, vmin=1, vmax=max(4, hot["v"].quantile(0.97)),
             linewidth=1.1 + hot["v"].clip(upper=8) * 0.3)
    # frame the dense core of the city (the long annexed corridors would shrink everything)
    c = seg.geometry.centroid
    x0, x1 = c.x.quantile(0.02), c.x.quantile(0.98)
    y0, y1 = c.y.quantile(0.02), c.y.quantile(0.98)
    pad = 0.04 * max(x1 - x0, y1 - y0)
    ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")

    out = DOCS / "og-image.png"
    fig.savefig(out, dpi=100, facecolor="white")
    print(f"Wrote {out.name}: {killed:,} killed, {serious:,} seriously injured, {span} "
          f"({out.stat().st_size/1e3:.0f} KB)")


if __name__ == "__main__":
    main()
