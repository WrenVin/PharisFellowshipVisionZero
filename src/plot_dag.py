"""Publication-grade render of the pre-registered causal DAG (paper Figure 1).

reports/dag.txt (dagitty format, pasteable at dagitty.net) remains the source
of truth: this script parses its node roles and edge list, so the published
figure and the verifiable specification cannot diverge. Only the layout is
redefined here (the dagitty browser render's scattered coordinates and small
labels were flagged by review as unreadable in print).

Outputs: reports/dag.png (copy into the paper's figures/ directory)
"""

import re
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

import config as cfg

NAVY, GOLD, RED, TAN, GREY = "#13385E", "#C5A55A", "#8C2D2D", "#F2E9D4", "#D9D9D9"

# --- parse dag.txt ----------------------------------------------------------
src = (cfg.REPORTS / "dag.txt").read_text()
roles, edges = {}, []
for line in src.splitlines():
    line = line.strip()
    m = re.match(r'^"([^"]+)"\s*\[([^\]]*)\]', line)
    if m:
        roles[m.group(1)] = m.group(2)
        continue
    m = re.match(r'^"([^"]+)"\s*(<->|->)\s*"([^"]+)"', line)
    if m:
        edges.append((m.group(1), m.group(3), m.group(2)))

# --- layered layout (published-DAG convention: causes left, mediators
# center, outcomes right; long edges ride dedicated top/bottom lanes).
# Segment length (the model offset) is stated in the caption, not drawn.
POS = {
    # rank 0: exogenous context
    "Land use":                                     (1.0, 9.3),
    "Zero-car households":                          (1.0, 7.9),
    "Population density":                           (1.0, 6.5),
    "Neighborhood income & poverty":                (1.0, 5.0),
    # rank 1: planning and exposure
    "Functional class (arterial / collector / local)": (3.45, 8.0),
    "Traffic volume (ADT)":                         (3.45, 5.4),
    # rank 2: measured design features
    "Sidewalk presence":                            (5.85, 9.0),
    "Lanes":                                        (5.85, 8.15),
    "Posted speed limit":                           (5.85, 7.3),
    "Median type":                                  (5.85, 6.45),
    "One-way operation":                            (5.85, 5.6),
    "Signals & intersection density":               (5.85, 4.6),
    # rank 3: composite exposure
    "Road design":                                  (7.9, 6.4),
    # rank 4: mediators
    "Pedestrian exposure":                          (9.55, 9.0),
    "Operating speed (85th pct)":                   (9.55, 3.7),
    # rank 5: outcomes and measurement
    "Severe crashes (true)":                        (10.85, 6.4),
    "Police reporting":                             (12.6, 8.8),
    "Severe crashes (recorded)":                    (13.0, 6.4),
}
SHORT = {"Functional class (arterial / collector / local)": "Functional class\n(arterial / collector / local)",
         "Signals & intersection density": "Signals &\nintersection density",
         "Neighborhood income & poverty": "Neighborhood\nincome & poverty",
         "Operating speed (85th pct)": "Operating speed\n(85th percentile)",
         "Severe crashes (true)": "Severe crashes\n(true)",
         "Severe crashes (recorded)": "Severe crashes\n(recorded)"}

CURVE = {  # long edges ride the top or bottom lane
    ("Land use", "Pedestrian exposure"): -0.13,          # top lane
    ("Zero-car households", "Pedestrian exposure"): -0.30,
    ("Population density", "Pedestrian exposure"): -0.44,
    ("Neighborhood income & poverty", "Sidewalk presence"): -0.04,
    ("Neighborhood income & poverty", "Police reporting"): 0.34,   # bottom lane
    ("Neighborhood income & poverty", "Severe crashes (true)"): 0.30,
    ("Traffic volume (ADT)", "Severe crashes (true)"): 0.28,
    ("Functional class (arterial / collector / local)", "Road design"): 0.35,
    ("Population density", "Traffic volume (ADT)"): 0.0,
    ("Land use", "Traffic volume (ADT)"): 0.10,
    ("Land use", "Functional class (arterial / collector / local)"): 0.0,
    ("Land use", "Neighborhood income & poverty"): 0.35,  # bow around the context column
}
SKIP = {"Segment length"}  # model offset; stated in the caption
SPINE = {("Road design", "Severe crashes (true)"),
         ("Road design", "Operating speed (85th pct)"),
         ("Road design", "Pedestrian exposure"),
         ("Operating speed (85th pct)", "Severe crashes (true)"),
         ("Pedestrian exposure", "Severe crashes (true)")}


