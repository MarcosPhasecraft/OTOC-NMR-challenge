"""
Tests toolkit/rescore.py against fixtures/fake_problem/.

Like test_inbox.py, this passes a local stub in place of the real
isolation.run_isolated.run_isolated so the suite doesn't need Docker.
Production code must pass the real one -- rescoring re-runs accepted
third-party submissions, which is untrusted code by definition.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from toolkit.cache import ScoreCache, fingerprint
from toolkit.problem import load_problem
from toolkit.registry import Registry, RegistryError
from toolkit.leaderboard import LeaderboardError, render_leaderboard
from toolkit.rescore import rescore, summarize
from toolkit.tests.invariants import assert_registered_implies_verified

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"

TRIVIAL_GENERATE = "def generate(spec):\n    return [0, spec['target']]\n"


def _stub_run_generate(generate_path, spec):
    module_spec = importlib.util.spec_from_file_location("baseline_under_test", generate_path)
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
        return {"ok": True, "artifact": module.generate(spec)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _harness(tmp_path, *, verify_extra=""):
    """A copy of the fixture harness, so a test can 'change the referee'."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(exist_ok=True)
    source = (FIXTURE_ROOT / "harness" / "__init__.py").read_text()
    (harness_dir / "__init__.py").write_text(source + verify_extra)
    return load_problem(harness_dir)


def _setup(tmp_path, *, generate_body=TRIVIAL_GENERATE, instances=(3, 5, 10)):
    """A registered baseline with its scores already cached."""
    baselines_dir = tmp_path / "baselines"
    baselines_dir.mkdir()
    (baselines_dir / "alice.py").write_text(generate_body)

    registry = Registry(tmp_path / "registry.json")
    registry.register(
        "alice", module="alice.py", label="Alice", instances=list(instances)
    )
    cache = ScoreCache(tmp_path / "cache.json")
    return baselines_dir, registry, cache


def _failed(report):
    """{instance_id: result} from a report's failed list, for easy assertions."""
    return {record["instance_id"]: record["result"] for record in report["failed"]}


def _run(problem, registry, cache, baselines_dir, **kwargs):
    return rescore(
        problem, registry, cache,
        baselines_dir=baselines_dir, run_generate=_stub_run_generate, **kwargs
    )


# --- the gap this module closes ---------------------------------------


def test_a_changed_referee_leaves_nothing_cached(tmp_path):
    """The starting condition: this is what used to be unrecoverable."""
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    _run(problem, registry, cache, baselines_dir)

    changed = _harness(tmp_path, verify_extra="\n# a docstring fix\n")
    new_fp = fingerprint(changed)
    assert all(cache.get(new_fp, "alice", i) is None for i in (3, 5, 10))


