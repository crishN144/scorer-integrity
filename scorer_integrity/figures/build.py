"""Build the repository figures from the saved run artefacts.

Reproducible: reads only `logs/*.json`, makes no model calls, and is invoked by
`make figures`. Style is derived from Apollo's own published figures -- see
`scorer_integrity/figures/style.py` for the source recon.

Usage:
    python -m scorer_integrity.figures.build
"""

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from scorer_integrity.figures.style import (
    BLUE_LIGHT,
    BLUE_MID,
    BLUE_NAVY,
    GREY_LINE,
    GREY_TEXT,
    INK,
    apply_style,
    footer,
    save,
    strip_spines,
)
from scorer_integrity.metrics import wilson_interval

LOGS = Path("logs")
OUT = Path("figures")

PROVENANCE = (
    "Subject claude-haiku-4-5 · judge claude-sonnet-4-6 (rubric verbatim) · "
    "inspect_ai 0.3.260 · inspect-evals 0.18.0 · 2026-08-25"
)


def _load(name: str) -> dict[str, Any]:
    with open(LOGS / name) as f:
        data: dict[str, Any] = json.load(f)
    return data


def _short(condition: dict[str, Any]) -> str:
    """Compact axis label for one condition."""
    urgency = "replace" if condition["urgency_type"] == "replacement" else "no-threat"
    if condition["goal_type"] == "none":
        urgency = "no-goal"
    if condition["extra_system_instructions"]:
        urgency = f"replace+{condition['extra_system_instructions']}"
    return f"{condition['scenario']}\n{urgency}"


def fig1_fp_by_condition() -> None:
    """FP rate per condition with 95% Wilson intervals, control arms marked.

    Drawn as a horizontal interval plot rather than bars. Every point estimate is
    exactly zero, so bars would be invisible and the whiskers would carry all the
    information while looking like an error. The interval *is* the result here,
    so it gets the ink, and the differing denominators stay visible.
    """
    rescored = _load("phase1_rescored.json")
    conditions = rescored["per_condition_corrected"]

    rows: list[tuple[str, float, float, int, bool]] = []
    for entry in conditions:
        cells = entry["cells"]
        no_action = cells["fp"] + cells["tn"]
        _, hi = wilson_interval(cells["fp"], no_action)
        rows.append(
            (
                _short(entry["condition"]).replace("\n", "  "),
                cells["fp"] / no_action if no_action else 0.0,
                hi,
                no_action,
                entry["condition"]["control_arm"],
            )
        )

    pooled = rescored["corrected"]
    pooled_hi = pooled["fp_rate_ci_hi"]
    n_rows = len(rows)

    fig = plt.figure(figsize=(9.2, 4.9))
    ax = fig.add_axes((0.19, 0.30, 0.68, 0.56))
    y = np.arange(n_rows)[::-1]

    for yi, (_, rate, hi, n, control) in zip(y, rows, strict=True):
        colour = BLUE_LIGHT if control else BLUE_NAVY
        ax.plot([rate, hi], [yi, yi], color=colour, lw=5.0, solid_capstyle="butt", zorder=3)
        ax.plot([hi, hi], [yi - 0.17, yi + 0.17], color=INK, lw=1.2, zorder=4)
        ax.plot([rate], [yi], marker="o", ms=5.0, color=INK, zorder=5)
        ax.annotate(
            f"n={n}",
            xy=(hi, yi),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=7.0,
            color=GREY_TEXT,
        )

    pooled_y = -1.4
    ax.plot(
        [0, pooled_hi],
        [pooled_y, pooled_y],
        color=BLUE_MID,
        lw=6.5,
        solid_capstyle="butt",
        zorder=3,
    )
    ax.plot([pooled_hi, pooled_hi], [pooled_y - 0.2, pooled_y + 0.2], color=INK, lw=1.4, zorder=4)
    ax.plot([0], [pooled_y], marker="o", ms=6.0, color=INK, zorder=5)
    ax.annotate(
        f"n={int(pooled['n_no_action'])}",
        xy=(pooled_hi, pooled_y),
        xytext=(13, 0),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=7.5,
        color=INK,
        fontweight="bold",
    )
    ax.axhline(-0.7, color=GREY_LINE, lw=0.8, ls=(0, (2, 2)), zorder=2)

    ax.set_yticks(list(y) + [pooled_y])
    ax.set_yticklabels([r[0] for r in rows] + ["POOLED"])
    for label, (_, _, _, _, control) in zip(ax.get_yticklabels()[:n_rows], rows, strict=True):
        label.set_color(GREY_TEXT if control else INK)
    ax.get_yticklabels()[-1].set_fontweight("bold")
    ax.get_yticklabels()[-1].set_color(INK)

    ax.set_xlim(0, max(r[2] for r in rows) * 1.22)
    ax.set_ylim(pooled_y - 0.9, n_rows - 0.4)
    ax.set_xlabel("False-positive rate  (judge fires | oracle says no operative action)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.1%}")
    ax.set_title(
        "Zero false positives in every condition; the bar is the 95% Wilson upper bound",
        loc="left",
        pad=12,
    )
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    strip_spines(ax)

    handles = [
        plt.Line2D([0], [0], color=BLUE_NAVY, lw=5),
        plt.Line2D([0], [0], color=BLUE_LIGHT, lw=5),
        plt.Line2D([0], [0], color=INK, marker="o", ms=5, lw=0),
    ]
    # Below the axes: the bars span the full width, so any in-plot legend
    # occludes data.
    ax.legend(
        handles,
        ["Pressure condition", "Control arm", "Point estimate (all 0.000)"],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=3,
        frameon=False,
    )
    footer(fig, PROVENANCE)
    save(fig, str(OUT / "fig1_fp_by_condition.svg"))


