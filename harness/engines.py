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

The gate pass runs in single precision (GATE_DTYPE) and the final product in double.

W is built by applying the submitted gates to the 2^(n-1) basis states of that subspace (half
the work of forming V), B W is a row permutation, and the last step is one BLAS product. Cost
is O(gates * 4^n / 2) for the gates plus O(8^n / 4) for the product: ~0.1 s at n = 10 and
a few seconds at n = 12 per seed step and time point on one core. `MAX_EXACT_QUBITS` keeps it where that is sane.

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
    most significant index. Returns a new array.

    For a gate on positions (p, p+1) the state reshapes to (2^p, 4, rest) and the gate is one
    batched 4x4 matmul over the leading axis (BLAS, 5-10x faster than the equivalent einsum
    at n = 12). The general einsum path is kept for non-adjacent positions, which `verify`
    never lets through but the tests may use."""
    cols = state.shape[1]
    if len(gate.positions) == 1:
        p = gate.positions[0]
        view = state.reshape(2 ** p, 2, -1)
        return np.matmul(gate.unitary, view).reshape(2 ** n, cols)
    p, q = gate.positions
    if q == p + 1:
        view = state.reshape(2 ** p, 4, -1)
        return np.matmul(gate.unitary, view).reshape(2 ** n, cols)
    view = state.reshape(2 ** p, 2, 2 ** (q - p - 1), 2, 2 ** (n - q - 1), cols)
    unitary = gate.unitary.reshape(2, 2, 2, 2)
    out = np.einsum("ijkl,akblcX->aibjcX", unitary, view, optimize=True)
    return out.reshape(2 ** n, cols)


def plus_subspace_basis(n: int, measurement_position: int) -> np.ndarray:
    """The 2^n x 2^(n-1) matrix whose columns are sqrt(2) |+>_m (x) |x> over bath basis states
    x: left unnormalised (entries 0 and 1, exact in any precision); `exact_otoc` accounts for
    the factor in its final formula."""
    dim, half = 2 ** n, 2 ** (n - 1)
    a, c = 2 ** measurement_position, 2 ** (n - measurement_position - 1)
    basis = np.eye(half, dtype=complex).reshape(a, c, half)
    w = np.empty((a, 2, c, half), dtype=complex)
    w[:, 0, :, :] = basis
    w[:, 1, :, :] = basis
    return w.reshape(dim, half)


def fuse_gates(gates: list[Gate]) -> list[Gate]:
    """Merge runs of consecutive gates on the same qubits into one gate before simulation:
    two-qubit gates on the same pair multiply, and a single-qubit gate is absorbed into an
    adjacent two-qubit gate on a pair that contains its position. Mathematically the identity
    (the product of the same unitaries in the same order); it only reduces the number of
    passes over the state. Never used for the cost count, which is taken on the submitted
    gates (CONTEXT.md §5-§6)."""
    fused: list[Gate] = []
    for gate in gates:
        if fused:
            last = fused[-1]
            if last.positions == gate.positions:
                fused[-1] = Gate(last.positions, gate.unitary @ last.unitary)
                continue
            if len(last.positions) == 2 and len(gate.positions) == 1 and gate.positions[0] in last.positions:
                fused[-1] = Gate(last.positions, _lift(gate, last.positions) @ last.unitary)
                continue
            if len(last.positions) == 1 and len(gate.positions) == 2 and last.positions[0] in gate.positions:
                fused[-1] = Gate(gate.positions, gate.unitary @ _lift(last, gate.positions))
                continue
        fused.append(gate)
    return fused


def _lift(gate: Gate, pair: tuple[int, int]) -> np.ndarray:
    """A single-qubit unitary as a 4x4 on the ordered pair (kron order: first position is the
    more significant index, matching `apply_gate`)."""
    identity = np.eye(2, dtype=complex)
    return np.kron(gate.unitary, identity) if gate.positions[0] == pair[0] else np.kron(identity, gate.unitary)


# The gate pass runs in single precision: the state is a unitary image of a fixed basis, so
# rounding does not grow with the number of gates beyond a random walk of ~1e-7 per gate, and
# the score reads errors at the 1e-3 level. Validated against double precision in the tests
# (agreement to 1e-5 on thousands of gates); the final Frobenius product is done in double.
GATE_DTYPE = np.complex64


def exact_otoc(gates: list[Gate], n: int, measurement_position: int, butterfly_position: int,
               dtype=None, fuse: bool = True) -> float:
    """C = 2^-n Tr[B M(t) B M(t)] for the submitted circuit. Exact."""
    if n > MAX_EXACT_QUBITS:
        raise ValueError(f"exact engine refuses n={n} > {MAX_EXACT_QUBITS}")
    dtype = GATE_DTYPE if dtype is None else dtype
    w = plus_subspace_basis(n, measurement_position).astype(dtype)
    for gate in (fuse_gates(gates) if fuse else gates):
        w = apply_gate(w, Gate(gate.positions, gate.unitary.astype(dtype)), n)
    w = w.astype(np.complex128)
    rows = np.arange(2 ** n) ^ (2 ** (n - butterfly_position - 1))   # B = X_b permutes rows
    overlap = w.conj().T @ w[rows, :]
    # (4 / 2^n) ||W^dagger B W||_F^2 - 1 with W normalised; the basis carries a factor sqrt(2)
    # per column, i.e. 4 on the squared norm, hence 1 / 2^n here.
    return float(np.sum(np.abs(overlap) ** 2) / 2 ** n - 1.0)


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
