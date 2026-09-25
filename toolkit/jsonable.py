"""
Converts a score/metric dict into something json.dumps() will accept.

This exists because the obvious way to write a scorer for a numerical
problem -- numpy in, numpy out -- produces values that are *not* JSON
serializable, and the crash lands somewhere useless. `np.float64`
happens to survive (it subclasses float), but `np.int64`, `np.bool_`,
and `np.ndarray` all raise, so a scorer can look fine in testing and
then fail the first time a metric happens to come back as an integer.

Without this, that failure arrives after the expensive work is already
done: `toolkit.results_log` raises after a successful evaluation, losing
the run, and `toolkit.cache` raises inside `toolkit.inbox` *after* the
registry has already been written, leaving a submission registered with
no scores and unable to be resubmitted.

This module owns the JSON boundary in both directions. Going out, that
is to_jsonable()/dumps() below. Coming in, it is load_json_object(): a
state file the toolkit wrote and is now reading back, whose failure modes
are the same family (a decode error, a parse error, the right type in the
wrong shape) and want the same treatment -- say which file, say what to
do, and never guess.

Two levels of strictness, and the difference matters:

- **Stored data** -- cached scores, the results log, registry instance
  ids -- converts strictly. Anything ambiguous raises, naming the type
  and its position. A benchmark's numbers are the whole point, and a
  silently lossy record is worse than a loud failure.
- **Reports for a human to read** pass `fallback=repr`, so an odd value
  in a diagnostic can't stop the report from being printed or saved.
  Never use a fallback for anything that gets stored.
"""
import json
from pathlib import Path

_PRIMITIVES = (str, int, float, bool, type(None))


class NotJSONSerializable(TypeError):
    """Raised for a value to_jsonable() will not guess at."""


def to_jsonable(value, _path: str = "value", *, fallback=None):
    """
    Returns an equivalent structure built only from dicts, lists, strings,
    numbers, booleans, and None.

    Handles the cases that actually come up: numpy scalars and arrays
    (both via .tolist(), which returns a plain scalar for the former and
    a nested list for the latter), tuples and sets (as lists), and
    anything with a __fspath__ (as a string).

    fallback: called on a value nothing else handles, and its result used
    instead. Default None means raise NotJSONSerializable, naming the
    type and its position, e.g. "score['weights'][0]".
    """
    # bool before int: bool is an int subclass and must stay a JSON bool.
    if isinstance(value, _PRIMITIVES):
        return value

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            # JSON object keys must be strings; json.dumps already coerces
            # the scalar types below, so only unusual keys need touching.
            key = key if isinstance(key, _PRIMITIVES) else str(key)
            out[key] = to_jsonable(item, f"{_path}[{key!r}]", fallback=fallback)
        return out

    if isinstance(value, (list, tuple, set, frozenset)):
        # A set has no order of its own; sort it so the same set always
        # logs identically and a cached score stays comparable run to run.
        items = sorted(value, key=repr) if isinstance(value, (set, frozenset)) else value
        return [
            to_jsonable(item, f"{_path}[{i}]", fallback=fallback)
            for i, item in enumerate(items)
        ]

    # numpy scalars and arrays, plus anything exposing the same method.
    #
    # .tolist() and not .item(): .item() succeeds on any *one-element*
    # array and returns its scalar, so np.array([5]) would silently
    # become 5 and a shape would be lost without anything raising.
    # .tolist() is correct for both -- np.int64(5).tolist() is 5,
    # np.array([5]).tolist() is [5].
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return to_jsonable(value.tolist(), _path, fallback=fallback)
        except (ValueError, TypeError) as e:
            if isinstance(e, NotJSONSerializable):
                raise

    if hasattr(value, "__fspath__"):
        return str(value)

    if fallback is not None:
        return fallback(value)

    raise NotJSONSerializable(
        f"{_path} is a {type(value).__name__}, which cannot be written as JSON. "
        "Scores, artifacts, specs, and instance ids must be plain data -- dicts, "
        "lists, strings, numbers, booleans, None. Convert numpy values with "
        ".tolist() first. See isolation/README.md's 'The boundary is plain JSON, "
        "never pickle'."
    )


def dumps(value, _path: str = "value", *, fallback=None, **kwargs) -> str:
    """
    json.dumps() over to_jsonable(). Use this anywhere harness-derived
    data gets serialized, so numpy can't turn a finished run into a
    traceback at the last step.
    """
    return json.dumps(to_jsonable(value, _path, fallback=fallback), **kwargs)


def load_json_object(path, *, error, what: str, recovery: str) -> dict:
    """
    Reads a JSON object from `path`, raising `error` with a message that
    names the file, says what is wrong with it, and says what to do.

    Returns {} when the file does not exist: a project that has not
    written one yet is not a corrupt project.

    Never recovers by returning {} for a file that exists and cannot be
    read. registry.json and .score_cache.json are both committed, so a bad
    merge is the realistic way either breaks, and starting from empty
    would silently discard the record of what passed -- turning one loud
    failure into a leaderboard that quietly lost rows. Refusing to start
    is the whole point; `recovery` is how the caller says what starting
    again requires.

    Handles every way a file read can fail here, not just bad JSON:
    read_text() raises UnicodeDecodeError on a file saved in another
    encoding and OSError on a directory or an unreadable file, and neither
    is a JSONDecodeError -- so catching only that one leaves two of the
    four cases as bare tracebacks naming nothing.
    """
    path = Path(path)
    if not path.exists():
        return {}

    try:
        raw = path.read_bytes()
    except OSError as e:
        raise error(f"{what} at {path} could not be read: {e}. {recovery}") from e

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise error(f"{what} at {path} is not valid UTF-8: {e}. {recovery}") from e

    if not text.strip():
        # Its own case because json's message for it -- "Expecting value:
        # line 1 column 1 (char 0)" -- describes the symptom of an empty
        # file without ever saying the file is empty.
        raise error(f"{what} at {path} is empty. {recovery}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise error(f"{what} at {path} is not valid JSON: {e}. {recovery}") from e

    if not isinstance(data, dict):
        raise error(
            f"{what} at {path} contains a {type(data).__name__} at the top "
            f"level, not an object. {recovery}"
        )
    return data
