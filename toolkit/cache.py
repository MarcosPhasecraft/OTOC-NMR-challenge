"""
Fingerprints a problem's frozen files (problem.frozen_globs) and caches
computed scores keyed to that fingerprint, so a score is only
recomputed when the referee itself changes -- not on every run, and
never served stale if the referee does change.
"""
import hashlib
import json
import os
from pathlib import Path

from toolkit.jsonable import dumps, load_json_object, to_jsonable


class FrozenGlobsError(Exception):
    """Raised when problem.frozen_globs matches no files at all."""


class ScoreCacheError(Exception):
    """Raised when the cache file exists but cannot be read as a cache."""


def fingerprint(problem) -> str:
    """
    One hash of every file matched by problem.frozen_globs, resolved
    relative to problem.root, in a stable sorted order. Two calls give
    the same fingerprint iff none of those files' contents (or which
    files match) changed.
    """
    paths = set()
    for pattern in problem.frozen_globs:
        paths.update(p for p in problem.root.glob(pattern) if p.is_file())

    if not paths:
        # Hashing nothing would return the SHA-256 of the empty string --
        # the same constant for every broken glob -- so the cache would
        # never invalidate and would happily serve scores computed under a
        # different referee. That is the exact failure this module exists
        # to prevent, so refuse rather than return a meaningless hash.
        raise FrozenGlobsError(
            f"FROZEN_GLOBS {problem.frozen_globs!r} matched no files under "
            f"{problem.root}. The fingerprint would be constant and the score "
            "cache would never invalidate. Check the patterns are relative to "
            "the directory containing harness/, e.g. ['harness/*.py']."
        )

    hasher = hashlib.sha256()
    for path in sorted(paths):
        # as_posix() so the same tree fingerprints identically regardless
        # of platform separator.
        name = path.relative_to(problem.root).as_posix().encode()
        content = path.read_bytes()
        # Length-prefix both fields. Feeding name and content in raw makes
        # the stream ambiguous -- ("a.py", b"X") and ("a.pyX", b"") hash
        # identically -- so a rename could go unnoticed by the cache.
        for field in (name, content):
            hasher.update(b"%d:" % len(field))
            hasher.update(field)
    return hasher.hexdigest()


class ScoreCache:
    """
    A JSON file mapping (fingerprint, baseline name, instance id) to a
    score dict. get() returns None on a miss -- including when the
    fingerprint no longer matches, which is treated as a miss rather
    than returning a stale score.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        return load_json_object(
            self.path,
            error=ScoreCacheError,
            what="score cache",
            recovery=(
                "This is the one project file that can be rebuilt: delete it and "
                "run toolkit.rescore.rescore() to recompute every registered "
                "baseline under the current referee. It is not cleared "
                "automatically, because an emptied cache is indistinguishable "
                "from a cold one -- you would get a silently empty leaderboard "
                "instead of this message."
            ),
        )

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: an interrupted run leaves the previous cache
        # intact rather than a half-written file that every later run
        # fails to parse.
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)

    @staticmethod
    def _key(fp: str, baseline_name: str, instance_id) -> str:
        # An instance id also has to survive JSON -- parse_instances() is
        # the fork's own code and can hand back numpy integers.
        return f"{fp}/{baseline_name}/{dumps(instance_id, 'instance id', sort_keys=True)}"

    def get(self, fp: str, baseline_name: str, instance_id):
        """
        The cached score, or None on a miss.

        Treats an entry that cannot be a valid score as a miss, the same
        way a fingerprint mismatch is one. Two kinds:

          - not a dict at all. Nothing here writes such a thing; a bad
            merge of the committed .score_cache.json does. Left alone it
            reached the leaderboard as `available.update(5)` and came out
            as "TypeError: 'int' object is not iterable".
          - a dict that says `passed` is anything but True. A cache entry
            under a fingerprint means "this verified under this referee",
            so an entry contradicting itself is not a score. rescore()
            otherwise called it "already current", never recomputed it,
            and the leaderboard published its metrics as a real result.

        A miss is always the safe answer -- the worst case is one
        recomputation, and rescore() then overwrites the bad entry with a
        real one. An entry with no `passed` key at all still hits: the
        toolkit always writes one, but a fork caching bare metrics through
        set() is not doing anything wrong.
        """
        value = self._data.get(self._key(fp, baseline_name, instance_id))
        if not isinstance(value, dict):
            return None
        if "passed" in value and value["passed"] is not True:
            return None
        return value

    def set(self, fp: str, baseline_name: str, instance_id, score: dict):
        """
        score is passed through to_jsonable() first, so a scorer returning
        numpy values caches correctly instead of raising here -- after the
        expensive work is already done. See toolkit/jsonable.py.
        """
        self._data[self._key(fp, baseline_name, instance_id)] = to_jsonable(score, "score")
        self._save()

    def forget(self, fp: str, baseline_name: str, instance_id) -> bool:
        """
        Drops one cached score, returning whether there was one to drop.

        A cache entry means "this verified under this fingerprint". When a
        re-run under the *same* fingerprint says otherwise -- a
        non-deterministic generate(), a sandbox timeout, a submission that
        depends on something that has since changed -- the old entry is no
        longer a record of anything, and leaving it in place would keep it
        on the leaderboard. toolkit.rescore calls this on every failure so
        the invariant holds through a forced pass; see its docstring.
        """
        key = self._key(fp, baseline_name, instance_id)
        if key not in self._data:
            return False
        del self._data[key]
        self._save()
        return True

    def forget_baseline(self, baseline_name: str) -> int:
        """
        Drops every cached score for one baseline, at any fingerprint,
        returning how many went. For de-registering a baseline by hand:
        cached scores are keyed by name and would otherwise linger after
        registry.json is edited, and reappear if the name is ever reused.
        """
        # Split rather than substring-match: a key is "<fp>/<name>/<json id>"
        # and an instance id is free to contain a slash of its own, so
        # "/name/" can appear inside a *different* baseline's key.
        # Neither a fingerprint nor a name can contain one.
        doomed = [
            k for k in self._data
            if len(parts := k.split("/", 2)) == 3 and parts[1] == baseline_name
        ]
        for key in doomed:
            del self._data[key]
        if doomed:
            self._save()
        return len(doomed)
