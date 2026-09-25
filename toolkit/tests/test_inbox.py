"""
Tests toolkit/inbox.py against fixtures/fake_problem/.

Uses _stub_run_generate below in place of the real
isolation.run_isolated.run_isolated, so this suite doesn't need Docker.
It mimics the same {"ok": ...} contract by importing generate.py
directly and calling it -- NOT a substitute for the real sandbox, and
never used outside this test file. Production code must pass the real
isolation.run_isolated.run_isolated to process_inbox() instead.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

from toolkit.cache import ScoreCache, fingerprint
from toolkit.tests.invariants import assert_registered_implies_verified
from toolkit.inbox import MAX_SUBMISSION_FILES, _unsafe_path_reason, process_inbox
from toolkit.problem import load_problem
from toolkit.registry import Registry

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def _stub_run_generate(generate_path, spec):
    module_spec = importlib.util.spec_from_file_location("submission_under_test", generate_path)
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
        return {"ok": True, "artifact": module.generate(spec)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _make_submission(inbox_dir, folder_name, *, generate_body, manifest, memory=None):
    folder = inbox_dir / folder_name
    folder.mkdir(parents=True)
    (folder / "generate.py").write_text(generate_body)
    (folder / "submission.json").write_text(json.dumps(manifest))
    if memory:
        memory_dir = folder / "memory"
        memory_dir.mkdir()
        for filename, content in memory.items():
            (memory_dir / filename).write_text(content)
    return folder


def _pipeline(tmp_path):
    """A fresh inbox/, baselines/, registry, and cache under tmp_path."""
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    baselines_dir = tmp_path / "baselines"
    registry = Registry(tmp_path / "registry.json")
    cache = ScoreCache(tmp_path / "cache.json")
    return inbox_dir, baselines_dir, registry, cache


TRIVIAL_GENERATE = "def generate(spec):\n    return [0, spec['target']]\n"


def test_accepts_a_submission_passing_at_every_claimed_instance(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice_trivial",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice_trivial", "label": "Alice's Trivial", "sizes": "3,5,10"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    [report] = reports
    assert report["accepted"] is True
    assert report["reason"] is None
    assert all(r["passed"] for r in report["per_instance"].values())

    entry = registry.get("alice_trivial")
    assert entry["module"] == "alice_trivial.py"
    assert entry["instances"] == [3, 5, 10]
    assert (baselines_dir / "alice_trivial.py").read_text() == TRIVIAL_GENERATE

    fp = fingerprint(problem)
    assert cache.get(fp, "alice_trivial", 3) is not None


def test_rejects_a_submission_that_fails_at_one_instance(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    # a "lookup table" that only handles target == 10
    _make_submission(
        inbox_dir, "cheat",
        generate_body=(
            "def generate(spec):\n"
            "    return [0, 10] if spec['target'] == 10 else [0, 0]\n"
        ),
        manifest={"name": "cheater", "label": "Cheater", "sizes": "10,20"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    [report] = reports
    assert report["accepted"] is False
    assert report["per_instance"][10]["passed"] is True
    assert report["per_instance"][20]["passed"] is False

    # no partial credit: nothing registered, nothing cached, not even for instance 10
    assert "cheater" not in registry.names()
    assert not (baselines_dir / "cheater.py").exists()
    fp = fingerprint(problem)
    assert cache.get(fp, "cheater", 10) is None


def test_rejects_a_folder_missing_generate_py(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    folder = inbox_dir / "incomplete"
    folder.mkdir()
    (folder / "submission.json").write_text(json.dumps({"name": "x", "label": "X", "sizes": "3"}))

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "generate.py" in report["reason"]


def test_rejects_invalid_json_manifest(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    folder = inbox_dir / "broken_json"
    folder.mkdir()
    (folder / "generate.py").write_text(TRIVIAL_GENERATE)
    (folder / "submission.json").write_text("{not valid json")

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "not valid JSON" in report["reason"]


def test_rejects_a_manifest_that_fails_validation(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "bad_name",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "NotLowercase", "label": "X", "sizes": "3"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False


def test_rejects_a_name_already_registered_from_a_previous_run(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    registry.register("alice_trivial", module="alice_trivial.py", label="Old", instances=[3])

    _make_submission(
        inbox_dir, "alice_trivial_again",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice_trivial", "label": "New attempt", "sizes": "3"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "already registered" in report["reason"]
    assert registry.get("alice_trivial")["label"] == "Old"  # untouched


def test_rejects_a_duplicate_name_within_the_same_batch(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "aaa_first",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "dup", "label": "First", "sizes": "3"},
    )
    _make_submission(
        inbox_dir, "zzz_second",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "dup", "label": "Second", "sizes": "3"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    by_folder = {r["folder"]: r for r in reports}
    assert by_folder["aaa_first"]["accepted"] is True   # processed first (sorted order)
    assert by_folder["zzz_second"]["accepted"] is False
    assert registry.get("dup")["label"] == "First"


def test_an_isolation_failure_is_recorded_as_a_failed_instance(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "times_out",
        generate_body=TRIVIAL_GENERATE,  # irrelevant -- run_generate below never actually runs it
        manifest={"name": "times_out", "label": "Times Out", "sizes": "3"},
    )

    def always_times_out(generate_path, spec):
        return {"ok": False, "error": "timed out after 30s"}

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=always_times_out,
    )

    assert report["accepted"] is False
    assert report["per_instance"][3]["passed"] is False
    assert report["per_instance"][3]["checks"]["generate"]["error"] == "timed out after 30s"


def test_copies_the_memory_folder_when_present(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice_trivial",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice_trivial", "label": "Alice's Trivial", "sizes": "3"},
        memory={"notes.md": "tried a few things\n"},
    )

    process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert (baselines_dir / "alice_trivial.memory" / "notes.md").read_text() == "tried a few things\n"


def test_processes_folders_in_sorted_order(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for folder_name, name in [("zzz", "zzz_name"), ("aaa", "aaa_name"), ("mmm", "mmm_name")]:
        _make_submission(
            inbox_dir, folder_name,
            generate_body=TRIVIAL_GENERATE,
            manifest={"name": name, "label": name, "sizes": "3"},
        )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert [r["folder"] for r in reports] == ["aaa", "mmm", "zzz"]


def test_ignores_non_directory_entries_in_inbox(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    (inbox_dir / "README.md").write_text("how to submit\n")

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert reports == []


# --- untrusted-folder handling ----------------------------------------
#
# An inbox folder is attacker-controlled input to ordinary host-side
# filesystem code. Sandboxing generate() does nothing for these; the
# copies below happen whether or not any submitted code ever runs.


def test_a_symlink_in_memory_cannot_exfiltrate_a_host_file(tmp_path):
    """
    shutil.copytree follows symlinks by default, so `memory/notes.md ->
    ~/.ssh/id_rsa` used to land that file's *contents* in
    baselines/<name>.memory/ -- a directory normally committed and
    published alongside the leaderboard. No submitted code has to run.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("SUPER SECRET HOST FILE")

    folder = _make_submission(
        inbox_dir, "evil",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "evil", "label": "Evil", "sizes": "5"},
        memory={"real_note.md": "hello"},
    )
    (folder / "memory" / "notes.md").symlink_to(secret)

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    [report] = reports
    assert report["accepted"] is False
    assert "symlink" in report["reason"]
    assert registry.names() == []
    # Nothing at all was copied out of the submission folder.
    assert not baselines_dir.exists() or list(baselines_dir.iterdir()) == []


