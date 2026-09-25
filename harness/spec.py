"""Instances: the manifest, `build_spec` and `parse_instances` (the toolkit contract's first two
functions; see TOOLKIT.md).

An instance is one converged protein cluster from the Google-generated dataset, identified by
its database name (`instance_4_d_5`). `data/manifest.json` lists every instance that has a
`tmax` with its size and tier; it is the only place instances are added or removed
(CLAUDE.md, "Tiers and access").

The spec is everything a candidate is allowed to know (CONTEXT.md §4): the Hamiltonian as
Pauli terms in the database convention, the chain, the observable sites, the time grid and
the CZ budget. It carries no instance name, no reference values and no hardness metadata.
"""
from __future__ import annotations

import csv
import json
import os
import re
from typing import Any

import numpy as np

from harness.vendor.gen_orderings import base_terms

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")
NUM_TIMES = 8
MEASUREMENT_SITE = 0
BUTTERFLY_SITE = 1
NUM_CARBONS = 2

#: Tier boundaries by qubit count (CONTEXT.md §3).
TIERS = {"tier0": (10, 12), "tier1": (13, 15), "tier2": (16, 16), "tier3": (17, 25)}


def tier_of(num_qubits: int) -> str | None:
    for name, (lo, hi) in TIERS.items():
        if lo <= num_qubits <= hi:
            return name
    return None


def build_manifest(tmax_csv: str | None = None) -> dict[str, dict[str, Any]]:
    """Rebuild the manifest from `data/tmax_table.csv`: every instance with a `tmax`.

    The manifest is committed; this is how it is regenerated when the tmax table changes.
    Instances below N = 10 (three N = 6 cases) have no tier and are listed with `tier: null`.
    """
    tmax_csv = tmax_csv or os.path.join(DATA_DIR, "tmax_table.csv")
    manifest: dict[str, dict[str, Any]] = {}
    with open(tmax_csv) as handle:
        for row in csv.DictReader(handle):
            if row["outcome"] != "crossed" or not row["tmax"]:
                continue
            num_qubits = int(row["N"])
            manifest[row["instance"]] = {
                "num_qubits": num_qubits,
                "tmax": float(row["tmax"]),
                "tier": tier_of(num_qubits),
            }
    return dict(sorted(manifest.items()))


def load_manifest() -> dict[str, dict[str, Any]]:
    with open(MANIFEST_PATH) as handle:
        return json.load(handle)


def load_coupling_matrix(instance_id: str) -> np.ndarray:
    path = os.path.join(DATA_DIR, "instances", instance_id, "hamiltonian_projected.npy")
    if not os.path.isfile(path):
        raise KeyError(f"unknown instance {instance_id!r}: no coupling matrix at {path}")
    matrix = np.load(path)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"{instance_id}: coupling matrix must be square, got {matrix.shape}")
    if not np.allclose(matrix, matrix.T):
        raise ValueError(f"{instance_id}: coupling matrix is not symmetric")
    return matrix


def hamiltonian_terms(matrix: np.ndarray) -> list[list]:
    """Pauli terms in the database convention: het bond -> ZZ +d, hom bond -> XX -d, YY +d.

    Delegates to the vendored `gen_orderings.base_terms` so the sign convention is the one
    every dataset in `otoc-trotter-error-bounds` was produced with. Returned as plain lists so
    the spec is JSON-serialisable.
    """
    return [[int(i), int(j), pauli, float(coeff)]
            for i, j, pauli, coeff in base_terms(matrix, nc=NUM_CARBONS, tiebreak="yx")]


def time_grid(tmax: float, num_times: int = NUM_TIMES) -> list[float]:
    return [float(tmax * k / num_times) for k in range(1, num_times + 1)]


def build_spec(instance_id: str, cz_budget: int | None = None) -> dict[str, Any]:
    """The full description of one instance, as handed to a candidate.

    `cz_budget` is set by the referee per budget on the ladder; `None` means unconstrained
    (used only for baseline calibration and tests).
    """
    entry = load_manifest().get(instance_id)
    if entry is None:
        raise KeyError(f"{instance_id!r} is not in data/manifest.json")
    matrix = load_coupling_matrix(instance_id)
    num_qubits = matrix.shape[0]
    if num_qubits != entry["num_qubits"]:
        raise ValueError(f"{instance_id}: manifest says N={entry['num_qubits']}, matrix is {num_qubits}")
    return {
        "num_qubits": num_qubits,
        "chain": list(range(num_qubits)),
        "terms": hamiltonian_terms(matrix),
        "measurement_site": MEASUREMENT_SITE,
        "butterfly_site": BUTTERFLY_SITE,
        "times": time_grid(entry["tmax"]),
        "cz_budget": cz_budget,
    }


_SIZE = re.compile(r"^N=(\d+)$")


def parse_instances(claim: str) -> list[str]:
    """The sizes grammar: a comma-separated mix of instance ids, `N=<int>` and tier names.

    Returns instance ids in manifest order, deduplicated. Unknown tokens raise, so a typo
    cannot look like an empty claim.
    """
    manifest = load_manifest()
    chosen: list[str] = []
    for token in (t.strip() for t in claim.split(",")):
        if not token:
            continue
        if token in manifest:
            chosen.append(token)
        elif token in TIERS:
            chosen.extend(k for k, v in manifest.items() if v["tier"] == token)
        elif _SIZE.match(token):
            size = int(_SIZE.match(token).group(1))
            chosen.extend(k for k, v in manifest.items() if v["num_qubits"] == size)
        else:
            raise ValueError(f"unknown instance, size or tier: {token!r}")
    order = {k: i for i, k in enumerate(manifest)}
    return sorted(set(chosen), key=order.__getitem__)
