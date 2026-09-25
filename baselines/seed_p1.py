"""The seed: Google's starting point (arXiv:2510.19550, Methods "Problem Specification").

First-order Trotter, every pair interaction once per step in brick-wall swap-network order with
the SWAP fused into the interaction gate, spins laid on the chain by time of flight. No
pruning, no rescaling, no merging: plain vanilla, so that everything an agent adds on top is
visible against it. The step count is the largest that fits the budget, each time point using
the step count closest to the common step size tmax / steps (`circuits.steps_per_time`).
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
    return circuits.network_artifact(spec["terms"], spec["times"], steps, mapping, spec["butterfly_site"],
                                     1, f"seed: first-order fused swap network, {steps} steps")
