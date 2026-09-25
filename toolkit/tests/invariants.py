"""
Properties that must hold after any pipeline run, asserted from many
tests rather than checked once.

KNOWN_ISSUES.md's "recurring failure class" section argues for this
directly: nearly every defect found across five audit passes was an
assumption about input the contract does not guarantee, each fix was
correct and narrow, and each following pass found another instance of the
same class in the previous pass's work. Testing instance by instance
never gets ahead of that. Testing the invariant does -- a defect only has
to violate the property, not to be one somebody thought to look for.
"""
from toolkit.cache import fingerprint


def assert_registered_implies_verified(problem, registry, cache):
    """
    The soundness property of the whole pipeline, in one assertion: every
    registered baseline has, for every instance it is registered at, a
    cached score under the current referee whose "passed" is true.

    Nothing should ever be registered that wasn't fully verified, and no
    cache entry should ever survive a run that contradicted it. Both
    halves have been broken by real defects:

      - inbox.py fingerprinted the referee *after* registry.register(), so
        a FROZEN_GLOBS that matched no files left a submission registered
        with no cached scores at all -- and aborted the rest of the batch.
      - rescore.py left a stale passing entry in place when a forced
        re-run failed, so the leaderboard kept publishing a score for a
        baseline that had just been rejected.

    Call this at the end of any test that runs an inbox or a rescore. It
    costs nothing and it does not care which defect it is catching.
    """
    fp = fingerprint(problem)
    unverified = []
    for name in registry.names():
        for instance_id in registry.get(name)["instances"]:
            score = cache.get(fp, name, instance_id)
            if score is None:
                unverified.append((name, instance_id, "no cached score"))
            elif not score.get("passed"):
                unverified.append((name, instance_id, "cached score did not pass"))
    assert not unverified, (
        "registered but not verified under the current referee: " + repr(unverified)
    )
