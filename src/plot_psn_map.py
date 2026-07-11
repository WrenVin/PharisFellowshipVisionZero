"""Figure: the Houston Concept Proactive Safety Network as its own layer.

The PSN as a standalone deliverable (605 smoothed miles), one network in one
color over the street grid, the way a city publishes its High Injury Network.
No HIN reference; the PSN stands on its own.

Outputs: reports/psn_only_map.png (standalone, one color)
         reports/psn_map.png (tiered against the adopted HIN; paper Figure 5,
         legend language aligned with Table 3 after review round 2)
"""

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import config as cfg

PSN = "#C0392B"   # the network


def main():
    seg = gpd.read_file(cfg.processed("segments_model.gpkg"),
                        layer="segments").to_crs(2278)
    boundary = gpd.read_file(cfg.DOCS / "boundary.geojson").to_crs(2278)

    psn = seg.psn.astype(bool)
    psn_mi = seg.length_ft[psn].sum() / 5280

    fig, ax = plt.subplots(figsize=(15, 13), dpi=200)
    boundary.plot(ax=ax, facecolor="none", edgecolor="#999999", linewidth=0.8)
    seg.plot(ax=ax, color="#e2ddce", linewidth=0.25, zorder=1)
    seg[psn].plot(ax=ax, color=PSN, linewidth=1.2, zorder=2)

    ax.set_axis_off()
    ax.set_title("Houston Concept Proactive Safety Network",
                 fontsize=20, color="#16395B", fontfamily="Georgia", pad=14)
    handles = [
        Line2D([], [], color=PSN, linewidth=3,
               label=f"Proactive Safety Network ({psn_mi:,.0f} miles)"),
        Line2D([], [], color="#e2ddce", linewidth=2, label="All other streets"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=13, frameon=True,
              facecolor="#FBF6E9", edgecolor="#C8A24B")
    plt.tight_layout()
    out = cfg.REPORTS / "psn_only_map.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"saved {out} | PSN {psn_mi:,.0f} mi")
    tiered(seg, boundary)


def tiered(seg, boundary):
    """Paper Figure 5: the PSN tiered against the adopted HIN."""
    tiers = [
        ("psn_and_hin", "#6e1f2e",
         "On both networks: high design risk and high crash history"),
        ("psn_only", "#C0392B",
         "PSN only: high design risk, absent from the adopted HIN"),
        ("hin_only", "#7a6fb0",
         "HIN only: high historical harm, lower modeled design risk"),
    ]
    fig, ax = plt.subplots(figsize=(15, 13), dpi=200)
    boundary.plot(ax=ax, facecolor="none", edgecolor="#999999", linewidth=0.8)
    seg.plot(ax=ax, color="#e2ddce", linewidth=0.25, zorder=1)
    handles = []
    for key, color, label in tiers:
        sub = seg[seg.psn_tier == key]
        mi = sub.length_ft.sum() / 5280
        sub.plot(ax=ax, color=color, linewidth=1.2, zorder=2)
        handles.append(Line2D([], [], color=color, linewidth=3,
                              label=f"{label} ({mi:,.0f} mi)"))
    handles.append(Line2D([], [], color="#e2ddce", linewidth=2,
                          label="All other streets"))
    ax.set_axis_off()
    ax.set_title("Houston Concept Proactive Safety Network, "
                 "tiered against the adopted HIN",
                 fontsize=19, color="#16395B", fontfamily="Georgia", pad=14)
    ax.legend(handles=handles, loc="lower left", fontsize=12.5, frameon=True,
              facecolor="#FBF6E9", edgecolor="#C8A24B")
    plt.tight_layout()
    out = cfg.REPORTS / "psn_map.png"
    plt.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