def test_a_symlinked_generate_py_is_rejected(tmp_path):
    """shutil.copy follows links too, so generate.py gets the same rule."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    elsewhere = tmp_path / "elsewhere.py"
    elsewhere.write_text(TRIVIAL_GENERATE)

    folder = inbox_dir / "linked"
    folder.mkdir()
    (folder / "generate.py").symlink_to(elsewhere)
    (folder / "submission.json").write_text(
        json.dumps({"name": "linked", "label": "Linked", "sizes": "5"})
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "symlink" in report["reason"]


def test_a_symlinked_directory_in_inbox_is_not_walked_as_a_submission(tmp_path):
    """Path.is_dir() follows symlinks, so the link itself must be checked."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (inbox_dir / "sneaky").symlink_to(outside, target_is_directory=True)

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert reports == []


def test_an_oversized_submission_folder_is_rejected(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "huge",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "huge", "label": "Huge", "sizes": "5"},
        memory={"blob.txt": "x" * 11_000_000},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "over the" in report["reason"]


# --- a harness that breaks its own contract ---------------------------


HARNESS_THAT_RAISES = '''
FROZEN_GLOBS = ["harness/*.py"]


def build_spec(instance_id):
    return {"target": instance_id}


def parse_instances(claim):
    return [int(part) for part in claim.split(",")]


def verify(spec, artifact):
    # A plausible authoring slip: assumes the artifact is subscriptable.
    return {"passed": artifact[0] + artifact[1] == spec["target"], "checks": {}}


def score(spec, artifact):
    return {"product": artifact[0] * artifact[1]}
'''


