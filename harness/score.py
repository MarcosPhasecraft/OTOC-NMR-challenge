"""`score(spec, artifact)`: the metric vector (CONTEXT.md §5-§7). Runs only after `verify`
passed. Never combines metrics into one number.

Reference values come from `harness/data/references/<instance>.json`. The spec does not name
the instance (the candidate must not know it), so the referee finds the reference through
`harness/data/references/index.json`, keyed by a digest of the spec's terms and times.

Budget compliance is reported here (`over_budget`) rather than failing `verify`: an
over-budget circuit is invalid *at that budget* but its (cost, error) point is still recorded
(CONTEXT.md §8). The eight time points are independent and are evaluated in parallel.
"""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np

from harness import cost, engines
from harness.artifact import Gate, parse_artifact

REFERENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "references")
MAX_WORKERS = min(8, os.cpu_count() or 1)


def terms_digest(spec: dict[str, Any]) -> str:
    payload = json.dumps([[int(i), int(j), p, round(float(c), 12)] for i, j, p, c in spec["terms"]]) \
        + json.dumps([round(float(t), 12) for t in spec["times"]])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_reference(spec: dict[str, Any]) -> dict[str, Any]:
    with open(os.path.join(REFERENCE_DIR, "index.json")) as handle:
        index = json.load(handle)
    instance_id = index.get(terms_digest(spec))
    if instance_id is None:
        raise KeyError("no reference for this spec (instance not in harness/data/references)")
    with open(os.path.join(REFERENCE_DIR, f"{instance_id}.json")) as handle:
        return json.load(handle)


def _tier_of(num_qubits: int) -> str | None:
    from harness.spec import tier_of
    return tier_of(num_qubits)


def _evaluate_one(args: tuple[list[Gate], int, int, int]) -> float:
    gates, n, m_pos, b_pos = args
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:  # then the OPENBLAS_NUM_THREADS default in harness/__init__.py is what we have
        return engines.exact_otoc(gates, n, m_pos, b_pos)
    # one BLAS thread per worker process: the workers already fill the cores
    with threadpool_limits(limits=1):
        return engines.exact_otoc(gates, n, m_pos, b_pos)


def score(spec: dict[str, Any], artifact: Any, workers: int | None = None) -> dict[str, Any]:
    parsed, result = parse_artifact(spec, artifact)
    if parsed is None:
        raise ValueError(f"score() called on an artifact that does not verify: {result['reason']}")
    reference = load_reference(spec)
    n = int(spec["num_qubits"])
    m_pos = parsed.initial_mapping[spec["measurement_site"]]
    times = list(range(len(spec["times"])))

    # X_B acts where the artifact says the butterfly spin sits after V(t_k); the measurement
    # spin is back at its initial position after V^dagger, so its position is fixed.
    jobs = [(parsed.circuits[k], n, m_pos, parsed.butterfly_positions[k]) for k in times]
    workers = MAX_WORKERS if workers is None else workers
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            values = list(pool.map(_evaluate_one, jobs))
    else:
        values = [_evaluate_one(job) for job in jobs]

    counts = [cost.echo_counts(parsed.circuits[k]) for k in times]
    signed = np.array(values) - np.array(reference["otoc"])
    max_cz = max(c["cz_count"] for c in counts)
    budget = spec.get("cz_budget")
    # The reference curve is returned for development tiers (0 and 1) so a logged score row
    # shows curve, reference and error side by side; it is withheld on tiers 2-3 (CONTEXT.md
    # §3), where a candidate is scored but the agent must not see the answer.
    tier = reference.get("tier") or _tier_of(n)
    show_reference = tier in ("tier0", "tier1")
    return {
        "times": [float(t) for t in spec["times"]],
        "reference_otoc": [float(v) for v in reference["otoc"]] if show_reference else None,
        "rmse": float(np.sqrt(np.mean(signed ** 2))),
        "mean_abs": float(np.mean(np.abs(signed))),
        "max_abs": float(np.max(np.abs(signed))),
        "signed_errors": [float(x) for x in signed],
        "otoc": [float(v) for v in values],
        "cz_count": int(max_cz),                       # the budget applies per circuit: the largest one
        "cz_per_time": [int(c["cz_count"]) for c in counts],
        "two_qubit_count": int(max(c["two_qubit_count"] for c in counts)),
        "two_qubit_per_time": [int(c["two_qubit_count"]) for c in counts],
        "over_budget": bool(budget is not None and max_cz > int(budget)),
        "sampling_se": 0.0,
        "regime": "exact",
    }
