"""Second-order (Strang) fused swap network, time-of-flight layout, no other changes.
An order-2 step is a half-step pass followed by its reverse, so it costs 2x a seed step;
the step count is the largest that fits the budget."""
from harness import circuits

CZ_PER_FUSED_GATE = 3


def generate(spec):
    n = spec["num_qubits"]
    mapping = circuits.time_of_flight_mapping(spec["terms"], n, spec["measurement_site"], spec["butterfly_site"])
    cz_per_step = 2 * 2 * CZ_PER_FUSED_GATE * n * (n - 1) // 2
    budget = spec.get("cz_budget")
    steps = 4 if budget is None else max(1, int(budget) // cz_per_step)
    return circuits.network_artifact(spec["terms"], spec["times"], steps, mapping, spec["butterfly_site"],
                                     2, f"second-order fused swap network, {steps} steps")
