"""Figures for the temporal result and calibration (paper Figures 3 and 3b).

fig_temporal_capture.png: prospective capture bars on the PRIMARY common
holdout (2023 through June 2026, postdating every map including the HIN),
with gold dots marking each crash-based map graded on its own selection-
window crashes (HIN: 2018-2022; Gi*: pre-2022), showing
the regression-to-the-mean fall the design model does not experience.

fig_calibration.png: pooled out-of-fold decile calibration (district-blocked
NB), predicted vs observed severe crashes per decile. Ordering is monotone;
over-prediction concentrates in the top decile. Values from
reports/model_validation_report.md (modeling step 3).

Outputs: reports/fig_temporal_capture.png, reports/fig_calibration.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config as cfg

NAVY, GOLD, CREAM = "#13385E", "#C5A55A", "#FDF9EE"

# Primary common holdout (2023 through June 2026), top 589 mi
ROWS = [
    ("Design model with imagery (v2)\nfit on 2016 to 2021 only", 51, "#13385E", None),
    ("Official HIN as adopted\n(2018 to 2022 data)",             46, "#7B6FB8", 59),
    ("Design model (v1)\nfit on 2016 to 2021 only",              48, "#5B84AE", None),
    ("Gradient-boosted reference (untuned)\nfit on 2016 to 2021 only", 53, "#4D4D4D", None),
    ("Context-and-exposure baseline\n(no design or class)",      43, "#9C9C9C", None),
    ("Crash-hotspot map (Gi*)\non pre-2022 crashes",             39, "#C0392B", 64),
]

# Pooled OOF decile calibration (validation report)
CAL_PRED = [49, 91, 125, 164, 224, 325, 483, 850, 1854, 5838]
CAL_OBS = [34, 96, 119, 180, 296, 316, 489, 1070, 2028, 5092]


def capture_fig():
    fig, ax = plt.subplots(figsize=(9.2, 6.1))
    fig.patch.set_facecolor("white")
    labels = [r[0] for r in ROWS][::-1]
    vals = [r[1] for r in ROWS][::-1]
    cols = [r[2] for r in ROWS][::-1]
    dots = [r[3] for r in ROWS][::-1]
    y = np.arange(len(ROWS))
    ax.barh(y, vals, color=cols, height=0.62)
    for yi, v in zip(y, vals):
        ax.text(v - 1.2, yi, f"{v}%", va="center", ha="right",
                color="white", fontsize=12, fontweight="bold")
    for yi, dv in zip(y, dots):
        if dv is not None:
            ax.plot(dv, yi, "o", color=GOLD, markersize=9)
            ax.annotate(f"in-sample: {dv}%",
                        (dv, yi), textcoords="offset points", xytext=(9, -3.5),
                        ha="left", fontsize=9.5, color="#8a7433")
    ax.set_yticks(y, labels, fontsize=10)
    ax.set_xlim(0, 78)
    ax.set_xlabel("Share of 2023 to mid-2026 severe crashes captured by each "
                  "map's top 589 miles", fontsize=10)
    ax.set_title("Temporally held-out screening performance",
                 fontsize=13, color=NAVY)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = cfg.REPORTS / "fig_temporal_capture.png"
    fig.savefig(out, dpi=200)
    print(f"wrote {out}")


def calibration_fig():
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    fig.patch.set_facecolor("white")
    lim = 6500
    ax.plot([0, lim], [0, lim], "--", color="#999", lw=1,
            label="perfect calibration")
    ax.plot(CAL_PRED, CAL_OBS, "o-", color=NAVY, markersize=7,
            label="out-of-fold deciles")
    top_excess = 100 * (CAL_PRED[-1] / CAL_OBS[-1] - 1)
    ax.annotate(f"top decile over-predicts by {top_excess:.0f}%",
                (CAL_PRED[-1], CAL_OBS[-1]), textcoords="offset points",
                xytext=(-190, -16), fontsize=10, color="#C0392B")
    ax.set_xlabel("Predicted severe crashes per decile (pooled out-of-fold)",
                  fontsize=10)
    ax.set_ylabel("Observed severe crashes per decile", fontsize=10)
    ax.set_title("Calibration by predicted-risk decile:\nordering is monotone; "
                 "over-prediction concentrates at the top", fontsize=12,
                 color=NAVY)
    ax.legend(fontsize=9, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = cfg.REPORTS / "fig_calibration.png"
    fig.savefig(out, dpi=200)
    print(f"wrote {out}")


if __name__ == "__main__":
    capture_fig()
    calibration_fig()
