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

# --- deliberate layout (x, y in 0..10) --------------------------------------
POS = {
    "Sidewalk presence":                            (0.95, 7.0),
    "Lanes":                                        (0.95, 5.9),
    "Posted speed limit":                           (0.95, 4.8),
    "Median type":                                  (0.95, 3.7),
    "One-way operation":                            (0.95, 2.6),
    "Signals & intersection density":               (0.95, 1.5),
    "Road design":                                  (3.35, 4.3),
    "Functional class (arterial / collector / local)": (1.55, 8.9),
    "Traffic volume (ADT)":                         (4.05, 8.9),
    "Land use":                                     (5.05, 9.6),
    "Neighborhood income & poverty":                (6.55, 8.35),
    "Population density":                           (8.15, 9.55),
    "Zero-car households":                          (9.25, 8.5),
    "Pedestrian exposure":                          (6.45, 6.2),
    "Operating speed (85th pct)":                   (5.25, 2.7),
    "Segment length":                               (4.65, 0.9),
    "Severe crashes (true)":                        (7.75, 4.3),
    "Severe crashes (recorded)":                    (9.5, 4.3),
    "Police reporting":                             (9.3, 6.5),
}
SHORT = {"Functional class (arterial / collector / local)": "Functional class\n(arterial / collector / local)",
         "Signals & intersection density": "Signals &\nintersection density",
         "Neighborhood income & poverty": "Neighborhood\nincome & poverty",
         "Operating speed (85th pct)": "Operating speed\n(85th percentile)",
         "Severe crashes (true)": "Severe crashes\n(true)",
         "Severe crashes (recorded)": "Severe crashes\n(recorded)"}

CURVE = {  # gentle arcs for long or crossing edges
    ("Land use", "Functional class (arterial / collector / local)"): 0.25,
    ("Neighborhood income & poverty", "Functional class (arterial / collector / local)"): 0.35,
    ("Land use", "Pedestrian exposure"): 0.0,
    ("Neighborhood income & poverty", "Sidewalk presence"): 0.22,
    ("Population density", "Traffic volume (ADT)"): -0.15,
    ("Neighborhood income & poverty", "Severe crashes (true)"): -0.12,
    ("Traffic volume (ADT)", "Severe crashes (true)"): -0.15,
    ("Neighborhood income & poverty", "Police reporting"): -0.15,
    ("Functional class (arterial / collector / local)", "Segment length"): 0.30,
    ("Segment length", "Severe crashes (true)"): -0.15,
}
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


fig, ax = plt.subplots(figsize=(12.2, 7.4))
fig.patch.set_facecolor("white")
ax.set_xlim(0, 10.4)
ax.set_ylim(0, 10.3)
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
x0, y0 = 6.55, 1.55
for i, (label, tc, box) in enumerate(legend_items):
    col = i // 3
    row = i % 3
    ax.annotate(label, (x0 + col * 2.0, y0 - row * 0.52), fontsize=9,
                ha="left", va="center", color=tc, zorder=4,
                bbox=dict(boxstyle="round,pad=0.28", lw=1.1, **box))

out = cfg.REPORTS / "dag.png"
fig.tight_layout()
fig.savefig(out, dpi=250, bbox_inches="tight", facecolor="white")
print(f"wrote {out}")
