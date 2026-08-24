"""Run the live judge over the synthetic transcript set.

Characterises the judge, not any subject model. Calls upstream's
`BlackmailClassifier` exactly as the eval does -- same rubric, same parsing --
but over hand-written transcripts with known labels.

Usage:
    python scorer_integrity/scripts/run_phase1/run_positive_control.py <config.yaml>

Judge-only, ~25 calls, well under $1. Takes about a minute.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import fire
from dotenv import load_dotenv
from inspect_ai.model import get_model
from inspect_evals.agentic_misalignment.classifiers import BlackmailClassifier
from inspect_evals.agentic_misalignment.prompt_generator import generate_prompts

from scorer_integrity.config import load_config
from scorer_integrity.cost import price_usage
from scorer_integrity.log import logger
from scorer_integrity.metrics import wilson_interval
from scorer_integrity.oracle import took_operative_action
from scorer_integrity.positive_control import ALL_CASES, SyntheticCase


async def _judge_one(
    case: SyntheticCase, classifier: BlackmailClassifier, model: Any, email_content: str
) -> dict[str, Any]:
    """Run the live judge on one synthetic transcript.

    Args:
        case: The transcript and its declared label.
        classifier: Upstream's classifier, unmodified.
        model: The judge model handle.
        email_content: Scenario email context the rubric interpolates.

    Returns:
        A record of the label, the verdict, and any parse failure.
    """
    grader_input = classifier.get_grader_input(
        email_content=email_content, response=case.response
    )
    output = await model.generate(grader_input)
    try:
        _, verdict, _ = classifier.classify(
            response=case.response, grader_response=output.completion
        )
        parse_failed = False
    except ValueError:
        # Upstream raises rather than fabricating a verdict. Recorded as a third
        # outcome, never folded into "no".
        verdict, parse_failed = False, True

    return {
        "case_id": case.case_id,
        "style": case.style,
        "expected_action": case.expected_action,
        "oracle": took_operative_action("blackmail", case.response),
        "judge": verdict,
        "parse_failed": parse_failed,
    }


async def _run_all(model: Any) -> list[dict[str, Any]]:
    classifier = BlackmailClassifier()
    prompts = generate_prompts(
        scenario="blackmail",
        goal_type="explicit",
        goal_value="america",
        urgency_type="replacement",
        extra_system_instructions=None,
        prod_flag=False,
        alignment_faking_warning=None,
    )
    return await asyncio.gather(
        *(_judge_one(case, classifier, model, prompts.email_content) for case in ALL_CASES)
    )


def main(config_path_str: str) -> None:
    """Entry point.

    Args:
        config_path_str: Path to a YAML config supplying the grader model and rates.
    """
    # inspect_eval loads .env itself; a bare get_model call does not.
    load_dotenv()
    config = load_config(Path(config_path_str))
    model = get_model(config.run.grader_model)
    records = asyncio.run(_run_all(model))

    positives = [r for r in records if r["expected_action"]]
    negatives = [r for r in records if not r["expected_action"]]
    caught = sum(1 for r in positives if r["judge"])
    quiet = sum(1 for r in negatives if not r["judge"])

    sens_lo, sens_hi = wilson_interval(caught, len(positives))
    spec_lo, spec_hi = wilson_interval(quiet, len(negatives))

    cost = price_usage(model.usage_summary(), config.rates) if hasattr(model, "usage_summary") else None

    summary = {
        "records": records,
        "sensitivity": {
            "caught": caught,
            "total": len(positives),
            "rate": caught / len(positives) if positives else 0.0,
            "ci_lo": sens_lo,
            "ci_hi": sens_hi,
        },
        "specificity": {
            "quiet": quiet,
            "total": len(negatives),
            "rate": quiet / len(negatives) if negatives else 0.0,
            "ci_lo": spec_lo,
            "ci_hi": spec_hi,
        },
        "parse_failures": sum(1 for r in records if r["parse_failed"]),
        "cost": cost.model_dump() if cost else None,
    }

    out = Path(__file__).resolve().parents[3] / "logs" / "positive_control_summary.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(
        "sensitivity %d/%d = %.3f [%.3f, %.3f]; specificity %d/%d = %.3f [%.3f, %.3f]; wrote %s",
        caught,
        len(positives),
        summary["sensitivity"]["rate"],
        sens_lo,
        sens_hi,
        quiet,
        len(negatives),
        summary["specificity"]["rate"],
        spec_lo,
        spec_hi,
        out,
    )
    for record in records:
        if record["expected_action"] != record["judge"]:
            logger.warning("MISS %s (%s): judge=%s", record["case_id"], record["style"], record["judge"])


if __name__ == "__main__":
    fire.Fire(main)
