"""Circuit-building helpers shared by the baselines and offered to candidates.

Everything here produces cirq circuits on `cirq.LineQubit(p)` chain positions, in the artifact
format of `harness.artifact`. Nothing here is required: a candidate may build circuits any way
it likes. It exists so that the standard constructions -- product formulas of orders 1, 2, 4
(otoc-core's `get_trotter_suzuki_circuit`), the brick-wall swap network with fused gates
(arXiv:2510.19550 Supplement §VIII.B-C), and the seven term orderings of the OTOC error
project -- are the same objects everywhere.

Conventions: a Pauli term `(i, j, "XX", c)` contributes `exp(-i c dt X_i X_j)` to one
first-order step of duration `dt`, i.e. otoc-core's `Gate(theta = 2 c dt)` with
`R = exp(-i theta/2 P)`. `spin_position[s]` is where spin `s` sits on the chain.
"""
from __future__ import annotations

import json
from typing import Any, Sequence

import cirq
import numpy as np
from openfermion import QubitOperator

from otoc_core.circuits import get_trotter_suzuki_circuit

from harness.vendor.gen_orderings import orderings as _orderings

PAULI = {"X": np.array([[0, 1], [1, 0]], dtype=complex),
         "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
         "Z": np.array([[1, 0], [0, -1]], dtype=complex)}
SWAP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex)


# ------------------------------------------------------------------ Hamiltonian bookkeeping
def coupling_matrix_from_terms(terms: Sequence[Sequence], num_qubits: int) -> np.ndarray:
    """Recover the symmetric coupling matrix d_ij from the spec's term list (inverse of the
    database convention: het -> ZZ +d, hom -> YY +d / XX -d)."""
    matrix = np.zeros((num_qubits, num_qubits))
    for i, j, pauli, coeff in terms:
        if pauli == "ZZ" or pauli == "YY":
            matrix[i, j] = matrix[j, i] = coeff
    return matrix


def term_orderings(terms: Sequence[Sequence], num_qubits: int, num_carbons: int = 2) -> dict[str, list[list]]:
    """The OTOC error project's orderings, each a list of groups of (i, j, pauli, coeff):
    mincoloring (XYZ layers), mincoloring_xzy, mincoloring_zxy, descending, ascending,
    interaction_descending, interaction_ascending, swapnet."""
    return _orderings(coupling_matrix_from_terms(terms, num_qubits), nc=num_carbons, tiebreak="yx")


def layers_as_qubit_operators(groups: Sequence[Sequence[Sequence]]) -> list[QubitOperator]:
    layers = []
    for group in groups:
        layer = QubitOperator()
        for i, j, pauli, coeff in group:
            layer += QubitOperator(f"{pauli[0]}{i} {pauli[1]}{j}", coeff)
        layers.append(layer)
    return layers


# ------------------------------------------------------------------ elementary gates
def pauli_rotation(pauli: str, theta: float) -> np.ndarray:
    """exp(-i theta/2 P) for a one- or two-letter Pauli string P."""
    generator = PAULI[pauli[0]] if len(pauli) == 1 else np.kron(PAULI[pauli[0]], PAULI[pauli[1]])
    dim = generator.shape[0]
    return np.cos(theta / 2) * np.eye(dim) - 1j * np.sin(theta / 2) * generator


# ------------------------------------------------------------------ product formulas, all-to-all
def trotter_circuit(groups: Sequence[Sequence[Sequence]], dt: float, steps: int, order: int,
                    spin_position: Sequence[int]) -> cirq.Circuit:
    """`steps` steps of the order-`order` Trotter-Suzuki formula built by otoc-core, laid on the
    chain by `spin_position`. Two-qubit rotations between spins that are NOT adjacent on the
    chain are emitted as-is and will be rejected by the referee; use `swap_network_circuit`
    or your own routing for a valid artifact. This builder is for the all-to-all constructions
    (baselines that assume adjacency, tests, and the exact engine cross-checks)."""
    step = get_trotter_suzuki_circuit(layers_as_qubit_operators(groups), dt, order=order)
    operations = []
    for _ in range(steps):
        for gate in step:
            (pauli_string, _), = gate.generator.terms.items()
            sites = [s for s, _ in pauli_string]
            pauli = "".join(p for _, p in pauli_string)
            qubits = [cirq.LineQubit(spin_position[s]) for s in sites]
            operations.append(cirq.MatrixGate(pauli_rotation(pauli, gate.theta)).on(*qubits))
    return cirq.Circuit(operations)


