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
