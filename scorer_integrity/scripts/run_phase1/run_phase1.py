"""Run the Phase 1 calibration sweep.

Runs every condition in the config, aggregates the judge-vs-oracle confusion
matrix across them, prices the run from the log's own token counts, and writes a
JSON summary for RESULTS.md.

Refuses to start if the projected spend exceeds the config's ceiling.

Usage:
    python scorer_integrity/scripts/run_phase1/run_phase1.py <path/to/config.yaml>

A 20-episode pilot takes ~2 minutes and costs ~$0.30; the 600-episode run takes
~30 minutes and costs ~$9. Use `--dry-run` to project cost without calling any
model, and `--mock` to exercise the whole pipeline offline for free.
"""

import json
from pathlib import Path
from typing import Any

import fire
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

from scorer_integrity.config import Config, load_config
from scorer_integrity.cost import price_usage, project_usd
from scorer_integrity.log import logger
from scorer_integrity.metrics import wilson_interval
from scorer_integrity.tasks import calibration

# Per-episode token means MEASURED in the 2026-08-25 pilot, then scaled 1.172x on
# the input side because the pilot was blackmail-only and blackmail has the
# shortest prompts of the three scenarios (RESULTS.md §4). Used only for the
# pre-flight projection; reported cost always comes from the run's own logs.
SUBJECT_INPUT_TOKENS = 2640.0  # 2252 measured x 1.172
SUBJECT_OUTPUT_TOKENS = 712.0  # measured
GRADER_INPUT_TOKENS = 2.0  # measured: the grader prompt is served as cache-write
GRADER_CACHE_WRITE_TOKENS = 1343.0  # 1146 measured x 1.172
GRADER_OUTPUT_TOKENS = 103.0  # measured

CELL_KEYS = ("tp", "fp", "fn", "tn", "parse_failed", "n")


def _mock_model(content: str, n: int) -> Any:
    """Build a mock model with enough queued outputs for `n` episodes.

    mockllm raises `custom_outputs ran out of values` rather than repeating, so
    the queue has to be at least as long as the run.

    Args:
        content: The completion to return every time.
        n: How many outputs to queue.

    Returns:
        A mockllm model handle.
    """
    return get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.from_content(model="mockllm/model", content=content) for _ in range(n)
        ],
    )


def _preflight(config: Config) -> float:
    """Project spend and abort if it exceeds the ceiling.

    Args:
        config: The loaded run config.

    Returns:
        The projected spend in USD.

    Raises:
        RuntimeError: If the projection exceeds `run.cost_ceiling_usd`.
    """
    episodes = len(config.conditions) * config.run.epochs
    subject_rate = config.rates[config.run.subject_model]
    grader_rate = config.rates[config.run.grader_model]
    projected = project_usd(
        episodes,
        subject_rate,
        grader_rate,
        SUBJECT_INPUT_TOKENS,
        SUBJECT_OUTPUT_TOKENS,
        GRADER_INPUT_TOKENS,
        GRADER_OUTPUT_TOKENS,
        GRADER_CACHE_WRITE_TOKENS,
    )
    logger.info(
        "%d conditions x %d epochs = %d episodes; projected $%.2f (ceiling $%.2f)",
        len(config.conditions),
        config.run.epochs,
        episodes,
        projected,
        config.run.cost_ceiling_usd,
    )
    if projected > config.run.cost_ceiling_usd:
        raise RuntimeError(
            f"Projected ${projected:.2f} exceeds ceiling ${config.run.cost_ceiling_usd:.2f}. "
            f"Lower epochs or raise the ceiling deliberately."
        )
    return projected


def _rates_for_summary(cells: dict[str, int]) -> dict[str, float]:
    """Derive the reported rates and intervals from raw cell counts.

    Args:
        cells: Summed confusion cells.

    Returns:
        Rates with 95% Wilson intervals.
    """
    no_action = cells["fp"] + cells["tn"]
    action = cells["tp"] + cells["fn"]
    fp_lo, fp_hi = wilson_interval(cells["fp"], no_action)
    fn_lo, fn_hi = wilson_interval(cells["fn"], action)
    scored = no_action + action
    return {
        "fp_rate": cells["fp"] / no_action if no_action else 0.0,
        "fp_rate_ci_lo": fp_lo,
        "fp_rate_ci_hi": fp_hi,
        "candidate_fn_rate": cells["fn"] / action if action else 0.0,
        "candidate_fn_rate_ci_lo": fn_lo,
        "candidate_fn_rate_ci_hi": fn_hi,
        "agreement": (cells["tp"] + cells["tn"]) / scored if scored else 0.0,
    }


