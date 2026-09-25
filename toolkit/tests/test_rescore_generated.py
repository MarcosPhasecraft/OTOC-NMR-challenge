"""
Property tests: random project states through rescore().

The sibling of test_inbox_generated.py, against the other pipeline that
runs untrusted code. What differs is the input surface. The inbox's is a
submission folder someone hands you; rescore()'s is the *project* -- a
registry.json that gets hand-edited and merged badly, a baselines/ that
accumulates across layouts and moves, and a committed score cache -- so
generators.build_project() generates states rather than folders.

The properties are again relational, and the sharp ones are about the
cache, because that is what the leaderboard publishes:

  - a cache entry under the current fingerprint means "this verified
    under this referee", and nothing may leave one behind that doesn't;
  - every registered instance of a usable baseline lands in exactly one
    of rescored / already_current / failed;
  - an unusable baseline costs the others nothing and changes nothing;
  - rescore() never writes to the registry at all;
  - and no path outside baselines/ is ever handed to run_generate(),
    whatever registry.json claims.
"""
import importlib.util
import json
import random
import shutil
from pathlib import Path

import pytest

from toolkit.cache import ScoreCache, fingerprint
from toolkit.problem import load_problem
from toolkit.registry import Registry, RegistryError
from toolkit.rescore import rescore, summarize
from toolkit.tests.generators import build_project, prefill_cache

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"
SEEDS = list(range(12))
REPORT_KEYS = {"baseline", "rescored", "already_current", "failed", "dropped", "unusable"}


def _harness(root: Path):
    """A copy of the fixture harness, so a test can change the referee."""
    harness_dir = root / "harness"
    if not harness_dir.exists():
        shutil.copytree(FIXTURE_ROOT / "harness", harness_dir)
    return load_problem(harness_dir)


def _outside(tmp_path: Path) -> Path:
    """A runnable module outside baselines/ that no run may ever reach."""
    path = tmp_path / "outside" / "forbidden.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "MARKER = 'this module lives outside baselines/'\n"
        "def generate(spec):\n    return [0, spec['target']]\n"
    )
    return path


def _recording_run_generate(seen, inner):
    def run(module_path, spec):
        seen.append(module_path)
        return inner(module_path, spec)
    return run