def test_a_harness_that_raises_does_not_abort_the_batch(tmp_path):
    """
    verify() is contractually required never to raise, but that's a rule
    the fork's author has to keep and an adversarial artifact is exactly
    what breaks it. One bad submission used to kill the run partway
    through, after earlier submissions were already registered.
    """
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(HARNESS_THAT_RAISES)
    problem = load_problem(harness_dir)

    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for name in ("aaa_good", "zzz_bad"):
        _make_submission(
            inbox_dir, name,
            generate_body=TRIVIAL_GENERATE,
            manifest={"name": name, "label": name, "sizes": "5"},
        )

    def run_generate(generate_path, spec):
        # zzz_bad returns None -- an artifact this verify() can't handle.
        if "zzz_bad" in str(generate_path):
            return {"ok": True, "artifact": None}
        return _stub_run_generate(generate_path, spec)

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=run_generate,
    )

    good, bad = reports  # sorted order, and both were reached
    assert good["accepted"] is True
    assert bad["accepted"] is False
    # The maintainer needs to tell "bad submission" from "my referee is
    # broken" -- they call for completely different responses.
    assert bad["harness_error"] is True
    assert good["harness_error"] is False
    assert "verify() must never raise" in bad["reason"]
    assert registry.names() == ["aaa_good"]


def test_a_scorer_returning_unwritable_values_registers_nothing(tmp_path):
    """
    The failure must land before the registry is touched. Registering and
    then failing to cache leaves a submission with no scores and its name
    permanently taken, so it can never be resubmitted.
    """
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        HARNESS_THAT_RAISES.replace(
            'return {"product": artifact[0] * artifact[1]}',
            'return {"product": object()}',
        )
    )
    problem = load_problem(harness_dir)

    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "opaque",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "opaque", "label": "Opaque", "sizes": "5"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert "unwritable values" in report["reason"]
    assert registry.names() == []
    assert not (baselines_dir / "opaque.py").exists()


def test_a_rejected_report_is_serializable_too(tmp_path):
    """
    Accepted reports were converted but rejected ones weren't -- and a
    rejected report is exactly the one a maintainer wants to save.
    """
    numpy = pytest.importorskip("numpy")
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        'import numpy\n'
        'FROZEN_GLOBS = ["harness/*.py"]\n'
        'def build_spec(i): return {"target": i}\n'
        'def parse_instances(c): return [int(x) for x in c.split(",")]\n'
        'def verify(s, a): return {"passed": False, "checks": {"n": numpy.int64(3)}}\n'
        'def score(s, a): return {}\n'
    )
    problem = load_problem(harness_dir)
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "x",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "x", "label": "X", "sizes": "5"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert reports[0]["accepted"] is False
    json.dumps(reports)  # would raise before the report was converted


