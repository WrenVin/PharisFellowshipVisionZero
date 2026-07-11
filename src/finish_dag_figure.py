"""Paper Figure 1: finish the dagitty.net export (trim + legend).

The author renders the DAG in dagitty (reports/dag.txt is the spec; the
export is saved as reports/dagitty_export.jpeg). This script trims the
export's whitespace and adds a legend for dagitty's color conventions.

Outputs: reports/dag.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from PIL import Image, ImageChops

import config as cfg

SRC = cfg.REPORTS / "dagitty_export.jpeg"

# dagitty's palette
EXPO = "#AECD2B"      # exposure (with black triangle)
ANC_EXPO = "#C7E06E"  # ancestor of exposure
OUTC = "#41AEE4"      # outcome (with black bar)
ANC_OUT = "#5FC0EA"   # ancestor of outcome
LATENT = "#DDDDDD"
WHITE = "#FFFFFF"

im = Image.open(SRC).convert("RGB")
bg = Image.new("RGB", im.size, (255, 255, 255))
bbox = ImageChops.difference(im, bg).getbbox()
pad = 25
im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
              min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad)))

w, h = im.size
LEG_H = 0.16  # legend fraction of image height
fig_w = 13.0
fig_h = fig_w * h / w * (1 + LEG_H)
fig = plt.figure(figsize=(fig_w, fig_h))
ax = fig.add_axes((0, LEG_H, 1, 1 - LEG_H))
ax.imshow(im)
ax.axis("off")

leg = fig.add_axes((0, 0, 1, LEG_H))
leg.set_xlim(0, 100)
leg.set_ylim(0, 10)
leg.axis("off")

items_row1 = [
    (EXPO, "▶", "Exposure: Road design"),
    (OUTC, "❘", "Outcome: recorded crashes (KSI)"),
    (ANC_EXPO, "", "Measured design feature"),
    (ANC_OUT, "", "Excluded mediator (speed)"),
]
items_row2 = [
    (LATENT, "", "Unmeasured (latent)"),
    (WHITE, "", "Adjusted covariate"),
]
xs1 = [2, 25, 52, 76]
xs2 = [2, 25]
for (color, sym, label), x in zip(items_row1, xs1):
    leg.add_patch(Ellipse((x, 7), 2.0, 3.2, facecolor=color,
                          edgecolor="#333333", lw=1.2))
    if sym:
        leg.text(x, 7, sym, ha="center", va="center", fontsize=7)
    leg.text(x + 1.6, 7, label, va="center", fontsize=11)
for (color, sym, label), x in zip(items_row2, xs2):
    leg.add_patch(Ellipse((x, 2.5), 2.0, 3.2, facecolor=color,
                          edgecolor="#333333", lw=1.2))
    leg.text(x + 1.6, 2.5, label, va="center", fontsize=11)
leg.plot([52.0, 55.0], [2.5, 2.5], color="#3AAA35", lw=2)
leg.annotate("", xy=(55.6, 2.5), xytext=(55.0, 2.5),
             arrowprops=dict(arrowstyle="-|>", color="#3AAA35", lw=2))
leg.text(56.4, 2.5, "Open causal path from exposure to outcome",
         va="center", fontsize=11)

out = cfg.REPORTS / "dag.png"
fig.savefig(out, dpi=220, facecolor="white")
print(f"wrote {out}")
