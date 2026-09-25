"""
Property tests: random submission folders through process_inbox().

The pass-five audit proposed two properties. The second one --
"registered implies verified" -- became invariants.py. This module is the
first: build random submission folders and assert the pipeline never
raises and never registers a submission it did not fully verify.

What makes this different from test_inbox.py is not coverage of a longer
list of hazards, it is that nobody chose the list. Every defect in
KNOWN_ISSUES.md's recurring-failure table was reachable from a grammar
like the one in generators.py; none of them was reachable from the
imagination of whoever wrote the previous pass. So the assertions below
are deliberately *relational* -- "if accepted then ...", "if rejected then
..." -- rather than a table of expected outcomes. Restating the
implementation as an oracle would only test that it agrees with itself.

Seeds are explicit, so a failure names the exact tree that produced it and
re-running reproduces it byte for byte.
"""
import importlib.util
import json
import random
from pathlib import Path

import pytest

from toolkit.cache import ScoreCache, fingerprint
from toolkit.inbox import process_inbox
from toolkit.problem import load_problem
from toolkit.registry import Registry
from toolkit.tests.generators import build_inbox
from toolkit.tests.invariants import assert_registered_implies_verified

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"
CANARY_TEXT = "CANARY-a-file-no-submission-may-ever-read"

SEEDS = list(range(12))
REPORT_KEYS = {"folder", "accepted", "harness_error", "reason", "per_instance"}


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def _honest_run_generate(generate_path, spec):
    """
    Runs the submission the way toolkit's other tests do. The bodies in
    generators.py are pure, so executing them in-process is safe; what is
    under test here is the host-side pipeline, not the sandbox.
    """
    module_spec = importlib.util.spec_from_file_location("generated_submission", generate_path)
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
        return {"ok": True, "artifact": module.generate(spec)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _capricious_run_generate(seed):
    """
    A run_generate that returns whatever a hijacked sandbox boundary might.

    run_isolated() returns the parsed JSON that came back over the
    boundary, and a submission that writes its own line to the real fd 1
    and calls os._exit() chooses that value outright -- so the pipeline
    has to survive shapes that are not the documented one. It must never
    raise here: SandboxUnavailable is the only thing allowed to stop a
    batch, and that is a host-side fault, not a submission's.
    """
    rng = random.Random(seed)

    def run(generate_path, spec):
        roll = rng.random()
        if roll < 0.35:
            return _honest_run_generate(generate_path, spec)
        return rng.choice([
            {"ok": True},                            # no artifact
            {},                                      # no ok either
            {"ok": False},                           # no error
            {"ok": "yes", "artifact": [0, spec["target"]]},   # truthy non-bool
            {"ok": True, "artifact": None},
            {"ok": True, "artifact": {"nested": {"deep": [1, 2]}}},
            5, None, "a string", [1, 2], True,       # not a dict at all
        ])

    return run


def _setup(tmp_path):
    canary = tmp_path / "outside" / "secret.txt"
    canary.parent.mkdir(parents=True, exist_ok=True)
    canary.write_text(CANARY_TEXT)
    return (
        _problem(),
        tmp_path / "inbox",
        tmp_path / "baselines",
        Registry(tmp_path / "registry.json"),
        ScoreCache(tmp_path / "cache.json"),
        canary,
    )


def _assert_properties(problem, reports, planted, registry, cache, baselines_dir, context,
                       pre_registered=frozenset()):
    """
    Everything that must hold after any process_inbox() run, whatever went
    in. pre_registered names what was already in the registry beforehand,
    for a run over an inbox that has been processed before.
    """
    __tracebackhide__ = True
    fp = fingerprint(problem)

    # One report per folder, in the documented order and shape.
    assert [r["folder"] for r in reports] == sorted(p["folder"] for p in planted), context
    for report in reports:
        assert set(report) == REPORT_KEYS, (report, context)
        assert isinstance(report["accepted"], bool), context
        assert isinstance(report["harness_error"], bool), context
        assert isinstance(report["per_instance"], dict), context
        assert (report["reason"] is None) == report["accepted"], (report, context)
        # A report is a thing a maintainer saves and prints.
        json.dumps(report)

    accepted = [r for r in reports if r["accepted"]]
    by_folder = {p["folder"]: p for p in planted}

    # The soundness property, from the shared fixture.
    assert_registered_implies_verified(problem, registry, cache)

    # Registered names are exactly the accepted folders' claimed names.
    claimed = {by_folder[r["folder"]]["name"] for r in accepted}
    assert set(registry.names()) == claimed | set(pre_registered), context

    for report in accepted:
        planted_row = by_folder[report["folder"]]
        name = planted_row["name"]

        # Accepted means every claimed instance actually passed -- no
        # partial credit, and nothing vacuous.
        assert report["per_instance"], (report, context)
        assert all(r.get("passed") for r in report["per_instance"].values()), (report, context)
        assert report["harness_error"] is False, context

        # The registry records what was verified, and the module is a
        # byte-for-byte copy of what was submitted.
        entry = registry.get(name)
        assert (sorted(entry["instances"], key=str)
                == sorted(report["per_instance"], key=str)), context
        copied = baselines_dir / entry["module"]
        assert copied.is_file(), context
        assert copied.read_bytes() == (Path(context["inbox"]) / report["folder"] / "generate.py").read_bytes()
        for instance_id in entry["instances"]:
            assert cache.get(fp, name, instance_id) is not None, (name, instance_id, context)

    # Nothing is cached for a name that isn't registered.
    for key in cache._data:
        assert key.split("/", 2)[1] in claimed | set(pre_registered), (key, context)

    # The security property, and the reason the canary exists: no byte of
    # a file outside the submission folder ever reaches baselines/,
    # however it was pointed at -- symlink, symlinked parent directory, or
    # hard link. Asserted over every hazard the grammar can plant, with
    # none held back.
    for path in baselines_dir.rglob("*"):
        if path.is_file() and not path.is_symlink():
            assert CANARY_TEXT not in path.read_text(errors="replace"), (path, context)

    # The registry on disk is what the registry in memory says it is.
    assert Registry(context["registry_path"]).entries() == registry.entries(), context


@pytest.mark.parametrize("seed", SEEDS)
def test_random_inboxes_never_crash_and_never_register_the_unverified(tmp_path, seed):
    problem, inbox_dir, baselines_dir, registry, cache, canary = _setup(tmp_path)
    planted = build_inbox(inbox_dir, seed, 12, canary=canary)

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_honest_run_generate,
    )

    _assert_properties(
        problem, reports, planted, registry, cache, baselines_dir,
        {"seed": seed, "inbox": inbox_dir, "registry_path": tmp_path / "registry.json",
         "planted": planted},
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_random_inboxes_survive_a_boundary_that_returns_anything(tmp_path, seed):
    """
    The same folders, but with a run_generate that returns whatever a
    submission could have written over the sandbox boundary. Only
    SandboxUnavailable may stop a batch; a malformed result is one
    submission's problem.
    """
    problem, inbox_dir, baselines_dir, registry, cache, canary = _setup(tmp_path)
    planted = build_inbox(inbox_dir, seed, 12, canary=canary)

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_capricious_run_generate(seed),
    )

    _assert_properties(
        problem, reports, planted, registry, cache, baselines_dir,
        {"seed": seed, "inbox": inbox_dir, "registry_path": tmp_path / "registry.json",
         "planted": planted},
    )


