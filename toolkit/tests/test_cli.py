"""
Tests toolkit/cli.py's main() against fixtures/fake_problem/.
"""
import json
from pathlib import Path

import pytest

from toolkit.cli import _coerce_instance, main
from toolkit.results_log import read_results

FIXTURE_HARNESS = Path(__file__).parent / "fixtures" / "fake_problem" / "harness"


def _write_solution(tmp_path, body: str) -> Path:
    path = tmp_path / "generate.py"
    path.write_text(body)
    return path


def test_coerce_instance_prefers_int():
    assert _coerce_instance("10") == 10


def test_coerce_instance_falls_back_to_string_for_non_numeric():
    assert _coerce_instance("8x4") == "8x4"


def test_evaluate_subcommand_runs_pipeline_and_logs(tmp_path):
    solution = _write_solution(tmp_path, "def generate(spec):\n    return [3, spec['target'] - 3]\n")
    results = tmp_path / "results.jsonl"

    exit_code = main([
        "evaluate",
        "--harness", str(FIXTURE_HARNESS),
        "--instance", "10",
        "--solution", str(solution),
        "--note", "trying something",
        "--results", str(results),
    ])

    assert exit_code == 0
    [entry] = read_results(results)
    assert entry["instance_id"] == 10
    assert entry["note"] == "trying something"
    assert entry["passed"] is True
    assert entry["product"] == 21
    assert entry["abs_diff"] == 4


def test_evaluate_subcommand_still_logs_a_failed_run(tmp_path):
    solution = _write_solution(tmp_path, "def generate(spec):\n    return [1, 1]\n")
    results = tmp_path / "results.jsonl"

    exit_code = main([
        "evaluate",
        "--harness", str(FIXTURE_HARNESS),
        "--instance", "10",
        "--solution", str(solution),
        "--results", str(results),
    ])

    assert exit_code == 1
    [entry] = read_results(results)
    assert entry["passed"] is False
    assert "product" not in entry  # score() never ran


def test_verify_subcommand_checks_a_raw_artifact_without_calling_generate(tmp_path):
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps([3, 7]))

    exit_code = main([
        "verify",
        "--harness", str(FIXTURE_HARNESS),
        "--instance", "10",
        "--artifact", str(artifact_path),
    ])

    assert exit_code == 0


def test_verify_subcommand_rejects_a_bad_artifact(tmp_path):
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps([3, 3]))

    exit_code = main([
        "verify",
        "--harness", str(FIXTURE_HARNESS),
        "--instance", "10",
        "--artifact", str(artifact_path),
    ])

    assert exit_code == 1


def test_verify_subcommand_writes_no_results_log(tmp_path):
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps([3, 7]))

    main(["verify", "--harness", str(FIXTURE_HARNESS), "--instance", "10", "--artifact", str(artifact_path)])

    assert not (tmp_path / "results.jsonl").exists()


def test_defaults_resolve_relative_to_current_directory(tmp_path, monkeypatch):
    """--harness/--solution/--results all default to paths relative to cwd."""
    import shutil

    monkeypatch.chdir(tmp_path)
    shutil.copytree(FIXTURE_HARNESS, tmp_path / "harness")
    (tmp_path / "solution").mkdir()
    (tmp_path / "solution" / "generate.py").write_text(
        "def generate(spec):\n    return [0, spec['target']]\n"
    )

    exit_code = main(["evaluate", "--instance", "10"])

    assert exit_code == 0
    assert (tmp_path / "results.jsonl").exists()


def _numpy_harness(tmp_path):
    """The fixture harness, but score() returns numpy -- the common case."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    source = (FIXTURE_HARNESS / "__init__.py").read_text().replace(
        'return {"product": a * b, "abs_diff": abs(a - b)}',
        'import numpy\n    return {"product": numpy.int64(a * b), "abs_diff": abs(a - b)}',
    )
    (harness_dir / "__init__.py").write_text(source)
    return harness_dir


def test_a_numpy_scorer_prints_and_logs_rather_than_crashing(tmp_path, capsys):
    """
    The printed result goes through the same conversion as the logged one.
    Fixing only the log left the CLI still dying on numpy one line earlier.
    """
    pytest.importorskip("numpy")
    solution = _write_solution(tmp_path, "def generate(spec):\n    return [2, spec['target'] - 2]\n")
    results = tmp_path / "results.jsonl"

    exit_code = main([
        "evaluate",
        "--harness", str(_numpy_harness(tmp_path)),
        "--instance", "10",
        "--solution", str(solution),
        "--results", str(results),
    ])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["product"] == 16
    assert read_results(results)[0]["product"] == 16


def test_a_metric_named_like_a_log_column_fails_before_writing(tmp_path):
    """
    Python raises on the duplicate keyword before append_result's own
    check can run, so the CLI has to catch this itself.
    """
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        'FROZEN_GLOBS = ["harness/*.py"]\n'
        'def build_spec(i): return {"target": i}\n'
        'def parse_instances(c): return [int(c)]\n'
        'def verify(s, a): return {"passed": True, "checks": {}}\n'
        'def score(s, a): return {"note": "fast"}\n'
    )
    solution = _write_solution(tmp_path, "def generate(spec):\n    return [1]\n")
    results = tmp_path / "results.jsonl"

    with pytest.raises(SystemExit, match="collide"):
        main([
            "evaluate",
            "--harness", str(harness_dir),
            "--instance", "10",
            "--solution", str(solution),
            "--results", str(results),
        ])
    assert not results.exists()  # nothing half-written
