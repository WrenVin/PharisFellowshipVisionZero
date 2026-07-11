"""Paper Figure 2: forest plot of Table 1 incidence-rate ratios.

Values are Table 1 of the TRB draft (NB2, cluster-robust CIs; continuous
effects per +1 SD). Footnote language is paper-appropriate (review round:
the old render referenced 'the caveat slide', deck language).

Outputs: reports/irr_forest.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg

NAVY, GOLD, RED, GREY, GREEN = "#13385E", "#C9A227", "#B03A2E", "#8A8A8A", "#1E8449"

ROWS = [  # label, irr, lo, hi, color
    ("Major arterial (vs local street)", 2.88, 2.19, 3.79, RED),
    ("Arterial (vs local street)",       2.56, 1.99, 3.29, RED),
    ("Collector (vs local street)",      2.37, 1.90, 2.97, RED),
    ("Sidewalk both sides *",            1.71, 1.47, 1.99, GOLD),
    ("Sidewalk partial *",               1.54, 1.40, 1.70, GOLD),
    ("Sidewalk one side *",              1.37, 1.24, 1.53, GOLD),
    ("Intersection connectivity (+1 SD)", 1.22, 1.16, 1.29, NAVY),
    ("Lanes (+1 SD)",                    1.21, 1.16, 1.27, NAVY),
    ("Signals (+1 SD)",                  1.16, 1.13, 1.19, NAVY),
    ("Traffic volume (+1 SD)",           1.16, 1.09, 1.23, GREY),
    ("Neighborhood poverty (+1 SD)",     1.11, 1.05, 1.16, GREY),
    ("Posted speed (+1 SD)",             1.10, 1.05, 1.16, NAVY),
    ("Median income (+1 SD)",            0.81, 0.75, 0.88, GREY),
    ("One-way street",                   0.74, 0.60, 0.92, GREEN),
]

fig, ax = plt.subplots(figsize=(9.6, 6.4))
fig.patch.set_facecolor("white")
ys = range(len(ROWS) - 1, -1, -1)
for y, (label, irr, lo, hi, c) in zip(ys, ROWS):
    ax.plot([lo, hi], [y, y], color=c, lw=3, solid_capstyle="round")
    ax.plot(irr, y, "o", color=c, markersize=9)
    ax.annotate(f"x{irr:.2f}", (hi, y), textcoords="offset points",
                xytext=(10, -4), fontsize=11, fontweight="bold", color=c)
ax.axvline(1.0, color="#555555", ls="--", lw=1)
ax.set_yticks(list(ys), [r[0] for r in ROWS], fontsize=11)
ax.set_xscale("log")
ticks = [0.6, 0.8, 1.0, 1.5, 2, 3, 4]
ax.set_xticks(ticks, [f"{t:g}x" for t in ticks], fontsize=10)
ax.set_xlim(0.55, 5.2)
ax.set_xlabel("Effect on expected severe crashes, holding all other features equal",
              fontsize=11)
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.13, 0.015,
         "* pedestrian-exposure proxy (sidewalks mark where people walk), "
         "not a design harm (Section 5.6). Grey and red rows are adjustment\n"
         "covariates (Table 1, Panel B) with no causal reading; all rows are "
         "conditional associations used for prediction.",
         fontsize=8.5, style="italic", color="#444444")
fig.tight_layout(rect=(0, 0.05, 1, 1))
out = cfg.REPORTS / "irr_forest.png"
fig.savefig(out, dpi=250, bbox_inches="tight")
print(f"wrote {out}")
