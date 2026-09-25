"""
Tests toolkit/leaderboard.py against fixtures/fake_problem/.
"""
from pathlib import Path

from toolkit.cache import ScoreCache, fingerprint
import pytest

from toolkit.leaderboard import LeaderboardError, render_leaderboard
from toolkit.problem import load_problem
from toolkit.registry import Registry

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _setup(tmp_path):
    problem = load_problem(FIXTURE_ROOT / "harness")
    registry = Registry(tmp_path / "registry.json")
    cache = ScoreCache(tmp_path / "cache.json")
    return problem, registry, cache


def test_header_row_lists_instance_columns_in_order(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("a", module="a.py", label="A", instances=[3, 5])
    fp = fingerprint(problem)
    cache.set(fp, "a", 3, {"product": 10})
    cache.set(fp, "a", 5, {"product": 20})

    table = render_leaderboard(problem, registry, cache, metric_key="product")

    assert table.splitlines()[0] == "| baseline | 3 | 5 |"


def test_ranks_ascending_by_mean_when_lower_is_better(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("worse", module="w.py", label="Worse", instances=[3])
    registry.register("better", module="b.py", label="Better", instances=[3])
    fp = fingerprint(problem)
    cache.set(fp, "worse", 3, {"product": 100})
    cache.set(fp, "better", 3, {"product": 10})

    table = render_leaderboard(problem, registry, cache, metric_key="product")

    rows = table.splitlines()[2:]
    assert rows[0].startswith("| Better")
    assert rows[1].startswith("| Worse")


def test_ranks_descending_when_lower_is_better_is_false(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("small", module="s.py", label="Small", instances=[3])
    registry.register("big", module="b.py", label="Big", instances=[3])
    fp = fingerprint(problem)
    cache.set(fp, "small", 3, {"product": 10})
    cache.set(fp, "big", 3, {"product": 100})

    table = render_leaderboard(
        problem, registry, cache, metric_key="product", lower_is_better=False
    )

    rows = table.splitlines()[2:]
    assert rows[0].startswith("| Big")
    assert rows[1].startswith("| Small")


def test_missing_cached_score_renders_as_a_dash(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("a", module="a.py", label="A", instances=[3, 5])
    fp = fingerprint(problem)
    cache.set(fp, "a", 3, {"product": 10})
    # instance 5 deliberately never cached

    table = render_leaderboard(problem, registry, cache, metric_key="product", instances=[3, 5])

    assert table.splitlines()[2] == "| A | 10 | — |"


def test_baseline_with_no_cached_scores_sorts_last(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("has_scores", module="a.py", label="Has Scores", instances=[3])
    registry.register("no_scores", module="b.py", label="No Scores", instances=[3])
    fp = fingerprint(problem)
    cache.set(fp, "has_scores", 3, {"product": 10})
    # no_scores never gets a cache entry

    table = render_leaderboard(problem, registry, cache, metric_key="product", instances=[3])

    rows = table.splitlines()[2:]
    assert rows[0].startswith("| Has Scores")
    assert rows[1].startswith("| No Scores")


def test_defaults_instances_to_the_sorted_union_of_cached_instances(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("a", module="a.py", label="A", instances=[3, 10])
    fp = fingerprint(problem)
    cache.set(fp, "a", 10, {"product": 1})
    cache.set(fp, "a", 3, {"product": 2})  # cached out of order -- default should still sort numerically

    table = render_leaderboard(problem, registry, cache, metric_key="product")

    assert table.splitlines()[0] == "| baseline | 3 | 10 |"


def test_explicit_instances_are_honored_in_the_order_given(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("a", module="a.py", label="A", instances=[3, 5, 10])
    fp = fingerprint(problem)
    for i in (3, 5, 10):
        cache.set(fp, "a", i, {"product": i})

    table = render_leaderboard(problem, registry, cache, metric_key="product", instances=[10, 3])

    assert table.splitlines()[0] == "| baseline | 10 | 3 |"


def test_a_baseline_not_covering_an_instance_at_all_renders_as_a_dash_too(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    registry.register("narrow", module="n.py", label="Narrow", instances=[3])
    fp = fingerprint(problem)
    cache.set(fp, "narrow", 3, {"product": 10})

    table = render_leaderboard(problem, registry, cache, metric_key="product", instances=[3, 999])

    assert table.splitlines()[2] == "| Narrow | 10 | — |"


def test_empty_registry_renders_just_a_header(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    table = render_leaderboard(problem, registry, cache, metric_key="product")
    assert table.splitlines() == ["| baseline |", "|---|"]


# --- an empty table always says why ------------------------------------


def _registered(tmp_path):
    """One registered baseline and the current fingerprint, nothing cached."""
    problem, registry, cache = _setup(tmp_path)
    registry.register("a", module="a.py", label="A", instances=[3])
    return problem, registry, cache, fingerprint(problem)


def test_a_typo_in_metric_key_raises_and_lists_what_is_available(tmp_path):
    """
    Rendering dashes for this is how an empty leaderboard gets published.
    It must be distinguishable from "nothing is cached yet".
    """
    problem, registry, cache, fp = _registered(tmp_path)
    cache.set(fp, "a", 3, {"product": 10, "abs_diff": 2})

    with pytest.raises(LeaderboardError) as excinfo:
        render_leaderboard(problem, registry, cache, metric_key="prodcut")

    message = str(excinfo.value)
    assert "prodcut" in message
    assert "'abs_diff', 'product'" in message  # says what you could have meant


def test_nothing_cached_at_all_points_at_rescore_instead(tmp_path):
    """The other cause of an empty table needs the opposite advice."""
    problem, registry, cache, fp = _registered(tmp_path)

    with pytest.raises(LeaderboardError, match="rescore"):
        render_leaderboard(problem, registry, cache, metric_key="product")


def test_an_empty_registry_is_still_not_an_error(tmp_path):
    """Nothing registered yet is a normal state, not a misconfiguration."""
    problem, registry, cache = _setup(tmp_path)
    assert render_leaderboard(problem, registry, cache, metric_key="product") == (
        "| baseline |\n|---|"
    )


def test_a_non_numeric_metric_says_which_baseline_and_value(tmp_path):
    problem, registry, cache, fp = _registered(tmp_path)
    cache.set(fp, "a", 3, {"product": "fast"})

    with pytest.raises(LeaderboardError) as excinfo:
        render_leaderboard(problem, registry, cache, metric_key="product")

    message = str(excinfo.value)
    assert "'a'" in message and "'fast'" in message


def test_a_single_pass_instances_argument_is_materialized(tmp_path):
    """`instances` is iterated once per baseline and measured for the separator."""
    problem, registry, cache, fp = _registered(tmp_path)
    registry.register("b", module="b.py", label="B", instances=[3])
    cache.set(fp, "a", 3, {"product": 1})
    cache.set(fp, "b", 3, {"product": 2})

    table = render_leaderboard(
        problem, registry, cache, metric_key="product", instances=(i for i in [3])
    )
    assert table == "| baseline | 3 |\n|---|---|\n| A | 1 |\n| B | 2 |"


def test_a_label_containing_a_pipe_cannot_forge_table_cells(tmp_path):
    """
    A label comes straight from a submitter's submission.json and is only
    checked for being a non-empty string. Interpolated raw, a "|" in it
    splits the row and writes cells of the submitter's choosing into the
    published table -- no code running anywhere.
    """
    problem, registry, cache = _setup(tmp_path)
    fp = fingerprint(problem)
    registry.register("alice", module="alice.py", label="A | 9999 | x", instances=[3])
    cache.set(fp, "alice", 3, {"product": 1, "abs_diff": 1})

    table = render_leaderboard(problem, registry, cache, metric_key="product")

    row = [line for line in table.splitlines() if "9999" in line][0]
    assert row.count("|") - row.count("\\|") == 3  # two ends and one column break
    assert r"A \| 9999 \| x" in row


def test_a_label_containing_a_newline_cannot_end_the_row(tmp_path):
    problem, registry, cache = _setup(tmp_path)
    fp = fingerprint(problem)
    registry.register("alice", module="alice.py", label="A\nrogue row", instances=[3])
    cache.set(fp, "alice", 3, {"product": 1, "abs_diff": 1})

    table = render_leaderboard(problem, registry, cache, metric_key="product")

    assert len(table.splitlines()) == 3  # header, separator, one row
    assert "A rogue row" in table