def _honest(module_path, spec):
    module_spec = importlib.util.spec_from_file_location("generated_baseline", module_path)
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
        return {"ok": True, "artifact": module.generate(spec)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _capricious(seed):
    """Whatever a hijacked sandbox boundary might hand back."""
    rng = random.Random(seed)

    def run(module_path, spec):
        if rng.random() < 0.4:
            return _honest(module_path, spec)
        return rng.choice([
            {"ok": True}, {}, {"ok": False},
            {"ok": "yes", "artifact": [0, spec["target"]]},
            {"ok": True, "artifact": None},
            5, None, "a string", [1, 2], True,
        ])

    return run


def _setup(tmp_path, seed, count=10, *, prefill=True):
    problem = _harness(tmp_path)
    outside = _outside(tmp_path)
    built = build_project(tmp_path, seed, count, outside=outside)
    registry = Registry(tmp_path / "registry.json")
    cache = ScoreCache(tmp_path / "cache.json")
    if prefill:
        prefill_cache(cache, built["planted"], fingerprint(problem), seed)
    return problem, registry, cache, built, outside


def _assert_properties(problem, reports, built, registry, cache, before, seen, outside, context):
    """Everything that must hold after any rescore() run, whatever went in."""
    __tracebackhide__ = True
    fp = fingerprint(problem)
    by_name = {row["name"]: row for row in built["planted"]}
    baselines = built["baselines"].resolve()

    # Report shape, one per selected baseline, JSON-serializable as it stands.
    for report in reports:
        assert set(report) == REPORT_KEYS, (report, context)
        assert report["baseline"] in by_name, (report, context)
        for key in ("rescored", "already_current", "failed", "dropped"):
            assert isinstance(report[key], list), (report, context)
        assert report["unusable"] is None or isinstance(report["unusable"], str), context
        json.dumps(report)
        # summarize() has to survive every report it may be handed.
        summarize([report])

        if report["unusable"] is not None:
            # Unusable means nothing ran and nothing moved.
            assert report["rescored"] == [] and report["failed"] == [], (report, context)
            assert report["already_current"] == [] and report["dropped"] == [], (report, context)

    # Every path handed to run_generate stays inside baselines/, whatever
    # registry.json claimed -- absolute, "..", or otherwise.
    for path in seen:
        resolved = Path(path).resolve()
        assert baselines in resolved.parents, (path, context)
        assert resolved != outside.resolve(), (path, context)

    for report in reports:
        name = report["baseline"]
        if report["unusable"] is not None:
            # Its cache entries are exactly as they were.
            assert _entries_for(cache, name) == _entries_for(before, name), (name, context)
            continue

        entry = registry.get(name)
        # Deduplicated: a repeat in a hand-edited registry.json carries no
        # information, and register() and rescore() both drop it.
        instances = list(dict.fromkeys(entry["instances"]))
        failed_ids = [record["instance_id"] for record in report["failed"]]
        accounted = report["rescored"] + report["already_current"] + failed_ids

        # Every registered instance lands in exactly one bucket, once.
        assert sorted(map(str, accounted)) == sorted(map(str, instances)), (report, context)
        assert set(report["dropped"]) <= set(map(_hashable, failed_ids)), (report, context)

        for instance_id in report["rescored"]:
            score = cache.get(fp, name, instance_id)
            assert score is not None and score.get("passed") is True, (name, instance_id, context)
        for instance_id in failed_ids:
            # A cache entry means "verified", so a failure must not leave one.
            assert cache.get(fp, name, instance_id) is None, (name, instance_id, context)
        for instance_id in report["already_current"]:
            score = cache.get(fp, name, instance_id)
            assert score is not None, (name, instance_id, context)
            assert score == before.get(fp, name, instance_id), context
            # "Already current" has to mean a score that actually verified,
            # not merely an entry that exists. A hand-edited or badly
            # merged cache can hold one saying passed=False, and treating
            # that as current meant it was never recomputed and the
            # leaderboard published its metrics as a real result.
            assert score.get("passed") is True, (name, instance_id, score, context)

    # The pass-six soundness invariant, restated for whatever the run left
    # behind: every cached score under the current referee has passed.
    for key, value in cache._data.items():
        if key.startswith(f"{fp}/"):
            name = key.split("/", 2)[1]
            if cache.get(fp, name, json.loads(key.split("/", 2)[2])) is not None:
                assert value.get("passed") is True, (key, value, context)

    # rescore() never writes to the registry.
    assert Registry(context["registry_path"]).entries() == context["registry_before"], context

    # Nothing was cached for a baseline that was not selected.
    selected = {r["baseline"] for r in reports}
    for key, value in cache._data.items():
        name = key.split("/", 2)[1]
        if name not in selected:
            assert before._data.get(key) == value, (key, context)


def _hashable(value):
    return json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value


def _entries_for(cache, name):
    return {k: v for k, v in cache._data.items() if k.split("/", 2)[1] == name}


def _snapshot(cache):
    clone = ScoreCache.__new__(ScoreCache)
    clone.path = cache.path
    clone._data = json.loads(json.dumps(cache._data))
    return clone


def _run(problem, registry, cache, built, outside, run_generate, **kwargs):
    seen = []
    before = _snapshot(cache)
    reports = rescore(
        problem, registry, cache, baselines_dir=built["baselines"],
        run_generate=_recording_run_generate(seen, run_generate), **kwargs
    )
    return reports, before, seen


@pytest.mark.parametrize("seed", SEEDS)
def test_random_project_states_never_crash(tmp_path, seed):
    problem, registry, cache, built, outside = _setup(tmp_path, seed)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}

    reports, before, seen = _run(problem, registry, cache, built, outside, _honest)

    _assert_properties(problem, reports, built, registry, cache, before, seen, outside, context)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_project_states_survive_a_boundary_that_returns_anything(tmp_path, seed):
    problem, registry, cache, built, outside = _setup(tmp_path, seed)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}

    reports, before, seen = _run(problem, registry, cache, built, outside, _capricious(seed))

    _assert_properties(problem, reports, built, registry, cache, before, seen, outside, context)


@pytest.mark.parametrize("seed", SEEDS)
def test_forcing_a_rescore_holds_the_same_properties(tmp_path, seed):
    """
    force=True is where the cache can be *contradicted* rather than only
    filled, so it is the setting the "no entry survives a failure"
    property actually bites in.
    """
    problem, registry, cache, built, outside = _setup(tmp_path, seed)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}

    reports, before, seen = _run(problem, registry, cache, built, outside, _honest, force=True)

    for report in reports:
        assert report["already_current"] == [], (report, context)  # force skips nothing
    _assert_properties(problem, reports, built, registry, cache, before, seen, outside, context)


