"""
Recomputes cached scores for already-registered baselines under the
current referee.

toolkit.cache only ever recomputes when the referee changes -- but until
this existed, nothing recomputed at all. toolkit.inbox writes the cache
once, for a submission it has just accepted, and never touches it again.
So any edit to a file matched by FROZEN_GLOBS changed the fingerprint,
every cached score became a miss, and the leaderboard collapsed to empty
cells with no way back short of reverting the edit byte for byte.

The referee is supposed to be frozen, so this should be rare. It is not
never: a genuine checker bug found late, a docstring fix, a new instance
size added to an existing baseline's claim.

**Runs untrusted code.** Everything registered in baselines/ includes
submissions accepted from other people, and rescoring means running their
generate() again. So `run_generate` is a required argument with no
default, exactly as in toolkit.inbox -- pass
isolation.run_isolated.run_isolated. Registry.load_generate() would
import the module into this process instead; never reach for it here.
"""
from pathlib import Path

from toolkit.cache import fingerprint
from toolkit.evaluate import checked_run_generate, evaluate_artifact_guarded
from toolkit.jsonable import NotJSONSerializable, to_jsonable
from toolkit.problem import Problem
from toolkit.registry import Registry, RegistryError


def rescore(
    problem: Problem,
    registry: Registry,
    cache,
    *,
    baselines_dir,
    run_generate,
    names=None,
    force: bool = False,
) -> list:
    """
    Fills in every missing cached score for the current fingerprint, by
    re-running each registered baseline at the instances it's registered
    at.

    run_generate(generate_path: str, spec: dict) -> {"ok": bool,
    "artifact": ...}. Required, no default -- see this module's docstring.

    names: restrict to these registered baselines (default: all of them).
    force: recompute even where a current cached score already exists.
    Useful for confirming a baseline is deterministic; wasteful otherwise.

    Raises RegistryError if `names` mentions a baseline that isn't
    registered, and does so before running anything -- a typo there is
    the caller's mistake, and finding out after several minutes of
    sandboxed runs helps nobody.

    Returns one report per baseline:
    {"baseline": name, "rescored": [...], "already_current": [...],
     "failed": [{"instance_id": ..., "result": {...}}, ...],
     "dropped": [...], "unusable": str or None}.

    "unusable" is set when the baseline couldn't be run at all -- its
    module file is gone, or its registry entry is malformed -- as
    distinct from running and failing, which lands in "failed". Neither
    stops the other baselines.

    "failed" is a list of records rather than a dict keyed by instance
    id, so a report is always JSON-serializable exactly as it stands.

    A baseline that no longer verifies is listed in "failed" and is
    *not* cached -- a cache entry means "verified under this fingerprint",
    and there is no score for something that didn't pass. Any entry a
    failed run contradicts is dropped, and its instance id listed in
    "dropped": that only arises under force=True, since otherwise a
    current entry is skipped rather than recomputed, and force exists
    precisely to catch a baseline that isn't deterministic. Leaving the
    old entry would let the leaderboard go on publishing a score for a
    baseline this run had just rejected.

    It stays registered: deciding what to do about a baseline the new
    referee rejects is a maintainer's call, the same way toolkit.inbox
    never deletes a rejected submission's folder. Expect it to keep
    appearing in this report until you deal with it -- and when you do,
    Registry.remove(name) and ScoreCache.forget_baseline(name) are the
    two halves of doing it, since cached scores are keyed by name and
    would otherwise outlive the registry entry.

    Instance ids come back from registry.json, so they have been through
    JSON. They are ints or strings by contract -- enforced when they enter
    the registry -- so build_spec() sees exactly what it saw at submission
    time. See TOOLKIT.md's second contract for why that restriction
    exists.
    """
    baselines_dir = Path(baselines_dir)
    if names is None:
        selected = registry.names()
    else:
        selected = list(names)
        unknown = [n for n in selected if n not in registry.names()]
        if unknown:
            raise RegistryError(
                f"names={unknown!r} are not registered. Registered baselines: "
                f"{registry.names()!r}."
            )

    fp = fingerprint(problem)

    return [
        _rescore_one(problem, registry, cache, baselines_dir, run_generate, fp, name, force)
        for name in selected
    ]


