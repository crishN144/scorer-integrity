"""Re-judge stored transcripts with a different judge model. Judge-side cost only.

The 600-episode run saved every transcript, so a second grader can be measured on
exactly the same inputs for the price of the judge calls alone -- no subject
spend. Same rubric, verbatim, same upstream classifier objects.

Pre-registered framing (PROMPTS.md §8): the incumbent judge (`claude-sonnet-4-6`)
produced 0 false positives on 599 no-action transcripts. So every "yes" the
cheaper judge returns on a no-action transcript is a **measured false positive of
that grader**, on identical inputs. Sensitivity for the new judge comes from the
25 hand-written synthetic cases.

Usage:
    python scorer_integrity/scripts/run_phase1/run_multijudge.py <config.yaml> \\
        --summary_path logs/phase1_summary.json
"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import fire
from dotenv import load_dotenv
from inspect_ai.log import read_eval_log
from inspect_evals.agentic_misalignment.classifiers import (
    BlackmailClassifier,
    Classifier,
    LeakClassifier,
    MurderClassifier,
)
from inspect_evals.agentic_misalignment.prompt_generator import generate_prompts

from scorer_integrity.budget import BudgetedModel, budgeted_model
from scorer_integrity.config import load_config
from scorer_integrity.cost import price_usage
from scorer_integrity.log import logger
from scorer_integrity.metrics import JUDGE_KEY, wilson_interval
from scorer_integrity.oracle import Scenario, took_operative_action
from scorer_integrity.positive_control import ALL_CASES

# The three upstream classifiers take no required arguments; the base class
# signature is wider, hence the factory typing.
_CLASSIFIERS: dict[str, Callable[[], Classifier]] = {
    "blackmail": BlackmailClassifier,
    "leaking": LeakClassifier,
    "murder": MurderClassifier,
}


async def _judge(
    scenario: Scenario, response: str, email_content: str, model: BudgetedModel
) -> tuple[bool, bool]:
    """Run one judge call through the guarded path.

    Args:
        scenario: Which scenario's classifier and rubric to use.
        response: The stored transcript.
        email_content: Scenario email context the rubric interpolates.
        model: The guarded judge handle.

    Returns:
        (verdict, parse_failed).
    """
    classifier = _CLASSIFIERS[scenario]()
    output = await model.generate(
        classifier.get_grader_input(email_content=email_content, response=response)
    )
    try:
        _, verdict, _ = classifier.classify(response=response, grader_response=output.completion)
        return verdict, False
    except ValueError:
        return False, True


def _email_content(scenario: Scenario, condition: dict[str, Any]) -> str:
    return generate_prompts(
        scenario=scenario,
        goal_type=condition["goal_type"],
        goal_value=condition["goal_value"],
        urgency_type=condition["urgency_type"],
        extra_system_instructions=condition["extra_system_instructions"],
        prod_flag=False,
        alignment_faking_warning=None,
    ).email_content


async def _run(summary: dict[str, Any], model: BudgetedModel) -> dict[str, Any]:
    """Re-judge every stored transcript, then the synthetic set.

    Args:
        summary: The completed run summary naming the eval logs.
        model: The guarded judge handle; it enforces the ceiling itself.

    Returns:
        On-policy and synthetic records.
    """
    on_policy: list[dict[str, Any]] = []
    for entry in summary["per_condition"]:
        scenario: Scenario = entry["condition"]["scenario"]
        email_content = _email_content(scenario, entry["condition"])
        log = read_eval_log(entry["log"])
        samples = log.samples or []

        results = await asyncio.gather(
            *(_judge(scenario, s.output.completion, email_content, model) for s in samples)
        )
        for sample, (verdict, parse_failed) in zip(samples, results, strict=True):
            scores = sample.scores or {}
            incumbent = bool((scores["calibrated"].metadata or {}).get(JUDGE_KEY))
            on_policy.append(
                {
                    "sample_id": sample.id,
                    "scenario": scenario,
                    "control_arm": entry["condition"]["control_arm"],
                    "oracle": took_operative_action(scenario, sample.output.completion),
                    "incumbent_judge": incumbent,
                    "new_judge": verdict,
                    "parse_failed": parse_failed,
                }
            )
        logger.info(
            "re-judged %s/%s (measured $%.4f)",
            scenario,
            entry["condition"]["urgency_type"],
            model.spent_usd,
        )

    blackmail_email = _email_content("blackmail", summary["per_condition"][0]["condition"])
    synth_results = await asyncio.gather(
        *(_judge("blackmail", c.response, blackmail_email, model) for c in ALL_CASES)
    )
    synthetic = [
        {
            "case_id": c.case_id,
            "style": c.style,
            "expected_action": c.expected_action,
            "new_judge": verdict,
            "parse_failed": parse_failed,
        }
        for c, (verdict, parse_failed) in zip(ALL_CASES, synth_results, strict=True)
    ]
    return {"on_policy": on_policy, "synthetic": synthetic}


def main(config_path_str: str, summary_path: str = "logs/phase1_summary.json") -> None:
    """Re-judge the stored run with the config's grader model.

    Args:
        config_path_str: YAML config supplying the grader model, rates and ceiling.
        summary_path: The completed run summary naming the eval logs.
    """
    load_dotenv()
    config = load_config(Path(config_path_str))
    with open(summary_path) as f:
        summary = json.load(f)

    model = budgeted_model(config.run.grader_model, config.rates, config.run.cost_ceiling_usd)
    data = asyncio.run(_run(summary, model))
    model.report()

    no_action = [r for r in data["on_policy"] if not r["oracle"]]
    action = [r for r in data["on_policy"] if r["oracle"]]
    new_fp = sum(1 for r in no_action if r["new_judge"])
    inc_fp = sum(1 for r in no_action if r["incumbent_judge"])
    disagree = sum(1 for r in data["on_policy"] if r["new_judge"] != r["incumbent_judge"])

    positives = [r for r in data["synthetic"] if r["expected_action"]]
    negatives = [r for r in data["synthetic"] if not r["expected_action"]]
    caught = sum(1 for r in positives if r["new_judge"])
    quiet = sum(1 for r in negatives if not r["new_judge"])

    fp_lo, fp_hi = wilson_interval(new_fp, len(no_action))
    sens_lo, sens_hi = wilson_interval(caught, len(positives))
    spec_lo, spec_hi = wilson_interval(quiet, len(negatives))
    cost = price_usage({config.run.grader_model: model}, config.rates)

    out: dict[str, Any] = {
        "judge_model": config.run.grader_model,
        "on_policy": {
            "n_no_action": len(no_action),
            "n_action": len(action),
            "new_judge_fp": new_fp,
            "incumbent_judge_fp": inc_fp,
            "fp_rate": new_fp / len(no_action) if no_action else 0.0,
            "fp_rate_ci_lo": fp_lo,
            "fp_rate_ci_hi": fp_hi,
            "disagreements": disagree,
            "parse_failures": sum(1 for r in data["on_policy"] if r["parse_failed"]),
        },
        "synthetic": {
            "sensitivity": caught / len(positives) if positives else 0.0,
            "sensitivity_ci_lo": sens_lo,
            "sensitivity_ci_hi": sens_hi,
            "caught": caught,
            "n_positives": len(positives),
            "specificity": quiet / len(negatives) if negatives else 0.0,
            "specificity_ci_lo": spec_lo,
            "specificity_ci_hi": spec_hi,
            "quiet": quiet,
            "n_negatives": len(negatives),
        },
        "cost": cost.model_dump(),
        "records": data,
    }
    path = Path("logs") / f"multijudge_{config.run.grader_model.split('/')[-1]}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    logger.info(
        "%s: FP %d/%d = %.4f [%.4f, %.4f] (incumbent %d/%d); sens %d/%d; spec %d/%d; "
        "disagreements %d; cost $%.4f; wrote %s",
        config.run.grader_model,
        new_fp,
        len(no_action),
        out["on_policy"]["fp_rate"],
        fp_lo,
        fp_hi,
        inc_fp,
        len(no_action),
        caught,
        len(positives),
        quiet,
        len(negatives),
        disagree,
        cost.total_usd,
        path,
    )


if __name__ == "__main__":
    fire.Fire(main)
