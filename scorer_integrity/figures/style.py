"""Figure style, derived from Apollo Research's own published figures."""

# ---------------------------------------------------------------------------
# SOURCE RECON -- parameters extracted, not guessed
#
# Sources read (2026-08-25):
#   [1] Meinke, Schoen, Scheurer, Balesni, Shah, Hobbhahn, "Frontier Models are
#       Capable of In-context Scheming", arXiv:2412.04984v2. Bar figure p9,
#       line figures p33. Colours sampled from the rendered PDF at 110-400 dpi.
#   [2] apolloresearch.ai blog (PBC announcement) -- web register.
#   [3] Paper title page [1] p1 -- wordmark and document register.
#
# WHAT THEY ACTUALLY DO
#
#   Palette          Monochromatic BLUE RAMP, three steps, sampled exactly:
#                      #99CCFF light   (series 1)
#                      #0080FF mid     (series 2)
#                      #003D80 navy    (series 3)
#                    No categorical rainbow. No red/green. Series identity is
#                    carried by lightness, so it survives greyscale printing.
#   Background       Pure #FFFFFF, both figure and axes. No tinted panels.
#   Gridlines        Horizontal only, DASHED, very light grey, drawn under the
#                    data. No vertical gridlines on bar charts.
#   Spines           Bar charts: left + bottom only, near-black, ~1.2pt.
#                    Line charts: full light-grey box.
#   Error bars       Black, capped (T-bar), thin (~1.2pt), cap ~3pt. Drawn on
#                    top of the bar, not recoloured to match the series.
#   ⭐ n annotation  Sample size printed INSIDE each bar, ROTATED 90 degrees,
#                    small, dark, near the bar's inner edge: "n=320", "n=1920".
#                    This is their most distinctive habit and it is a good one --
#                    the reader never has to hunt the caption for the denominator.
#   Legend           Boxed, thin light-grey border, white fill, rounded corners.
#                    Inside the axes (upper left) when there is room; above the
#                    axes, horizontal, for multi-panel line figures. Titled when
#                    the series need a category name ("Evaluation Types").
#   Second encoding  Solid vs DASHED linestyle carries a second dimension
#                    (e.g. TP vs FP) rather than a second hue.
#   Typography       Sans-serif throughout the figures (paper body is serif).
#                    Small: tick labels ~7pt, axis labels ~8pt, titles ~9pt bold.
#   Panel titles     Bold, centred, directly above the axes.
#   Tone             Restrained, academic, high whitespace. No shadows, no
#                    gradients, no 3D, no chartjunk, no logos inside plots.
# ---------------------------------------------------------------------------

from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt

# Sampled from arXiv:2412.04984 figures.
BLUE_LIGHT = "#99CCFF"
BLUE_MID = "#0080FF"
BLUE_NAVY = "#003D80"

# Extensions of the same ramp, for arms that need a fourth/fifth step or a
# deliberately de-emphasised series. Kept inside the same hue family.
BLUE_PALE = "#D6E9FF"
BLUE_DEEP = "#00264F"

INK = "#111111"
GREY_TEXT = "#4A4A4A"
GREY_LINE = "#BFBFBF"
GREY_GRID = "#DDDDDD"

SERIES = (BLUE_LIGHT, BLUE_MID, BLUE_NAVY, BLUE_PALE, BLUE_DEEP)


def apply_style() -> None:
    """Install the Apollo-derived rcParams globally.

    Call once before building figures. Font family falls back gracefully: the
    named faces match the register of Apollo's figures and site, and DejaVu Sans
    is the matplotlib default that will always be present.
    """
    mpl.rcParams.update(
        {
            "figure.facecolor": "#FFFFFF",
            "axes.facecolor": "#FFFFFF",
            "savefig.facecolor": "#FFFFFF",
            "savefig.bbox": "tight",
            "svg.fonttype": "none",  # keep text as text in the SVG
            "font.family": "sans-serif",
            "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 8.0,
            "axes.titlesize": 9.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 8.5,
            "axes.labelcolor": GREY_TEXT,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "xtick.color": GREY_TEXT,
            "ytick.color": GREY_TEXT,
            "xtick.major.size": 0.0,  # Apollo show no tick marks
            "ytick.major.size": 3.0,
            "xtick.major.pad": 5.0,
            "axes.edgecolor": INK,
            "axes.linewidth": 1.1,
            "axes.grid": True,
            "axes.grid.axis": "y",  # horizontal only
            "grid.color": GREY_GRID,
            "grid.linestyle": (0, (3, 3)),  # dashed
            "grid.linewidth": 0.7,
            "grid.alpha": 1.0,
            "axes.axisbelow": True,
            "legend.frameon": True,
            "legend.facecolor": "#FFFFFF",
            "legend.edgecolor": GREY_LINE,
            "legend.framealpha": 1.0,
            "legend.fontsize": 7.5,
            "legend.title_fontsize": 8.0,
            "legend.borderpad": 0.6,
            "legend.fancybox": True,
            "lines.linewidth": 1.8,
            "errorbar.capsize": 3.0,
        }
    )


def strip_spines(ax: Any, keep: tuple[str, ...] = ("left", "bottom")) -> None:
    """Remove all spines except `keep`, following the bar-figure treatment.

    Args:
        ax: The axes to modify.
        keep: Spine names to retain.
    """
    for name, spine in ax.spines.items():
        spine.set_visible(name in keep)


def annotate_n(ax: Any, x: float, n: int, colour: str = INK) -> None:
    """Print the sample size inside a bar, rotated, as Apollo's figures do.

    Anchored at the axes bottom so it reads identically whether the bar is tall
    or flat against zero -- which matters here, where most bars are zero.

    Args:
        ax: The axes.
        x: Bar centre in data coordinates.
        n: Sample size.
        colour: Text colour.
    """
    ax.annotate(
        f"n={n}",
        xy=(x, 0),
        xycoords=("data", "axes fraction"),
        xytext=(0, 6),
        textcoords="offset points",
        rotation=90,
        ha="center",
        va="bottom",
        fontsize=6.5,
        color=colour,
    )


def footer(fig: Any, text: str) -> None:
    """Add a small provenance line under the figure.

    Args:
        fig: The figure.
        text: Provenance text (models, versions, date).
    """
    fig.text(0.0, -0.17, text, fontsize=6.2, color=GREY_TEXT, ha="left", va="top")


def save(fig: Any, path: str) -> None:
    """Write the figure as SVG and close it.

    Args:
        fig: The figure.
        path: Destination path.
    """
    fig.savefig(path, format="svg")
    plt.close(fig)