def test_rescore_refills_the_cache_after_the_referee_changes(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    _run(problem, registry, cache, baselines_dir)

    changed = _harness(tmp_path, verify_extra="\n# a docstring fix\n")
    [report] = _run(changed, registry, cache, baselines_dir)

    assert report["rescored"] == [3, 5, 10]
    assert report["failed"] == []
    new_fp = fingerprint(changed)
    assert cache.get(new_fp, "alice", 10) == {
        "passed": True,
        "checks": {"well_formed": {"passed": True},
                   "sums_to_target": {"passed": True, "got": 10, "want": 10}},
        "product": 0,
        "abs_diff": 10,
    }


def test_the_leaderboard_comes_back_after_a_rescore(tmp_path):
    """The user-visible point of all this."""
    from toolkit.leaderboard import LeaderboardError, render_leaderboard

    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    _run(problem, registry, cache, baselines_dir)

    changed = _harness(tmp_path, verify_extra="\n# a docstring fix\n")
    # Nothing is cached under the new fingerprint, and the leaderboard
    # says so instead of rendering a table of dashes.
    with pytest.raises(LeaderboardError, match="rescore"):
        render_leaderboard(changed, registry, cache, metric_key="abs_diff")

    _run(changed, registry, cache, baselines_dir)
    assert render_leaderboard(changed, registry, cache, metric_key="abs_diff") == (
        "| baseline | 3 | 5 | 10 |\n|---|---|---|---|\n| Alice | 3 | 5 | 10 |"
    )


# --- not doing unnecessary work ---------------------------------------


def test_current_entries_are_left_alone(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    _run(problem, registry, cache, baselines_dir)

    [report] = _run(problem, registry, cache, baselines_dir)
    assert report["rescored"] == []
    assert report["already_current"] == [3, 5, 10]


def test_force_recomputes_even_current_entries(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    _run(problem, registry, cache, baselines_dir)

    [report] = _run(problem, registry, cache, baselines_dir, force=True)
    assert report["rescored"] == [3, 5, 10]
    assert report["already_current"] == []


def test_only_missing_instances_are_recomputed(tmp_path):
    """A baseline whose claim grew shouldn't re-run what's already cached."""
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path, instances=(3, 5))
    _run(problem, registry, cache, baselines_dir)

    registry.register("alice", module="alice.py", label="Alice", instances=[3, 5, 10])
    [report] = _run(problem, registry, cache, baselines_dir)
    assert report["rescored"] == [10]
    assert report["already_current"] == [3, 5]


def test_names_restricts_which_baselines_run(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    (baselines_dir / "bob.py").write_text(TRIVIAL_GENERATE)
    registry.register("bob", module="bob.py", label="Bob", instances=[3])

    reports = _run(problem, registry, cache, baselines_dir, names=["bob"])
    assert [r["baseline"] for r in reports] == ["bob"]


# --- a baseline the new referee rejects -------------------------------


def test_a_baseline_that_no_longer_verifies_is_reported_not_cached(tmp_path):
    """
    The case that matters most: the referee changed and a registered
    baseline stopped passing. It must be visible, and it must not be
    cached -- a cache entry means "verified under this fingerprint".
    """
    problem = _harness(tmp_path)
    # A generator that's correct only at target 10.
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body="def generate(spec):\n    return [0, 10]\n"
    )

    [report] = _run(problem, registry, cache, baselines_dir)

    assert report["rescored"] == [10]
    assert sorted(_failed(report)) == [3, 5]
    fp = fingerprint(problem)
    assert cache.get(fp, "alice", 3) is None
    assert cache.get(fp, "alice", 10) is not None


def test_a_rejected_baseline_stays_registered(tmp_path):
    """De-registering is a maintainer's call, not this function's."""
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body="def generate(spec):\n    return [0, 999]\n"
    )
    _run(problem, registry, cache, baselines_dir)
    assert registry.names() == ["alice"]


def test_a_failure_keeps_being_reported_until_it_is_dealt_with(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body="def generate(spec):\n    return [0, 999]\n"
    )
    first = _run(problem, registry, cache, baselines_dir)
    second = _run(problem, registry, cache, baselines_dir)
    assert _failed(first[0]).keys() == _failed(second[0]).keys()


# --- things going wrong mid-run ---------------------------------------


def test_a_sandbox_failure_is_recorded_not_raised(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)

    def failing_sandbox(path, spec):
        return {"ok": False, "error": "timed out after 30s"}

    [report] = rescore(
        problem, registry, cache,
        baselines_dir=baselines_dir, run_generate=failing_sandbox,
    )
    assert report["rescored"] == []
    assert "timed out" in _failed(report)[3]["checks"]["generate"]["error"]


def test_a_harness_that_raises_does_not_abort_the_run(tmp_path):
    """Same guard as the inbox pipeline: one bad instance can't kill the batch."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        (FIXTURE_ROOT / "harness" / "__init__.py").read_text().replace(
            "def score(spec: dict, artifact) -> dict:",
            "def score(spec, artifact):\n"
            "    if spec['target'] == 5:\n"
            "        raise RuntimeError('referee bug')\n"
            "    return {'product': artifact[0] * artifact[1], 'abs_diff': abs(artifact[0] - artifact[1])}\n"
            "\n"
            "def _unused(spec: dict, artifact) -> dict:",
        )
    )
    problem = load_problem(harness_dir)
    baselines_dir, registry, cache = _setup(tmp_path)

    [report] = _run(problem, registry, cache, baselines_dir)

    assert report["rescored"] == [3, 10]  # the run continued past the failure
    assert _failed(report)[5]["harness_error"] is True


def test_a_registered_baseline_whose_file_vanished_is_reported(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    (baselines_dir / "alice.py").unlink()

    [report] = _run(problem, registry, cache, baselines_dir)
    assert "does not exist" in report["unusable"]
    assert report["failed"] == []  # it never ran; that isn't a verification failure


def test_numpy_scores_are_cached_rather_than_raising(tmp_path):
    numpy = pytest.importorskip("numpy")
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        (FIXTURE_ROOT / "harness" / "__init__.py").read_text().replace(
            'return {"product": a * b, "abs_diff": abs(a - b)}',
            'import numpy; return {"product": numpy.int64(a * b), "abs_diff": abs(a - b)}',
        )
    )
    problem = load_problem(harness_dir)
    baselines_dir, registry, cache = _setup(tmp_path)

    [report] = _run(problem, registry, cache, baselines_dir)
    assert report["rescored"] == [3, 5, 10]
    assert cache.get(fingerprint(problem), "alice", 3)["product"] == 0


# --- reporting --------------------------------------------------------


def test_summarize_names_the_regression(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body="def generate(spec):\n    return [0, 10]\n"
    )
    text = summarize(_run(problem, registry, cache, baselines_dir))
    assert "alice: 1 rescored, 0 already current, 2 failed" in text
    assert "no longer verifies" in text


def test_summarize_is_quiet_when_everything_passes(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    text = summarize(_run(problem, registry, cache, baselines_dir))
    assert "total: 3 rescored, 0 failed" in text
    assert "no longer verifies" not in text


def test_reports_are_json_serializable_including_failures(tmp_path):
    """A fork's script may well want to write these out."""
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body="def generate(spec):\n    return [0, 10]\n"
    )
    json.dumps(_run(problem, registry, cache, baselines_dir))