@pytest.mark.parametrize("seed", SEEDS[:8])
def test_a_second_rescore_recomputes_nothing_it_already_has(tmp_path, seed):
    """
    Rescoring is meant to be cheap to repeat: the second pass should find
    everything the first one cached and re-run only what failed.
    """
    problem, registry, cache, built, outside = _setup(tmp_path, seed, prefill=False)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}

    first, _, _ = _run(problem, registry, cache, built, outside, _honest)
    second, before, seen = _run(problem, registry, cache, built, outside, _honest)

    _assert_properties(problem, second, built, registry, cache, before, seen, outside, context)
    for one, two in zip(first, second):
        assert one["baseline"] == two["baseline"]
        assert two["rescored"] == [], (two, context)
        assert sorted(map(str, two["already_current"])) == sorted(map(str, one["rescored"])), context


@pytest.mark.parametrize("seed", SEEDS[:8])
def test_a_changed_referee_invalidates_everything_and_a_rescore_restores_it(tmp_path, seed):
    """
    The scenario rescore() exists for: a frozen file changes, every cached
    score becomes a miss, and rescoring fills back in exactly what still
    verifies -- and nothing that doesn't.
    """
    problem, registry, cache, built, outside = _setup(tmp_path, seed, prefill=False)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}
    _run(problem, registry, cache, built, outside, _honest)

    harness_file = tmp_path / "harness" / "__init__.py"
    harness_file.write_text(harness_file.read_text() + "\n# a docstring fix\n")
    changed = load_problem(tmp_path / "harness")
    new_fp = fingerprint(changed)
    for name in registry.names():
        try:
            for instance_id in registry.get(name)["instances"]:
                assert cache.get(new_fp, name, instance_id) is None, context
        except RegistryError:
            pass  # a malformed entry; nothing was cached for it anyway

    reports, before, seen = _run(changed, registry, cache, built, outside, _honest)

    _assert_properties(changed, reports, built, registry, cache, before, seen, outside, context)


@pytest.mark.parametrize("seed", SEEDS[:8])
def test_selecting_names_touches_only_those_baselines(tmp_path, seed):
    problem, registry, cache, built, outside = _setup(tmp_path, seed)
    context = {"seed": seed, "registry_path": tmp_path / "registry.json",
               "registry_before": Registry(tmp_path / "registry.json").entries(),
               "planted": built["planted"]}
    rng = random.Random(seed)
    all_names = registry.names()
    chosen = rng.sample(all_names, k=max(1, len(all_names) // 3))

    reports, before, seen = _run(problem, registry, cache, built, outside, _honest, names=chosen)

    assert [r["baseline"] for r in reports] == chosen, context
    _assert_properties(problem, reports, built, registry, cache, before, seen, outside, context)


def test_an_unregistered_name_raises_before_anything_runs(tmp_path):
    problem, registry, cache, built, outside = _setup(tmp_path, 0)
    seen = []
    before = _snapshot(cache)

    with pytest.raises(RegistryError, match="not registered"):
        rescore(problem, registry, cache, baselines_dir=built["baselines"],
                run_generate=_recording_run_generate(seen, _honest),
                names=[registry.names()[0], "no_such_baseline"])

    assert seen == []
    assert cache._data == before._data


def test_the_generator_reaches_every_kind_and_both_outcomes(tmp_path):
    """
    Guards against a hollow suite: every "if rescored then ..." property is
    vacuously true of a run where nothing runs, and every entry kind that
    stops being produced silently shrinks the grammar.
    """
    from toolkit.tests.generators import CACHE_KINDS, ENTRY_KINDS, MODULE_BODY_KINDS

    seen_entry, seen_body, seen_cache = set(), set(), set()
    rescored = failed = unusable = 0
    for seed in SEEDS:
        root = tmp_path / f"p{seed}"
        root.mkdir()
        problem, registry, cache, built, outside = _setup(root, seed)
        for row in built["planted"]:
            seen_entry.add(row["kind"])
            seen_body.add(row["body_kind"])
            seen_cache.add(row["cache_kind"])
        for report in _run(problem, registry, cache, built, outside, _honest)[0]:
            rescored += len(report["rescored"])
            failed += len(report["failed"])
            unusable += report["unusable"] is not None

    assert seen_entry == set(ENTRY_KINDS), set(ENTRY_KINDS) - seen_entry
    assert seen_body == set(MODULE_BODY_KINDS), set(MODULE_BODY_KINDS) - seen_body
    assert seen_cache == set(CACHE_KINDS), set(CACHE_KINDS) - seen_cache
    assert rescored > 10, rescored
    assert failed > 10, failed
    assert unusable > 5, unusable
