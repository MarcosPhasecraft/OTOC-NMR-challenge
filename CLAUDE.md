# OTOC-NMR-challenge

Read `CONTEXT.md` (the contract) and `PLAN.md` (staged plan) before doing any work here.
This file holds durable rules: the frozen/editable boundary, tier and access rules, and
traps already hit. Not findings (`NOTES.md`), not a plan (`PLAN.md`).

## Frozen vs editable

- `harness/`, `baselines/`, `harness/data/` (reference values, per-draw values,
  seed-calibrated caps), `data/` and `isolation/` are **frozen** once Phase 0 step 6 is
  signed off. They are never modified to make a submission pass.
- `solution/` is the only editable directory, and only after the sign-off.
- If a frozen file must change (a real referee bug), stop, flag it, change it, then run
  `toolkit.rescore.rescore()` in the same sitting: every cached score is invalidated on
  purpose.

## The referee never edits a submission

It parses, checks, assembles the echo around the submitted V (V as given, butterfly, V† by
reversal and inversion), counts, simulates, scores. It does not drop, merge, reorder, route,
re-project or simplify any gate. Non-unitary gates, non-adjacent gates, gates on three or
more qubits are rejected, never repaired. Pruning and every other simplification are the
candidate's job and the candidate's credit.

## Running submissions

Never call a submission's `generate()` directly; always through `isolation/run_isolated()`
(no network, `harness/` read-only, 10 s wall-clock and 2 GB per call). If Docker is down,
the helper raises; do not work around it.

## Tiers and access

- Tier 0 (N = 10–12): unlimited screening, **never a score**. A tier-0 result enters the
  results log only as a note pointing at the tier-1 run that confirmed or killed it.
- Tier 1 (13–15): scored; keep/revert decisions are made here.
- Tier 2 (16): aggregate feedback on a schedule only; references hidden; every query logged.
- Tier 3 (17–25): sealed until a policy is frozen. Opening it to feedback turns it into
  tier 2 permanently.
- Instances without a `tmax` are excluded; the manifest is the only place to add them.

## Scoring rules

- Budgets are a ladder `{0.5, 1, 2, 4} × cap_i` per instance; the candidate is called once
  per budget with `cz_budget` set. Never interpolate between budgets.
- Two scores differ only if the gap exceeds 2σ (σ = 0 in the exact regime).
- Keep-or-revert: one champion per budget bin; a candidate is kept if it beats a champion in
  any bin by more than the noise.
- Every kept candidate gets the rediscovery checklist (`CONTEXT.md` §13).

## Conventions

- Python 3.13; `otoc-core` installed `--no-deps`; cirq pinned in `requirements.txt`.
- KAK CZ counting: `cirq.two_qubit_matrix_to_cz_operations(..., allow_partial_czs=False)`,
  default tolerance; the decomposition only produces a number.
- Hamiltonian sign convention: `harness/vendor/gen_orderings.py` (het → ZZ +d, hom → XX −d,
  YY +d); `M = X_0`, `B = X_1`.
- `verify()` never raises; `score()` returns a vector.

## Traps

(empty until one is hit; each entry points at the fuller story in NOTES.md)
