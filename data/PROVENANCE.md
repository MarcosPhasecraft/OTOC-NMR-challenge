# Data provenance

Nothing in `data/` is computed here; every file is a copy, and this file says from where.

## `data/instances/<instance>/`

`hamiltonian_projected.npy` (N×N coupling matrix, kHz-scale, symmetric, zero diagonal;
sites 0 and 1 are the two carbons) and `metadata.json`, for all 835 converged instances of
the Google-generated protein dataset.

- Source: `PhaseCraft/google-nmr`, commit `1642e6610d933a469701418121d8d7e63bfb43c4`
  (2026-07-30), path `google_generated_hamiltonians_2026_02_02/data/converged_instances/`.
- Origin: Google Quantum AI, February 2026 ("260202_processed_protein_dataset"); construction
  described in that folder's `Constructing_realistic_ensembles_of_dipolar_coupled_systems-1.pdf`.
- Not copied: `atom_positions.npy`, `field_direction_mol_frame.npy`, `indices_projected.npy`,
  the openfermion/protobuf copies of the Hamiltonian, and Google's `otoc_converged.pkl` /
  `otoc_Nmax.pkl` (first-order Trotterised, 20 samples, unreproducible seed — not used as
  references here).

## `data/tmax_table.csv`

Per-instance `tmax` (time at which the exact OTOC first reaches 0.1) and outcome.

- Source: `PhaseCraft/otoc-trotter-error-bounds`, commit
  `0c594590ae56cd65cfd7dc61e206e1330cf3385b` (2026-09-24), `tmax_table.csv`.
- 788 of 835 instances have a `tmax` (`outcome == crossed`); the rest are excluded from the
  challenge (35 `wall_cap`, 3 `t_cap`, 9 `not_extended`). See that repository's README §4.

## `harness/vendor/gen_orderings.py`

The term orderings and the verified sign convention (het bond → ZZ +d, hom bond → XX −d and
YY +d), byte-compatible with the decompositions used throughout the OTOC error project.

- Source: `PhaseCraft/otoc-trotter-error-bounds`, same commit, `code/gen_orderings.py`,
  unmodified.

## Related sources not copied

- `PhaseCraft/otoc-core` commit `abff8d4b31cf18f2a80316bcca706cc57d4ca059` (2026-09-24):
  simulation engines, installed as a dependency (`--no-deps`).
- `PhaseCraft/Sagecraft` commit `ebc5666d7a8b36d465d3c0de649804a25e743008` (2026-09-05):
  the template this repository was built from.
- `PhaseCraft/AutoCraft` commit `9a5541976f1535cd68dcc12aa2993781f879f49d` (2026-09-12):
  the research loop.
- arXiv:2510.19550v1, Zhang et al., "Quantum computation of molecular geometry via
  many-body nuclear spin echoes": the AlphaEvolve setup this challenge mirrors.