def test_what_the_inbox_caches_is_what_the_leaderboard_reads(tmp_path):
    """
    The two sides have to agree on the cache key. They briefly didn't:
    converting the whole per_instance dict stringified non-scalar keys, so
    an accepted submission was cached under a key nothing ever read back
    and never appeared on the leaderboard. String ids are the case where
    that mismatch would show up.
    """
    from toolkit.leaderboard import render_leaderboard

    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        'FROZEN_GLOBS = ["harness/*.py"]\n'
        'def build_spec(i):\n'
        '    w, h = i.split("x")\n'
        '    return {"w": int(w), "h": int(h)}\n'
        'def parse_instances(c): return [p.strip() for p in c.split(",")]\n'
        'def verify(s, a): return {"passed": True, "checks": {}}\n'
        'def score(s, a): return {"cost": s["w"] * s["h"]}\n'
    )
    problem = load_problem(harness_dir)
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "a",
        generate_body="def generate(spec):\n    return [1]\n",
        manifest={"name": "a", "label": "A", "sizes": "8x4,15x15"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache,
        run_generate=lambda path, spec: {"ok": True, "artifact": [1]},
    )
    assert report["accepted"] is True

    # Rendered straight from the registry and cache the inbox just wrote.
    assert render_leaderboard(problem, registry, cache, metric_key="cost") == (
        "| baseline | 15x15 | 8x4 |\n|---|---|---|\n| A | 225 | 32 |"
    )


def test_a_submission_with_too_many_files_is_rejected(tmp_path):
    """
    The byte cap alone doesn't bound this: a million one-byte files costs
    nothing to produce and passes any size limit, while still being
    expensive to walk and to copy into baselines/.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    folder = _make_submission(
        inbox_dir, "many",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "many", "label": "Many", "sizes": "5"},
        memory={"note.md": "hi"},
    )
    for i in range(MAX_SUBMISSION_FILES + 5):
        (folder / "memory" / f"f{i}").write_bytes(b"x")

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "more than" in report["reason"]


def test_a_symlinked_directory_inside_a_submission_is_rejected(tmp_path):
    """os.walk doesn't descend into one, but it must still be refused."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "secret").write_text("SUPER SECRET HOST FILE")

    folder = _make_submission(
        inbox_dir, "linkdir",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "linkdir", "label": "Link", "sizes": "5"},
        memory={"note.md": "hi"},
    )
    (folder / "memory" / "sneaky").symlink_to(elsewhere, target_is_directory=True)

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "symlink" in report["reason"]
    assert not (baselines_dir / "linkdir.memory").exists()


def test_the_scan_stops_at_the_first_disqualifying_entry(tmp_path):
    """
    A pathological submission should cost the time to reach its first bad
    entry, not the time to enumerate all of it -- and the entry named
    must be the same on every run.
    """
    folder = tmp_path / "sub"
    (folder / "deep").mkdir(parents=True)
    for name in ("b_link", "a_link", "c_link"):
        (folder / name).symlink_to(tmp_path / "anywhere")
    for i in range(50):
        (folder / "deep" / f"f{i}").write_bytes(b"x")

    reasons = {_unsafe_path_reason(folder) for _ in range(5)}
    assert len(reasons) == 1
    assert reasons.pop().startswith("a_link is a symlink")


