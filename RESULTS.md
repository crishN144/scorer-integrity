# RESULTS

> ⚠️ **Pending.** No live model has been called. This file is a placeholder so
> that nothing in the repo reads as though results exist.
>
> Blocked on `PROMPTS.md` sign-off, then the 20-episode pilot, then a re-projected
> cost estimate, then the full run.

What will be here:

- Confusion matrices per scenario and pooled, with raw cell counts
- The sound false-positive rate with 95% Wilson intervals: how often the raw
  judge fires on transcripts where the oracle says no operative action
- The same, control-arm conditions only
- The candidate-FN upper bound, labelled as a bound
- Agreement rates, parse failures, and any Inspect sample errors
- Cost accounting from the run's own token counts, against the $20 ceiling
- ⛔ **Docker is not installed on the build machine.** That is what defers the
  bidirectionally-sound file-diff oracle (`inspect_evals.gdm_self_reasoning`) to
  Phase 3. Installing Docker is the single unblock.