def style(name):
    r = roles.get(name, "")
    if "exposure" in r:
        return dict(fc=NAVY, ec=NAVY, tc="white", ls="-", lw=1.4, bold=True)
    if "outcome" in r:
        return dict(fc=RED, ec=RED, tc="white", ls="-", lw=1.4, bold=True)
    if "latent" in r:
        return dict(fc=GREY, ec="#777777", tc="#333333", ls="--", lw=1.1, bold=False)
    if "adjusted" in r:
        return dict(fc=TAN, ec=GOLD, tc="#222222", ls="-", lw=1.2, bold=False)
    if name == "Operating speed (85th pct)":
        return dict(fc="white", ec=RED, tc="#222222", ls="--", lw=1.4, bold=False)
    return dict(fc="white", ec=NAVY, tc="#222222", ls="-", lw=1.1, bold=False)


fig, ax = plt.subplots(figsize=(13.6, 7.2))
fig.patch.set_facecolor("white")
ax.set_xlim(0, 14.1)
ax.set_ylim(1.2, 10.2)
ax.axis("off")

anns = {}
for name, (x, y) in POS.items():
    s = style(name)
    anns[name] = ax.annotate(
        SHORT.get(name, name), (x, y), ha="center", va="center",
        fontsize=11.5, color=s["tc"], fontweight="bold" if s["bold"] else "normal",
        zorder=3,
        bbox=dict(boxstyle="round,pad=0.42", fc=s["fc"], ec=s["ec"],
                  ls=s["ls"], lw=s["lw"]))
fig.canvas.draw()

for a, b, kind in edges:
    if a in SKIP or b in SKIP:
        continue
    spine = (a, b) in SPINE
    rad = CURVE.get((a, b), 0.0)
    arrow = FancyArrowPatch(
        POS[a], POS[b],
        connectionstyle=f"arc3,rad={rad}",
        arrowstyle="<|-|>" if kind == "<->" else "-|>",
        mutation_scale=15,
        linestyle="--" if kind == "<->" else "-",
        color=NAVY if spine else "#8A8A8A",
        lw=2.2 if spine else 1.1,
        patchA=anns[a].get_bbox_patch(), patchB=anns[b].get_bbox_patch(),
        shrinkA=2, shrinkB=2, zorder=2)
    ax.add_patch(arrow)

legend_items = [
    ("Composite exposure", "white", dict(fc=NAVY, ec=NAVY)),
    ("Outcome (recorded)", "white", dict(fc=RED, ec=RED)),
    ("Adjusted covariate", "#222222", dict(fc=TAN, ec=GOLD)),
    ("Unmeasured (latent)", "#222222", dict(fc=GREY, ec="#777777", ls="--")),
    ("Measured design feature", "#222222", dict(fc="white", ec=NAVY)),
    ("Mediator, deliberately excluded", "#222222", dict(fc="white", ec=RED, ls="--")),
]
x0, y0 = 7.9, 2.5
for i, (label, tc, box) in enumerate(legend_items):
    col = i // 3
    row = i % 3
    ax.annotate(label, (x0 + col * 2.6, y0 - row * 0.5), fontsize=9,
                ha="left", va="center", color=tc, zorder=4,
                bbox=dict(boxstyle="round,pad=0.28", lw=1.1, **box))

out = cfg.REPORTS / "dag.png"
fig.tight_layout()
fig.savefig(out, dpi=250, bbox_inches="tight", facecolor="white")
print(f"wrote {out}")
