"""Paper Figure 6: the City's High Injury Network across three vintages.

Replaces an ad-hoc render whose title misstated the 0.42 mile-Jaccard as
"only 42% of miles survive" (the survival share of 2022 miles is 54%; 0.42
is intersection over union). The Jaccard is computed live from the layer.

Outputs: reports/fig_hin_vintages.png
"""

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg

PANELS = [
    ("on_hin_2018", "HIN 2018", "2014 to 2018 data", "#b08d2f"),
    ("on_hin",      "HIN 2022", "2018 to 2022 data", "#7a6fb0"),
    ("on_hin_2025", "HIN 2025", "2021 to 2025 data", "#C0392B"),
]


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"),
                        layer="segments").to_crs(2278)
    boundary = gpd.read_file(cfg.DOCS / "boundary.geojson").to_crs(2278)

    a = seg.on_hin.astype(bool)
    b = seg.on_hin_2025.astype(bool)
    mi = seg.length_ft / 5280
    jac = mi[a & b].sum() / mi[a | b].sum()

    fig, axes = plt.subplots(1, 3, figsize=(24, 8.5), dpi=170)
    for ax, (col, name, window, color) in zip(axes, PANELS):
        on = seg[seg[col].astype(bool)]
        boundary.plot(ax=ax, facecolor="none", edgecolor="#999999",
                      linewidth=0.7)
        seg.plot(ax=ax, color="#e9e5d8", linewidth=0.15, zorder=1)
        on.plot(ax=ax, color=color, linewidth=0.9, zorder=2)
        ax.set_axis_off()
        ax.set_title(f"{name}\n({window})\n"
                     f"{on.length_ft.sum()/5280:,.0f} miles on this network",
                     fontsize=14, color="#16395B", fontfamily="Georgia")
    fig.suptitle("The City's High Injury Network across three vintages: "
                 f"mile overlap (Jaccard) between the 2022 and 2025 editions "
                 f"is {jac:.2f}",
                 fontsize=17, color="#16395B", fontfamily="Georgia", y=0.99)
    plt.tight_layout()
    out = cfg.REPORTS / "fig_hin_vintages.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"saved {out} | Jaccard {jac:.3f}")


if __name__ == "__main__":
    main()