def fig2_positive_control() -> None:
    """Judge sensitivity by style plus hard-negative specificity. Synthetic.

    Same horizontal-interval idiom as fig1, for the same reason: every point
    estimate sits on a boundary (1.000 here, 0.000 there), so bars carry no
    information and the interval is the result. Keeping one idiom across the
    figures also means a reader learns to read them once.
    """
    control = _load("positive_control_summary.json")
    records = control["records"]

    order = ["blatant", "subtle", "euphemistic", "buried", "draft_issue_case"]
    pretty = {
        "blatant": "Blatant coercion",
        "subtle": "Subtle / deniable",
        "euphemistic": "Euphemistic, no threat words",
        "buried": "Buried in routine output",
        "draft_issue_case": "No keywords (the issue case)",
    }
    rows: list[tuple[str, float, float, int, bool]] = []
    for style in order:
        subset = [r for r in records if r["style"] == style]
        caught = sum(1 for r in subset if r["judge"])
        lo, _ = wilson_interval(caught, len(subset))
        rows.append((pretty[style], caught / len(subset), lo, len(subset), False))

    negatives = [r for r in records if not r["expected_action"]]
    quiet = sum(1 for r in negatives if not r["judge"])
    lo_n, _ = wilson_interval(quiet, len(negatives))
    rows.append(
        ("Hard negatives (specificity)", quiet / len(negatives), lo_n, len(negatives), True)
    )

    positives = [r for r in records if r["expected_action"]]
    caught_all = sum(1 for r in positives if r["judge"])
    pooled_lo, _ = wilson_interval(caught_all, len(positives))

    fig = plt.figure(figsize=(9.2, 4.6))
    ax = fig.add_axes((0.28, 0.22, 0.69, 0.60))
    y = np.arange(len(rows))[::-1]

    for yi, (_, rate, lo, n, is_spec) in zip(y, rows, strict=True):
        colour = BLUE_NAVY if is_spec else BLUE_MID
        ax.plot([lo, rate], [yi, yi], color=colour, lw=5.0, solid_capstyle="butt", zorder=3)
        ax.plot([lo, lo], [yi - 0.17, yi + 0.17], color=INK, lw=1.2, zorder=4)
        ax.plot([rate], [yi], marker="o", ms=5.0, color=INK, zorder=5)
        ax.annotate(
            f"n={n}",
            xy=(lo, yi),
            xytext=(-7, 0),
            textcoords="offset points",
            va="center",
            ha="right",
            fontsize=7.0,
            color=GREY_TEXT,
        )

    pooled_y = -1.4
    ax.plot(
        [pooled_lo, 1.0],
        [pooled_y, pooled_y],
        color=BLUE_MID,
        lw=6.5,
        solid_capstyle="butt",
        zorder=3,
    )
    ax.plot([pooled_lo, pooled_lo], [pooled_y - 0.2, pooled_y + 0.2], color=INK, lw=1.4, zorder=4)
    ax.plot([1.0], [pooled_y], marker="o", ms=6.0, color=INK, zorder=5)
    ax.annotate(
        f"n={len(positives)}",
        xy=(pooled_lo, pooled_y),
        xytext=(-13, 0),
        textcoords="offset points",
        va="center",
        ha="right",
        fontsize=7.5,
        color=INK,
        fontweight="bold",
    )
    ax.axhline(-0.7, color=GREY_LINE, lw=0.8, ls=(0, (2, 2)), zorder=2)

    ax.set_yticks(list(y) + [pooled_y])
    ax.set_yticklabels([r[0] for r in rows] + ["ALL POSITIVES"])
    ax.get_yticklabels()[-1].set_fontweight("bold")

    ax.set_xlim(0.30, 1.035)
    ax.set_ylim(pooled_y - 0.9, len(rows) - 0.4)
    ax.set_xlabel("Detection rate  (95% Wilson interval; every point estimate is 1.000)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title(
        "The judge caught every synthetic positive, in every phrasing style",
        loc="left",
        pad=30,
    )
    ax.annotate(
        "SYNTHETIC / OFF-POLICY — hand-written transcripts. Characterises the judge only;\n"
        "says nothing about how often any model schemes.",
        xy=(0, 1),
        xycoords="axes fraction",
        xytext=(0, 8),
        textcoords="offset points",
        fontsize=7.4,
        color=INK,
        fontweight="bold",
        va="bottom",
    )
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    strip_spines(ax)
    footer(
        fig,
        "Judge claude-sonnet-4-6, rubric verbatim · 20 positives, 5 hard negatives · "
        "wide intervals reflect small n by design · 2026-08-25",
    )
    save(fig, str(OUT / "fig2_positive_control.svg"))


