"""Recompute the confusion matrix from saved eval logs. No model calls.

The judge's verdict is stored per sample, so a corrected oracle can be applied to
a completed run without re-running it. Used after the murder-predicate fix
(RESULTS.md §3): the judge verdicts are exactly as measured, only the mechanical
label changes.

Both matrices are reported -- as-run and corrected -- because silently replacing
one with the other would be changing the analysis after seeing the result.

Usage:
    python scorer_integrity/scripts/run_phase1/rescore.py logs/phase1_summary.json
"""

import json
from pathlib import Path
from typing import Any

import fire
from inspect_ai.log import read_eval_log

from scorer_integrity.log import logger
from scorer_integrity.metrics import JUDGE_KEY, ORACLE_KEY, wilson_interval
from scorer_integrity.oracle import Scenario, took_operative_action

CELL_KEYS = ("tp", "fp", "fn", "tn", "parse_failed", "n")


def _blank() -> dict[str, int]:
    return dict.fromkeys(CELL_KEYS, 0)


def _add(cells: dict[str, int], judge: bool, oracle: bool) -> None:
    cells["n"] += 1
    if judge and oracle:
        cells["tp"] += 1
    elif judge and not oracle:
        cells["fp"] += 1
    elif oracle and not judge:
        cells["fn"] += 1
    else:
        cells["tn"] += 1


def _rates(cells: dict[str, int]) -> dict[str, float]:
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
        "n_no_action": float(no_action),
        "n_action": float(action),
    }


def main(summary_path_str: str) -> None:
    """Recompute both matrices from the logs referenced by a run summary.

    Args:
        summary_path_str: Path to a `phase1_summary.json`.
    """
    with open(summary_path_str) as f:
        summary = json.load(f)
    as_run, corrected = _blank(), _blank()
    per_condition: list[dict[str, Any]] = []
    changed: list[str] = []

    for entry in summary["per_condition"]:
        scenario: Scenario = entry["condition"]["scenario"]
        log = read_eval_log(entry["log"])
        cond_corrected = _blank()

        for sample in log.samples or []:
            scores = sample.scores or {}
            metadata = scores["calibrated"].metadata or {}
            judge = bool(metadata.get(JUDGE_KEY))
            oracle_as_run = bool(metadata.get(ORACLE_KEY))
            oracle_now = took_operative_action(scenario, sample.output.completion)

            _add(as_run, judge, oracle_as_run)
            _add(corrected, judge, oracle_now)
            _add(cond_corrected, judge, oracle_now)

            if oracle_as_run != oracle_now:
                changed.append(f"{sample.id}: oracle {oracle_as_run} -> {oracle_now}")

        per_condition.append({"condition": entry["condition"], "cells": cond_corrected})

    out: dict[str, Any] = {
        "as_run": {"cells": as_run, **_rates(as_run)},
        "corrected": {"cells": corrected, **_rates(corrected)},
        "per_condition_corrected": per_condition,
        "relabelled_samples": changed,
    }
    path = Path(summary_path_str).parent / "phase1_rescored.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    as_run_rates, corrected_rates = _rates(as_run), _rates(corrected)
    logger.info("as-run    cells=%s fp_rate=%.5f", as_run, as_run_rates["fp_rate"])
    logger.info("corrected cells=%s fp_rate=%.5f", corrected, corrected_rates["fp_rate"])
    logger.info("%d samples relabelled; wrote %s", len(changed), path)


if __name__ == "__main__":
    fire.Fire(main)
