"""
Append-only JSONL results log: one JSON object per line. Written by
toolkit.cli's `run.py evaluate` after each run. JSONL rather than the
fermion project's fixed-column TSV, because a fixed set of columns
assumes every problem's metrics look alike, and they don't -- one
problem's score() might return {"total_weight": ..., "max_weight": ...},
another's {"t_count": ..., "ancillas": ...}, and neither should have to
fit the other's columns.
"""
import json
import time
from pathlib import Path

from toolkit.jsonable import to_jsonable

# Column names append_result() writes itself. A metric sharing one of
# these would overwrite the run's own identity, so callers spreading a
# score dict into **fields should check against this first -- Python
# raises a bare "multiple values for keyword argument" before this
# function's own body ever runs.
RESERVED_FIELDS = ("timestamp", "instance_id", "note")


class _NoNote:
    """Sentinel: tells an omitted note from one a spread metric supplied."""

    def __repr__(self):
        return "<no note>"


_NO_NOTE = _NoNote()


def reserved_collisions(fields) -> list:
    """Which of RESERVED_FIELDS appear in `fields`. [] when it's safe to spread."""
    return sorted(set(RESERVED_FIELDS) & set(fields))


def append_result(log_path, *, instance_id, note=_NO_NOTE, **fields) -> dict:
    """
    Appends one line: {"timestamp": ..., "instance_id": ..., "note": ...,
    **fields} and returns it. `fields` is typically an evaluate() result
    spread in directly (passed/checks/whatever score() reported), so
    this never needs to know a problem's own metric names.

    instance_id is an int or a string, the same scalar the rest of the
    toolkit requires (see TOOLKIT.md's second contract). Everything
    written is passed
    through to_jsonable() first, so a scorer returning numpy values logs
    correctly rather than raising here, after the run already succeeded.

    A metric named "instance_id", "note", or "timestamp" would collide
    with this function's own columns; that raises rather than silently
    overwriting the run's identity.
    """
    # "note" and "instance_id" are named parameters, so a metric of either
    # name binds the parameter instead of landing in `fields`. For
    # "instance_id" Python raises "multiple values for keyword argument"
    # before this body runs, which is loud enough. For "note" it does not:
    # append_result(path, instance_id=3, **{"note": 7}) simply sets the
    # note to 7, silently overwriting the run's own column with a metric --
    # exactly what the docstring promises cannot happen. Catch it here.
    if note is not _NO_NOTE and not isinstance(note, str):
        raise ValueError(
            "score()/verify() returned reserved field name(s) ['note'], "
            "which would overwrite the log's own columns. Rename the metric."
        )
    if note is _NO_NOTE:
        note = ""

    collisions = reserved_collisions(fields)
    if collisions:
        raise ValueError(
            f"score()/verify() returned reserved field name(s) {collisions}, "
            "which would overwrite the log's own columns. Rename the metric."
        )

    entry = to_jsonable({
        "timestamp": time.time(),
        "instance_id": instance_id,
        "note": note,
        **fields,
    }, _path="log entry")
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_results(log_path) -> list:
    """Every entry in the log, in the order written. [] if the file doesn't exist yet."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
