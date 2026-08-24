"""Tests for cost accounting.

The regression these guard is a real one: the Phase 1 pilot's grader spend landed
almost entirely in `input_tokens_cache_write`, and an earlier version of
`price_usage` read only `input_tokens`, undercounting the grader ~3.7x. A cost
model that reads low is worse than none, because it silently authorises runs the
balance cannot cover.
"""

from types import SimpleNamespace

import pytest

from scorer_integrity.config import ModelRates
from scorer_integrity.cost import price_usage, project_usd

RATES = {"m": ModelRates(input_per_mtok=3.0, output_per_mtok=15.0)}


def test_prices_plain_input_and_output() -> None:
    """Base case: no cache involved."""
    usage = {"m": SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000)}
    assert price_usage(usage, RATES).total_usd == pytest.approx(18.0)


def test_cache_write_is_priced_at_1_25x_input() -> None:
    """Cache writes cost more than plain input, and must not be ignored."""
    usage = {
        "m": SimpleNamespace(
            input_tokens=0, output_tokens=0, input_tokens_cache_write=1_000_000
        )
    }
    assert price_usage(usage, RATES).total_usd == pytest.approx(3.75)


def test_cache_read_is_priced_at_0_1x_input() -> None:
    """Cache reads are cheap but not free."""
    usage = {
        "m": SimpleNamespace(
            input_tokens=0, output_tokens=0, input_tokens_cache_read=1_000_000
        )
    }
    assert price_usage(usage, RATES).total_usd == pytest.approx(0.3)


def test_pilot_grader_shape_is_not_undercounted() -> None:
    """The exact token shape observed in the pilot must price above the naive figure.

    Per condition the grader logged 20 input, 1,059 output and 11,371 cache-write
    tokens. Pricing only input+output gives $0.0159; the correct figure is ~3.7x
    that once the cache write is counted.
    """
    usage = {
        "m": SimpleNamespace(
            input_tokens=20, output_tokens=1_059, input_tokens_cache_write=11_371
        )
    }
    naive = (20 / 1e6 * 3.0) + (1_059 / 1e6 * 15.0)
    actual = price_usage(usage, RATES).total_usd

    assert actual > naive * 3
    assert actual == pytest.approx(naive + 11_371 / 1e6 * 3.0 * 1.25)


def test_unknown_model_prices_zero_but_is_still_reported() -> None:
    """A missing rate must show as a visible zero line, not vanish from the total."""
    usage = {"unknown": SimpleNamespace(input_tokens=999, output_tokens=999)}
    report = price_usage(usage, RATES)

    assert report.total_usd == 0.0
    assert len(report.lines) == 1
    assert report.lines[0].input_tokens == 999


def test_projection_is_linear_in_episodes() -> None:
    """Sanity check on the pre-flight projection."""
    rate = ModelRates(input_per_mtok=1.0, output_per_mtok=5.0)
    one = project_usd(1, rate, rate, 1000, 100, 1000, 100)
    assert project_usd(10, rate, rate, 1000, 100, 1000, 100) == pytest.approx(one * 10)
