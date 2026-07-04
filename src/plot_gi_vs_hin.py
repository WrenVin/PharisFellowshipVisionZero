"""Figure: the two crash-based maps, separated side by side.

Left: the Gi* severe-crash hotspot map built by this project from raw CRIS
crashes (FDR-significant hotspots). Right: the City's adopted High Injury
Network (2022 vintage, 2018-2022 data) as ingested. Same crashes underneath,
two methods; the segment-level overlap is printed in the footnote.

Output: reports/gi_vs_hin.png
"""

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"),
                        layer="segments").to_crs(2278)
    boundary = gpd.read_file(cfg.DOCS / "boundary.geojson").to_crs(2278)

    gi = seg.hotspot.astype(bool)
    hin = seg.on_hin.astype(bool)
    tot = seg.n_severe.sum()
    pct_gi_on_hin = 100 * (gi & hin).sum() / gi.sum()

    panels = [
        ("Severe-crash hotspot map (Gi*)",
         "Built by this project from raw CRIS crashes: Getis-Ord Gi*,\n"
         "999 permutations, false-discovery-rate corrected",
         gi, "#C0392B"),
        ("City of Houston High Injury Network",
         "The adopted product (2022 network, 2018 to 2022 data):\n"
         "half-mile crash-density screening",
         hin, "#7a6fb0"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(22, 11), dpi=180)
    for ax, (title, sub, mask, color) in zip(axes, panels):
        boundary.plot(ax=ax, facecolor="none", edgecolor="#999999",
                      linewidth=0.8)
        seg.plot(ax=ax, color="#e2ddce", linewidth=0.2, zorder=1)
        seg[mask].plot(ax=ax, color=color, linewidth=1.1, zorder=2)
        mi = seg.length_ft[mask].sum() / 5280
        cap = 100 * seg.n_severe[mask].sum() / tot
        ax.set_axis_off()
        ax.set_title(f"{title}\n{sub}", fontsize=15, color="#16395B",
                     fontfamily="Georgia", pad=10)
        ax.text(0.02, 0.02,
                f"{mi:,.0f} miles\n{cap:.0f}% of severe crashes 2016 to 2026",
                transform=ax.transAxes, fontsize=13, va="bottom",
                bbox=dict(facecolor="#FBF6E9", edgecolor="#C8A24B",
                          boxstyle="round,pad=0.5"))
    fig.suptitle("Two crash-based maps of the same crashes, two methods",
                 fontsize=19, color="#16395B", fontfamily="Georgia", y=0.99)
    fig.text(0.5, 0.015,
             f"Only {pct_gi_on_hin:.0f}% of the hotspot map's segments are "
             "on the City's HIN, from the same crashes: crash-based "
             "screening is method-sensitive.",
             ha="center", fontsize=13, color="#16395B")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    out = cfg.REPORTS / "gi_vs_hin.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
