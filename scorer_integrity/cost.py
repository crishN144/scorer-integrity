"""Cost accounting for eval runs.

Inspect reports per-model token usage on every log. This turns that into dollars
against a rate table carried in the run config, so the number in RESULTS.md is
measured rather than estimated.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from scorer_integrity.config import ModelRates


class CostLine(BaseModel):
    """Spend attributed to one model."""

    model: str
    input_tokens: int
    output_tokens: int
    usd: float


class CostReport(BaseModel):
    """Total spend across a run."""

    lines: list[CostLine]
    total_usd: float


def price_usage(model_usage: Mapping[str, Any], rates: dict[str, ModelRates]) -> CostReport:
    """Price a log's `model_usage` against a rate table.

    Models absent from the rate table are priced at zero and reported with zero
    tokens attributed, so a missing rate shows up as a suspicious line rather
    than silently deflating the total. `mockllm/model` is free by definition.

    Args:
        model_usage: `EvalStats.model_usage`, mapping model name to a usage
            object exposing `input_tokens` and `output_tokens`.
        rates: USD-per-million-token rates keyed by model name.

    Returns:
        A CostReport with one line per model and the total.
    """
    lines: list[CostLine] = []
    for model, usage in model_usage.items():
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        rate = rates.get(model)
        usd = (
            0.0
            if rate is None
            else input_tokens / 1e6 * rate.input_per_mtok
            + output_tokens / 1e6 * rate.output_per_mtok
        )
        lines.append(
            CostLine(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usd=usd,
            )
        )
    return CostReport(lines=lines, total_usd=sum(line.usd for line in lines))


def project_usd(
    n_episodes: int,
    subject_rate: ModelRates,
    grader_rate: ModelRates,
    subject_input_tokens: float,
    subject_output_tokens: float,
    grader_input_tokens: float,
    grader_output_tokens: float,
) -> float:
    """Project the cost of a run before starting it.

    Args:
        n_episodes: Total episodes (conditions x epochs).
        subject_rate: Rates for the model under evaluation.
        grader_rate: Rates for the judge.
        subject_input_tokens: Mean subject input tokens per episode.
        subject_output_tokens: Mean subject output tokens per episode.
        grader_input_tokens: Mean grader input tokens per episode.
        grader_output_tokens: Mean grader output tokens per episode.

    Returns:
        Projected spend in USD.
    """
    subject = (
        subject_input_tokens / 1e6 * subject_rate.input_per_mtok
        + subject_output_tokens / 1e6 * subject_rate.output_per_mtok
    )
    grader = (
        grader_input_tokens / 1e6 * grader_rate.input_per_mtok
        + grader_output_tokens / 1e6 * grader_rate.output_per_mtok
    )
    return n_episodes * (subject + grader)
