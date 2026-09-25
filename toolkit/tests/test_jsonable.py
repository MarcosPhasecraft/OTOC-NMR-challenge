"""
Tests toolkit/jsonable.py. numpy is the reason this module exists, so
the whole file is skipped when it isn't installed rather than tested
against a stand-in that might not behave the same way.
"""
import json

import pytest

from toolkit.jsonable import NotJSONSerializable, dumps, to_jsonable

np = numpy = pytest.importorskip("numpy", reason="numpy-specific cases")


def _roundtrip(value):
    """to_jsonable() is only useful if json.dumps() then accepts the result."""
    return json.loads(json.dumps(to_jsonable(value)))


def test_plain_data_passes_through_unchanged():
    value = {"t_count": 3, "ratio": 1.5, "ok": True, "name": "x", "none": None}
    assert to_jsonable(value) == value


def test_numpy_scalars_become_python_scalars():
    out = _roundtrip({
        "count": numpy.int64(7),
        "weight": numpy.float64(1.5),
        "flag": numpy.bool_(True),
    })
    assert out == {"count": 7, "weight": 1.5, "flag": True}


def test_numpy_bool_stays_a_bool_not_an_int():
    """np.bool_ is the one that silently becomes 1/0 if converted carelessly."""
    assert to_jsonable(numpy.bool_(True)) is True


def test_numpy_arrays_become_nested_lists():
    assert _roundtrip({"m": numpy.array([[1, 2], [3, 4]])}) == {"m": [[1, 2], [3, 4]]}


def test_conversion_reaches_arbitrarily_deep():
    value = {"outer": [{"inner": (numpy.int64(1), numpy.int64(2))}]}
    assert _roundtrip(value) == {"outer": [{"inner": [1, 2]}]}


def test_tuples_become_lists():
    assert to_jsonable({"pair": (1, 2)}) == {"pair": [1, 2]}


def test_sets_become_sorted_lists_so_a_cached_score_stays_comparable():
    first = to_jsonable({"s": {3, 1, 2}})
    second = to_jsonable({"s": {2, 3, 1}})
    assert first == second  # same set, same JSON, run to run


def test_an_unrepresentable_value_raises_naming_type_and_position():
    class Opaque:
        pass

    with pytest.raises(NotJSONSerializable) as excinfo:
        to_jsonable({"metrics": [Opaque()]})

    message = str(excinfo.value)
    assert "Opaque" in message
    assert "value['metrics'][0]" in message  # says exactly where to look


def test_a_lossy_coercion_is_never_silently_substituted():
    """
    The point of raising is that a benchmark's numbers stay exact. A
    str()-ed object in a results log would look like data and not be.
    """
    class Opaque:
        def __str__(self):
            return "3.14"

    with pytest.raises(NotJSONSerializable):
        to_jsonable({"weight": Opaque()})


def test_a_single_element_array_keeps_its_shape():
    """
    The regression that motivated using .tolist() instead of .item():
    .item() succeeds on any one-element array and returns its scalar, so
    np.array([5]) silently became 5 -- a shape lost with nothing raised.
    """
    assert to_jsonable(np.array([5])) == [5]
    assert to_jsonable(np.array([[7]])) == [[7]]
    assert to_jsonable({"m": np.array([[1], [2]])}) == {"m": [[1], [2]]}


def test_numpy_scalars_still_become_bare_scalars():
    """The other half: .tolist() must not wrap a scalar in a list."""
    assert to_jsonable(np.int64(5)) == 5
    assert not isinstance(to_jsonable(np.int64(5)), list)


def test_fallback_lets_a_human_readable_report_survive_an_odd_value():
    class Opaque:
        def __repr__(self):
            return "<Opaque>"

    out = to_jsonable({"checks": [Opaque()]}, fallback=repr)
    assert out == {"checks": ["<Opaque>"]}


def test_fallback_is_opt_in_so_stored_data_stays_strict():
    class Opaque:
        pass

    with pytest.raises(NotJSONSerializable):
        to_jsonable({"weight": Opaque()})  # no fallback -> still raises


def test_dumps_round_trips_through_json():
    assert json.loads(dumps({"count": np.int64(3), "m": np.array([1, 2])})) == {
        "count": 3, "m": [1, 2]
    }
