"""Cost model (CONTEXT.md §6): CZ count of the echo built from the circuit as submitted.

Each two-qubit gate is KAK-decomposed *to count* how many CZs it is worth on a CZ-native chain
(0-3). The decomposition changes nothing: the simulated gate is the submitted matrix. Single-
qubit gates cost 0. The echo is V, the butterfly (single-qubit) and V^dagger, so its cost is
twice V's; `echo_cz_count` is what the budget applies to.

Settings are pinned: `cirq.two_qubit_matrix_to_cz_operations` with `allow_partial_czs=False`
and cirq's default tolerance; cirq itself is pinned in requirements.txt. Results are memoised
by the gate matrix (rounded to 1e-12) because a Trotter circuit repeats the same few gates.
"""
from __future__ import annotations

from functools import lru_cache

import cirq
import numpy as np

from harness.artifact import Gate

_Q0, _Q1 = cirq.LineQubit.range(2)


@lru_cache(maxsize=65536)
def _cz_count_cached(key: bytes) -> int:
    matrix = np.frombuffer(key, dtype=complex).reshape(4, 4)
    operations = cirq.two_qubit_matrix_to_cz_operations(_Q0, _Q1, matrix, allow_partial_czs=False)
    return sum(1 for op in operations if isinstance(op.gate, cirq.CZPowGate))


def cz_count(gate: Gate) -> int:
    if len(gate.positions) == 1:
        return 0
    return _cz_count_cached(np.ascontiguousarray(np.round(gate.unitary, 12)).tobytes())


def forward_counts(gates: list[Gate]) -> dict[str, int]:
    two_qubit = [g for g in gates if len(g.positions) == 2]
    return {
        "cz_count": sum(cz_count(g) for g in two_qubit),
        "two_qubit_count": len(two_qubit),
        "one_qubit_count": len(gates) - len(two_qubit),
    }


def echo_counts(gates: list[Gate]) -> dict[str, int]:
    """Counts for V + butterfly + V^dagger; the butterfly is one single-qubit X."""
    forward = forward_counts(gates)
    return {
        "cz_count": 2 * forward["cz_count"],
        "two_qubit_count": 2 * forward["two_qubit_count"],
        "one_qubit_count": 2 * forward["one_qubit_count"] + 1,
    }