def test_a_special_file_is_rejected_without_crashing_the_batch(tmp_path):
    """
    shutil.copytree raises on a named pipe, and it raised mid-batch --
    after generate.py had been copied into baselines/, before the registry
    was written, with every later submission never reached. is_file() is
    False for a FIFO, so the size and count checks stepped right over it.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for name in ("aaa_fifo", "zzz_good"):
        _make_submission(
            inbox_dir, name,
            generate_body=TRIVIAL_GENERATE,
            manifest={"name": name, "label": name, "sizes": "5"},
            memory={"note.md": "hi"},
        )
    os.mkfifo(inbox_dir / "aaa_fifo" / "memory" / "pipe")

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    by_name = {r["folder"]: r for r in reports}

    assert by_name["aaa_fifo"]["accepted"] is False
    assert "not a regular file" in by_name["aaa_fifo"]["reason"]
    # The batch continued, and nothing of the bad one was left behind.
    assert by_name["zzz_good"]["accepted"] is True
    assert registry.names() == ["zzz_good"]
    assert not (baselines_dir / "aaa_fifo.py").exists()


def test_a_submission_resolving_to_no_instances_is_never_accepted(tmp_path, monkeypatch):
    """
    Acceptance is "every claimed instance passed", which is vacuously true
    of none of them. validate_manifest refuses an empty claim, so this
    guard is unreachable from outside -- which is the point: the property
    this pipeline exists to guarantee shouldn't rest on a check made in
    another module. Reached here by stubbing that check out, the way a
    future change to it could.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "empty",
        generate_body=TRIVIAL_GENERATE,
        manifest={"name": "empty", "label": "Empty", "sizes": "5"},
    )
    monkeypatch.setattr(
        "toolkit.inbox.validate_manifest",
        lambda manifest, problem: {
            "name": "empty", "label": "Empty", "instances": [], "generated_by": None,
        },
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert report["accepted"] is False
    assert "nothing would be verified" in report["reason"]
    assert registry.names() == []


def test_a_generator_parse_instances_still_checks_every_instance(tmp_path):
    """
    The whole failure in one test: a garbage submission was accepted and
    registered, because validating the claim consumed the generator and
    left zero instances to actually verify.
    """
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "__init__.py").write_text(
        'FROZEN_GLOBS = ["harness/*.py"]\n'
        'def build_spec(i): return {"target": i}\n'
        'def parse_instances(c): return (int(x) for x in c.split(","))\n'
        'def verify(s, a): return {"passed": a == [0, s["target"]], "checks": {}}\n'
        'def score(s, a): return {"cost": 1}\n'
    )
    problem = load_problem(harness_dir)
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "junk",
        generate_body="def generate(spec):\n    return 'garbage'\n",
        manifest={"name": "junk", "label": "Junk", "sizes": "3,5,10"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )
    assert sorted(report["per_instance"]) == [3, 5, 10]  # all three checked
    assert report["accepted"] is False
    assert registry.names() == []


# --- regressions from the sixth audit pass ---------------------------


def test_a_referee_that_cannot_be_fingerprinted_registers_nothing(tmp_path):
    """
    fingerprint() raises when FROZEN_GLOBS matches no files. It used to be
    called after registry.register(), so that raise left the submission
    registered with no cached scores and its name permanently taken --
    the exact end state TOOLKIT.md item 12 says the toolkit prevents --
    and took the rest of the batch down with it.
    """
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    source = (FIXTURE_ROOT / "harness" / "__init__.py").read_text()
    (harness_dir / "__init__.py").write_text(
        source.replace('FROZEN_GLOBS = ["harness/*.py"]', 'FROZEN_GLOBS = ["harness/*.txt"]')
    )
    problem = load_problem(harness_dir)
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for folder in ("alice", "bob"):
        _make_submission(
            inbox_dir, folder, generate_body=TRIVIAL_GENERATE,
            manifest={"name": folder, "label": folder.title(), "sizes": "3"},
        )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert [r["folder"] for r in reports] == ["alice", "bob"]  # the batch survived
    assert [r["accepted"] for r in reports] == [False, False]
    assert "cannot fingerprint the referee" in reports[0]["reason"]
    # Not assert_registered_implies_verified() here: it fingerprints the
    # referee too, and this problem's referee is exactly what cannot be
    # fingerprinted. An empty registry is the property in this case.
    assert registry.names() == []


