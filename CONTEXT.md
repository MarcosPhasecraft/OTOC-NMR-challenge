# OTOC-NMR challenge — problem and benchmark contract

Contract v1, agreed 25 September 2026. This file is the problem statement (Sagecraft's
`CONTEXT.md`): what an instance is, what a candidate is, how it is checked and scored, and
why. Items marked **[agreed]** record decisions taken during the design discussion.
Build status lives in `PLAN.md`, findings in `NOTES.md`, rules in `CLAUDE.md`.

## 1. Purpose and comparison level

A prover/verifier challenge in the Sagecraft shape, driven by the AutoCraft loop, that scores
**the same thing Google's AlphaEvolve experiment scored** (arXiv:2510.19550, Methods and
Supplement §VI) and admits **the same kinds of improvement**, on Phasecraft's own instances.

Comparison level: *methodology reproduction* (handover §4). Same candidate type, objective,
resource constraint and feedback; different instances; departures listed in §12. A
numerical reproduction on Google's DMBP landscape is not a goal of this contract.

Sequence: **Stage R** (mirror Google at 12–16 qubits; does our loop reach a comparable
seed→evolved improvement?) then **Stage G** (transfer across instances and sizes; later,
target-error objective and certificates).

## 2. Physics

- Hamiltonian family (database convention, `otoc-trotter-error-bounds/code/gen_orderings.py`):
  `H = Σ_hom d_ij (−X_iX_j + Y_iY_j) + Σ_het d_ij Z_iZ_j`, coefficients multiply Pauli matrices,
  units as stored (kHz-scale); heteronuclear bonds are those with exactly one carbon
  (sites 0, 1). Identity terms dropped.
