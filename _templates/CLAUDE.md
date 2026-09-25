# [project name]

Read `CONTEXT.md` (problem/background) and `PLAN.md` (staged plan) before
doing any work here. This file is durable guidance that doesn't change as
the code does — traps, conventions, the frozen/editable boundary. Not
findings (those go in `NOTES.md`), not a plan (that's `PLAN.md`).

## Frozen vs editable

- `harness/` and `baselines/` (or wherever your checker/scorer/reference
  solutions live) are **frozen** once Stage 1 is signed off. Do not modify
  them to make a submission pass — that defeats the point of a referee
  anyone can trust.
- `solution/` is the only editable directory, and only from Stage 2
  onward.
- If a change to the frozen side ever seems necessary, stop and flag it
  explicitly rather than making it quietly. It means either a real bug in
  the referee (rare, high-stakes, confirm very carefully) or a submission
  trying to game it (assume this first).
- If a frozen file does change, every cached score is invalidated on
  purpose and the leaderboard will render empty until you run
  `toolkit.rescore.rescore()`. Do that in the same sitting, and read its
  report: a baseline that stops verifying under the corrected referee is
  a real result, not noise to clear.

## Running submissions

**Never call a submission's `generate()` directly — always through
`isolation/run_isolated()`.** `verify()` only checks `generate()`'s
*output*; by the time it runs, arbitrary code has already executed. See
`isolation/README.md`. If Docker isn't available, that helper fails
closed (raises) rather than falling back to running the submission
unsandboxed — never bypass that, even temporarily, even for a submission
that "looks fine."

## Stage gating

Stage 2 (an editable, generator-written submission) does not begin until
every test named in `PLAN.md`'s Stage 1 section passes. The
published-result-reproduction test (if your problem has one) is the gate
— treat it as the last, most expensive check, run after the cheaper ones
pass.

## Traps

[Empty until you hit one — see PLAN.md's own Traps section, which should
have a one-line pointer to the fuller story in NOTES.md for each entry.]

## Conventions

[Language, test runner, any project-specific rule worth stating once so
nobody has to rediscover it — e.g. "verify() never raises," "metrics are
always reported as a vector, never combined into one number."]
