"""
Tests toolkit/evaluate.py against fixtures/fake_problem/.
"""
from pathlib import Path

import pytest

from toolkit.evaluate import (
    ScoreCollisionError,
    evaluate,
    evaluate_artifact,
    evaluate_artifact_guarded,
)
from toolkit.problem import load_problem

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def test_evaluate_runs_generate_then_verify_then_score():
    problem = _problem()
    spec = problem.build_spec(10)

    result = evaluate(problem, spec, generate_fn=lambda s: [3, 7])

    assert result["passed"] is True
    assert result["product"] == 21
    assert result["abs_diff"] == 4


def test_evaluate_skips_score_when_verify_fails():
    problem = _problem()
    spec = problem.build_spec(10)

    result = evaluate(problem, spec, generate_fn=lambda s: [3, 3])

    assert result["passed"] is False
    assert "product" not in result
    assert "abs_diff" not in result


def test_evaluate_never_calls_score_for_malformed_artifact():
    problem = _problem()
    spec = problem.build_spec(10)

    # generate_fn returns garbage, not even the right shape
    result = evaluate(problem, spec, generate_fn=lambda s: "not a list")

    assert result["passed"] is False
    assert "product" not in result


def test_evaluate_artifact_matches_evaluate_when_artifact_already_known():
    problem = _problem()
    spec = problem.build_spec(10)
    artifact = [4, 6]

    via_generate = evaluate(problem, spec, generate_fn=lambda s: artifact)
    via_artifact = evaluate_artifact(problem, spec, artifact)

    assert via_generate == via_artifact


def test_a_metric_that_would_overwrite_verifys_verdict_is_refused():
    """
    evaluate_artifact() merges score() over verify()'s result, so a metric
    named "passed" or "checks" lands on top of the referee's verdict --
    and every caller downstream reads result["passed"] to decide whether
    to register, cache, and publish. A verified artifact came back marked
    failed, with no indication why.
    """
    problem = _problem()
    original = problem.score
    problem.score = lambda spec, artifact: {**original(spec, artifact), "passed": False}

    with pytest.raises(ScoreCollisionError, match=r"\['passed'\]"):
        evaluate_artifact(problem, {"target": 3}, [0, 3])


def test_a_colliding_metric_is_a_harness_error_not_a_submission_failure():
    """In a batch it must land as harness_error -- it is the fork's bug."""
    problem = _problem()
    original = problem.score
    problem.score = lambda spec, artifact: {**original(spec, artifact), "checks": {}}

    result = evaluate_artifact_guarded(problem, {"target": 3}, [0, 3])

    assert result["passed"] is False
    assert result["harness_error"] is True
    assert "ScoreCollisionError" in result["checks"]["harness"]["error"]
