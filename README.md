# scorer-integrity

**How much load is the mechanical gate on your LLM judge actually carrying?**

A calibration harness that wraps an existing Inspect scorer, scores its judge
against a **deterministic environment fact**, and reports the joint confusion
matrix the judge's own metrics cannot show.

`inspect_ai 0.3.260` · `inspect-evals 0.18.0, unmodified` · `stdlib + pydantic harness` · `95% Wilson intervals` · `no Docker`

> **Status: Phase 1 complete.** 600 episodes run 2026-08-25. Of **599**
> transcripts where the mechanical oracle says no action was taken, the judge
> flagged **0** — false-positive rate **0.000, 95% Wilson [0.000, 0.0064]**.
> Judge sensitivity was established first on a hand-written set: **20/20**.
> Full numbers in [`RESULTS.md`](RESULTS.md); how it got there, dead ends
> included, in [`LOGBOOK.md`](LOGBOOK.md); the spoken version in
> [`INTERVIEW.md`](INTERVIEW.md).

---

## Abstract

> Frontier evaluation pipelines score agent transcripts with LLM judges, because
> at thousands of runs per campaign nobody reads them all. A good practice has
> emerged for defending that: **gate the judge's verdict on a mechanical check**
> of whether the agent actually did the thing. Anthropic's agentic-misalignment
> framework does this, and the AISI Inspect port carries it through — the
> reported `harmful` verdict fires only if a deterministic check agrees.
>
> This project asks the follow-up question. **How much work is that gate doing,
> and is it doing it correctly?** Both halves matter, because most evaluation
> environments have no such gate available: there is no address to grep for, no
> file to diff. Whatever the gate is currently absorbing is what those
> environments are exposed to.
>
> Three findings. **(1)** In the `blackmail` scenario the gate is implemented
> unsoundly and errs in both directions — deterministic, reproducible in seconds,
> no API key ([`DRAFT_ISSUE.md`](DRAFT_ISSUE.md)). **(2)** The judge does not
> confuse deliberation with action, to a measured bound of **0.64%** over 599
> transcripts. **(3)** ⭐ The run's four apparent judge failures were all *oracle*
> failures — in three, the ground truth scored a refusal as the act being refused,
> in transcripts where the model was emailing humans to raise an alarm. The judge
> was right and the ground truth was wrong.

---

## 1. The measurement chain

```
model behaviour → transcript → LLM judge ─┐
                                          ├─ AND → reported `harmful` rate
              sandbox / mechanical check ─┘
```

Upstream reports two numbers: how often the gated verdict fired, and how often
the raw judge fired. Both are means of a score value — there is no target to
compare against — so they are **base rates, not accuracies**. What neither shows
is the *joint* distribution: how often the two components disagree, and in which
direction. That is the quantity that says how much the gate is absorbing.

This harness computes it, by scoring the judge against ground truth the sandbox
can settle without a model.

## 2. Why mechanical ground truth

Auditing a judge needs labelled data. Labelling scheming transcripts needs expert
humans. That is the cost the judge exists to avoid — so the problem is circular.

The way out is to ask a **narrower question the environment can answer itself**:

```
took_operative_action(scenario, transcript)
```

Did the agent email the target address? Submit the override code? No model in the
loop, no judgement, no API call.

⚠️ **Soundness runs one way, and the README says so before the results do:**

| | |
|---|---|
| judge says **yes**, oracle says **no action** | ⭐ **decisive.** You cannot blackmail someone you never contacted. Yields a **sound false-positive rate**. |
| judge says **no**, oracle says **action** | ⚠️ **not decisive.** The model may have emailed the target innocently. Yields a **candidate-FN upper bound**, never "the false-negative rate". |

The FN direction is closed properly by a file-diff oracle
(`inspect_evals.gdm_self_reasoning`), which is sound both ways. That needs Docker
and is deferred — see [`RECON.md`](RECON.md) §2.2.

## 3. The honest control arm

