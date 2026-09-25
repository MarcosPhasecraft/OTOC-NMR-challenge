"""Evaluate the OTOC of a submitted forward circuit (CONTEXT.md §2, §5).

The physical experiment the referee assembles around V is

    |+>_m (x) bath  --V--  X_b  --V^dagger--  measure X_m,

with m, b the chain positions of the measurement and butterfly spins under `initial_mapping`.
Averaged over the bath its expectation is exactly

    C = 2^-n Tr[ B M(t) B M(t) ],   M(t) = V M V^dagger,   M = X_m, B = X_b.

`exact_otoc` (tier 0) computes this with no sampling and no approximation of anything the
candidate did not submit. It uses M = 2 Pi - I with Pi the projector on |+>_m, so that
V M V^dagger = 2 W W^dagger - I with W = V restricted to the 2^(n-1)-dimensional |+>_m
subspace, and then

    C = (4 / 2^n) * || W^dagger B W ||_F^2  -  1.

W is built by applying the submitted gates to the 2^(n-1) basis states of that subspace (half
the work of forming V), B W is a row permutation, and the last step is one BLAS product. Cost
is O(gates * 4^n / 2) for the gates plus O(8^n / 4) for the product: 0.3 s at n = 10 and
~13 s at n = 12 per time point on one core. `MAX_EXACT_QUBITS` keeps it where that is sane.

`_dense_reference` is the plain M(t) = V M V^dagger route, kept for the tests: two
formulations of the same trace that agree to floating point.

`sampled_otoc` (tiers 1-3, Phase 1) is not implemented yet.
"""
from __future__ import annotations

import numpy as np

from harness.artifact import Gate

MAX_EXACT_QUBITS = 13


def apply_gate(state: np.ndarray, gate: Gate, n: int) -> np.ndarray:
    """Apply a gate to a batch of column states `state` of shape (2^n, cols); qubit 0 is the
    most significant index. Returns a new array."""
    cols = state.shape[1]
    if len(gate.positions) == 1:
        p = gate.positions[0]
        view = state.reshape(2 ** p, 2, 2 ** (n - p - 1), cols)
        out = np.einsum("ij,ajcX->aicX", gate.unitary, view, optimize=True)
        return out.reshape(2 ** n, cols)
    p, q = gate.positions
    view = state.reshape(2 ** p, 2, 2 ** (q - p - 1), 2, 2 ** (n - q - 1), cols)
    unitary = gate.unitary.reshape(2, 2, 2, 2)
    out = np.einsum("ijkl,akblcX->aibjcX", unitary, view, optimize=True)
    return out.reshape(2 ** n, cols)


def plus_subspace_basis(n: int, measurement_position: int) -> np.ndarray:
    """The 2^n x 2^(n-1) matrix whose columns are |+>_m (x) |x> over bath basis states x."""
    dim, half = 2 ** n, 2 ** (n - 1)
    a, c = 2 ** measurement_position, 2 ** (n - measurement_position - 1)
    basis = np.eye(half, dtype=complex).reshape(a, c, half) / np.sqrt(2.0)
    w = np.empty((a, 2, c, half), dtype=complex)
    w[:, 0, :, :] = basis
    w[:, 1, :, :] = basis
    return w.reshape(dim, half)


def exact_otoc(gates: list[Gate], n: int, measurement_position: int, butterfly_position: int) -> float:
    """C = 2^-n Tr[B M(t) B M(t)] for the submitted circuit. Exact."""
    if n > MAX_EXACT_QUBITS:
        raise ValueError(f"exact engine refuses n={n} > {MAX_EXACT_QUBITS}")
    w = plus_subspace_basis(n, measurement_position)
    for gate in gates:
        w = apply_gate(w, gate, n)
    rows = np.arange(2 ** n) ^ (2 ** (n - butterfly_position - 1))   # B = X_b permutes rows
    overlap = w.conj().T @ w[rows, :]
    return float(4.0 / 2 ** n * np.sum(np.abs(overlap) ** 2) - 1.0)


def _dense_reference(gates: list[Gate], n: int, measurement_position: int, butterfly_position: int) -> float:
    """The same trace via the dense M(t) = V M V^dagger; tests only."""
    dim = 2 ** n
    identity = np.eye(dim, dtype=complex)
    v = identity
    for gate in gates:
        v = apply_gate(v, gate, n)
    m_rows = np.arange(dim) ^ (2 ** (n - measurement_position - 1))
    evolved = v @ v.conj().T[m_rows, :]          # V (M V^dagger), M a row permutation of V^dagger
    b_rows = np.arange(dim) ^ (2 ** (n - butterfly_position - 1))
    product = evolved[b_rows, :]
    return float(np.real(np.sum(product * product.T) / dim))
