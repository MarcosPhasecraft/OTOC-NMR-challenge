# OTOC-NMR-challenge

A prover/verifier challenge for **low-cost Trotter circuits of NMR out-of-time-order
correlators**: a program proposes a circuit for the forward evolution of a dipolar spin
Hamiltonian, frozen code assembles the OTOC echo around it, counts its CZ cost, and scores
its error against an exact reference. Built on the [Sagecraft](https://github.com/PhaseCraft/Sagecraft)
template and driven by the [AutoCraft](https://github.com/PhaseCraft/AutoCraft) loop.

The benchmark scores the same thing Google's AlphaEvolve experiment scored
(arXiv:2510.19550, Methods and Supplement §VI) and admits the same kinds of improvement, on
Phasecraft's own instances from the Google-generated protein dataset. Stage R asks whether
an agent loop reaches a comparable seed→evolved improvement at 10–16 qubits; Stage G asks
whether what it finds transfers across instances and sizes.

## Read these first

| file | what it is |
|---|---|
| `CONTEXT.md` | the problem and the benchmark contract: instance, candidate, referee, cost, error, budget ladder, tiers, baselines |
| `PLAN.md` | build phases, data formats, function signatures, what is done and what is next |
| `CLAUDE.md` | the frozen/editable boundary, tier and access rules, traps |
| `NOTES.md` | findings and measurements as they accumulate |
| `data/PROVENANCE.md` | where every data file came from, with source commits |

`PLAYBOOK.md`, `TOOLKIT.md`, `KNOWN_ISSUES.md` and `PROBLEMS.md` are Sagecraft's and describe
the machinery, not this problem.

## Status

Phase 0 (tier 0, 10–12 qubits, exact scoring) is being built. Nothing is frozen yet and
there is no `solution/` candidate. See `PLAN.md`.

## Running it

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps "otoc-core @ git+ssh://git@github.com/PhaseCraft/otoc-core.git"
pytest
```

`otoc-core` is installed without its dependencies on purpose: its Julia bounds bridge and
`datacraft` need Phasecraft's private package index, and this challenge uses only its
simulation modules (dense and parity-sector exact OTOCs, the Haar harness, the
Trotter-Suzuki circuit builder), which need nothing beyond `requirements.txt`.

Processing submissions needs Docker (`isolation/`); the test suite does not.

## License

Apache License 2.0, inherited from Sagecraft — see `LICENSE`. Copyright 2026 Phasecraft.
