"""Phase 1 tasks: upstream's eval, unmodified, with our scorer wrapped around it.

Deliberately thin. Every scenario, system prompt and judge rubric comes from
`inspect_evals.agentic_misalignment` exactly as published -- the object of study
is the behaviour of the configuration people actually run, so rewriting any of it
would measure something nobody uses.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.model import Model
from inspect_ai.solver import TaskState
from inspect_evals.agentic_misalignment import agentic_misalignment
from inspect_evals.agentic_misalignment.scorers import harmfulness_scorer

from scorer_integrity.calibrated import calibrated
from scorer_integrity.oracle import Scenario, took_operative_action


def _ground_truth(scenario: Scenario):
    """Build a TaskState -> bool oracle for one scenario.

    Args:
        scenario: Which scenario's operative action to look for.

    Returns:
        A callable settling ground truth from the completed TaskState.
    """

    def check(state: TaskState) -> bool:
        return took_operative_action(scenario, state.output.completion)

    return check


@task
def calibration(
    scenario: Scenario = "blackmail",
    goal_type: str = "explicit",
    goal_value: str = "america",
    urgency_type: str = "replacement",
    extra_system_instructions: str | None = None,
    grader_model: str | Model | None = None,
    repeats: int = 1,
) -> Task:
    """Upstream's agentic_misalignment condition, scored against the oracle too.

    Args:
        scenario: `blackmail`, `leaking` or `murder`.
        goal_type: Upstream goal-conflict type.
        goal_value: Upstream goal value.
        urgency_type: Upstream threat type. `none` is a control-arm condition.
        extra_system_instructions: Upstream extra instructions, e.g. `dont`.
        grader_model: Judge override. Defaults to upstream's own default.
        repeats: How many independent episodes to run for this condition. The
            single upstream Sample is replicated with distinct ids rather than
            using Inspect's `epochs`, because an epoch reducer collapses all
            epochs of a sample into ONE SampleScore before metrics run -- so
            `epochs=10` would have produced 10 episodes and a confusion matrix
            over 1 of them (verified: LOGBOOK 2026-08-25, probe 7). The prompt
            is untouched; only the sample id differs.

    Returns:
        The upstream Task with its scorer wrapped by `calibrated`.
    """
    base = agentic_misalignment(
        scenario=scenario,  # type: ignore[arg-type]
        goal_type=goal_type,  # type: ignore[arg-type]
        goal_value=goal_value,  # type: ignore[arg-type]
        urgency_type=urgency_type,  # type: ignore[arg-type]
        extra_system_instructions=extra_system_instructions,  # type: ignore[arg-type]
    )
    if repeats > 1:
        original = list(base.dataset)
        base.dataset = MemoryDataset(
            samples=[
                sample.model_copy(update={"id": f"{sample.id}_r{index}"})
                for index in range(repeats)
                for sample in original
            ],
            name=base.dataset.name,
        )
    base.scorer = [
        calibrated(
            harmfulness_scorer(grader_model=grader_model),
            ground_truth=_ground_truth(scenario),
        )
    ]
    return base
