"""
Tests toolkit/cache.py: fingerprint() against a synthetic set of frozen
files (a real Problem isn't needed -- fingerprint() only ever touches
.root and .frozen_globs), and ScoreCache against a temp file.
"""
import json

import pytest

from toolkit.cache import FrozenGlobsError, ScoreCache, ScoreCacheError, fingerprint
from toolkit.problem import Problem


def _fake_problem(root, frozen_globs=("harness/*.py",)):
    return Problem(
        build_spec=None,
        parse_instances=None,
        verify=None,
        score=None,
        frozen_globs=list(frozen_globs),
        root=root,
    )


def _write_harness(root, verify_body="pass"):
    harness = root / "harness"
    harness.mkdir(exist_ok=True)
    (harness / "verify.py").write_text(f"def verify():\n    {verify_body}\n")


def test_fingerprint_is_stable_when_nothing_changes(tmp_path):
    _write_harness(tmp_path)
    problem = _fake_problem(tmp_path)

    assert fingerprint(problem) == fingerprint(problem)


def test_fingerprint_changes_when_a_frozen_file_changes(tmp_path):
    _write_harness(tmp_path, verify_body="pass")
    problem = _fake_problem(tmp_path)
    before = fingerprint(problem)

    _write_harness(tmp_path, verify_body="return True")
    after = fingerprint(problem)

    assert before != after


def test_fingerprint_ignores_files_outside_frozen_globs(tmp_path):
    _write_harness(tmp_path)
    problem = _fake_problem(tmp_path)
    before = fingerprint(problem)

    (tmp_path / "NOTES.md").write_text("unrelated notes\n")

    assert fingerprint(problem) == before


def test_fingerprint_ignores_directories_matched_by_the_glob(tmp_path):
    _write_harness(tmp_path)
    (tmp_path / "harness" / "subdir").mkdir()
    problem = _fake_problem(tmp_path, frozen_globs=["harness/*"])

    # would raise IsADirectoryError if directories weren't filtered out
    fingerprint(problem)


def test_cache_miss_returns_none(tmp_path):
    cache = ScoreCache(tmp_path / "cache.json")
    assert cache.get("fp1", "trivial", 10) is None


def test_cache_set_then_get_round_trips(tmp_path):
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "trivial", 10, {"product": 21})
    assert cache.get("fp1", "trivial", 10) == {"product": 21}


def test_cache_treats_a_fingerprint_change_as_a_miss(tmp_path):
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "trivial", 10, {"product": 21})
    assert cache.get("fp2", "trivial", 10) is None


def test_cache_persists_to_disk_across_new_instances(tmp_path):
    path = tmp_path / "cache.json"
    ScoreCache(path).set("fp1", "trivial", 10, {"product": 21})

    reloaded = ScoreCache(path)
    assert reloaded.get("fp1", "trivial", 10) == {"product": 21}


def test_cache_distinguishes_different_instance_ids_and_baselines(tmp_path):
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "trivial", 10, {"product": 21})
    cache.set("fp1", "trivial", 20, {"product": 42})
    cache.set("fp1", "other_baseline", 10, {"product": 99})

    assert cache.get("fp1", "trivial", 10) == {"product": 21}
    assert cache.get("fp1", "trivial", 20) == {"product": 42}
    assert cache.get("fp1", "other_baseline", 10) == {"product": 99}


def test_frozen_globs_matching_nothing_raises_instead_of_hashing_nothing(tmp_path):
    """
    Hashing an empty file set returns the SHA-256 of the empty string --
    the same constant for every broken glob -- so the cache would never
    invalidate and would serve scores computed under a different referee.
    A typo in FROZEN_GLOBS must be loud, not silently disable the whole
    invalidation mechanism.
    """
    _write_harness(tmp_path)
    problem = _fake_problem(tmp_path, frozen_globs=["harnes/*.py"])  # typo

    with pytest.raises(FrozenGlobsError, match="matched no files"):
        fingerprint(problem)


def test_two_different_broken_globs_do_not_collide_on_the_empty_hash(tmp_path):
    _write_harness(tmp_path)
    for pattern in (["harnes/*.py"], ["nothing_at_all/*"]):
        with pytest.raises(FrozenGlobsError):
            fingerprint(_fake_problem(tmp_path, frozen_globs=pattern))


def test_cache_stores_numpy_metrics_rather_than_raising(tmp_path):
    """
    A scorer returning np.int64 used to raise inside ScoreCache.set() --
    in the inbox pipeline that lands *after* registry.register(), leaving
    a submission registered with no scores and its name taken for good.
    """
    numpy = pytest.importorskip("numpy")
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "trivial", 10, {"t_count": numpy.int64(7)})
    assert cache.get("fp1", "trivial", 10) == {"t_count": 7}


def test_cache_file_is_replaced_atomically(tmp_path):
    """An interrupted write must leave the previous cache parseable."""
    path = tmp_path / "cache.json"
    cache = ScoreCache(path)
    cache.set("fp1", "trivial", 10, {"product": 21})
    cache.set("fp1", "trivial", 11, {"product": 30})

    assert json.loads(path.read_text())  # never a truncated file
    assert not list(tmp_path.glob("*.tmp"))  # and no leftover scratch file


