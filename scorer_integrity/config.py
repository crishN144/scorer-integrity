"""Pydantic config for Phase 1 runs, loaded from YAML.

Follows the config pattern in ApolloResearch/sample: nested `BaseModel`s, a
top-level `seed`, and a `load_config` that asserts before it parses.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel

from scorer_integrity.oracle import Scenario


class ConditionConfig(BaseModel):
    """One upstream agentic_misalignment condition."""

    scenario: Scenario
    goal_type: str
    goal_value: str
    urgency_type: str
    extra_system_instructions: str | None = None
    # Marks a condition intended as an honest-control arm: the opportunity is
    # present but the pressure to take it is not.
    control_arm: bool = False


class ModelRates(BaseModel):
    """USD per million tokens, for cost accounting."""

    input_per_mtok: float
    output_per_mtok: float


class RunConfig(BaseModel):
    """What to run and how much may be spent."""

    subject_model: str
    grader_model: str
    epochs: int
    max_connections: int = 10
    # Hard ceiling. The run aborts before starting if the projection exceeds it,
    # and the actual spend is reported against it afterwards.
    cost_ceiling_usd: float


class Config(BaseModel):
    """Top-level Phase 1 config."""

    seed: int
    run: RunConfig
    rates: dict[str, ModelRates]
    conditions: list[ConditionConfig]


def load_config(config_path: Path) -> Config:
    """Load the config from a YAML file into a pydantic model.

    Args:
        config_path: Path to a `.yaml` config file.

    Returns:
        The parsed Config.
    """
    assert config_path.suffix == ".yaml", f"Config file {config_path} must be a YAML file."
    assert config_path.exists(), f"Config file {config_path} does not exist."
    with open(config_path) as f:
        config_dict = yaml.safe_load(f)
    return Config(**config_dict)
