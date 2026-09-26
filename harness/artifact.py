"""The artifact: what a candidate returns, and `verify` (CONTEXT.md §4-§5).

    artifact = {
        "initial_mapping": [int],                 # spin s sits at chain position initial_mapping[s]
        "circuits": {"0": <circuit>, ..., "7": <circuit>},   # forward V(t_k) per time index
        "butterfly_positions": [int],             # optional: chain position of the butterfly spin
                                                  # after V(t_k), per time index (see below)
        "note": str,                              # free text, never read by the referee
    }

A circuit is a gate list:

    {"gates": [[positions, matrix], ...]}
        positions: [p] or [p, p+1]            chain positions (two-qubit gates on adjacent ones)
        matrix:    32 (or 8) floats           the unitary, row-major, [re, im] per entry, in the
                                              basis where the first position is the more
                                              significant bit (|p p+1>)

About 500 bytes per gate. A cirq circuit serialised with `cirq.to_json` on `cirq.LineQubit(p)`
qubits is accepted too (`harness.circuits.circuit_json` converts one to the gate list), but
at ~1 KB per gate it is 2-3x larger and far slower to parse; for thousands of gates use the
gate list. Every gate must be unitary to 1e-8 and finite. `verify` never raises: a malformed or
adversarial artifact is an expected input. It never repairs anything either -- non-unitary,
non-adjacent or too-wide gates are rejected, not projected, routed or decomposed (CLAUDE.md,
"The referee never edits a submission").

The echo is V, then X on the butterfly spin, then V^dagger. A circuit may move spins around
(a swap network reverses the chain every pass), so the artifact says where the butterfly spin
sits when V ends; omitted, it is taken to be where `initial_mapping` put it. The measurement
spin needs no such entry: V^dagger returns every spin to its initial position.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import cirq
import numpy as np

UNITARITY_TOLERANCE = 1e-8


@dataclass(frozen=True)
class Gate:
    """One gate as the referee sees it: chain positions (ascending) and its unitary."""
    positions: tuple[int, ...]
    unitary: np.ndarray


@dataclass(frozen=True)
class ParsedArtifact:
    initial_mapping: tuple[int, ...]
    circuits: dict[int, list[Gate]]   # time index -> gate list, circuit order
    butterfly_positions: tuple[int, ...]   # per time index, the position X_B acts on


def _fail(checks: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"passed": False, "checks": checks, "reason": reason}


def _check_gate(index: int, positions: tuple[int, ...], matrix: np.ndarray, num_qubits: int) -> str | None:
    if len(positions) not in (1, 2):
        return f"gate {index}: acts on {len(positions)} qubits; only 1- and 2-qubit gates are allowed"
    if any(p < 0 or p >= num_qubits for p in positions):
        return f"gate {index}: chain position out of range {positions}"
    if len(positions) == 2 and positions[1] - positions[0] != 1:
        return f"gate {index}: two-qubit gate on non-adjacent positions {positions}"
    dim = 2 ** len(positions)
    if matrix.shape != (dim, dim) or not np.all(np.isfinite(matrix)):
        return f"gate {index}: matrix must be finite and {dim}x{dim}"
    if np.linalg.norm(matrix.conj().T @ matrix - np.eye(dim)) > UNITARITY_TOLERANCE:
        return f"gate {index}: not unitary (||U^dagger U - I|| > {UNITARITY_TOLERANCE})"
    return None


def parse_gate_list(circuit: Any, num_qubits: int) -> tuple[list[Gate] | None, str | None]:
    """The gate-list format (module docstring) into referee gates."""
    entries = circuit.get("gates")
    if not isinstance(entries, list):
        return None, "gate list: 'gates' must be a list"
    gates: list[Gate] = []
    for index, entry in enumerate(entries):
        if not (isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], list)
                and all(isinstance(p, int) and not isinstance(p, bool) for p in entry[0])
                and isinstance(entry[1], list)):
            return None, f"gate {index}: expected [positions, matrix]"
        positions = tuple(entry[0])
        if len(positions) not in (1, 2):
            return None, f"gate {index}: acts on {len(positions)} qubits; only 1- and 2-qubit gates are allowed"
        if len(positions) == 2 and positions[0] > positions[1]:
            return None, f"gate {index}: positions must be ascending {positions}"
        dim = 2 ** len(positions)
        try:
            values = np.asarray(entry[1], dtype=float)
        except (TypeError, ValueError):
            return None, f"gate {index}: matrix entries must be numbers"
        if values.shape != (2 * dim * dim,):
            return None, f"gate {index}: matrix must be {2 * dim * dim} floats ([re, im] x {dim}x{dim} row-major)"
        matrix = (values[0::2] + 1j * values[1::2]).reshape(dim, dim)
        reason = _check_gate(index, positions, matrix, num_qubits)
        if reason:
            return None, reason
        gates.append(Gate(positions, matrix))
    return gates, None


def parse_circuit(circuit_json: Any, num_qubits: int) -> tuple[list[Gate] | None, str | None]:
    """Turn one circuit (gate list, or cirq JSON) into referee gates; returns (gates, None) or
    (None, reason)."""
    if isinstance(circuit_json, dict) and "gates" in circuit_json and "cirq_type" not in circuit_json:
        return parse_gate_list(circuit_json, num_qubits)
    try:
        circuit = cirq.read_json(json_text=json.dumps(circuit_json))
    except Exception as error:  # noqa: BLE001 -- anything cirq throws is "not a circuit"
        return None, f"circuit JSON does not parse as a cirq object: {type(error).__name__}"
    if not isinstance(circuit, cirq.Circuit):
        return None, f"expected a cirq.Circuit, got {type(circuit).__name__}"
    gates: list[Gate] = []
    for index, operation in enumerate(circuit.all_operations()):
        qubits = operation.qubits
        if not all(isinstance(q, cirq.LineQubit) for q in qubits):
            return None, f"operation {index}: qubits must be cirq.LineQubit chain positions"
        positions = tuple(sorted(q.x for q in qubits))
        if cirq.is_measurement(operation) or not cirq.has_unitary(operation):
            return None, f"operation {index}: no unitary (measurement, channel or symbolic gate)"
        try:
            matrix = np.asarray(cirq.unitary(operation), dtype=complex)
        except Exception as error:  # noqa: BLE001
            return None, f"operation {index}: unitary could not be extracted: {type(error).__name__}"
        # cirq orders the unitary by the operation's own qubit order; put it in ascending position order
        if len(positions) == 2 and matrix.shape == (4, 4) and qubits[0].x > qubits[1].x:
            swap = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
            matrix = swap @ matrix @ swap
        reason = _check_gate(index, positions, matrix, num_qubits)
        if reason:
            return None, reason
        gates.append(Gate(positions, matrix))
    return gates, None


def parse_artifact(spec: dict[str, Any], artifact: Any) -> tuple[ParsedArtifact | None, dict[str, Any]]:
    """Full structural check. Returns (parsed, result) where result is what `verify` reports."""
    checks: dict[str, Any] = {}
    if not isinstance(artifact, dict):
        return None, _fail(checks, "artifact must be a JSON object")
    n = int(spec["num_qubits"])
    mapping = artifact.get("initial_mapping")
    checks["initial_mapping_is_permutation"] = (
        isinstance(mapping, list) and len(mapping) == n and all(isinstance(m, int) and not isinstance(m, bool) for m in mapping)
        and sorted(mapping) == list(range(n)))
    if not checks["initial_mapping_is_permutation"]:
        return None, _fail(checks, f"initial_mapping must be a permutation of 0..{n - 1}")
    circuits = artifact.get("circuits")
    expected = [str(k) for k in range(len(spec["times"]))]
    checks["all_times_present"] = isinstance(circuits, dict) and sorted(circuits, key=str) == sorted(expected)
    if not checks["all_times_present"]:
        return None, _fail(checks, f"circuits must have exactly the keys {expected}")
    parsed: dict[int, list[Gate]] = {}
    for key in expected:
        gates, reason = parse_circuit(circuits[key], n)
        if gates is None:
            checks[f"circuit_{key}"] = reason
            return None, _fail(checks, f"circuit {key}: {reason}")
        checks[f"circuit_{key}"] = f"ok ({len(gates)} gates)"
        parsed[int(key)] = gates
    default_b = mapping[int(spec["butterfly_site"])]
    positions = artifact.get("butterfly_positions", [default_b] * len(expected))
    checks["butterfly_positions_valid"] = (
        isinstance(positions, list) and len(positions) == len(expected)
        and all(isinstance(b, int) and not isinstance(b, bool) and 0 <= b < n for b in positions))
    if not checks["butterfly_positions_valid"]:
        return None, _fail(checks, f"butterfly_positions must be {len(expected)} chain positions in 0..{n - 1}")
    checks["note_is_text"] = isinstance(artifact.get("note", ""), str)
    return (ParsedArtifact(tuple(mapping), parsed, tuple(positions)),
            {"passed": True, "checks": checks, "reason": ""})


def verify(spec: dict[str, Any], artifact: Any) -> dict[str, Any]:
    """Structural validity only. Budget compliance is checked in `score`, which reports
    `over_budget` rather than failing verification, so an over-budget circuit is still a
    recorded (invalid-at-this-budget) point. Never raises."""
    try:
        _, result = parse_artifact(spec, artifact)
        return result
    except Exception as error:  # noqa: BLE001 -- a verifier that raises is a verifier that can be crashed
        return _fail({}, f"internal error while verifying: {type(error).__name__}: {error}")
