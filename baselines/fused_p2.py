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
    dt = spec["times"][-1] / steps
    circs = [circuits.fused_network_circuit(spec["terms"], dt, max(1, round(t / dt)), mapping, order=2)
             for t in spec["times"]]
    return circuits.make_artifact(mapping, circs, f"second-order fused swap network, {steps} steps")