def test_a_run_generate_missing_its_artifact_fails_one_folder_not_the_batch(tmp_path):
    """
    run_isolated() returns whatever JSON came back over the sandbox
    boundary, and a submission that writes its own line to fd 1 and calls
    os._exit() controls that completely. `{"ok": true}` with no artifact
    used to raise KeyError out of the batch loop, losing every remaining
    submission in the run.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for folder in ("alice", "bob"):
        _make_submission(
            inbox_dir, folder, generate_body=TRIVIAL_GENERATE,
            manifest={"name": folder, "label": folder.title(), "sizes": "3"},
        )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache,
        run_generate=lambda path, spec: {"ok": True},
    )

    assert [r["folder"] for r in reports] == ["alice", "bob"]
    assert [r["accepted"] for r in reports] == [False, False]
    assert "no 'artifact' key" in json.dumps(reports[0]["per_instance"])
    assert registry.names() == []


def test_a_run_generate_returning_a_non_dict_fails_one_folder_not_the_batch(tmp_path):
    """The same hijack, returning a bare JSON scalar: AttributeError before."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=lambda path, spec: 5,
    )

    assert report["accepted"] is False
    assert "not a dict" in json.dumps(report["per_instance"])
    assert registry.names() == []


def test_an_accepted_submission_satisfies_the_soundness_invariant(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3,5,10"},
    )
    _make_submission(
        inbox_dir, "bob", generate_body="def generate(spec):\n    return [1, 1]\n",
        manifest={"name": "bob", "label": "Bob", "sizes": "3,5"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert [r["accepted"] for r in reports] == [True, False]
    assert_registered_implies_verified(problem, registry, cache)


# --- found by the generated-input property tests (pass seven) ---------
#
# Each of these aborted the whole batch, not just the folder that caused
# it: the exception escaped _process_one() and every later submission in
# the run went unprocessed. All five are the same shape -- a file
# operation that assumed something about the path it was given.


def test_a_manifest_that_is_valid_json_but_not_an_object_is_rejected(tmp_path):
    """
    `5`, `true` and `null` are all valid JSON documents, and
    `"name" not in 5` is a TypeError rather than a missing field -- so it
    escaped validate_manifest()'s contract and inbox's except clause.
    Nine bytes to stop an inbox.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    for folder, text in (("a", "5"), ("b", "true"), ("c", "null")):
        _make_submission(
            inbox_dir, folder, generate_body=TRIVIAL_GENERATE,
            manifest={"name": folder, "label": folder, "sizes": "3"},
        )
        (inbox_dir / folder / "submission.json").write_text(text)
    _make_submission(
        inbox_dir, "d_good", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "good", "label": "Good", "sizes": "3"},
    )

    reports = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert [r["accepted"] for r in reports] == [False, False, False, True]
    for report in reports[:3]:
        assert "not an object" in report["reason"]
    assert registry.names() == ["good"]  # the batch ran to the end


def test_a_manifest_that_is_not_utf8_is_rejected(tmp_path):
    """A manifest saved in cp1252 raises UnicodeDecodeError, not JSONDecodeError."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
    )
    (inbox_dir / "alice" / "submission.json").write_bytes(b'{"label": "caf\xe9"}')

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert "not valid UTF-8" in report["reason"]


def test_a_manifest_that_cannot_be_read_is_rejected(tmp_path):
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
    )
    manifest = inbox_dir / "alice" / "submission.json"
    os.chmod(manifest, 0o000)
    if os.access(manifest, os.R_OK):
        pytest.skip("running as a user that ignores file permissions")

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert "could not be read" in report["reason"]


@pytest.mark.parametrize("name", ["submission.json", "generate.py"])
def test_a_directory_where_a_file_belongs_is_rejected(tmp_path, name):
    """
    A directory named submission.json exists, isn't a symlink, and never
    appears in os.walk()'s filenames -- so it passes every check in
    _unsafe_path_reason() and reaches read_text() (or shutil.copy) as a
    directory. exists() was the wrong question; is_file() is the right one.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    folder = _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
    )
    (folder / name).unlink()
    (folder / name).mkdir()

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert report["reason"] == f"{name} is not a regular file"
    assert registry.names() == []


def test_a_stale_memory_path_that_is_a_file_does_not_abort_the_batch(tmp_path):
    """
    baselines/<name>.memory is removed before the new one is copied in,
    with rmtree -- which raises NotADirectoryError if what's there is a
    plain file, left by a previous layout or a hand-tidied baselines/.
    That raised after generate.py had already been copied and before the
    registry was written, so it also left baselines/ dirty.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
        memory={"notes.md": "what I tried"},
    )
    baselines_dir.mkdir(parents=True, exist_ok=True)
    (baselines_dir / "alice.memory").write_text("stale file, not a directory")

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is True
    assert (baselines_dir / "alice.memory").is_dir()
    assert (baselines_dir / "alice.memory" / "notes.md").read_text() == "what I tried"
    assert_registered_implies_verified(problem, registry, cache)


