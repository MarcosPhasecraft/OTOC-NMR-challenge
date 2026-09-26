#!/usr/bin/env python3
"""Score a candidate `generate.py` on the development set the way the leaderboard will, and
print its row next to the seed's (CONTEXT.md §8).

    python3 scripts/evaluate_candidate.py path/to/generate.py --name my_idea
    python3 scripts/evaluate_candidate.py path/to/generate.py --name my_idea --instances instance_35_d_5,instance_4_d_5
    python3 scripts/evaluate_candidate.py path/to/generate.py --name my_idea --sandbox --full

Two stages, enforced here rather than left to the candidate: stage 1 scores the N = 10
instances only (about a minute), and the candidate is promoted to the full development set
(stage 2) only if its cost ratio to the seed there is below --promote-below (default 1.0:
it beats the seed on the small instances). A candidate that fails stage 1 gets its stage-1
row and stops; --no-staging evaluates everything. The loop calls this, so the agent cannot
skip the screen.

The adaptive budget sweep (scripts/sweep.py) is used: cheapest rung first, stop once the
target error is met, never below x1. Results are cached in `.dev_cache.json` under the
candidate's name and the current referee fingerprint, so a rerun after a code change costs
only the cells that are missing -- pass a new --name when generate.py changed, or --force.

By default the candidate runs in this process (it is your own code); --sandbox runs it in
the Docker sandbox exactly as the inbox will. Nothing here touches the leaderboard: a row
only gets there through the inbox (CLAUDE.md).
"""
import argparse
import importlib.util
import sys
import traceback

from _common import CACHE_PATH, ROOT, load
from instance_set import phase0_instances
import render_leaderboard
from sweep import sweep_entry

from harness import spec
from toolkit.cache import ScoreCache, fingerprint

DEV_CACHE_PATH = ".dev_cache.json"


def in_process_runner(generate_path: str):
    module_spec = importlib.util.spec_from_file_location("candidate", generate_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not hasattr(module, "generate"):
        raise SystemExit(f"{generate_path} has no generate(spec) function")

    def run(path, cell_spec):
        try:
            return {"ok": True, "artifact": module.generate(cell_spec)}
        except Exception:  # noqa: BLE001 -- the candidate's own failure, reported as such
            return {"ok": False, "error": traceback.format_exc(limit=3)}
    return run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generate_path")
    parser.add_argument("--name", required=True, help="label for this candidate in the dev cache")
    parser.add_argument("--instances", default=None, help="comma-separated subset of the development set")
    parser.add_argument("--sandbox", action="store_true", help="run through isolation.run_isolated")
    parser.add_argument("--full", action="store_true", help="evaluate every rung, not just up to the target")
    parser.add_argument("--force", action="store_true", help="recompute cached cells")
    parser.add_argument("--no-staging", action="store_true", help="evaluate every instance without the N=10 screen")
    parser.add_argument("--promote-below", type=float, default=1.0,
                        help="stage-1 cost ratio to the seed below which the candidate is promoted to the full set")
    args = parser.parse_args(argv)

    problem, registry, board_cache = load()
    fp = fingerprint(problem)
    instances = phase0_instances() if args.instances is None else [i.strip() for i in args.instances.split(",")]
    unknown = [i for i in instances if i not in phase0_instances()]
    if unknown:
        raise SystemExit(f"not in the development set: {unknown}")

    if args.sandbox:
        from isolation.run_isolated import ensure_available, run_isolated
        ensure_available()
        runner = run_isolated
    else:
        runner = in_process_runner(args.generate_path)

    dev_cache = ScoreCache(DEV_CACHE_PATH)
    scores = render_leaderboard.collect(registry, board_cache, fp)
    seed_scores = scores.get("seed_p1", {})
    promoted = True
    if not args.no_staging:
        stage1 = [i for i in instances if spec.load_manifest()[i]["num_qubits"] == min(
            spec.load_manifest()[j]["num_qubits"] for j in instances)]
        report = sweep_entry(problem, dev_cache, fp, args.name, args.generate_path, stage1, runner,
                             force_full=args.full, force=args.force)
        ratio = stage_ratio(dev_cache, fp, args.name, seed_scores, stage1)
        promoted = decide_promotion(ratio, args.promote_below, report["failed"])
        print(f"stage 1 ({len(stage1)} instances at N={spec.load_manifest()[stage1[0]]['num_qubits']}): "
              f"ratio to seed {'—' if ratio is None else f'{ratio:.3f}'} -> {'promoted' if promoted else 'not promoted'}")
        instances = instances if promoted else stage1
    if promoted:
        report = sweep_entry(problem, dev_cache, fp, args.name, args.generate_path, instances, runner,
                             force_full=args.full, force=args.force)
    if report["failed"]:
        print("\nFAILED cells:", file=sys.stderr)
        for f in report["failed"]:
            print(f"  {f['cell']}: {f['result'].get('reason') or f['result'].get('checks')}", file=sys.stderr)

    # the candidate's row next to the registered entries, in the leaderboard's own format
    cells = {}
    for instance in instances:
        for mult in spec.LADDER:
            cell = f"{instance}@{spec.format_multiplier(mult)}"
            hit = dev_cache.get(fp, args.name, cell)
            if hit is not None:
                cells[cell] = hit
    scores[args.name] = cells

    class Labels:  # the renderer asks the registry for labels; the candidate is not registered
        def get(self, name):
            return registry.get(name) if name in registry.names() else {"label": f"* {name} (candidate)"}

    print(render_leaderboard.target_table(Labels(), scores, instances))
    print(render_leaderboard.google_table(Labels(), scores, instances))
    return 1 if report["failed"] or not promoted else 0


def stage_ratio(cache, fp, name, seed_scores, instances):
    """Geometric-mean cost ratio at the target over `instances`; None if either side misses."""
    import math
    ratios = []
    for instance in instances:
        cells = {c: cache.get(fp, name, c) for c in render_leaderboard.rungs(instance)}
        cells = {c: v for c, v in cells.items() if v is not None}
        e = render_leaderboard.cost_at_target(cells, instance, spec.TARGET_RMSE)
        s = render_leaderboard.cost_at_target(seed_scores, instance, spec.TARGET_RMSE)
        if e is None or s is None:
            return None
        ratios.append(e[0] / s[0])
    return math.exp(sum(math.log(r) for r in ratios) / len(ratios))


def decide_promotion(ratio, promote_below: float, failed) -> bool:
    """Stage 1 -> stage 2 only when every stage-1 cell verified, the target was met everywhere,
    and the cost ratio to the seed is below the threshold."""
    return not failed and ratio is not None and ratio < promote_below


if __name__ == "__main__":
    sys.exit(main())
