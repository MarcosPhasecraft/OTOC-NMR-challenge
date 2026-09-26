"""The adaptive budget sweep (CONTEXT.md §8): evaluate one entry on one instance rung by rung,
from the cheapest budget up, and stop at the first rung whose circuit meets the target
error -- never below the x1 rung, so the Google-comparable cell is always filled.

    cells evaluated:   x0.25, x0.35, ..., up to max(x1, first rung with rmse <= target)
    cells skipped:     every rung above that

The top rungs cost two thirds of a full ladder and say nothing about the primary metric
(the cheapest measured point under the target) once a lower rung has met it; the
secondary metric only needs x1. A skipped rung is simply absent from the cache, which the
leaderboard reads as "not needed", and `force_full=True` evaluates the whole ladder for the
frontier plots.

Every call goes through `run_generate` (in production `isolation.run_isolated`) and the
toolkit's guarded evaluate; results land in the score cache under the current referee
fingerprint, one at a time, so an interrupted sweep keeps what it paid for. A cell that
fails to verify is a finding, reported and never cached, and the sweep of that instance goes
on so the report shows every failure at once.
"""
from __future__ import annotations

from toolkit.evaluate import checked_run_generate, evaluate_artifact_guarded
from toolkit.jsonable import NotJSONSerializable, to_jsonable

from harness import spec as harness_spec


def rungs_of(instance: str) -> list[str]:
    """The instance's cells in ladder order, cheapest first."""
    return [f"{instance}@{harness_spec.format_multiplier(m)}" for m in harness_spec.LADDER]


def stop_after(cell: str, result: dict) -> bool:
    """True when this rung ends the sweep: at or above x1, valid at its budget, target met."""
    _, mult = harness_spec.split_instance_id(cell)
    return (mult is not None and mult >= 1.0 and result.get("passed") is True
            and not result.get("over_budget") and bool(result.get("met_target")))


def sweep_instance(problem, cache, fp: str, name: str, generate_path: str, instance: str,
                   run_generate, *, force_full: bool = False, force: bool = False) -> dict:
    """Evaluate `name` on every rung of `instance` the rule asks for. Returns
    {"evaluated": [cells], "cached": [cells], "skipped": [cells], "failed": [{cell, result}]}."""
    report = {"evaluated": [], "cached": [], "skipped": [], "failed": []}
    stopped = False
    for cell in rungs_of(instance):
        if stopped and not force_full:
            report["skipped"].append(cell)
            continue
        cached = None if force else cache.get(fp, name, cell)
        if cached is not None:
            report["cached"].append(cell)
            stopped = stopped or stop_after(cell, cached)
            continue
        cell_spec = problem.build_spec(cell)
        run_result = checked_run_generate(run_generate, generate_path, cell_spec)
        if not run_result.get("ok"):
            report["failed"].append({"cell": cell, "result": {
                "passed": False, "checks": {"generate": {"passed": False, "error": run_result.get("error")}}}})
            cache.forget(fp, name, cell)
            continue
        result = evaluate_artifact_guarded(problem, cell_spec, run_result["artifact"])
        if not result.get("passed"):
            report["failed"].append({"cell": cell, "result": to_jsonable(result, "result", fallback=repr)})
            cache.forget(fp, name, cell)
            continue
        try:
            result = to_jsonable(result, "result")
        except NotJSONSerializable as error:
            report["failed"].append({"cell": cell, "result": {
                "passed": False, "checks": {"score": {"passed": False, "error": str(error)}}}})
            continue
        cache.set(fp, name, cell, result)
        report["evaluated"].append(cell)
        stopped = stopped or stop_after(cell, result)
    return report


def sweep_entry(problem, cache, fp: str, name: str, generate_path: str, instances, run_generate,
                *, force_full: bool = False, force: bool = False, log=print) -> dict:
    """`sweep_instance` over every base instance; instances may be given as cells or bases."""
    bases = list(dict.fromkeys(harness_spec.split_instance_id(i)[0] for i in instances))
    total = {"entry": name, "evaluated": [], "cached": [], "skipped": [], "failed": []}
    for instance in bases:
        report = sweep_instance(problem, cache, fp, name, generate_path, instance, run_generate,
                                force_full=force_full, force=force)
        for key in ("evaluated", "cached", "skipped", "failed"):
            total[key].extend(report[key])
        if log:
            done = report["evaluated"] + report["cached"]
            last = cache.get(fp, name, done[-1]) if done else None
            tail = (f"stopped at {done[-1].split('@')[1]} (rmse {last['rmse']:.4f}, {last['cz_count']} CZ)"
                    if last else "no valid cell")
            log(f"{name} {instance}: {len(report['evaluated'])} evaluated, {len(report['cached'])} cached, "
                f"{len(report['skipped'])} skipped, {len(report['failed'])} failed; {tail}")
    return total


def summarize(reports: list[dict]) -> str:
    lines = []
    for r in reports:
        lines.append(f"{r['entry']}: {len(r['evaluated'])} evaluated, {len(r['cached'])} already current, "
                     f"{len(r['skipped'])} skipped above the target, {len(r['failed'])} failed")
    return "\n".join(lines)