def _rescore_one(problem, registry, cache, baselines_dir, run_generate, fp, name, force) -> dict:
    report = {
        "baseline": name,
        "rescored": [],
        "already_current": [],
        "failed": [],
        "dropped": [],
        "unusable": None,
    }

    try:
        entry = registry.get(name)
    except RegistryError as e:
        # A malformed registry.json entry is a project-level problem, but
        # it shouldn't cost the other baselines their run -- the same call
        # this pipeline makes about a submission that fails verification.
        report["unusable"] = str(e)
        return report

    module_path = baselines_dir / entry["module"]
    # register() deduplicates, so this only matters for a hand-edited or
    # badly merged registry.json -- which is exactly the file people do
    # edit by hand. A repeat would otherwise be run twice and reported in
    # two buckets at once.
    instances = list(dict.fromkeys(entry["instances"]))

    if not module_path.exists():
        # Registered but its file is gone -- a hand-edited registry, or a
        # baselines/ that didn't survive a move.
        report["unusable"] = f"{module_path} does not exist"
        return report

    def fail(instance_id, result):
        """
        Record a failure, and drop any cached score this run just
        contradicted.

        Only reachable with something cached when force=True -- otherwise a
        current entry short-circuits above. That is exactly the case force
        exists for ("confirming a baseline is deterministic"), and leaving
        the old entry would let the leaderboard keep publishing a score for
        a baseline that has just failed under the same fingerprint. A cache
        entry has one meaning and it has to keep it.
        """
        report["failed"].append({"instance_id": instance_id, "result": result})
        if cache.forget(fp, name, instance_id):
            report["dropped"].append(instance_id)

    for instance_id in instances:
        if not force and cache.get(fp, name, instance_id) is not None:
            report["already_current"].append(instance_id)
            continue

        spec = problem.build_spec(instance_id)
        run_result = checked_run_generate(run_generate, str(module_path), spec)

        if not run_result.get("ok"):
            fail(instance_id, {
                "passed": False,
                "checks": {"generate": {"passed": False, "error": run_result.get("error")}},
            })
            continue

        result = evaluate_artifact_guarded(problem, spec, run_result["artifact"])
        if not result.get("passed"):
            # A report for a human: convert leniently so an odd value in a
            # diagnostic can't stop the whole report being saved.
            fail(instance_id, to_jsonable(result, "result", fallback=repr))
            continue

        try:
            result = to_jsonable(result, "result")  # strict: about to be cached
        except NotJSONSerializable as e:
            fail(instance_id, {
                "passed": False,
                "checks": {"score": {"passed": False, "error": str(e)}},
            })
            continue

        # Saved one at a time on purpose. Each of these cost a full
        # generate() run, so persisting immediately means an interrupted
        # rescore keeps everything it has already paid for.
        cache.set(fp, name, instance_id, result)
        report["rescored"].append(instance_id)

    return report


def summarize(reports: list) -> str:
    """One line per baseline, plus a total. For printing from a fork's own script."""
    lines = []
    total_rescored = total_failed = total_unusable = 0
    for report in reports:
        rescored, failed = len(report["rescored"]), len(report["failed"])
        total_rescored += rescored
        total_failed += failed
        if report["unusable"]:
            lines.append(f"{report['baseline']}: could not run -- {report['unusable']}")
            total_unusable += 1
            continue
        lines.append(
            f"{report['baseline']}: {rescored} rescored, "
            f"{len(report['already_current'])} already current, {failed} failed"
        )

    totals = f"total: {total_rescored} rescored, {total_failed} failed"
    if total_unusable:
        totals += f", {total_unusable} could not run"

    total_dropped = sum(len(r["dropped"]) for r in reports)
    if total_dropped:
        totals += f", {total_dropped} stale entries dropped"
    lines.append(totals)

    if total_failed:
        lines.append(
            "a registered baseline no longer verifies under the current referee -- "
            "nothing was de-registered, see the reports for which instances. "
            "Registry.remove(name) + ScoreCache.forget_baseline(name) if you decide to."
        )
    return "\n".join(lines)
