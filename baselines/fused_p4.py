"""Fourth-order (Suzuki) fused swap network, time-of-flight layout. An order-4 step is five
Strang steps, 10x a seed step in CZs; the step count is the largest that fits the budget.
At small budgets no order-4 step fits, and the baseline then submits one step anyway, which
the referee records as over budget (a valid, recorded, invalid-at-this-budget point)."""
from harness import circuits

CZ_PER_FUSED_GATE = 3


def generate(spec):
    n = spec["num_qubits"]
    mapping = circuits.time_of_flight_mapping(spec["terms"], n, spec["measurement_site"], spec["butterfly_site"])
    cz_per_step = 10 * 2 * CZ_PER_FUSED_GATE * n * (n - 1) // 2
    budget = spec.get("cz_budget")
    steps = 2 if budget is None else max(1, int(budget) // cz_per_step)
    dt = spec["times"][-1] / steps
    circs = [circuits.fused_network_circuit(spec["terms"], dt, max(1, round(t / dt)), mapping, order=4)
             for t in spec["times"]]
    return circuits.make_artifact(mapping, circs, f"fourth-order fused swap network, {steps} steps")