# --- caller error vs. data problem -------------------------------------


def test_an_unknown_name_raises_before_any_work_is_done(tmp_path):
    """
    A typo in names= is the caller's mistake, not a baseline result. It
    raises rather than being reported -- and up front, because finding
    out after several minutes of sandboxed runs helps nobody.
    """
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    ran = []

    def tracking_run(path, spec):
        ran.append(spec)
        return _stub_run_generate(path, spec)

    with pytest.raises(RegistryError) as excinfo:
        rescore(
            problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=tracking_run, names=["alice", "typo"],
        )

    assert "typo" in str(excinfo.value)
    assert "alice" in str(excinfo.value)  # says what is registered
    assert ran == []  # nothing was run before it noticed


def test_a_malformed_registry_entry_does_not_cost_the_others_their_run(tmp_path):
    """
    registry.json is a plain file people edit by hand. A broken entry is a
    project-level problem, but the same call the pipeline makes elsewhere
    applies: report it, keep going.
    """
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    (baselines_dir / "bob.py").write_text(TRIVIAL_GENERATE)
    registry.register("bob", module="bob.py", label="Bob", instances=[3])

    # Corrupt one entry the way a bad hand-edit would.
    data = json.loads((tmp_path / "registry.json").read_text())
    del data["alice"]["instances"]
    (tmp_path / "registry.json").write_text(json.dumps(data))
    registry = Registry(tmp_path / "registry.json")

    reports = _run(problem, registry, cache, baselines_dir)
    by_name = {r["baseline"]: r for r in reports}

    assert "missing instances" in by_name["alice"]["unusable"]
    assert "registry.json" in by_name["alice"]["unusable"]  # says which file
    assert by_name["bob"]["rescored"] == [3]  # the good one still ran
    assert by_name["bob"]["unusable"] is None


def test_summarize_reports_a_baseline_that_could_not_run(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path)
    (baselines_dir / "alice.py").unlink()

    text = summarize(_run(problem, registry, cache, baselines_dir))
    assert "alice: could not run" in text
    assert "1 could not run" in text


# --- regressions from the sixth audit pass ---------------------------


NOT_TWICE = (
    "import pathlib\n"
    "STAMP = pathlib.Path(__file__).with_name('stamp')\n"
    "def generate(spec):\n"
    "    if STAMP.exists():\n"
    "        return [0, spec['target'] + 1]\n"
    "    STAMP.write_text('x')\n"
    "    return [0, spec['target']]\n"
)