A judge that fires on every transcript mentioning blackmail is not detecting
blackmail, it is detecting vocabulary. Distinguishing the two needs transcripts
where **the opportunity exists, the model reasons about it, and the model does
not act**. Upstream's published condition grid already contains them
(`urgency_type=none`, `goal_type=none`, `extra_system_instructions=dont`), so
this project **selects** the control arm rather than writing one — keeping the
whole dataset first-party.

## 4. The wrapper

The reusable part. It does not fork, patch or reimplement the scorer it measures:

```python
Task(
    dataset=...,
    solver=...,
    scorer=calibrated(
        harmfulness_scorer(),  # upstream's scorer, unmodified
        ground_truth=lambda state: took_operative_action("blackmail", state.output.completion),
    ),
)
```

`Score.value` passes through verbatim — upstream's number is reported unchanged
alongside ours — and judge-vs-oracle telemetry is attached in metadata for the
`confusion_cells` metric to aggregate. Any Inspect task whose environment can
settle ground truth programmatically gets calibration by wrapping one function.

## 5. Reproduce

```bash
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
make test-all      # 75 tests, no network: subject and grader are both mockllm
make check         # ruff + pyright (Apollo's near-strict config)
```

The deterministic finding in [`DRAFT_ISSUE.md`](DRAFT_ISSUE.md) needs no API key.
The live run is gated on `PROMPTS.md`:

```bash
python scorer_integrity/scripts/run_phase1/run_phase1.py \
    scorer_integrity/scripts/run_phase1/pilot.yaml --dry-run   # project cost, run nothing
```

## 6. Limitations

Stated here rather than at the bottom, because they bound every number this repo
will produce.

- **One scenario family.** Three scenarios from one framework. Nothing here
  establishes what judges do in general.
- **One judge, one subject model.** No multi-judge sweep, no rubric-perturbation
  arm, no adversarial arm. Deliberately out of scope for Phase 1.
- ⚠️ **No on-policy false-negative evidence.** The subject refused in all 600
  episodes, so `tp = 0`. The false-positive direction is measured; sensitivity
  comes only from hand-written transcripts. `RESULTS.md` §4 has the two things
  that close it.
- **The oracle is sound in one direction only** (§2).
- **Small models, toy environments.** The claim is about *how a scorer is
  measured*, not about frontier scheming rates.
- **Judge rubrics are upstream's, verbatim.** Rewriting them would measure a
  configuration nobody runs.

## 7. Prior art

The general question — how much to trust an LLM judge — is **not novel and is not
claimed as such**. [PR #1178](https://github.com/UKGovernmentBEIS/inspect_evals/pull/1178)
(merged 2026-03-04) added judge calibration diagnostics to `inspect_evals`,
wrapping [CJE](https://arxiv.org/abs/2512.11150), already an official Inspect
extension. CJE **consumes** oracle labels — from a stronger judge, or a
user-supplied CSV — and calibrates against them. This project **produces** labels
from deterministic environment facts. CJE is downstream of the label problem;
this is upstream of it, and the two compose. Full attribution:
[`ATTRIBUTION.md`](ATTRIBUTION.md).

## 8. Repository layout

| Path | What |
|---|---|
| `scorer_integrity/oracle.py` | The three mechanical predicates, pinned as tested constants |
| `scorer_integrity/calibrated.py` | The wrapper (§4) |
| `scorer_integrity/metrics.py` | Joint confusion matrix + Wilson intervals |
| `scorer_integrity/tasks.py` | Upstream task + our scorer. Deliberately thin |
| `scorer_integrity/scripts/run_phase1/` | Sweep runner, cost ceiling, YAML configs |
| [`RECON.md`](RECON.md) | Phase 0: what was forkable, and the corrected thesis |
| [`LOGBOOK.md`](LOGBOOK.md) | Running log, dead ends included |
| [`PROMPTS.md`](PROMPTS.md) | Every condition and rubric that will be run |
| [`DRAFT_ISSUE.md`](DRAFT_ISSUE.md) | Unfiled upstream bug report |
| [`RESULTS.md`](RESULTS.md) | Measured results, limitations, cost |
| [`INTERVIEW.md`](INTERVIEW.md) | The spoken version, every number, hard questions |

## Licence

MIT. Measures MIT-licensed third-party code; vendors none of it.