@pytest.mark.parametrize("seed", SEEDS[:6])
def test_a_second_pass_over_the_same_inbox_changes_nothing(tmp_path, seed):
    """
    Rejected folders are never moved or deleted, so a maintainer who runs
    the pipeline twice runs it over the same inbox. Everything accepted
    the first time must be refused as a duplicate the second, and the
    registry must come out identical.
    """
    problem, inbox_dir, baselines_dir, registry, cache, canary = _setup(tmp_path)
    planted = build_inbox(inbox_dir, seed, 10, canary=canary)
    context = {"seed": seed, "inbox": inbox_dir,
               "registry_path": tmp_path / "registry.json", "planted": planted}

    first = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_honest_run_generate,
    )
    after_first = registry.entries()

    second = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_honest_run_generate,
    )

    assert registry.entries() == after_first, context
    for report in second:
        assert report["accepted"] is False, (report, context)
        assert "already registered" in report["reason"] or not any(
            r["folder"] == report["folder"] and r["accepted"] for r in first
        ), (report, context)
    _assert_properties(problem, second, planted, registry, cache, baselines_dir, context,
                       pre_registered=set(after_first))


@pytest.mark.parametrize("seed", SEEDS[:6])
def test_random_inboxes_survive_a_polluted_baselines_directory(tmp_path, seed):
    """
    baselines/ is not guaranteed empty: it is a committed directory that a
    previous run, a different layout, or a hand-tidy has been through.
    Names collide with whatever is already sitting there, and the pipeline
    has to overwrite or refuse rather than raise.
    """
    problem, inbox_dir, baselines_dir, registry, cache, canary = _setup(tmp_path)
    planted = build_inbox(inbox_dir, seed, 12, canary=canary)

    rng = random.Random(seed)
    baselines_dir.mkdir(parents=True, exist_ok=True)
    # Unique names: the generator reuses a name about a fifth of the time,
    # and two junk kinds landing on one path is the test tripping over
    # itself rather than anything about the pipeline.
    for name in sorted({row["name"] for row in planted}):
        junk = rng.choice(["memory_file", "memory_dir", "module_dir", "nothing"])
        if junk == "memory_file":
            (baselines_dir / f"{name}.memory").write_text("stale, and not a directory")
        elif junk == "memory_dir":
            stale = baselines_dir / f"{name}.memory"
            stale.mkdir()
            (stale / "old.md").write_text("from a previous run")
        elif junk == "module_dir":
            (baselines_dir / f"{name}.py").mkdir()

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_honest_run_generate,
    )

    _assert_properties(
        problem, reports, planted, registry, cache, baselines_dir,
        {"seed": seed, "inbox": inbox_dir, "registry_path": tmp_path / "registry.json",
         "planted": planted},
    )


