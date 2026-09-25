"""
Tests toolkit/problem.py's load_problem() directly: the happy path
against fixtures/fake_problem/, the two ways a fork's harness/ can fail
the second contract, and that repeated calls never leak a stale module
from one loaded problem into the next.
"""
from pathlib import Path

import pytest

from toolkit.problem import Problem, ProblemContractError, load_problem

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def test_loads_a_valid_problem():
    problem = load_problem(FIXTURE_ROOT / "harness")

    assert isinstance(problem, Problem)
    assert problem.frozen_globs == ["harness/*.py"]
    assert problem.root == FIXTURE_ROOT.resolve()

    spec = problem.build_spec(10)
    assert spec == {"target": 10}
    assert problem.parse_instances("3,5-7") == [3, 5, 6, 7]

    artifact = [3, 7]
    result = problem.verify(spec, artifact)
    assert result["passed"] is True
    assert problem.score(spec, artifact) == {"product": 21, "abs_diff": 4}


def test_rejects_a_directory_that_is_not_a_package(tmp_path):
    not_a_package = tmp_path / "harness"
    not_a_package.mkdir()
    (not_a_package / "verify.py").write_text("def verify(spec, artifact): pass\n")
    # deliberately no __init__.py

    with pytest.raises(ProblemContractError, match="not a Python package"):
        load_problem(not_a_package)


def test_rejects_a_harness_missing_contract_members(tmp_path):
    incomplete = tmp_path / "harness"
    incomplete.mkdir()
    (incomplete / "__init__.py").write_text(
        "def build_spec(instance_id):\n"
        "    return {}\n"
        "\n"
        "def verify(spec, artifact):\n"
        "    return {'passed': True, 'checks': {}}\n"
        # parse_instances, score, FROZEN_GLOBS all deliberately missing
    )

    with pytest.raises(ProblemContractError, match="parse_instances"):
        load_problem(incomplete)


def test_repeated_calls_do_not_leak_a_stale_module(tmp_path):
    """
    Loading one problem, then a different one, must not leak the first
    problem's functions into the second -- a real risk since both get
    registered under the same top-level name, "harness".
    """
    first = load_problem(FIXTURE_ROOT / "harness")
    assert first.build_spec(5) == {"target": 5}

    other = tmp_path / "harness"
    other.mkdir()
    (other / "__init__.py").write_text(
        "FROZEN_GLOBS = ['harness/*.py']\n"
        "\n"
        "def build_spec(instance_id):\n"
        "    return {'different': instance_id}\n"
        "\n"
        "def parse_instances(claim):\n"
        "    return [int(claim)]\n"
        "\n"
        "def verify(spec, artifact):\n"
        "    return {'passed': True, 'checks': {}}\n"
        "\n"
        "def score(spec, artifact):\n"
        "    return {}\n"
    )
    second = load_problem(other)
    assert second.build_spec(5) == {"different": 5}

    # loading the first one again must not have picked up the second's module
    first_again = load_problem(FIXTURE_ROOT / "harness")
    assert first_again.build_spec(5) == {"target": 5}


def test_frozen_globs_as_a_plain_string_is_rejected_at_load(tmp_path):
    """
    An easy slip, and a nasty one left unchecked: a string iterates one
    character at a time and surfaced much later as "Non-relative patterns
    are unsupported". Loading through here exists to catch exactly this.
    """
    harness = _write_harness(tmp_path, frozen_globs='"harness/*.py"')
    with pytest.raises(ProblemContractError, match="must be a list of glob strings"):
        load_problem(harness)


def test_non_string_entries_in_frozen_globs_are_rejected(tmp_path):
    harness = _write_harness(tmp_path, frozen_globs="[3]")
    with pytest.raises(ProblemContractError, match="non-string entries"):
        load_problem(harness)


def test_a_contract_member_that_isnt_callable_is_rejected(tmp_path):
    harness = _write_harness(tmp_path, verify="verify = 42")
    with pytest.raises(ProblemContractError, match="aren't callable"):
        load_problem(harness)


def _write_harness(tmp_path, *, frozen_globs='["harness/*.py"]', verify=None):
    """A minimal contract-satisfying harness, with one piece optionally broken."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(exist_ok=True)
    (harness_dir / "__init__.py").write_text(
        f"FROZEN_GLOBS = {frozen_globs}\n"
        "def build_spec(i): return {}\n"
        "def parse_instances(c): return [1]\n"
        + (verify or 'def verify(s, a): return {"passed": True, "checks": {}}') + "\n"
        "def score(s, a): return {}\n"
    )
    return harness_dir
