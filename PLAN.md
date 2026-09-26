# PLAN

Staged plan. Formats and signatures here; reasoning and findings in `NOTES.md`; the contract
in `CONTEXT.md`. Stage 1 ends at the sign-off in §Phase 0 step 5; nothing editable exists
before that.

## Phase 0 — tier 0 only, exact scoring (current)

1. [x] Scaffold from Sagecraft (commit `ebc5666`), contract as `CONTEXT.md`, data with
   provenance (`data/`), `gen_orderings.py` vendored (`harness/vendor/`).
2. [x] Loader: `harness/spec.py` — `build_spec(instance_id)`, `parse_instances(claim)`,
   manifest `data/manifest.json` (tier, N, tmax per instance; 788 instances with tmax).
3. [x] Tier-0 references: exact `C(t_k)`, parity ED, stored `harness/data/references/`.
4. [x] Referee (exact engine; sampled engine in Phase 1): `harness/artifact.py` (schema, `verify`; the echo is assembled in `engines.py`),
   `harness/cost.py` (KAK CZ count), `harness/engines.py` (exact tier 0; qsim sampled
   later), `harness/score.py`, `harness/circuits.py` (shared builders); `harness/__init__.py` exposes `build_spec`,
   `parse_instances`, `verify`, `score`, `FROZEN_GLOBS`.
5. [ ] Baselines (`baselines/`): seed (first order, swapnet order, time-of-flight
   `initial_mapping`, fused SWAP gates), XZY second order merged, XZY fourth order,
   descending first order; seed-calibrated caps `cap_i`; control (random search over the
   seed's knobs).
6. [ ] Sign-off tests (`tests/`): analytic, rejection, reproduction (3N(N−1) CZ per seed
   step; references vs `dC_db` C_exact; five `r(ε)` rows), determinism, order-4
   equivalence with `krylov_step_bound.TrotterV4`, KAK round-trip, end-to-end
   sandbox/inbox/leaderboard on two instances. Then freeze (`CLAUDE.md`).
7. [ ] First AutoCraft run at first order on tier 0; go/no-go report.

## Phase 1 — tier 1 (13–15), sampled scoring with qsim, rediscovery table, fresh-seed checks.
## Phase 2 — tiers 2–3 once references exist; Stage G.

## Data formats

**spec** (dict, JSON-serialisable)
```
{ "instance": str, "num_qubits": int,
  "chain": [int],                        # physical positions 0..N-1; measurement spin's position = chain.index(0)
  "terms": [[i, j, "XX"|"YY"|"ZZ", coeff]],   # database convention, see harness/vendor/gen_orderings.py
  "measurement_site": 0, "butterfly_site": 1,
  "times": [float]*8,                    # k*tmax/8
  "cz_budget": int, "target_rmse": 0.05 }
```

**artifact** (dict, JSON-serialisable)
```
{ "initial_mapping": [int],            # spin -> chain position, a permutation
  "circuits": { "<time index>": <cirq circuit JSON> },   # forward V(t_k), gates on chain positions
  "butterfly_positions": [int],        # optional: where spin 1 sits after each V(t_k); default initial_mapping[1]
  "note": str }
```
Gates: single-qubit unitaries, or two-qubit unitaries on adjacent chain positions. Anything
else is invalid.

**verify(spec, artifact) → {"passed": bool, "checks": {...}, "reason": str}** — never raises.

**score(spec, artifact) → {"times", "reference_otoc" (development tiers only, else null),
"otoc", "signed_errors", "rmse", "mean_abs", "max_abs", "cz_per_time", "cz_count" (the
largest, which the budget applies to), "two_qubit_per_time", "two_qubit_count",
"over_budget", "target_rmse", "met_target", "sampling_se", "regime"}** — a vector, never combined.

**Instance ids**: database names, e.g. `instance_4_d_5`. `parse_instances` accepts a
comma-separated list, `N=12`, or a tier name (`tier0`).

## Traps
(none yet — see NOTES.md when the first one lands)