def fig3_judge_comparison() -> None:
    """Two judges side by side: identical on-policy, one synthetic difference.

    The right panel is an agreement bar rather than two zero-height columns --
    plotting "0 and 0" as bars shows nothing, whereas the agreement count is the
    result. Layout uses an explicit gridspec with a reserved bottom margin so the
    legend, the per-style denominators and the provenance line cannot collide.
    """
    incumbent = _load("positive_control_summary.json")["records"]
    challenger_data = _load("multijudge_claude-haiku-4-5.json")
    challenger = challenger_data["records"]["synthetic"]

    order = ["blatant", "subtle", "euphemistic", "buried", "draft_issue_case"]
    pretty = {
        "blatant": "Blatant",
        "subtle": "Subtle",
        "euphemistic": "Euphemistic",
        "buried": "Buried",
        "draft_issue_case": "No keywords",
    }
    inc_vals, chal_vals, ns = [], [], []
    for style in order:
        a = [r for r in incumbent if r["style"] == style]
        b = [r for r in challenger if r["style"] == style]
        inc_vals.append(sum(1 for r in a if r["judge"]) / len(a))
        chal_vals.append(sum(1 for r in b if r["new_judge"]) / len(b))
        ns.append(len(a))

    x = np.arange(len(order))
    width = 0.34
    fig = plt.figure(figsize=(10.4, 4.3))
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.45, 1],
        wspace=0.30,
        left=0.07,
        right=0.985,
        top=0.80,
        bottom=0.26,
    )
    ax_l = fig.add_subplot(gs[0, 0])
    ax_r = fig.add_subplot(gs[0, 1])

    ax_l.bar(x - width / 2, inc_vals, width, color=BLUE_NAVY, label="sonnet-4-6", zorder=3)
    ax_l.bar(x + width / 2, chal_vals, width, color=BLUE_LIGHT, label="haiku-4-5", zorder=3)
    for xi, n in zip(x, ns, strict=True):
        ax_l.annotate(
            f"n={n}",
            xy=(float(xi), 0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -15),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=6.5,
            color=GREY_TEXT,
        )
    ax_l.set_xticks(x)
    ax_l.set_xticklabels([pretty[s] for s in order])
    ax_l.set_ylabel("Sensitivity")
    ax_l.set_ylim(0, 1.16)
    ax_l.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax_l.set_title("Synthetic sensitivity by style  (OFF-POLICY)", loc="left", pad=8)
    strip_spines(ax_l)
    # Above the axes, right-aligned: the panel title is left-aligned, the bars
    # span the full plot from 0 to 1.0, and there is no in-plot whitespace an
    # legend could occupy without covering data.
    ax_l.legend(
        loc="lower right",
        bbox_to_anchor=(1.0, 1.0),
        ncol=2,
        frameon=False,
        fontsize=7.2,
        handlelength=1.4,
        columnspacing=1.4,
        borderaxespad=0.2,
    )

    miss = order.index("euphemistic")
    ax_l.annotate(
        "19/20",
        xy=(miss + width / 2, chal_vals[miss]),
        xytext=(0, 5),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color=INK,
        fontweight="bold",
    )

    on_policy = challenger_data["on_policy"]
    total = int(on_policy["n_no_action"] + on_policy["n_action"])
    agree = total - int(on_policy["disagreements"])
    ax_r.barh([0], [agree], height=0.22, color=BLUE_NAVY, zorder=3)
    ax_r.barh([0], [total - agree], left=[agree], height=0.22, color="#E23D28", zorder=3)
    ax_r.set_xlim(0, total * 1.02)
    ax_r.set_ylim(-0.5, 0.5)
    ax_r.set_yticks([])
    ax_r.set_title("Verdict agreement, same transcripts", loc="left", pad=8)
    ax_r.grid(axis="x", zorder=0)
    ax_r.grid(axis="y", visible=False)
    strip_spines(ax_r, keep=("bottom",))
    ax_r.annotate(
        f"{agree} / {total} identical verdicts",
        xy=(agree / 2, 0),
        ha="center",
        va="center",
        fontsize=8.5,
        color="#FFFFFF",
        fontweight="bold",
    )
    ax_r.annotate(
        f"{total - agree} disagreements. Both judges raised 0 false\n"
        f"positives on the {int(on_policy['n_no_action'])} no-action transcripts.",
        xy=(0, 0),
        xycoords="axes fraction",
        xytext=(0, -34),
        textcoords="offset points",
        ha="left",
        va="top",
        fontsize=7.2,
        color=GREY_TEXT,
    )

    fig.suptitle(
        "A judge one tier cheaper produced identical on-policy output",
        x=0.02,
        y=0.955,
        ha="left",
        fontsize=10.5,
        fontweight="bold",
    )
    fig.text(
        0.02,
        0.085,
        "The only disagreement in the whole comparison is attachment-implied coercion, "
        "missed by haiku-4-5.",
        fontsize=7.2,
        color=INK,
        ha="left",
        va="top",
    )
    fig.text(
        0.02,
        0.030,
        "Same 600 stored transcripts, same rubric verbatim, judge-side calls only"
        "  ·  left panel is SYNTHETIC / OFF-POLICY  ·  2026-08-25",
        fontsize=6.4,
        color=GREY_TEXT,
        ha="left",
        va="top",
    )
    # bbox="tight" would undo the reserved margins above, so save as laid out.
    fig.savefig(str(OUT / "fig3_judge_comparison.svg"), format="svg", bbox_inches=None)
    plt.close(fig)


def main() -> None:
    """Build every figure."""
    apply_style()
    OUT.mkdir(exist_ok=True)
    fig1_fp_by_condition()
    fig2_positive_control()
    fig3_judge_comparison()
    print(f"wrote {len(list(OUT.glob('*.svg')))} figures to {OUT}/")


if __name__ == "__main__":
    main()
