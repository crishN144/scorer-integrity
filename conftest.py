"""Add runslow option and skip slow tests if not specified.

Follows the pattern in ApolloResearch/sample, which took it from
https://docs.pytest.org/en/latest/example/simple.html.

In this repo `slow` marks anything that spins up a full Inspect eval, even
with mocked models. Nothing marked `slow` makes a network call.
"""

from collections.abc import Iterable

import pytest
from pytest import Config, Item, Parser


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--runslow", action="store_true", default=False, help="run slow tests")


def pytest_configure(config: Config) -> None:
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config: Config, items: Iterable[Item]) -> None:
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