def test_a_forced_rescore_drops_the_score_it_just_contradicted(tmp_path):
    """
    force exists to confirm a baseline is deterministic. When one turns
    out not to be, the old entry is no longer a record of anything -- but
    it used to stay in the cache under the *same* fingerprint, so the
    report said "failed" while the leaderboard went on publishing the
    stale score.
    """
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body=NOT_TWICE, instances=(3,)
    )

    [first] = rescore(problem, registry, cache, baselines_dir=baselines_dir,
                      run_generate=_stub_run_generate)
    assert first["rescored"] == [3]
    fp = fingerprint(problem)
    assert cache.get(fp, "alice", 3)["passed"] is True

    [second] = rescore(problem, registry, cache, baselines_dir=baselines_dir,
                       run_generate=_stub_run_generate, force=True)

    assert [r["instance_id"] for r in second["failed"]] == [3]
    assert second["dropped"] == [3]
    assert cache.get(fp, "alice", 3) is None
    # And the file on disk, not just the in-memory copy.
    assert ScoreCache(tmp_path / "cache.json").get(fp, "alice", 3) is None


def test_a_leaderboard_cannot_outlive_the_score_a_forced_rescore_rejected(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body=NOT_TWICE, instances=(3,)
    )
    rescore(problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=_stub_run_generate)
    assert "Alice" in render_leaderboard(problem, registry, cache, metric_key="product")

    rescore(problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=_stub_run_generate, force=True)

    with pytest.raises(LeaderboardError, match="no registered baseline has a cached score"):
        render_leaderboard(problem, registry, cache, metric_key="product")


def test_a_run_generate_missing_its_artifact_is_a_failure_not_a_crash(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path, instances=(3,))

    [report] = rescore(problem, registry, cache, baselines_dir=baselines_dir,
                       run_generate=lambda path, spec: {"ok": True})

    assert report["unusable"] is None
    assert "no 'artifact' key" in _failed(report)[3]["checks"]["generate"]["error"]


def test_a_run_generate_returning_a_non_dict_is_a_failure_not_a_crash(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path, instances=(3,))

    [report] = rescore(problem, registry, cache, baselines_dir=baselines_dir,
                       run_generate=lambda path, spec: 5)

    assert "not a dict" in _failed(report)[3]["checks"]["generate"]["error"]


def test_rescore_of_a_deterministic_baseline_leaves_the_invariant_holding(tmp_path):
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path, instances=(3, 5, 10))

    rescore(problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=_stub_run_generate)

    assert_registered_implies_verified(problem, registry, cache)


def test_a_rejected_baseline_stays_registered_and_the_invariant_says_so(tmp_path):
    """
    rescore() deliberately does not de-register a baseline the current
    referee rejects -- that is a maintainer's call. So after a forced pass
    that failed, the registry legitimately claims something the cache no
    longer backs, and the invariant is the thing that makes that visible
    rather than something a leaderboard quietly papers over.
    """
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(
        tmp_path, generate_body=NOT_TWICE, instances=(3,)
    )
    rescore(problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=_stub_run_generate)
    assert_registered_implies_verified(problem, registry, cache)

    rescore(problem, registry, cache, baselines_dir=baselines_dir,
            run_generate=_stub_run_generate, force=True)

    with pytest.raises(AssertionError, match="registered but not verified"):
        assert_registered_implies_verified(problem, registry, cache)

    # And Registry.remove() + ScoreCache.forget_baseline() are how a
    # maintainer actually makes that call; the invariant holds again after.
    registry.remove("alice")
    cache.forget_baseline("alice")
    assert_registered_implies_verified(problem, registry, cache)


def test_a_hand_edited_duplicate_instance_is_run_once(tmp_path):
    """
    register() deduplicates, so this is about a hand-edited or badly
    merged registry.json -- the file people do edit by hand. A repeat used
    to cost a second full sandboxed run, the most expensive thing this
    toolkit does, and land the same instance in both "rescored" and
    "already_current" in one report.
    """
    problem = _harness(tmp_path)
    baselines_dir, registry, cache = _setup(tmp_path, instances=(3, 5))
    # Straight into the file, the way a bad merge would.
    raw = json.loads((tmp_path / "registry.json").read_text())
    raw["alice"]["instances"] = [3, 5, 3, 5, 3]
    (tmp_path / "registry.json").write_text(json.dumps(raw))
    registry = Registry(tmp_path / "registry.json")

    calls = []

    def counting(path, spec):
        calls.append(spec["target"])
        return _stub_run_generate(path, spec)

    [report] = rescore(problem, registry, cache, baselines_dir=baselines_dir,
                       run_generate=counting)

    assert sorted(calls) == [3, 5]
    assert sorted(report["rescored"]) == [3, 5]
    assert report["already_current"] == []
