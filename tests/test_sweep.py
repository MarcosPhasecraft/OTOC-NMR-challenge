"""The adaptive budget sweep (scripts/sweep.py): rung order, the stop rule, caching, failures."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sweep  # noqa: E402

from harness import spec  # noqa: E402


class FakeProblem:
    """rmse falls with the budget multiplier; the referee is not involved."""
    def __init__(self, rmse_of_mult):
        self.rmse_of_mult = rmse_of_mult

    def build_spec(self, cell):
        base, mult = spec.split_instance_id(cell)
        return {"cell": cell, "mult": mult, "cz_budget": int(1000 * mult), "target_rmse": 0.05}

    def verify(self, s, artifact):
        return {"passed": artifact.get("ok", True), "checks": {}, "reason": "" if artifact.get("ok", True) else "bad"}

    def score(self, s, artifact):
        return {"rmse": self.rmse_of_mult(s["mult"]), "cz_count": s["cz_budget"] - 1, "over_budget": False,
                "met_target": self.rmse_of_mult(s["mult"]) <= 0.05}


class FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, fp, name, cell):
        return self.data.get((fp, name, cell))

    def set(self, fp, name, cell, value):
        self.data[(fp, name, cell)] = value

    def forget(self, fp, name, cell):
        return self.data.pop((fp, name, cell), None) is not None


def generate_ok(path, s):
    return {"ok": True, "artifact": {"ok": True}}


def test_rungs_are_the_ladder_in_order():
    cells = sweep.rungs_of("instance_4_d_5")
    assert cells[0] == "instance_4_d_5@0.25" and cells[4] == "instance_4_d_5@1" and cells[-1] == "instance_4_d_5@8"
    assert len(cells) == len(spec.LADDER)


def test_stops_at_first_rung_meeting_target_but_not_below_x1():
    # target met from x0.5 on: still sweeps up to x1, skips the six rungs above it
    problem, cache = FakeProblem(lambda m: 0.2 / m / 10), FakeCache()
    r = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", generate_ok)
    assert [c.split("@")[1] for c in r["evaluated"]] == ["0.25", "0.3536", "0.5", "0.7071", "1"]
    assert len(r["skipped"]) == 6 and not r["failed"]
    # target met only from x2.83 on: sweeps up to that rung, skips x4 and above
    problem, cache = FakeProblem(lambda m: 0.13 / m), FakeCache()
    r = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", generate_ok)
    assert r["evaluated"][-1] == "instance_4_d_5@2.8284" and len(r["skipped"]) == 3
    # never met: the whole ladder is evaluated
    problem, cache = FakeProblem(lambda m: 0.5), FakeCache()
    r = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", generate_ok)
    assert len(r["evaluated"]) == len(spec.LADDER) and not r["skipped"]


def test_full_ladder_and_cached_cells():
    problem, cache = FakeProblem(lambda m: 0.2 / m / 10), FakeCache()
    r = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", generate_ok, force_full=True)
    assert len(r["evaluated"]) == len(spec.LADDER)
    again = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", generate_ok)
    assert not again["evaluated"] and len(again["cached"]) == 5 and len(again["skipped"]) == 6


def test_failures_are_reported_not_cached_and_do_not_stop_the_sweep():
    problem, cache = FakeProblem(lambda m: 0.5), FakeCache()
    calls = []

    def flaky(path, s):
        calls.append(s["cell"])
        if s["mult"] == 1.0:
            return {"ok": False, "error": "timeout"}
        if s["mult"] == 2.0:
            return {"ok": True, "artifact": {"ok": False}}
        return {"ok": True, "artifact": {"ok": True}}

    r = sweep.sweep_instance(problem, cache, "fp", "e", "g.py", "instance_4_d_5", flaky)
    assert [f["cell"].split("@")[1] for f in r["failed"]] == ["1", "2"]
    assert len(r["evaluated"]) == len(spec.LADDER) - 2 and len(calls) == len(spec.LADDER)
    assert cache.get("fp", "e", "instance_4_d_5@1") is None


def test_promotion_rule():
    import evaluate_candidate as ec
    assert ec.decide_promotion(0.8, 1.0, []) is True
    assert ec.decide_promotion(1.0, 1.0, []) is False          # must beat the seed, not tie it
    assert ec.decide_promotion(None, 1.0, []) is False         # missed the target somewhere
    assert ec.decide_promotion(0.5, 1.0, [{"cell": "x"}]) is False   # a failed cell is never promoted
    assert ec.decide_promotion(1.1, 1.2, []) is True           # a looser threshold, if the loop wants one
