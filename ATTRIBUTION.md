# Attribution

This project **measures** third-party evaluation code. It vendors none of it —
everything is a pinned PyPI dependency, imported and used unmodified. Nothing in
`scorer_integrity/` is copied from another project.

## Measured

**`inspect_evals`** — MIT, Copyright (c) 2024 UK AI Security Institute.
https://github.com/UKGovernmentBEIS/inspect_evals · pinned at `0.18.0`.

**`inspect_evals/agentic_misalignment`** — MIT, Copyright (c) 2025 Aengus Lynch.
An Inspect port (by [@bmillwood-aisi](https://github.com/bmillwood-aisi)) of
Anthropic's Agentic Misalignment framework
(https://github.com/anthropic-experimental/agentic-misalignment). The scenarios,
system prompts and judge rubrics measured here are theirs, used **verbatim and
unmodified** — that is the point, since the object of study is the behaviour of
the published configuration.

**`inspect_ai`** — MIT, UK AI Security Institute. Pinned at `0.3.260`.

## Conventions borrowed

Repository layout, ruff/pyright configuration, Makefile targets, `conftest.py`
`--runslow` pattern and this `ACCESS.md` convention follow
[`ApolloResearch/sample`](https://github.com/ApolloResearch/sample), Apollo
Research's public engineering-practices template. Conventions were matched
deliberately; **no files were copied** (that repo carries no licence).

## Prior art

**CJE (Causal Judge Evaluation)** — [arXiv:2512.11150](https://arxiv.org/abs/2512.11150),
an official Inspect AI extension, wrapped for `inspect_evals` in
[PR #1178](https://github.com/UKGovernmentBEIS/inspect_evals/pull/1178) (merged
2026-03-04) as `tools/judge_calibration_diagnostics.py`. It asks the same general
question — how much should you trust an LLM judge. It differs in where the labels
come from: CJE **consumes** oracle labels (from a stronger judge, or a
user-supplied CSV) and calibrates against them. This project **produces** labels
from deterministic environment facts. CJE is downstream of the label problem;
this is upstream of it. They compose.