def test_a_module_path_blocked_by_a_directory_is_rejected_not_half_written(tmp_path):
    """
    shutil.copy() into an existing *directory* copies the file inside it
    rather than over it, so the submission was accepted and registered
    with a "module" naming a directory -- rescore() then calls it unusable
    forever and load_generate() can't import it. Found by the generated
    suite, which pollutes baselines/ the way a real one accumulates.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
    )
    baselines_dir.mkdir(parents=True, exist_ok=True)
    (baselines_dir / "alice.py").mkdir()

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert "not a regular file" in report["reason"]
    assert registry.names() == []
    assert not (baselines_dir / "alice.py" / "generate.py").exists()


def test_a_hard_linked_file_in_memory_is_rejected(tmp_path):
    """
    The symlink problem with the link already resolved. `stat` cannot tell
    a hard link from an ordinary file by type -- st_nlink is the only
    signal -- so shutil.copy would read the target's inode and write its
    bytes into baselines/<name>.memory/, which is normally committed and
    published. link() needs no read permission on the target, only on the
    containing directory.
    """
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    secret = tmp_path / "outside_the_inbox.txt"
    secret.write_text("a private key, or anything else the maintainer can read")

    folder = _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3"},
        memory={"notes.md": "ordinary notes"},
    )
    os.link(secret, folder / "memory" / "leak.md")

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is False
    assert "hard link" in report["reason"]
    assert registry.names() == []
    for path in baselines_dir.rglob("*"):
        assert not path.is_file() or "private key" not in path.read_text(errors="replace")


def test_an_ordinary_submission_is_not_mistaken_for_a_hard_link(tmp_path):
    """st_nlink is 1 for a normal file; the check must not reject everything."""
    problem = _problem()
    inbox_dir, baselines_dir, registry, cache = _pipeline(tmp_path)
    _make_submission(
        inbox_dir, "alice", generate_body=TRIVIAL_GENERATE,
        manifest={"name": "alice", "label": "Alice", "sizes": "3,5"},
        memory={"notes.md": "ordinary notes", "more.md": "and more"},
    )

    [report] = process_inbox(
        problem, inbox_dir=inbox_dir, baselines_dir=baselines_dir,
        registry=registry, cache=cache, run_generate=_stub_run_generate,
    )

    assert report["accepted"] is True, report["reason"]


def test_a_missing_inbox_directory_says_so(tmp_path):
    """
    PLAYBOOK.md Step 6's wiring snippet passes inbox_dir="inbox", and the
    template ships no such directory -- so a fork that followed the
    documented snippet got a bare FileNotFoundError out of Path.iterdir(),
    naming neither the argument nor what to do about it. Found by building
    a real problem on this template.
    """
    problem = _problem()
    _, baselines_dir, registry, cache = _pipeline(tmp_path)

    with pytest.raises(FileNotFoundError, match="no inbox directory at"):
        process_inbox(
            problem, inbox_dir=tmp_path / "absent", baselines_dir=baselines_dir,
            registry=registry, cache=cache, run_generate=_stub_run_generate,
        )


def test_an_inbox_that_is_a_file_is_not_mistaken_for_an_empty_one(tmp_path):
    problem = _problem()
    _, baselines_dir, registry, cache = _pipeline(tmp_path)
    not_a_dir = tmp_path / "inbox.txt"
    not_a_dir.write_text("oops")

    with pytest.raises(FileNotFoundError, match="no inbox directory at"):
        process_inbox(
            problem, inbox_dir=not_a_dir, baselines_dir=baselines_dir,
            registry=registry, cache=cache, run_generate=_stub_run_generate,
        )
