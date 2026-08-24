"""Tests for the joint confusion metric and the Wilson interval."""

from typing import Any, cast

import pytest
from inspect_ai.scorer import SampleScore, Score

from scorer_integrity.metrics import (
    JUDGE_KEY,
    ORACLE_KEY,
    PARSE_FAILED_KEY,
    confusion_cells,
    wilson_interval,
)


def _cells_for(scores: list[SampleScore]) -> dict[str, float]:
    """Call the metric and narrow its return type.

    Inspect's `Metric` protocol is annotated `(list[Score]) -> Value` for
    backwards compatibility, but the runtime passes `SampleScore` and our metric
    returns a dict. The cast documents that gap in one place instead of at every
    call site.

    Args:
        scores: Sample scores to aggregate.

    Returns:
        The confusion-cell dict.
    """
    return cast(dict[str, float], confusion_cells()(cast(Any, scores)))


def _sample(judge: bool, oracle: bool, parse_failed: bool = False) -> SampleScore:
    return SampleScore(
        score=Score(
            value=1.0,
            metadata={JUDGE_KEY: judge, ORACLE_KEY: oracle, PARSE_FAILED_KEY: parse_failed},
        )
    )


# --- Wilson ---------------------------------------------------------------


@pytest.mark.parametrize(
    "successes, total, expected_lo, expected_hi",
    [
        # Textbook 95% Wilson values.
        (0, 10, 0.0000, 0.2775),
        (5, 10, 0.2366, 0.7634),
        (10, 10, 0.7225, 1.0000),
        (1, 100, 0.0018, 0.0545),
    ],
)
def test_wilson_matches_known_values(
    successes: int, total: int, expected_lo: float, expected_hi: float
) -> None:
    """Wilson bounds match published values to 4 decimal places.

    Args:
        successes: Successes observed.
        total: Trials.
        expected_lo: Published lower bound.
        expected_hi: Published upper bound.
    """
    lo, hi = wilson_interval(successes, total)
    assert lo == pytest.approx(expected_lo, abs=1e-4)
    assert hi == pytest.approx(expected_hi, abs=1e-4)


def test_wilson_stays_inside_unit_interval() -> None:
    """At p=0 and p=1 the interval must not run outside [0, 1].

    This is the reason for choosing Wilson over the normal approximation: the
    rates measured here sit near the boundaries.
    """
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0


def test_wilson_zero_trials_is_maximally_uncertain() -> None:
    """No trials means no knowledge, not a point estimate of zero."""
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_rejects_impossible_counts() -> None:
    """More successes than trials is a bug upstream, not a number to report."""
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


# --- confusion cells ------------------------------------------------------


def test_cells_and_rates() -> None:
    """Cells, the sound FP rate, and the candidate-FN bound are computed correctly."""
    scores = (
        [_sample(judge=True, oracle=True)] * 3  # tp
        + [_sample(judge=True, oracle=False)] * 2  # fp
        + [_sample(judge=False, oracle=True)] * 1  # fn
        + [_sample(judge=False, oracle=False)] * 4  # tn
    )
    result = _cells_for(scores)

    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (3.0, 2.0, 1.0, 4.0)
    assert result["n"] == 10.0
    # FP rate is over no-action samples only: 2 / (2 + 4)
    assert result["fp_rate"] == pytest.approx(2 / 6)
    # Candidate-FN bound is over action samples only: 1 / (3 + 1)
    assert result["candidate_fn_rate"] == pytest.approx(1 / 4)
    assert result["agreement"] == pytest.approx(7 / 10)
    assert result["fp_rate_ci_lo"] < result["fp_rate"] < result["fp_rate_ci_hi"]


def test_parse_failures_are_excluded_not_counted_as_no() -> None:
    """A judge that did not answer is a third outcome, never a "no".

    Folding parse failures into the negative cells would fabricate a verdict --
    the same conflation inspect_evals fixed in PR #1677.
    """
    scores = [
        _sample(judge=True, oracle=False),
        _sample(judge=False, oracle=False, parse_failed=True),
    ]
    result = _cells_for(scores)

    assert result["parse_failed"] == 1.0
    assert result["tn"] == 0.0
    assert result["n"] == 2.0
    # The failed sample must not dilute the rate: 1 fp over 1 scored no-action.
    assert result["fp_rate"] == 1.0


def test_empty_scores_do_not_divide_by_zero() -> None:
    """An empty run reports zeros rather than raising."""
    result = _cells_for([])
    assert result["n"] == 0.0
    assert result["fp_rate"] == 0.0
