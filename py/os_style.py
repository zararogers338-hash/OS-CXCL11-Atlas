"""Marrow visual system for matplotlib/scanpy. Every colour comes from style/palette.json.

    from os_style import use_style, PALETTE, save_figure
    use_style()
    fig, ax = plt.subplots(figsize=figsize("single", 60))
    save_figure(fig, "results/figures/fig4a_umap")
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE_DIR = ROOT / "style"
PALETTE: dict = json.loads((STYLE_DIR / "palette.json").read_text(encoding="utf-8"))

MM_PER_INCH = 25.4


def figsize(width: str = "single", height_mm: float = 60) -> tuple[float, float]:
    w_mm = PALETTE["size_mm"][width]
    if height_mm > PALETTE["size_mm"]["max_height"]:
        raise ValueError(f"height {height_mm} mm exceeds journal max {PALETTE['size_mm']['max_height']} mm")
    return w_mm / MM_PER_INCH, height_mm / MM_PER_INCH


def entity_colors() -> dict[str, str]:
    return dict(PALETTE["entity"])


def use_style() -> None:
    """Apply os.mplstyle and register the Marrow colormaps (os_seq, os_div)."""
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    plt.style.use(STYLE_DIR / "os.mplstyle")
    div = PALETTE["diverging"]
    cmaps = {
        "os_seq": PALETTE["sequential"]["crimson"],
        "os_div": [*div["negative"], div["mid"], *div["positive"]],
    }
    for name, colors in cmaps.items():
        if name not in mpl.colormaps:
            mpl.colormaps.register(LinearSegmentedColormap.from_list(name, colors))


def save_figure(fig, path_no_ext: str | Path, formats: tuple[str, ...] | None = None) -> Path:
    """Save as vector PDF + 600-dpi LZW TIFF (journal-ready)."""
    path = Path(path_no_ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    for fmt in formats or PALETTE["export"]["formats"]:
        kwargs = {"pil_kwargs": {"compression": "tiff_lzw"}} if fmt == "tiff" else {}
        fig.savefig(path.with_suffix(f".{fmt}"), dpi=PALETTE["export"]["dpi"], **kwargs)
    return path
