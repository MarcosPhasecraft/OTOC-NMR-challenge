"""
Tests toolkit/held_out.py against fixtures/fake_problem/.
"""
from pathlib import Path

from toolkit.held_out import check_generalizes
from toolkit.problem import load_problem

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def test_a_genuinely_uniform_rule_passes_everywhere():
    problem = _problem()

    def uniform_rule(spec):
        return [0, spec["target"]]

    report = check_generalizes(problem, uniform_rule, held_out_instances=[1, 50, 999])

    assert all(r["passed"] for r in report.values())
    assert set(report) == {1, 50, 999}


def test_a_lookup_table_fails_on_instances_it_does_not_cover():
    problem = _problem()
    table = {10: [3, 7], 20: [5, 15]}

    def cheat(spec):
        return table.get(spec["target"], [0, 0])

    report = check_generalizes(problem, cheat, held_out_instances=[10, 20, 30])

    assert report[10]["passed"] is True
    assert report[20]["passed"] is True
    assert report[30]["passed"] is False


def test_a_crash_on_one_instance_does_not_stop_the_rest_of_the_check():
    problem = _problem()

    def flaky(spec):
        if spec["target"] == 15:
            raise ValueError("not tuned for this one")
        return [0, spec["target"]]

    report = check_generalizes(problem, flaky, held_out_instances=[10, 15, 20])

    assert report[10]["passed"] is True
    assert report[15]["passed"] is False
    assert "not tuned for this one" in report[15]["checks"]["generate"]["error"]
    assert report[20]["passed"] is True


def test_a_build_spec_that_refuses_an_instance_does_not_abort_the_report():
    """
    A held-out id is by definition one nobody chose deliberately, so it is
    the likeliest place for a problem's own build_spec() to refuse a size
    it does not support. That used to raise straight out of the loop,
    discarding the instances already checked and never reaching the rest --
    contradicting TOOLKIT.md item 6's "sees every failure at once".
    """
    problem = _problem()
    original = problem.build_spec

    def picky(instance_id):
        if instance_id == 999:
            raise ValueError("unsupported size")
        return original(instance_id)

    problem.build_spec = picky

    report = check_generalizes(problem, lambda spec: [0, spec["target"]], [11, 999, 13])

    assert sorted(report) == [11, 13, 999]
    assert report[11]["passed"] is True
    assert report[13]["passed"] is True
    assert report[999]["passed"] is False
    assert "unsupported size" in report[999]["checks"]["generate"]["error"]
