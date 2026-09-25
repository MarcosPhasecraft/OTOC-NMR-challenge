"""
Validates the fake_problem fixture itself -- the "known answers" every
later toolkit test builds on. Mirrors PLAYBOOK.md's own Stage-1 order:
analytic sanity first, then rejection cases.

Loaded via toolkit.problem.load_problem(), the same way every other
toolkit piece will access a problem -- this exercises the loader on
every run here too, on top of test_problem.py's own dedicated tests.
"""
import importlib.util
from pathlib import Path

from toolkit.problem import load_problem

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def _load_generate(path):
    module_spec = importlib.util.spec_from_file_location("baseline", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.generate


def test_build_spec():
    assert _problem().build_spec(10) == {"target": 10}


def test_frozen_globs_is_a_list_of_strings():
    assert _problem().frozen_globs == ["harness/*.py"]


def test_parse_instances_plain_and_ranges():
    assert _problem().parse_instances("3,5-7,10") == [3, 5, 6, 7, 10]


def test_parse_instances_dedupes_keeping_first_occurrence():
    assert _problem().parse_instances("3,3,1-3") == [3, 1, 2]


def test_analytic_sanity():
    problem = _problem()
    spec = problem.build_spec(10)
    artifact = [3, 7]
    result = problem.verify(spec, artifact)
    assert result["passed"] is True
    assert problem.score(spec, artifact) == {"product": 21, "abs_diff": 4}


def test_rejects_wrong_sum():
    problem = _problem()
    spec = problem.build_spec(10)
    result = problem.verify(spec, [3, 3])
    assert result["passed"] is False
    assert result["checks"]["sums_to_target"]["passed"] is False


def test_rejects_wrong_length():
    problem = _problem()
    spec = problem.build_spec(10)
    result = problem.verify(spec, [1, 2, 3])
    assert result["passed"] is False
    assert result["checks"]["well_formed"]["passed"] is False


def test_rejects_non_int_entries():
    problem = _problem()
    spec = problem.build_spec(10)
    result = problem.verify(spec, [1, "nine"])
    assert result["passed"] is False
    assert result["checks"]["well_formed"]["passed"] is False


def test_never_raises_on_garbage_input():
    problem = _problem()
    spec = problem.build_spec(10)
    for garbage in ["not a list", None, 42, {"a": 1}, [1, 2, 3, 4]]:
        result = problem.verify(spec, garbage)
        assert result["passed"] is False


def test_trivial_baseline_always_verifies():
    problem = _problem()
    generate = _load_generate(FIXTURE_ROOT / "baselines" / "trivial.py")
    for instance_id in [1, 5, 100]:
        spec = problem.build_spec(instance_id)
        assert problem.verify(spec, generate(spec))["passed"] is True


def test_bad_baseline_is_correctly_rejected():
    problem = _problem()
    generate = _load_generate(FIXTURE_ROOT / "baselines" / "bad.py")
    spec = problem.build_spec(10)
    assert problem.verify(spec, generate(spec))["passed"] is False