def test_the_generator_actually_reaches_both_outcomes(tmp_path):
    """
    Guards against a vacuous suite. Every "if accepted then ..." property
    above is trivially true of a run that accepts nothing, so a generator
    that only ever produced junk would pass while testing nothing.
    """
    problem, inbox_dir, baselines_dir, registry, cache, canary = _setup(tmp_path)
    accepted = rejected = 0
    for seed in SEEDS:
        folder = inbox_dir / f"s{seed}"
        planted = build_inbox(folder, seed, 12, canary=canary)
        reports = process_inbox(
            problem, inbox_dir=folder, baselines_dir=baselines_dir / f"s{seed}",
            registry=Registry(tmp_path / f"r{seed}.json"),
            cache=ScoreCache(tmp_path / f"c{seed}.json"),
            run_generate=_honest_run_generate,
        )
        accepted += sum(r["accepted"] for r in reports)
        rejected += sum(not r["accepted"] for r in reports)
        del planted

    total = accepted + rejected
    assert accepted > total // 10, f"only {accepted} of {total} folders accepted"
    assert rejected > total // 10, f"only {rejected} of {total} folders rejected"


def test_every_hazard_and_manifest_kind_is_actually_reached(tmp_path):
    """
    The grammar is only worth as much as the part of it the seeds reach.
    If a branch of generators.py stops being produced, this says so rather
    than letting the suite quietly shrink.
    """
    from toolkit.tests.generators import HAZARDS, MANIFEST_KINDS

    canary = tmp_path / "secret.txt"
    canary.write_text(CANARY_TEXT)
    seen_hazards, seen_manifests = set(), set()
    for seed in SEEDS:
        for row in build_inbox(tmp_path / f"in{seed}", seed, 12, canary=canary):
            seen_hazards.add(row["hazard"])
            seen_manifests.add(row["manifest_kind"])

    assert seen_hazards == set(HAZARDS), set(HAZARDS) - seen_hazards
    assert seen_manifests == set(MANIFEST_KINDS), set(MANIFEST_KINDS) - seen_manifests
