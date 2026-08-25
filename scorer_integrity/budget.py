"""The single guarded path for model calls, with spend enforced on measurement.

Why this module exists, stated plainly because the lesson cost real money:
across Phase 1 and 2 the cost **projection** was wrong five separate times --
cache-write tokens ignored in the reporting path, then again in the projection
path, then a subject-specific output constant applied to a different subject,
then a judge-specific output constant applied to a different judge. Each time the
error was caught by comparing measured against projected.

The conclusion is not "estimate better". It is:

    Projections are for planning. Measured spend is the only control.

The multi-judge run overshot a $1.50 ceiling to $2.01 because the ceiling was
declared in its YAML and the script simply never read it -- a new script silently
opted out of a guard that lived in a different script. So the guard now lives
where the API calls go through, and `tests/test_budget_guard.py` fails the build
if any module reaches for the provider directly instead.
"""

from typing import Any

from inspect_ai.model import get_model

from scorer_integrity.config import ModelRates
from scorer_integrity.cost import price_usage
from scorer_integrity.log import logger

# Providers that cannot cost anything, so they bypass the guard.
FREE_MODELS = ("mockllm/model",)


class CostCeilingExceeded(RuntimeError):
    """Raised when measured spend passes the configured ceiling."""


class BudgetedModel:
    """Wraps a model handle, accumulating usage and enforcing a hard ceiling.

    Every call updates measured spend and checks it. There is no mode in which a
    caller can run past the ceiling by forgetting to check.
    """

    def __init__(self, name: str, rates: dict[str, ModelRates], ceiling_usd: float) -> None:
        """Build a guarded handle.

        Args:
            name: Provider-qualified model name.
            rates: USD-per-million-token rates keyed by model name.
            ceiling_usd: Hard spend limit for this handle.
        """
        self.name = name
        self._model = get_model(name)
        self._rates = rates
        self._ceiling = ceiling_usd
        self.input_tokens = 0
        self.output_tokens = 0
        self.input_tokens_cache_write = 0
        self.input_tokens_cache_read = 0
        self.calls = 0

    @property
    def spent_usd(self) -> float:
        """Measured spend so far, in USD."""
        return price_usage({self.name: self}, self._rates).total_usd

    def _accumulate(self, usage: Any) -> None:
        for field in (
            "input_tokens",
            "output_tokens",
            "input_tokens_cache_write",
            "input_tokens_cache_read",
        ):
            setattr(self, field, getattr(self, field) + int(getattr(usage, field, 0) or 0))

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        """Generate, then account and enforce.

        Args:
            *args: Passed through to the underlying model.
            **kwargs: Passed through to the underlying model.

        Returns:
            The provider's ModelOutput.

        Raises:
            CostCeilingExceeded: If measured spend has passed the ceiling. Raised
                *after* the call that crossed it, so the overshoot is bounded by
                one call rather than by a whole run.
        """
        output = await self._model.generate(*args, **kwargs)
        self.calls += 1
        if output.usage:
            self._accumulate(output.usage)
        if self.name not in FREE_MODELS and self.spent_usd > self._ceiling:
            raise CostCeilingExceeded(
                f"measured spend ${self.spent_usd:.4f} exceeded ceiling "
                f"${self._ceiling:.2f} after {self.calls} calls; stopping"
            )
        return output

    def report(self) -> None:
        """Log the final measured spend for this handle."""
        logger.info(
            "%s: %d calls, in=%d cache_w=%d out=%d, measured $%.4f of $%.2f ceiling",
            self.name,
            self.calls,
            self.input_tokens,
            self.input_tokens_cache_write,
            self.output_tokens,
            self.spent_usd,
            self._ceiling,
        )


def budgeted_model(name: str, rates: dict[str, ModelRates], ceiling_usd: float) -> BudgetedModel:
    """Construct a guarded model handle.

    This is the only sanctioned way to obtain a model in this package.

    Args:
        name: Provider-qualified model name.
        rates: Rate table.
        ceiling_usd: Hard spend limit.

    Returns:
        A BudgetedModel.
    """
    return BudgetedModel(name, rates, ceiling_usd)
