"""Fresh-instance validation (CONTEXT.md §8): re-score a candidate on instances it was not
developed on, next to the seed, and decide whether its development-set gain holds.

    python3 scripts/validation.py path/to/generate.py --name my_idea --generation 3

The draw is `instance_set.fresh_draw(generation)`: four instances from the validation pool,
one per size at least, different for each generation of the loop and reproducible from the
generation number. Both the candidate and the seed are swept adaptively on the draw (the
seed's cells are computed once and cached), the primary metric is read off exactly as on the
board, and the verdict is:

    holds  = the candidate beats the seed on the draw (geometric-mean cost ratio at the
             target < 1) AND that ratio is within GAP of its development-set ratio
             (validation_ratio <= dev_ratio * (1 + GAP)),

so a policy tuned to the 12 development instances loses, and one that merely got lucky on a
draw does not pass on the next generation either. Records land in `validation.json`
(`--record`) for the leaderboard's validation table.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from _common import ROOT
from instance_set import fresh_draw, phase0_instances
import render_leaderboard
from sweep import sweep_entry

from harness import spec
from toolkit.cache import fingerprint

GAP = 0.25
SEED = "seed_p1"
SEED_PATH = "baselines/seed_p1.py"
RECORD_PATH = ROOT / "validation.json"


def cost_ratio(cache, fp, name, seed_name, instances, target):
    """Geometric mean over `instances` of (entry CZ at target / seed CZ at target); None if an
    instance has no valid point for either."""
    ratios = []
    for instance in instances:
        cells_e = {c: cache.get(fp, name, c) for c in render_leaderboard.rungs(instance)}
        cells_s = {c: cache.get(fp, seed_name, c) for c in render_leaderboard.rungs(instance)}
        cells_e = {c: v for c, v in cells_e.items() if v is not None}
        cells_s = {c: v for c, v in cells_s.items() if v is not None}
        e = render_leaderboard.cost_at_target(cells_e, instance, target)
        s = render_leaderboard.cost_at_target(cells_s, instance, target)
        if e is None or s is None:
            return None
        ratios.append(e[0] / s[0])
    return math.exp(sum(math.log(r) for r in ratios) / len(ratios))


def validate(problem, cache, seed_cache, fp, name, generate_path, runner, generation, *, dev_ratio=None, log=print):
    draw = fresh_draw(generation)
    target = spec.TARGET_RMSE
    seed_report = sweep_entry(problem, seed_cache, fp, SEED, SEED_PATH, draw, runner, log=log)
    report = sweep_entry(problem, cache, fp, name, generate_path, draw, runner, log=log)
    # the seed's cells live in the leaderboard cache when the draw overlaps registered cells,
    # else in the dev cache; read whichever has them
    class Both:
        def get(self, fp_, n, c):
            return seed_cache.get(fp_, n, c) if n == SEED else cache.get(fp_, n, c)
    val_ratio = cost_ratio(Both(), fp, name, SEED, draw, target)
    holds = val_ratio is not None and val_ratio < 1.0 and (dev_ratio is None or val_ratio <= dev_ratio * (1 + GAP))
    return {"entry": name, "generation": generation, "draw": draw, "dev_ratio": dev_ratio,
            "validation_ratio": val_ratio, "gap": GAP, "holds": bool(holds),
            "failed": report["failed"] + seed_report["failed"]}


def record(result: dict) -> None:
    data = json.loads(RECORD_PATH.read_text()) if RECORD_PATH.exists() else {}
    data[result["entry"]] = {k: v for k, v in result.items() if k != "failed"}
    RECORD_PATH.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def main(argv=None) -> int:
    import argparse
    from evaluate_candidate import DEV_CACHE_PATH, in_process_runner
    from _common import load
    from toolkit.cache import ScoreCache
    parser = argparse.ArgumentParser()
    parser.add_argument("generate_path")
    parser.add_argument("--name", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--dev-ratio", type=float, default=None, help="the candidate's development-set ratio, if known")
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument("--record", action="store_true", help="write the verdict to validation.json (maintainer)")
    args = parser.parse_args(argv)
    problem, registry, board_cache = load()
    fp = fingerprint(problem)
    if args.sandbox:
        from isolation.run_isolated import ensure_available, run_isolated
        ensure_available()
        runner = run_isolated
    else:
        runner = in_process_runner(args.generate_path)
    dev_cache = ScoreCache(DEV_CACHE_PATH)
    result = validate(problem, dev_cache, dev_cache, fp, args.name, args.generate_path, runner, args.generation,
                      dev_ratio=args.dev_ratio)
    print(json.dumps({k: v for k, v in result.items() if k != "failed"}, indent=1))
    if result["failed"]:
        print("FAILED cells:", [f["cell"] for f in result["failed"]], file=sys.stderr)
    if args.record:
        record(result)
    return 0 if result["holds"] and not result["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
