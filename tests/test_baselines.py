"""The frozen baselines: valid artifacts, the documented costs, and convergence."""
import numpy as np
import pytest

from baselines import fused_p2, fused_p4, seed_p1
from harness import circuits, spec
from harness.artifact import verify
from harness.score import score

INSTANCE = "instance_4_d_5"   # N = 10


@pytest.fixture(scope="module")
def instance_spec():
    return spec.build_spec(INSTANCE)


def with_budget(instance_spec, budget):
    return {**instance_spec, "cz_budget": budget}


def test_time_of_flight_mapping_is_a_permutation_with_measurement_first(instance_spec):
    n = instance_spec["num_qubits"]
    mapping = circuits.time_of_flight_mapping(instance_spec["terms"], n)
    assert sorted(mapping) == list(range(n))
    assert mapping[0] == 0


def test_seed_costs_exactly_3n_n_minus_1_per_step_and_respects_budget(instance_spec):
    n = instance_spec["num_qubits"]
    per_step = 3 * n * (n - 1)
    for steps in (1, 2, 3):
        s = with_budget(instance_spec, per_step * steps + 5)      # just above `steps` steps
        art = seed_p1.generate(s)
        assert verify(s, art)["passed"]
        result = score(s, art, workers=1)
        assert result["cz_count"] == per_step * steps
        assert result["over_budget"] is False


def test_higher_orders_are_valid_and_cost_as_documented(instance_spec):
    n = instance_spec["num_qubits"]
    per_step = 3 * n * (n - 1)
    s2 = with_budget(instance_spec, 2 * per_step)
    r2 = score(s2, fused_p2.generate(s2), workers=1)
    assert r2["cz_count"] == 2 * per_step and not r2["over_budget"]
    s4 = with_budget(instance_spec, 10 * per_step)
    r4 = score(s4, fused_p4.generate(s4), workers=1)
    assert r4["cz_count"] == 10 * per_step and not r4["over_budget"]
    # below one step of its own the baseline still returns one step, flagged over budget
    tight = with_budget(instance_spec, per_step)
    assert score(tight, fused_p4.generate(tight), workers=1)["over_budget"] is True


def test_strang_step_restores_spin_order_and_is_second_order(instance_spec):
    """A Strang step's mirrored half retraces the forward half, so the chain order is restored;
    and halving dt cuts the error by ~4x where first order cuts it by ~2x."""
    n = instance_spec["num_qubits"]
    mapping = list(range(n))
    tmax = instance_spec["times"][-1]

    def rmse(order, steps):
        dt = tmax / steps
        circs = [circuits.fused_network_circuit(instance_spec["terms"], dt, max(1, round(t / dt)), mapping, order)
                 for t in instance_spec["times"]]
        return score(instance_spec, circuits.make_artifact(mapping, circs, ""), workers=1)["rmse"]

    e2_8, e2_16 = rmse(2, 8), rmse(2, 16)
    assert e2_16 < e2_8 / 2.5
    e1_8, e1_16 = rmse(1, 8), rmse(1, 16)
    assert e2_16 < e1_16
