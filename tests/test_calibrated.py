"""Tests for the `calibrated` wrapper.

The wrapper's contract is narrow and worth pinning down: it must not change the
number the wrapped scorer produced. If it did, the calibration story would be
circular -- we would be measuring our own edit rather than their grader.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest
from inspect_ai.scorer import Score, Scorer, Target, Value, scorer
from inspect_ai.solver import TaskState

from scorer_integrity.calibrated import calibrated
from scorer_integrity.metrics import JUDGE_KEY, ORACLE_KEY


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine in a fresh event loop.

    Used instead of pytest-asyncio so the test suite needs no extra plugin; the
    wrapper is the only async surface in the package.

    Args:
        coro: The coroutine to run.

    Returns:
        Whatever the coroutine returned.
    """
    return asyncio.run(coro)


@scorer(metrics=[])
def _stub_inner(value: Value, metadata: dict[str, Any] | None = None) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        return Score(value=value, explanation="inner explanation", metadata=metadata or {})

    return score


def test_passes_inner_value_through_unchanged() -> None:
    """The wrapped scorer's value survives verbatim, dict and all."""
    inner_value = {"harmful": 0.0, "classifier_verdict": 1.0}
    wrapped = calibrated(
        _stub_inner(inner_value, {"classifier_verdict": True}),
        ground_truth=lambda _state: False,
    )

    result = _run(wrapped(None, Target("")))  # type: ignore[arg-type]
    assert result is not None

    assert result.value == inner_value
    assert result.explanation == "inner explanation"


def test_attaches_judge_and_oracle_flags() -> None:
    """Telemetry is added alongside, and the inner metadata is preserved."""
    wrapped = calibrated(
        _stub_inner({"classifier_verdict": 1.0}, {"classifier_verdict": True}),
        ground_truth=lambda _state: False,
    )

    result = _run(wrapped(None, Target("")))  # type: ignore[arg-type]
    assert result is not None

    assert result.metadata is not None
    assert result.metadata[JUDGE_KEY] is True
    assert result.metadata[ORACLE_KEY] is False
    # inner metadata still there
    assert result.metadata["classifier_verdict"] is True


def test_reads_judge_from_dict_value_when_absent_from_metadata() -> None:
    """Scorers that put the verdict only in `value` are still wrappable."""
    wrapped = calibrated(
        _stub_inner({"classifier_verdict": 1.0}, metadata={}),
        ground_truth=lambda _state: True,
    )

    result = _run(wrapped(None, Target("")))  # type: ignore[arg-type]
    assert result is not None

    assert result.metadata is not None
    assert result.metadata[JUDGE_KEY] is True


def test_missing_judge_key_raises_with_actionable_message() -> None:
    """Pointing the wrapper at the wrong key fails loudly, not silently as False.

    A silent False here would land in the `tn` cell and quietly deflate the
    measured false-positive rate.
    """
    wrapped = calibrated(
        _stub_inner(1.0, metadata={}),
        ground_truth=lambda _state: False,
        judge_key="not_a_key",
    )

    with pytest.raises(KeyError, match="not_a_key"):
        _run(wrapped(None, Target("")))  # type: ignore[arg-type]
