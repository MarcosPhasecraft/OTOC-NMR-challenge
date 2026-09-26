# NOTES

Findings and measurements, organised by topic. Clean summaries, not a diary.

## Measurements behind the contract (25 Sep 2026, 4-core cloud container, one core)

- Exact reference by otoc-core parity ED, 8 times: 2.9 s (N = 10), 40 s (N = 12), 80 s
  (N = 13); ~10–15 min extrapolated at N = 15.
- Exact (unsampled) Trotter OTOC via parity sectors, r = 16, 8 times: 1 s (N = 10), 20 s
  (N = 12), 132 s (N = 13) — above 12 the sampled path is cheaper.
- Sampled Trotter OTOC (otoc-core numpy statevector), N = 15, 184 terms/step: 42 s at r = 2
  and 351 s at r = 8 for 250 draws × 8 times. qsim/AVX expected 5–10× faster.
- KAK CZ counting (cirq 1.7): 2–6 s per 630 gates, i.e. one full-echo first-order step at
  N = 15; fused SWAP·interaction gates cost 3 CZ, bare XX−YY or ZZ rotations 2.
- Ordering headroom from `complete_3orderings.csv` (fully measured rows): median r/r_best
  1.00–1.24, p90 1.5–2.0, no consistent winner; at ε = 0.05 second order needs about the
  same step count as first order (so ~2× the gates).

## Google's setup, as read from arXiv:2510.19550v1
See `CONTEXT.md` §1, §6, §12. Key facts: Cirq KAK CZ count with SWAPs fused into the
interaction gates (3N(N−1) CZ per echo step); 250 fixed-seed initial states vs exact 2^15
reference; RMS fitness over a (landscape, time) grid with an error matrix as feedback; seed
= first-order Trotter + brick-wall swap network; deepest final circuit 792 CZ ≈ one pruned
step; mean error 10.4 % → 0.82 %, RMS ≈ 0.01 (Fig. S43); the six concepts of the evolved
program are listed in Supplement §VI.

## Findings from the Phase 0 build (26 Sep 2026)

- **Per-time step size.** Each time point's circuit must evolve for exactly its own time;
  building V(t_k) with the tmax step size and `round(t_k / dt)` steps evolved for the wrong
  duration at low step counts. Fixed via `circuits.steps_per_time`.
- **Where the butterfly acts.** One brick-wall pass reverses the chain, so after an odd number
  of first-order passes spin 1 sits at the mirrored position. The artifact now declares
  `butterfly_positions`; with it the referee reproduces Alberto's swapnet ladders per time
  point (identity layout).
- **Odd N: the alternating-direction first-order network is Strang.** Reversing the chain each
  pass makes pass k+1 the mirror image of pass k when N is odd (position parity flips under
  reversal), so 2m first-order passes at dt/2 are exactly m Strang steps at dt: on N = 11 the
  seed and `fused_p2` produce identical scores at equal CZ. For even N pass k+1 repeats pass
  k and the two differ. Google's 15-spin seed was therefore effectively second order.
- **Hard instances.** 8 of 46 tier-0 instances (tmax 1.8-20, weakly coupled carbon, bath
  couplings ~15) need 70-300 seed steps for 10 % mean error; first-order error is not
  monotone in the step count there (also seen in the error-bounds repo). They form the hard
  set; the development set was chosen among the other 38 (`data/analysis/tier0_seed_scan.md`).
- **Layout matters more than expected.** On instance_35_d_5 the time-of-flight layout gives
  RMSE 0.046 at 16 seed steps where the identity layout gives 0.016.
- **Speed.** Exact engine: batched 4x4 matmul instead of einsum (5-10x at N = 12), complex64
  gate pass (1.75x, agreement 1e-5), adaptive budget sweep (~3x). At ~18 ms per gate at
  N = 12 the engine is near one core's memory bandwidth; the remaining lever is cores. The
  parity trick does not stack with the |+>-subspace formulation (same factor of two).
- **Artifact size.** cirq JSON is ~1 KB per gate (45 MB at the x8 rung of the second-order
  baseline, killed in a 512 MB sandbox); the gate-list format is ~500 bytes per gate.
