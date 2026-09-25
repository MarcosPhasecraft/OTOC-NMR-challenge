"""Compute exact reference OTOCs, `C(t_k)` on each instance's time grid, into
`harness/data/references/<instance>.json`.

Exact means exact: otoc-core's parity-sector ED (`parity_ED`), no Trotterisation and no
sampling, so a stored value carries no error bar. Feasible for N <= 15 (2.9 s at N = 10,
40 s at N = 12, ~10-15 min at N = 15 on one core); larger sizes get their references from
elsewhere (CONTEXT.md §7) and are refused here unless `--max-qubits` is raised.

    python scripts/compute_references.py tier0            # all of tier 0
    python scripts/compute_references.py instance_4_d_5   # one instance

Existing files are skipped, so a killed run resumes. Each file records the method, the
otoc-core version, the time grid and the values, and is covered by FROZEN_GLOBS once the
referee is frozen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
from openfermion import QubitOperator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import spec  # noqa: E402

REFERENCE_DIR = os.path.join(os.path.dirname(spec.DATA_DIR), "harness", "data", "references")


def hamiltonian_from_spec(instance_spec: dict) -> QubitOperator:
    hamiltonian = QubitOperator()
    for i, j, pauli, coeff in instance_spec["terms"]:
        hamiltonian += QubitOperator(f"{pauli[0]}{i} {pauli[1]}{j}", coeff)
    return hamiltonian


def compute_reference(instance_id: str) -> dict:
    import otoc_core
    from otoc_core.exact import simulate_otoc_exact_time_evolution

    instance_spec = spec.build_spec(instance_id)
    hamiltonian = hamiltonian_from_spec(instance_spec)
    butterfly = QubitOperator(f"X{instance_spec['butterfly_site']}")
    measurement = QubitOperator(f"X{instance_spec['measurement_site']}")
    times = np.array(instance_spec["times"])
    start = time.perf_counter()
    _, values, meta = simulate_otoc_exact_time_evolution(
        hamiltonian, instance_spec["num_qubits"], butterfly, measurement, times, "parity_ED")
    values = np.asarray(values)
    if np.max(np.abs(np.imag(values))) > 1e-9:
        raise RuntimeError(f"{instance_id}: reference has an imaginary part {np.max(np.abs(np.imag(values)))}")
    return {
        "instance": instance_id,
        "num_qubits": instance_spec["num_qubits"],
        "method": meta["method"],
        "otoc_core_version": otoc_core.__version__,
        "measurement_site": instance_spec["measurement_site"],
        "butterfly_site": instance_spec["butterfly_site"],
        "times": [float(t) for t in times],
        "otoc": [float(np.real(v)) for v in values],
        "standard_errors": [0.0] * len(times),
        "regime": "exact",
        "wall_seconds": round(time.perf_counter() - start, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("claim", help="instance ids, N=<n> or tier names, comma-separated")
    parser.add_argument("--max-qubits", type=int, default=15)
    args = parser.parse_args()
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    manifest = spec.load_manifest()
    for instance_id in spec.parse_instances(args.claim):
        path = os.path.join(REFERENCE_DIR, f"{instance_id}.json")
        if os.path.exists(path):
            continue
        if manifest[instance_id]["num_qubits"] > args.max_qubits:
            print(f"skip {instance_id}: N={manifest[instance_id]['num_qubits']} > --max-qubits", flush=True)
            continue
        record = compute_reference(instance_id)
        with open(path + ".tmp", "w") as handle:
            json.dump(record, handle, indent=1)
        os.replace(path + ".tmp", path)
        print(f"{instance_id}: N={record['num_qubits']} {record['wall_seconds']}s "
              f"C={np.round(record['otoc'], 4).tolist()}", flush=True)


if __name__ == "__main__":
    main()