# ------------------------------------------------------------------ brick-wall swap network
def swap_network_rounds(num_qubits: int) -> list[list[tuple[int, int]]]:
    """Odd-even transposition network: N rounds of disjoint adjacent pairs; after all rounds every
    pair has been adjacent exactly once and the order is reversed."""
    rounds = []
    for r in range(num_qubits):
        start = r % 2
        rounds.append([(p, p + 1) for p in range(start, num_qubits - 1, 2)])
    return rounds


def swap_network_step(terms: Sequence[Sequence], dt: float, spin_position: Sequence[int],
                      scale: float = 1.0) -> tuple[list[cirq.Operation], list[int]]:
    """One first-order Trotter step of all pair interactions as a brick-wall swap network with
    each SWAP fused into the interaction it accompanies (Supplement §VIII.C):
        gate(p, p+1) = SWAP . exp(-i dt (c_XX X X + c_YY Y Y + c_ZZ Z Z))  on the pair of spins
    currently at positions p, p+1. Returns the operations and the spin order after the step
    (reversed). `scale` multiplies every coupling (a knob for the control search)."""
    num_qubits = len(spin_position)
    by_pair: dict[tuple[int, int], np.ndarray] = {}
    for i, j, pauli, coeff in terms:
        key = (min(i, j), max(i, j))
        by_pair.setdefault(key, np.zeros((4, 4), dtype=complex))
        by_pair[key] = by_pair[key] + scale * coeff * np.kron(PAULI[pauli[0]], PAULI[pauli[1]])
    order = list(np.argsort(spin_position))          # order[p] = spin at position p
    operations = []
    for pairs in swap_network_rounds(num_qubits):
        for p, q in pairs:
            spin_a, spin_b = order[p], order[q]
            key = (min(spin_a, spin_b), max(spin_a, spin_b))
            generator = by_pair.get(key, np.zeros((4, 4), dtype=complex))
            if spin_a > spin_b:  # the generator is written for (smaller spin, larger spin) = (p, q)
                generator = SWAP @ generator @ SWAP
            eigenvalues, vectors = np.linalg.eigh(generator)
            interaction = (vectors * np.exp(-1j * dt * eigenvalues)) @ vectors.conj().T
            operations.append(cirq.MatrixGate(SWAP @ interaction).on(cirq.LineQubit(p), cirq.LineQubit(q)))
            order[p], order[q] = order[q], order[p]
    new_position = [0] * num_qubits
    for p, spin in enumerate(order):
        new_position[spin] = p
    return operations, new_position


def swap_network_circuit(terms: Sequence[Sequence], dt: float, steps: int,
                         spin_position: Sequence[int], scale: float = 1.0) -> cirq.Circuit:
    """`steps` fused swap-network first-order steps; the spin order reverses every step, so odd
    step counts leave the spins reversed (the referee tracks positions only through the
    initial mapping and the gates, so this is fine: the OTOC is basis-independent)."""
    position = list(spin_position)
    operations: list[cirq.Operation] = []
    for _ in range(steps):
        step_ops, position = swap_network_step(terms, dt, position, scale)
        operations.extend(step_ops)
    return cirq.Circuit(operations)


# ------------------------------------------------------------------ artifact assembly
def circuit_json(circuit: cirq.Circuit) -> Any:
    return json.loads(cirq.to_json(circuit))


def make_artifact(initial_mapping: Sequence[int], circuits: Sequence[cirq.Circuit], note: str) -> dict[str, Any]:
    return {"initial_mapping": [int(p) for p in initial_mapping],
            "circuits": {str(k): circuit_json(c) for k, c in enumerate(circuits)},
            "note": note}
