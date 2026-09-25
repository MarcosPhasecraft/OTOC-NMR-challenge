"""The seed: Google's starting point (arXiv:2510.19550, Methods "Problem Specification").

First-order Trotter, every pair interaction once per step in brick-wall swap-network order with
the SWAP fused into the interaction gate, spins laid on the chain by time of flight. No
pruning, no rescaling, no merging: plain vanilla, so that everything an agent adds on top is
visible against it. The step count is the largest that fits the budget, each time point using
the number of steps that keeps dt = tmax / steps.
"""
from harness import circuits

CZ_PER_FUSED_GATE = 3


def steps_for_budget(spec) -> int:
    n = spec["num_qubits"]
    cz_per_step = 2 * CZ_PER_FUSED_GATE * n * (n - 1) // 2      # echo: forward + backward
    budget = spec.get("cz_budget")
    if budget is None:
        return 8
    return max(1, int(budget) // cz_per_step)


def generate(spec):
    n = spec["num_qubits"]
    mapping = circuits.time_of_flight_mapping(spec["terms"], n, spec["measurement_site"], spec["butterfly_site"])
    steps = steps_for_budget(spec)
    tmax = spec["times"][-1]
    dt = tmax / steps
    circs = [circuits.fused_network_circuit(spec["terms"], dt, max(1, round(t / dt)), mapping, order=1)
             for t in spec["times"]]
    return circuits.make_artifact(mapping, circs, f"seed: first-order fused swap network, {steps} steps")
