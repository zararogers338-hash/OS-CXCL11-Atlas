"""Figure 1 -- study design (a) and the three-compartment CXCL11 hypothesis (b).

    python py/F_fig1_study_design.py

Hand-built vector schematic in the Marrow visual system (no generative imagery).
Sample sizes are read from results/stats.json; cohorts not yet verified carry no n.
Output: results/figures/fig1_study_design.{pdf,tiff,png}  (180 mm wide)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

sys.path.insert(0, str(Path(__file__).parent))
from os_style import PALETTE, save_figure, use_style  # noqa: E402

W, H = 180.0, 120.0  # mm
INK, INK2, AXIS, GRID = (PALETTE["ink"][k] for k in ("primary", "secondary", "axis", "grid"))
E = PALETTE["entity"]
IVORY, PANEL = PALETTE["surfaces"]["page"], PALETTE["surfaces"]["panel"]
FS = 7  # every label >= 7 pt


def stat(key: str) -> str | None:
    p = Path("results/stats.json")
    stats = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return stats.get(key, {}).get("display")


def box(ax, x, y, w, h, *, fc="white", ec=AXIS, lw=0.5, r=1.2, ls="-", z=1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))


def text(ax, x, y, s, *, size=FS, weight="normal", color=INK, ha="center", va="center", z=5, **kw):
    ax.text(x, y, s, fontsize=size, fontweight=weight, color=color, ha=ha, va=va, zorder=z, **kw)


def lines(ax, x, y_top, rows, *, step=3.0, first_bold=True, color=INK2):
    for i, s in enumerate(rows):
        text(ax, x, y_top - i * step, s, weight="bold" if (first_bold and i == 0) else "normal",
             color=INK if (first_bold and i == 0) else color)


def arrow(ax, x1, y1, x2, y2, *, color=AXIS, lw=0.6, ms=5, z=2, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=ms,
                                 color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0))


def receptor(ax, x, y, angle_deg, color, size=1.4, lw=0.7, z=6):
    """Y-shaped receptor: stem pointing along angle, two arms at the tip."""
    a = np.deg2rad(angle_deg)
    tip = (x + size * np.cos(a), y + size * np.sin(a))
    ax.plot([x, tip[0]], [y, tip[1]], color=color, lw=lw, solid_capstyle="round", zorder=z)
    for d in (35, -35):
        b = a + np.deg2rad(d)
        ax.plot([tip[0], tip[0] + 0.75 * size * np.cos(b)], [tip[1], tip[1] + 0.75 * size * np.sin(b)],
                color=color, lw=lw, solid_capstyle="round", zorder=z)


def panel_a(ax):
    text(ax, 1.5, 116.5, "a", size=9, weight="bold", ha="left")
    text(ax, 6, 116.5, "Study design: four parallel tracks converge", size=8, weight="bold", ha="left")
    xs, w = [2, 27, 52, 77], 23

    # Row 1 -- public data
    n_target = stat("target_n_primary")
    sources = [
        ["Bulk RNA", "TARGET-OS", f"n = {n_target}" if n_target else "", "+ GEO cohorts (planned)"],
        ["Single-cell", "GSE152048", "GSE162454"],
        ["ICB cohorts", "4 pan-cancer", "transfer only"],
        ["Cell lines/drugs", "DepMap", "GDSC2"],
    ]
    for x, rows in zip(xs, sources):
        box(ax, x, 95, w, 15, fc=PANEL, ec=PANEL)
        rows = [r for r in rows if r]
        lines(ax, x + w / 2, 106.2 if len(rows) < 4 else 107.3, rows, step=3.0 if len(rows) < 4 else 2.9)
    text(ax, 51, 92.2, "public data only", color=INK2, style="italic")

    # Bus to tracks
    ax.plot([13.5, 88.5], [89.5, 89.5], color=AXIS, lw=0.6, zorder=2)
    ax.plot([51, 51], [91, 89.5], color=AXIS, lw=0.6, zorder=2)
    for x in xs:
        arrow(ax, x + w / 2, 89.5, x + w / 2, 86.2)

    # Row 2 -- tracks
    tracks = [
        ("A", "Clinical", ["OS/EFS, metastasis", "Chemo response", "Nomogram"]),
        ("B", "Molecular", ["IFN-γ → STAT1", "CXCR3 vs ACKR3", "Pathways (GSEA)"]),
        ("C", "TME", ["Deconvolution", "Single-cell map", "Cell–cell signalling"]),
        ("D", "Immunotherapy", ["TIDE / IPS", "ICB transfer", "Drug sensitivity"]),
    ]
    for x, (letter, title, rows) in zip(xs, tracks):
        box(ax, x, 64, w, 22, fc="white", ec=AXIS)
        ax.add_patch(Circle((x + 0.6, 85.4), 2.0, fc=INK, ec="white", lw=0.8, zorder=4))
        text(ax, x + 0.6, 85.35, letter, color="white", weight="bold")
        text(ax, x + w / 2, 82.4, title, weight="bold")
        for i, r in enumerate(rows):
            text(ax, x + w / 2, 77.2 - i * 3.6, r, color=INK2)

    # Bus to convergence
    for x in xs:
        ax.plot([x + w / 2, x + w / 2], [64, 61], color=AXIS, lw=0.6, zorder=2)
    ax.plot([13.5, 88.5], [61, 61], color=AXIS, lw=0.6, zorder=2)
    arrow(ax, 51, 61, 51, 57.6)

    # Row 3 -- convergence (CXCL11 accent)
    box(ax, 2, 43, 98, 14.5, fc="white", ec=E["CXCL11"], lw=0.9)
    text(ax, 51, 53.6, "Convergence: CXCL11 compartment balance", weight="bold")
    text(ax, 51, 49.7, r"ABS = $\mathregular{R_{imm}}$ − ($\mathregular{R_{tum}}$ + $\mathregular{S_{endo}}$) / 2", color=INK)
    text(ax, 51, 46.0, "modules defined in single-cell data · interpretable ML (nested CV, SHAP)", color=INK2)
    arrow(ax, 51, 43, 51, 39.6)

    # Row 4 -- outputs
    outs = [["Prognostic", "stratification"], ["Immunotherapy", "relevance"], ["Open atlas", "and pipeline"]]
    for i, rows in enumerate(outs):
        x = 2 + i * 33
        box(ax, x, 27, 32, 12, fc=PANEL, ec=PANEL)
        lines(ax, x + 16, 34.6, rows, step=3.2, first_bold=False, color=INK)

    # Open & reproducible band
    box(ax, 2, 3, 98, 19.5, fc="white", ec=AXIS, ls=(0, (3, 2)))
    text(ax, 51, 18.3, "Open and reproducible by design", weight="bold")
    text(ax, 51, 14.2, "one-command Snakemake pipeline · fixed seeds · locked environments", color=INK2)
    text(ax, 51, 10.6, "every reported number traced to a pipeline output", color=INK2)
    text(ax, 51, 7.0, "code and atlas to be archived with a DOI on release", color=INK2)


def panel_b(ax):
    x0, x1 = 105, 178.5
    text(ax, x0, 116.5, "b", size=9, weight="bold", ha="left")
    text(ax, x0 + 4.5, 116.5, "Three-compartment hypothesis", size=8, weight="bold", ha="left")

    # Tissue field
    box(ax, x0, 33, x1 - x0, 79, fc=IVORY, ec=GRID, r=2.5)
    # Cortical bone strip with trabecular hatching
    ax.add_patch(FancyBboxPatch((x0 + 1.2, 103), x1 - x0 - 2.4, 7.6, boxstyle="round,pad=0,rounding_size=1.8",
                                fc="#e9e1d1", ec="#d3c7b0", lw=0.5, zorder=1))
    for xi in np.arange(x0 + 3, x1 - 2, 2.6):
        ax.plot([xi, xi + 2.2], [104, 109.6], color="#d3c7b0", lw=0.45, zorder=2)
    text(ax, x0 + 3.2, 100.6, "cortical bone", color=INK2, ha="left")

    # CXCL11 gradient around the producer cell
    px, py = 133.0, 73.5
    for r, a in [(17, 0.06), (12.5, 0.09), (8.5, 0.13), (5.0, 0.18)]:
        ax.add_patch(Circle((px, py), r, fc=E["CXCL11"], ec="none", alpha=a, zorder=2))
    rng = np.random.default_rng(11)
    for _ in range(60):
        rad = 4.2 + 12.5 * rng.random() ** 1.25
        th = rng.random() * 2 * np.pi
        cx, cy = px + rad * np.cos(th), py + rad * 0.9 * np.sin(th)
        in_label = (cy > 77.5 and abs(cx - px) < 7) or (cy > 82 and cx < px - 6)
        if x0 + 2 < cx < x1 - 2 and 54 < cy < 89.5 and not in_label:
            ax.add_patch(Circle((cx, cy), 0.42, fc=E["CXCL11"], ec="none", zorder=4))
    ax.add_patch(Circle((px, py), 3.3, fc="white", ec=E["CXCL11"], lw=0.9, zorder=5))
    ax.add_patch(Circle((px, py), 1.2, fc=E["CXCL11"], ec="none", zorder=6))
    text(ax, px, py + 6.0, "CXCL11", weight="bold", color=INK)
    text(ax, px - 11.5, py + 12.5, "IFN-γ", color=INK2)
    arrow(ax, px - 9.2, py + 10.6, px - 2.9, py + 3.0, color=INK2, lw=0.6, ms=5)

    # Tumour island (R_tum): CXCR3A+ tumour cells
    tx, ty = 156.5, 70.5
    ax.add_patch(Ellipse((tx, ty), 27, 19, fc="#ead8c6", ec=E["tumor_osteoblastic"], lw=0.8, zorder=3))
    cells = [(-7.5, 3.5), (-1.5, 5.5), (4.8, 4.0), (-8.0, -3.0), (-2.0, -0.5), (4.5, -2.5), (0.5, -6.2), (8.8, 0.8)]
    for dx, dy in cells:
        ax.add_patch(Circle((tx + dx, ty + dy), 2.2, fc="white", ec=E["tumor_osteoblastic"], lw=0.6, zorder=4))
    for dx, dy, ang in [(-1.5, 5.5, 125), (-7.5, 3.5, 150), (-8.0, -3.0, 190)]:
        receptor(ax, tx + dx + 2.2 * np.cos(np.deg2rad(ang)), ty + dy + 2.2 * np.sin(np.deg2rad(ang)),
                 ang, E["tumor_osteoblastic"], size=1.1, lw=0.6)
    arrow(ax, tx + 10.5, ty - 6.0, tx + 17.5, ty - 10.5, color=E["tumor_osteoblastic"], lw=0.8, ms=6, style="-|>")

    # T/NK cells (R_imm) migrating up the gradient
    tcells = [(112.5, 74.0), (114.5, 62.5), (121.5, 55.5)]
    for cx, cy in tcells:
        ax.add_patch(Circle((cx, cy), 2.4, fc="#dff1ee", ec=E["CXCR3_T"], lw=0.8, zorder=5))
        ang = np.degrees(np.arctan2(py - cy, px - cx))
        receptor(ax, cx + 2.4 * np.cos(np.deg2rad(ang)), cy + 2.4 * np.sin(np.deg2rad(ang)), ang,
                 E["CXCR3_T"], size=1.1, lw=0.6)
        ux, uy = (px - cx), (py - cy)
        n = np.hypot(ux, uy)
        arrow(ax, cx + ux / n * 5.0, cy + uy / n * 5.0, cx + ux / n * 9.2, cy + uy / n * 9.2,
              color=E["CXCR3_T"], lw=0.7, ms=5)

    # ACKR3+ vessel (S_endo) scavenging CXCL11
    vx = np.linspace(x0 + 1.5, x1 - 1.5, 200)
    vy = 47.0 + 1.6 * np.sin((vx - x0) / 9.0)
    ax.fill_between(vx, vy - 2.4, vy + 2.4, color=E["ACKR3_endothelial"], alpha=0.16, lw=0, zorder=3)
    ax.plot(vx, vy + 2.4, color=E["ACKR3_endothelial"], lw=0.8, zorder=4)
    ax.plot(vx, vy - 2.4, color=E["ACKR3_endothelial"], lw=0.8, zorder=4)
    for rx in [128, 141, 154, 167]:
        ry = 47.0 + 1.6 * np.sin((rx - x0) / 9.0) + 2.4
        receptor(ax, rx, ry, 90, E["ACKR3_endothelial"], size=1.3, lw=0.7)
        ax.add_patch(Circle((rx, ry + 2.75), 0.42, fc=E["CXCL11"], ec="none", zorder=7))

    # Compartment labels (ink text + colour key dot)
    def key(x, y, color, name, role):
        ax.add_patch(Circle((x, y), 1.1, fc=color, ec="none", zorder=7))
        text(ax, x + 2.2, y, name, ha="left", weight="bold")
        text(ax, x + 2.2, y - 3.1, role, ha="left", color=INK2)

    key(x0 + 2.2, 95.5, E["CXCR3_T"], r"$\mathregular{R_{imm}}$  CXCR3$\mathregular{^+}$ T/NK cells", "recruitment (anti-tumour)")
    key(146.5, 95.5, E["tumor_osteoblastic"], r"$\mathregular{R_{tum}}$  CXCR3A$\mathregular{^+}$", "tumour-cell migration")
    key(x0 + 2.2, 40.2, E["ACKR3_endothelial"], r"$\mathregular{S_{endo}}$  ACKR3$\mathregular{^+}$ endothelium",
        "CXCL11 scavenging")

    # Balance beam: ABS
    fx, fy = 141.75, 9.0
    ax.add_patch(Polygon([[fx - 3, fy - 4], [fx + 3, fy - 4], [fx, fy + 0.8]], closed=True, fc=INK, ec="none", zorder=4))
    ax.plot([x0 + 6, x1 - 6], [fy + 1.1, fy + 1.1], color=INK, lw=1.0, zorder=4)
    ax.add_patch(Rectangle((x0 + 7, fy + 1.4), 15, 4.6, fc=E["CXCR3_T"], ec="none", zorder=4))
    text(ax, x0 + 14.5, fy + 3.7, r"$\mathregular{R_{imm}}$", color="white", weight="bold")
    ax.add_patch(Rectangle((x1 - 33, fy + 1.4), 13, 4.6, fc=E["tumor_osteoblastic"], ec="none", zorder=4))
    text(ax, x1 - 26.5, fy + 3.7, r"$\mathregular{R_{tum}}$", color="white", weight="bold")
    ax.add_patch(Rectangle((x1 - 19.5, fy + 1.4), 13, 4.6, fc=E["ACKR3_endothelial"], ec="none", zorder=4))
    text(ax, x1 - 13, fy + 3.7, r"$\mathregular{S_{endo}}$", color="white", weight="bold")
    text(ax, fx, 26.0, "Hypothesis: a higher balance score (ABS)", color=INK)
    text(ax, fx, 22.6, "marks an immune-favourable niche", color=INK2)


def main() -> int:
    use_style()
    plt.rcParams["figure.constrained_layout.use"] = False
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    panel_a(ax)
    panel_b(ax)
    out = save_figure(fig, "results/figures/fig1_study_design", formats=("pdf", "tiff", "png"))
    print(f"-> {out}.pdf/.tiff/.png  ({W:.0f} x {H:.0f} mm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
