"""
Tests toolkit/results_log.py.
"""
import pytest

from toolkit.results_log import append_result, read_results, reserved_collisions


def test_read_results_empty_when_file_missing(tmp_path):
    assert read_results(tmp_path / "results.jsonl") == []


def test_append_creates_parent_directory(tmp_path):
    log_path = tmp_path / "nested" / "results.jsonl"
    append_result(log_path, instance_id=5, note="first run", passed=True)
    assert log_path.exists()


def test_append_and_read_round_trip(tmp_path):
    log_path = tmp_path / "results.jsonl"

    entry = append_result(log_path, instance_id=5, note="hi", passed=True, product=21)

    assert entry["instance_id"] == 5
    assert entry["note"] == "hi"
    assert entry["passed"] is True
    assert entry["product"] == 21
    assert isinstance(entry["timestamp"], float)

    [read_back] = read_results(log_path)
    assert read_back == entry


def test_multiple_appends_are_read_back_in_order(tmp_path):
    log_path = tmp_path / "results.jsonl"

    append_result(log_path, instance_id=1, passed=True)
    append_result(log_path, instance_id=2, passed=False)
    append_result(log_path, instance_id=3, passed=True)

    entries = read_results(log_path)
    assert [e["instance_id"] for e in entries] == [1, 2, 3]


def test_note_defaults_to_empty_string(tmp_path):
    log_path = tmp_path / "results.jsonl"
    entry = append_result(log_path, instance_id=1, passed=True)
    assert entry["note"] == ""


def test_tuple_instance_id_round_trips_as_a_list(tmp_path):
    log_path = tmp_path / "results.jsonl"
    append_result(log_path, instance_id=(8, 4), passed=True)
    [entry] = read_results(log_path)
    assert entry["instance_id"] == [8, 4]


def test_numpy_metrics_are_logged_rather_than_raising(tmp_path):
    """
    np.int64 isn't JSON-serializable, so this used to raise *after* a
    successful evaluation -- losing the run it was meant to record.
    """
    numpy = pytest.importorskip("numpy")
    log_path = tmp_path / "results.jsonl"
    append_result(log_path, instance_id=10, passed=True, t_count=numpy.int64(7))
    [entry] = read_results(log_path)
    assert entry["t_count"] == 7


def test_a_metric_colliding_with_a_log_column_is_refused(tmp_path):
    """
    Silently overwriting the run's own identity would make the log lie
    about which instance a result belongs to.
    """
    with pytest.raises(ValueError, match="reserved field name"):
        append_result(tmp_path / "results.jsonl", instance_id=10, **{"timestamp": 0})


def test_reserved_collisions_reports_what_a_caller_must_check_first():
    # cli.py spreads a score dict into **fields, and Python raises a bare
    # TypeError before append_result's own body can check anything.
    assert reserved_collisions({"passed": True, "note": "x"}) == ["note"]
    assert reserved_collisions({"passed": True, "t_count": 3}) == []


def test_a_metric_named_note_is_refused_rather_than_overwriting_the_note(tmp_path):
    """
    "note" is a named parameter, so a score dict spread in with a metric of
    that name binds the parameter instead of landing in **fields -- no
    TypeError, no collision check, and the run's own note silently replaced
    by a metric. The docstring has always promised this raises.
    """
    with pytest.raises(ValueError, match=r"\['note'\]"):
        append_result(tmp_path / "results.jsonl", instance_id=3,
                      **{"note": 7, "passed": True})


def test_an_ordinary_note_still_works(tmp_path):
    log = tmp_path / "results.jsonl"
    entry = append_result(log, instance_id=3, note="a real note", passed=True)
    assert entry["note"] == "a real note"
    assert append_result(log, instance_id=4, passed=True)["note"] == ""
