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

Phase 0 (tier 0, 10–12 qubits, exact scoring) is built and awaiting sign-off: referee,
baselines, control, board, validation and hard set. Nothing is frozen yet and there is no
`solution/` candidate. See `PLAN.md` and `SIGNOFF.md`.

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

### Running it on your own machine

Everything lives in this repository; nothing depends on the machine it was built on.

1. Clone, create a Python 3.13 environment and install as above (the otoc-core line needs SSH
   access to Phasecraft's GitHub).
2. `pytest tests/` (about two minutes). A pass means your referee reproduces the analytic
   cases, otoc-core and the database ladders bit for bit with the numbers here.
3. Docker (Docker Desktop on macOS: give its VM most of your cores and memory), then build the
   sandbox image once: `docker build -t sagecraft-runner:latest isolation/` (see
   `isolation/README.md`; behind a TLS-intercepting proxy add
   `--build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"`).
4. The board comes with the repo: `python scripts/render_leaderboard.py` re-renders
   `LEADERBOARD.md` from the committed score cache (`.score_cache.json`), valid as long as
   the frozen files match (the cache is keyed by their fingerprint).
5. Work the way an agent does: `python scripts/evaluate_candidate.py my/generate.py --name X`
   (N = 10 screen first, then the full development set), `python scripts/validation.py ...`
   for the fresh-instance check, `python run.py evaluate --instance instance_35_d_5@1
   --solution my/generate.py` for a single scored call.

Throughput scales with cores: the referee runs the eight time points in parallel and
instances and budget rungs are independent. On 4 cores a full development-set evaluation
of a good candidate is about an hour, a screen a minute; on 16-32 cores, minutes.

## License

Apache License 2.0, inherited from Sagecraft — see `LICENSE`. Copyright 2026 Phasecraft.
