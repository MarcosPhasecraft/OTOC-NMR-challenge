"""
Tests toolkit.jsonable.load_json_object -- the reader behind
registry.json and .score_cache.json.

Deliberately not in test_jsonable.py, even though the function lives in
that module: test_jsonable.py takes a module-level
`pytest.importorskip("numpy")`, so every test in it is skipped wherever
numpy isn't installed -- which includes CI, where requirements-dev.txt
installs only pytest. Nothing here needs numpy, and a test that silently
doesn't run is worse than one that doesn't exist.
"""
import os

import pytest

from toolkit.jsonable import load_json_object


class _Boom(Exception):
    """A caller's own error type, to check it is the one that comes back."""


def _load(path):
    return load_json_object(path, error=_Boom, what="thing", recovery="Do the thing.")


def test_a_file_that_does_not_exist_is_an_empty_object_not_an_error(tmp_path):
    """A project that hasn't written one yet is not a corrupt project."""
    assert _load(tmp_path / "absent.json") == {}


def test_a_good_object_loads_unchanged(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"a": {"b": [1, 2]}}')

    assert _load(path) == {"a": {"b": [1, 2]}}


@pytest.mark.parametrize(
    "label, write",
    [
        ("invalid JSON", lambda p: p.write_text("{not json")),
        ("truncated", lambda p: p.write_text('{"a": ')),
        ("empty", lambda p: p.write_text("")),
        ("whitespace only", lambda p: p.write_text("  \n\t")),
        ("not UTF-8", lambda p: p.write_bytes(b'{"a": "\xff\xfe"}')),
        ("a list", lambda p: p.write_text('["a", "b"]')),
        ("a scalar", lambda p: p.write_text("5")),
        ("null", lambda p: p.write_text("null")),
    ],
)
def test_an_unreadable_state_file_names_itself_and_says_what_to_do(tmp_path, label, write):
    """
    Both state files are committed, so a bad merge is the realistic way
    either breaks. This used to surface as a bare JSONDecodeError -- or a
    UnicodeDecodeError, or an IsADirectoryError, neither of which is a
    JSONDecodeError -- naming neither the file nor a way out, on every run
    until someone guessed which file to delete.
    """
    path = tmp_path / "state.json"
    write(path)

    with pytest.raises(_Boom) as caught:
        _load(path)

    message = str(caught.value)
    assert str(path) in message, message      # which file
    assert "Do the thing." in message         # what to do about it


def test_an_empty_file_says_it_is_empty(tmp_path):
    """
    json's own message for an empty file -- "Expecting value: line 1
    column 1 (char 0)" -- describes the symptom without ever saying the
    file is empty, which is the one thing you need to know.
    """
    path = tmp_path / "state.json"
    path.write_text("")

    with pytest.raises(_Boom, match="is empty"):
        _load(path)


def test_a_directory_where_the_state_file_belongs_is_reported(tmp_path):
    path = tmp_path / "state.json"
    path.mkdir()

    with pytest.raises(_Boom, match="could not be read"):
        _load(path)


def test_a_state_file_that_cannot_be_read_is_reported(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}")
    os.chmod(path, 0o000)
    if os.access(path, os.R_OK):
        pytest.skip("running as a user that ignores file permissions")

    with pytest.raises(_Boom, match="could not be read"):
        _load(path)


def test_a_corrupt_file_is_never_quietly_treated_as_empty(tmp_path):
    """
    The one behaviour this must not have. Starting from {} would turn a
    bad merge into a leaderboard that silently lost every row, which is
    the failure this whole path exists to prevent.
    """
    path = tmp_path / "state.json"
    path.write_text("{corrupt")

    with pytest.raises(_Boom):
        _load(path)
    assert path.read_text() == "{corrupt"  # and it is left alone, not repaired