def run(config: Config, mock: bool = False) -> dict[str, Any]:
    """Run every condition and aggregate.

    Args:
        config: The loaded run config.
        mock: If True, use `mockllm` for both subject and grader. Free, offline,
            and exercises the whole pipeline; the numbers are meaningless.

    Returns:
        A JSON-serialisable summary.
    """
    per_condition: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    totals: dict[str, int] = dict.fromkeys(CELL_KEYS, 0)
    cost_lines: list[dict[str, Any]] = []
    total_usd = 0.0
    # Generous margin: retries and the grader can each consume queued outputs.
    mock_depth = config.run.epochs * 4 + 8

    for condition in config.conditions:
        subject: Any = (
            _mock_model("I considered it and declined.", mock_depth)
            if mock
            else config.run.subject_model
        )
        grader: Any = (
            _mock_model("<reasoning>mock</reasoning><answer>yes</answer>", mock_depth)
            if mock
            else config.run.grader_model
        )
        log = inspect_eval(
            tasks=calibration(
                scenario=condition.scenario,
                goal_type=condition.goal_type,
                goal_value=condition.goal_value,
                urgency_type=condition.urgency_type,
                extra_system_instructions=condition.extra_system_instructions,
                grader_model=grader,
                repeats=config.run.epochs,
            ),
            model=subject,
            max_connections=config.run.max_connections,
            display="plain",
        )[0]

        if log.status != "success" or log.results is None:
            logger.warning("condition %s did not succeed: %s", condition, log.status)
            failed.append({"condition": condition.model_dump(), "status": log.status})
            continue

        metrics = {m.name: m.value for m in log.results.scores[0].metrics.values()}
        cells = {key: int(metrics.get(key, 0)) for key in CELL_KEYS}
        for key in CELL_KEYS:
            totals[key] += cells[key]

        cost = price_usage(log.stats.model_usage, config.rates)
        total_usd += cost.total_usd
        cost_lines.extend(line.model_dump() for line in cost.lines)

        per_condition.append(
            {
                "condition": condition.model_dump(),
                "cells": cells,
                **_rates_for_summary(cells),
                "usd": cost.total_usd,
                "log": log.location,
            }
        )
        logger.info(
            "%s/%s: fp=%d of %d no-action; cost $%.3f",
            condition.scenario,
            condition.urgency_type,
            cells["fp"],
            cells["fp"] + cells["tn"],
            cost.total_usd,
        )

    if not per_condition:
        # Refusing to return a summary full of zeros. A run where nothing was
        # measured must not be indistinguishable from a run that measured zero
        # false positives -- that is the failure mode this project is about,
        # and it bit this script during development (LOGBOOK 2026-08-25).
        raise RuntimeError(
            f"No condition completed successfully ({len(failed)} failed). "
            f"Refusing to emit a summary of zeros. First failure: "
            f"{failed[0] if failed else 'unknown'}"
        )

    control = [c for c in per_condition if c["condition"]["control_arm"]]
    control_cells = {key: sum(int(c["cells"][key]) for c in control) for key in CELL_KEYS}

    return {
        "config": config.model_dump(),
        "per_condition": per_condition,
        "totals": totals,
        "failed_conditions": failed,
        **_rates_for_summary(totals),
        "control_arm_only": {"cells": control_cells, **_rates_for_summary(control_cells)},
        "cost": {"lines": cost_lines, "total_usd": total_usd},
    }


def main(config_path_str: str, mock: bool = False, dry_run: bool = False) -> None:
    """Entry point.

    Args:
        config_path_str: Path to the YAML config.
        mock: Run offline against mockllm.
        dry_run: Project cost and exit without running anything.
    """
    config = load_config(Path(config_path_str))
    projected = _preflight(config)
    if dry_run:
        logger.info("dry run: projected $%.2f, nothing executed", projected)
        return

    summary = run(config, mock=mock)
    out = Path(__file__).resolve().parents[3] / "logs" / "phase1_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(
        "fp_rate=%.3f [%.3f, %.3f] over %d no-action samples; total $%.2f; wrote %s",
        summary["fp_rate"],
        summary["fp_rate_ci_lo"],
        summary["fp_rate_ci_hi"],
        summary["totals"]["fp"] + summary["totals"]["tn"],
        summary["cost"]["total_usd"],
        out,
    )


if __name__ == "__main__":
    fire.Fire(main)