- Observable: infinite-temperature OTOC `C(t) = 2^-n Tr[B M(t) B M(t)]`, `M(t) = W M W†`,
  with **M = X_0, B = X_1** (database-wide; Google's methyl-rotation butterfly is not used).
- Physical circuit the referee evaluates: `H_0 · V · X_1 · V† · H_0`, measure `Z_0`,
  initial state `|+>_0 ⊗ Haar_bath` (this equals C(t) in expectation for any V; otoc-core
  `krylov/haar_otoc.py` has the proof). `V` is the candidate's forward circuit; `V†` is its
  exact reverse. **[agreed]** the candidate submits V only; a full-echo (asymmetric) contract
  would be a separately versioned extension.
- Time grid per instance: `K = 8` points `t_k = k·tmax/8`, `tmax` = time at which the exact
  OTOC first reaches 0.1 (from `tmax_table.csv`). **[agreed]** keep the tmax window.
- Qubit labelling: the database's (carbons at sites 0, 1, rest as stored). **[agreed]** the
  artifact carries an `initial_mapping` (permutation of spins onto chain positions), applied
  before any gate and free of charge; time-of-flight order is one choice among many.
- Where the butterfly acts: V may move spins (one brick-wall swap-network pass reverses the
  chain), so the artifact also carries `butterfly_positions`, the chain position of spin 1
  after each V(t_k); omitted, it defaults to `initial_mapping[1]`. The referee applies X
  there, then V†, which returns every spin to its initial position, so the measurement
  spin needs no such entry. The declared position is part of the submission: a wrong one
  simply scores a different (wrong) quantity, like any other error in V.

## 3. Instances, tiers, access

Source: the 835 converged PDB instances (`google-nmr`), coupling matrices only; no
truncation, no synthetic instances. Reference data recomputed here (§7); Google's
`otoc_converged.pkl` values are not used (Trotterized, 20 samples, unreproducible seed).

| tier | N | instances (with tmax) | reference | candidate evaluation | agent access |
|---|---|---|---|---|---|
| 0 screen | 10–12 | 46 | exact (parity ED) | exact (parity sectors), no sampling | unlimited, unscored |
| 1 development | 13–15 | 276 (fixed subset of ~24 scored) | exact | 250 shared draws | full, scored |
| 2 validation | 16 | 246 | exact | 250 shared draws | aggregate feedback on schedule; references hidden; every query logged |
| 3 test | 17–25 | 220 | exact trace / many draws | 250 draws + fresh seeds | none until a policy is frozen |

Splits are by instance; no instance appears in two tiers. Opening tier 3 to feedback turns
it into tier 2 permanently. **[agreed]** the 47 instances without `tmax` are excluded; the
instance list lives in a manifest so additions (new `tmax`, new data) are one-line changes.
**[agreed]** Phase 0 uses tier 0 only (12 scored instances at N = 10–12; 46 available); tier 1 follows once
the machine works; tiers 2–3 wait for references (Alberto's computation, if compatible).
Data files: the 835 coupling matrices and the `tmax` table are copied into the repo with the
source commits recorded; `gen_orderings.py` is vendored for the sign convention.

## 4. The candidate

One file `generate.py` with one function `generate(spec) -> artifact`, run inside the
Sagecraft sandbox (`isolation/`): no network, no filesystem beyond `harness/` read-only,
CPU/memory/wall-clock caps. **[agreed]** 10 s wall-clock and 2 GB per `generate` call,
well below the cost of an exact OTOC at the tier's size (20–40 s at N = 12 here); raised
only if a legitimate generator needs it. Heavy optimisation belongs offline, its result in
the code.
Product-formula order is not a referee parameter: the candidate submits a circuit, so any
order or mixture is allowed. Baselines and the candidate helper library use otoc-core's
`get_trotter_suzuki_circuit` (orders 1, 2, 4; Suzuki `u_k = 1/(4 − 4^{1/(2k−1)})`), to be
checked numerically against `krylov_step_bound.TrotterV4` at sign-off. **[agreed]** the
loop starts at first order.

`spec` (everything the candidate knows):
```
num_qubits, chain (qubit order, measurement qubit at one end),
terms: [(i, j, "XX"|"YY"|"ZZ", coeff)], measurement_site=0, butterfly_site=1,
times: [t_1..t_8], cz_budget, target_rmse
```
No instance id, no reference values, no hardness metadata. `cz_budget` is the input the
candidate optimises against, exactly as in Google's setup; `target_rmse` (0.05) is
informational, the error the board ranks cost at (§8): the candidate is never asked to
estimate its own error, the referee sweeps budgets and reads the cost off the frontier.

`artifact`: one forward circuit per time `t_k` as a gate list (`{"gates": [[positions,
matrix], ...]}`, the matrix row-major as [re, im] pairs; cirq JSON is accepted too but is
2-3x larger and slow to parse): single-qubit unitaries and two-qubit unitaries on
**chain-adjacent** qubits only; `initial_mapping`, `butterfly_positions`; plus a short
method note. Freedoms (all of Google's): term and qubit ordering, fused SWAP+interaction
gates, coupling rescaling, non-uniform and modulated step sizes, higher-order or split
layers, dropping gates, arbitrary two-qubit unitaries. Prohibited: gates on non-adjacent
qubits, non-unitary or non-finite entries, ancillas, mid-circuit measurement, any output
other than a circuit.

## 5. The referee (frozen after Stage 1 sign-off)

For each instance and each budget on the ladder (§8):
1. `verify`: parse (gate list only: 2×2 on one qubit or 4×4 on two chain-adjacent qubits
   under `initial_mapping`; larger gates rejected); per-gate unitarity `‖G†G − I‖ ≤ 1e-8`,
   **rejected outright if violated, never re-projected**; finiteness; never raises.
2. Assemble the echo around V (§2) after applying `initial_mapping`: V exactly as submitted,
   the butterfly X at `butterfly_positions[k]`, then V† = the submitted gates reversed and
   inverted. The referee never
   edits, drops, merges or reorders the candidate's gates.
3. **[agreed] No referee-side pruning.** Light-cone pruning is the candidate's to discover;
   the baselines are plain Trotter that prunes nothing itself. The referee counts what is
   submitted.
4. Count CZs by Cirq KAK (`two_qubit_matrix_to_cz_operations`, `allow_partial_czs=False`,
   Cirq's default tolerance 1e-8, pinned Cirq version), memoised by gate unitary. The
   decomposition only produces the number; the simulated gate is the submitted matrix.
   Single-qubit gates cost 0. `cz_count > cz_budget` → invalid at this budget.
5. Simulate the echo: tier 0 exactly (parity sectors for XX/YY/ZZ circuits, dense fallback
   for arbitrary gates at N ≤ 12); tiers 1–3 with **qsim** on the cirq circuit, 250 draws
   `haar_state(seed, index)` shared with the stored per-draw exact values (§7). otoc-core's
   numpy engines serve as cross-checks only. **[agreed]**
6. `score` (vector, never combined), per instance and budget rung: `rmse` over the time
   grid, `mean_abs`, `max_abs`; the **signed error at every time**, the candidate's **OTOC
   value at every time**, the `times`, and on development tiers (0-1) the **reference curve**
   itself; the **CZ count of every time's circuit** and the largest (`cz_count`, which the
   budget applies to); two-qubit gate counts per time; `over_budget`; sampling standard error
   (0 in tier 0); `regime: exact|sampled`. This is Google's error matrix (their landscape x
   time is our instance x time) plus per-time costs, and it is what the results log stores.

Feedback to the agent (handover §7): everything in the score vector, plus read access to the
reference curves and the referee itself on tiers 0-1 (it may run any diagnostic it likes,
including on single times or single gates, as often as it likes on tier 0). Tier 2 returns
aggregates on a schedule; tier 3 nothing. The candidate program at runtime sees only the spec.

Determinism: fixed seeds, frozen reference files under `FROZEN_GLOBS`, pinned cirq version.
Finalists are re-scored on fresh draws and against the exact trace before any claim.

## 6. Cost model

Cost = KAK CZ count of the echo built from the **submitted circuit exactly as submitted**
(forward V + butterfly + V†, so twice V's count; the butterfly is single-qubit). Each
two-qubit gate is KAK-decomposed only to *count* the CZs it is worth: a fused SWAP+interaction
gate counts 3, a bare XX−YY or ZZ rotation 2, any two-qubit unitary at most 3. The referee
never drops, merges, reorders or simplifies a gate; a gate the candidate leaves in is paid
for. Reference point: 3N(N−1) CZ per first-order step of the echo for the plain
swap-network seed (630 at N = 15), matching the paper's G(N). Raw two-qubit gate count and a rotation count reported alongside
for the fault-tolerant view. **[agreed]**

## 7. Error metric and references

- Error at each time: `|C_cand(t_k) − C_ref(t_k)|` on the sample-mean curve (hardware
  convention; exact at tier 0). RMS over k is the primary number; mean and max diagnostics.
  This differs from the database's per-draw double RMS (`r_targets.csv`); baselines are
  re-measured under this convention.
- References: exact `C(t_k)` by otoc-core parity ED at N ≤ 15 (2.9 s at N = 10, 40 s at 12,
  80 s at 13, ~10–15 min at 15, one-off), Krylov exact with many draws above. Stored per
  instance with the method, version and (where sampled) standard error.
- Per-draw exact values `F_exact(ψ_i, t_k)` for the 250 fixed draws, stored, so sampled scores
  carry common-random-numbers cancellation.
- Noise floor: a sampled score is reported with its standard error; two scores differ only
  if the gap exceeds 2σ.

## 8. Budget ladder, ranking and frontier

- Per instance, the **seed-calibrated cap** `cap_i` = CZ count of the plain seed baseline
  (§9: first order, no pruning, no rescaling) at the smallest step count at which its mean
  error on the grid is ≤ 0.10. **This fixes the cost axis, not an accuracy target**: it is
  the cost at which vanilla Trotter sits at the 10 % error Google's seed started from
  (10.4 %), so error at `1 × cap_i` is directly comparable to their 10.4 % → 0.82 %. The
  calibration is stored in `harness/data/budgets.json`, frozen with the referee.
- **[agreed]** Ladder: 11 rungs, `2^(k/2) × cap_i` for k = −4..6 (x0.25 to x8, ratio √2).
  The candidate is called once per rung with `cz_budget` set; each call yields one measured
  point `(cz_count, rmse)`. An over-budget call is recorded but invalid at that rung.
  **[agreed]** The sweep is adaptive: rungs are evaluated cheapest first and the sweep stops
  at the first rung that meets the target error, never below x1 (so the Google-comparable
  cell is always measured); rungs above are skipped, since they cannot change either metric.
  The top three rungs are two thirds of a full ladder's cost. `--full` evaluates them all.
- **Primary metric (ranks the board): cost at the target error.** Per instance, the CZ
  count of the cheapest valid point with `rmse ≤ target_rmse = 0.05`, reported with its
  ratio to the seed's own cost at the same target; entries are ranked by the geometric mean
  of that ratio over the development instances (lower is better). An entry that never meets
  the target on some instance ranks below every entry that meets it everywhere. Resolution
  is the ladder's √2; no interpolation, a cost at target is always a measured point.
- **Secondary metric: error at the Google-comparable budget.** `rmse` at the x1 rung and
  the improvement factor over the seed (AlphaEvolve: 12.7× in mean error at fixed budget).
- Per instance: the nondominated set of all measured points (the Pareto frontier), each with
  the entry and rung that produced it. Dominance judged with error bars on sampled tiers.
- Search rule (AutoCraft `keep or revert`): a candidate is kept if it improves the primary
  metric, or, at equal primary, the secondary; the full frontier is logged either way so a
  later change of primary metric (e.g. another target, or error at budget) is a change to
  the leaderboard script, not to the referee or to any candidate.
- **[agreed] Fresh-instance validation.** Tier 0 has 46 instances; 12 are on the board, 26
  more of the same regime form the validation pool (`scripts/instance_set.py`) and are never
  optimised on. A candidate that would be kept is re-scored, next to the seed, on a fresh
  draw of four pool instances (deterministic per generation of the loop, at least one per
  size). It is kept only if it beats the seed there and its cost ratio on the draw is within
  25 % of its development-set ratio (`scripts/validation.py`); the verdict is on the board.
- **[agreed] Hard set.** The 8 tier-0 instances the seed cannot bring to 10 % within 16
  steps (tmax 1.8-20, weakly coupled carbon, fast bath) are a separate, unranked table:
  caps from a geometric search seeded by the error-bounds repo's step counts, every kept
  entry reported there, nobody optimising on them. A second generalisation axis.

## 9. Baselines (frozen reference solutions)

1. **Seed**: first-order Trotter, brick-wall swap-network ordering (`swapnet` in
   `gen_orderings.py`), time-of-flight `initial_mapping`, fused SWAP gates, no pruning —
   Google's seed. Reimplemented from Supplement §VIII.B–C on otoc-core's builder and
   validated against 3N(N−1) CZ per step (`otoccompilation` is not reachable from here;
   if it becomes available, cross-check against it).
0. **Control** (not a baseline, a non-agent search): random search over the seed's knobs
   (step count, ordering, uniform coupling scale, initial mapping) with the same evaluation
   budget as an agent run. The agent must beat the control's frontier. **[agreed]** built in
   Phase 0.
2. XZY-ordered second order with merged layers (the deck's recommendation).
3. Fourth order (Suzuki), XZY.
4. Descending-strength ordering, first order.
All at every budget on the ladder, so the seed's own frontier is the floor.

## 10. Frozen/editable boundary and sign-off tests

Frozen: `harness/` (loader, artifact checks, echo assembly, KAK count, engines, score,
circuit helpers), `baselines/`, reference and budget data files, `isolation/`. Editable:
`solution/` only, from Stage 2.
Sign-off before anything is editable (Sagecraft Step 3):
- analytic: t = 0 → C = 1; commuting H (ZZ only) → seed error 0; single bond → closed form.
- rejection: non-adjacent gate, non-unitary, over budget, wrong qubit count, malformed JSON.
- reproduction: seed CZ count = 3N(N−1) per step; exact references agree with
  `dC_db` `C_exact` at the database's query times within their stated `se`; 5 re-measured
  `r(ε)` rows agree with `r_targets.csv` up to the metric-convention factor.
- determinism: same candidate, same seeds → identical score bytes; registry fingerprint
  changes when any frozen file changes.

## 11. Success criteria

Stage R: on the development subset, the loop produces a readable policy that beats the seed
and the control on the primary metric (§8): cost at RMSE 0.05, geometric-mean ratio to the
seed below 1 with margin, and a frontier that dominates theirs. The Google comparison is the
secondary column: error at `1 × cap_i`, where the seed sits at ≈ 0.10 mean error by
construction; Google's reference ratio is 10.4 % → 0.82 % mean (≈ 12×), ≈ 5× in RMS.
Handover S1 floor: halve RMSE there.
Gain must survive fresh seeds and tier-2 validation.
Stage G: frozen policy run on tier 2 and 3; report gain vs N and vs hardness on both metrics.

## 12. Departures from Google, recorded

B = X_1 instead of methyl rotation; PDB instances instead of one molecule × 9 PMFs; no
landscape index; per-instance tmax grids; exact scores at tier 0; seed-calibrated budgets;
references exact and reproducible. As in Google's setup, all pruning and simplification is
the candidate's; the referee only assembles the echo around the submitted V and measures.

## 13. Rediscovery checklist

For every kept candidate the results log records which of Google's six concepts it uses
(coupling rescaling, interaction-graph decomposition, dynamic budgeting, step-size
modulation, adaptive symmetric second order, light-cone pruning), from the method note and a
static look at the code. "Recovered Google's ideas" is then a table row, not an anecdote.

## 14. Build phases and remaining decisions

- Repository: a personal GitHub repo of the author's, attached to the build session;
  otoc-core installed `--no-deps` (documented route). **[agreed]**
- Compute: cloud sessions (4 cores here) for Phase 0 and tier 1; larger tiers later.
- **Phase 0** (tier 0 only, minutes of compute): scaffold from Sagecraft; loader + manifest;
  tier-0 references (≈15 min); referee (§5); seed, three baselines, control; sign-off tests
  (§10, plus the order-4 equivalence check and one end-to-end sandbox/inbox/leaderboard
  run); freeze; AutoCraft loop at first order. Go/no-go on whether the loop finds anything.
- **Phase 1**: tier 1 (24 instances at 13–15, sampled scoring with qsim), the rediscovery
  table, fresh-seed re-checks.
- **Phase 2**: tiers 2–3 once references exist; Stage G.
- Nothing remains open except creating the repository.