def test_fingerprint_distinguishes_a_rename_that_shifts_the_name_boundary(tmp_path):
    """
    Feeding name and content in raw makes the byte stream ambiguous:
    ("a.py", b"X") and ("a.pyX", b"") concatenate identically. Length
    prefixes are what keep the two apart.
    """
    root_a = tmp_path / "a"
    (root_a / "harness").mkdir(parents=True)
    (root_a / "harness" / "m.py").write_text("X")

    root_b = tmp_path / "b"
    (root_b / "harness").mkdir(parents=True)
    (root_b / "harness" / "m.pyX").write_text("")

    fp_a = fingerprint(_fake_problem(root_a, frozen_globs=["harness/*"]))
    fp_b = fingerprint(_fake_problem(root_b, frozen_globs=["harness/*"]))
    assert fp_a != fp_b


def test_a_file_matched_by_two_globs_is_only_hashed_once(tmp_path):
    _write_harness(tmp_path)
    one = fingerprint(_fake_problem(tmp_path, frozen_globs=["harness/*.py"]))
    twice = fingerprint(
        _fake_problem(tmp_path, frozen_globs=["harness/*.py", "harness/verify.py"])
    )
    assert one == twice


# --- forget()/forget_baseline(), added in the sixth audit pass -------


def test_forget_drops_one_entry_and_reports_whether_there_was_one(tmp_path):
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "alice", 3, {"passed": True, "product": 0})
    cache.set("fp1", "alice", 5, {"passed": True, "product": 0})

    assert cache.forget("fp1", "alice", 3) is True
    assert cache.forget("fp1", "alice", 3) is False  # already gone
    assert cache.get("fp1", "alice", 3) is None
    assert cache.get("fp1", "alice", 5) is not None
    assert ScoreCache(tmp_path / "cache.json").get("fp1", "alice", 3) is None


def test_forget_baseline_drops_every_fingerprint_for_one_name(tmp_path):
    """
    Cached scores are keyed by name, so hand-editing registry.json to
    de-register a baseline used to leave them behind to accumulate --
    and to reappear if the name were ever reused.
    """
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "alice", 3, {"passed": True})
    cache.set("fp2", "alice", 3, {"passed": True})
    cache.set("fp1", "bob", 3, {"passed": True})

    assert cache.forget_baseline("alice") == 2
    assert cache.get("fp1", "alice", 3) is None
    assert cache.get("fp2", "alice", 3) is None
    assert cache.get("fp1", "bob", 3) is not None
    assert cache.forget_baseline("nobody") == 0


def test_forget_baseline_is_not_fooled_by_a_slash_inside_an_instance_id(tmp_path):
    """
    A key is "<fp>/<name>/<json id>" and an instance id is free to contain
    a slash, so a substring match on "/alice/" would also match bob's key
    for the id "x/alice/y" and silently drop someone else's score.
    """
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "bob", "x/alice/y", {"passed": True})

    assert cache.forget_baseline("alice") == 0
    assert cache.get("fp1", "bob", "x/alice/y") is not None


# --- a committed cache is a merge casualty too (pass eight) -----------


def test_a_cached_entry_that_says_it_failed_is_a_miss(tmp_path):
    """
    A cache entry under a fingerprint means "this verified under this
    referee". One saying otherwise is not a score, and rescore() called it
    "already current" -- never recomputing it, while the leaderboard
    published its metrics as a real result.
    """
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "alice", 3, {"passed": False, "product": 999})

    assert cache.get("fp1", "alice", 3) is None


@pytest.mark.parametrize("value", [5, "a string", [1, 2], None, True])
def test_a_cached_entry_that_is_not_a_dict_is_a_miss(tmp_path, value):
    """The leaderboard did `available.update(5)` and came out as a TypeError."""
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "alice", 3, value)

    assert cache.get("fp1", "alice", 3) is None


def test_a_passing_score_and_a_bare_metrics_dict_both_still_hit(tmp_path):
    """
    A miss is the safe answer, but it must not be the only answer: the
    toolkit always writes "passed", and a fork caching bare metrics
    through set() isn't doing anything wrong.
    """
    cache = ScoreCache(tmp_path / "cache.json")
    cache.set("fp1", "alice", 3, {"passed": True, "product": 12})
    cache.set("fp1", "bob", 3, {"t_count": 4})

    assert cache.get("fp1", "alice", 3)["product"] == 12
    assert cache.get("fp1", "bob", 3)["t_count"] == 4


def test_a_corrupt_cache_file_says_which_file_and_how_to_rebuild(tmp_path):
    """
    .score_cache.json is committed, so a bad merge is how it realistically
    breaks. It used to raise a bare JSONDecodeError from the constructor,
    naming neither the file nor a way out, on every run until someone
    guessed which one to delete.

    The cache is the one project file that *can* be rebuilt, and the
    message says so -- the registry's cannot.
    """
    path = tmp_path / ".score_cache.json"
    path.write_text('{"a": ')

    with pytest.raises(ScoreCacheError) as caught:
        ScoreCache(path)

    message = str(caught.value)
    assert str(path) in message
    assert "rescore" in message
    assert path.exists()  # refused, not silently reset


def test_a_cache_file_that_is_not_an_object_is_refused(tmp_path):
    """
    A list top level loaded fine and failed later with a bare
    AttributeError from inside a dict method -- the gap Registry had
    closed and the cache had not.
    """
    path = tmp_path / ".score_cache.json"
    path.write_text('["not", "a", "cache"]')

    with pytest.raises(ScoreCacheError, match="not an object"):
        ScoreCache(path)


def test_a_missing_cache_file_is_still_just_an_empty_cache(tmp_path):
    assert ScoreCache(tmp_path / "absent.json").get("fp", "a", 3) is None
