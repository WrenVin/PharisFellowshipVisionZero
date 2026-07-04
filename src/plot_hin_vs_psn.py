"""Figure: the City's HIN and the Houston Concept PSN, side by side.

Two networks of near-identical mileage, one built from crash history
(2014-2018 data, adopted with the 2020 Vision Zero Action Plan), one from
the validated design-risk model. Stat boxes report each network's capture of
past (2016-2026) and post-2021 severe crashes.

Output: reports/hin_vs_psn.png
"""

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as cfg


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"),
                        layer="segments").to_crs(2278)
    boundary = gpd.read_file(cfg.DOCS / "boundary.geojson").to_crs(2278)

    cr = gpd.read_file(cfg.processed("crashes.gpkg"), ignore_geometry=True)
    cr = cr[(cr.severe == 1) & cr.seg_id.notna()].copy()
    cr["date"] = pd.to_datetime(cr["date"])
    post = cr[cr.date >= "2022-01-01"].groupby("seg_id").size().rename("n_post")
    seg = seg.merge(post, on="seg_id", how="left")
    seg["n_post"] = seg.n_post.fillna(0)

    hin = seg[seg.on_hin.astype(bool)]
    psn = seg[seg.psn.astype(bool)]
    tot_all, tot_post = seg.n_severe.sum(), seg.n_post.sum()

    panels = [
        ("City of Houston High Injury Network",
         "Built from crash history (2014 to 2018 data, adopted 2020)",
         hin, "#7a6fb0"),
        ("Houston Concept Proactive Safety Network",
         "Built from street design: the validated model, no crash history used",
         psn, "#C0392B"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(22, 11), dpi=180)
    for ax, (title, sub, net, color) in zip(axes, panels):
        boundary.plot(ax=ax, facecolor="none", edgecolor="#999999",
                      linewidth=0.8)
        seg.plot(ax=ax, color="#e2ddce", linewidth=0.2, zorder=1)
        net.plot(ax=ax, color=color, linewidth=1.1, zorder=2)
        mi = net.length_ft.sum() / 5280
        cap = 100 * net.n_severe.sum() / tot_all
        cap_p = 100 * net.n_post.sum() / tot_post
        ax.set_axis_off()
        ax.set_title(f"{title}\n{sub}", fontsize=15, color="#16395B",
                     fontfamily="Georgia", pad=10)
        ax.text(0.02, 0.02,
                f"{mi:,.0f} miles\n"
                f"{cap:.0f}% of severe crashes 2016 to 2026\n"
                f"{cap_p:.0f}% of severe crashes 2022 to 2026",
                transform=ax.transAxes, fontsize=13, va="bottom",
                bbox=dict(facecolor="#FBF6E9", edgecolor="#C8A24B",
                          boxstyle="round,pad=0.5"))
    fig.suptitle("Two maps of dangerous streets, same size, different evidence",
                 fontsize=19, color="#16395B", fontfamily="Georgia", y=0.99)
    plt.tight_layout()
    out = cfg.REPORTS / "hin_vs_psn.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
