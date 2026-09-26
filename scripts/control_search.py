#!/usr/bin/env python3
"""The control (CONTEXT.md §9): random search over the seed's own knobs, no new ideas.

    python3 scripts/control_search.py --configs 12 --seed 0 [--instances instance_35_d_5,...]

Each configuration is a random point in the space a person could reach by twiddling the
seed: chain layout (time of flight, identity, or a random permutation with the measurement
spin kept first), a global coupling scale, the product-formula order (1, 2 or 4) and how many
of the budget's steps are actually spent (a fraction, since spending less can help in the
non-asymptotic regime). Every configuration is scored on the (given or development) instances
with the same adaptive sweep an agent gets, and the best by the primary metric (cost at the
target, geometric-mean ratio to the seed) is written out as `baselines/control_random.py`,
a frozen generator carrying only those constants -- so the control can be registered,
validated and re-run through the sandbox like any other entry. `control_search.json` keeps
every configuration tried, with its score, for the record.

The point of the control: an agent's gain must beat what random search over the same knobs
finds with the same evaluation budget; otherwise it has not found an idea.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys

from _common import ROOT, load
from instance_set import phase0_instances
import render_leaderboard
from sweep import sweep_entry

from harness import spec
from toolkit.cache import ScoreCache, fingerprint

SEARCH_CACHE = ".control_cache.json"
RECORD = ROOT / "control_search.json"
TEMPLATE = '''"""The control (CONTEXT.md §9): the best of {n_configs} random settings of the seed's own knobs,
found by scripts/control_search.py (seed {search_seed}) on the development set. Frozen constants,
no ideas: an agent has to beat this, not just the seed.

    layout={layout!r}, layout_seed={layout_seed}, scale={scale}, order={order}, spend={spend}
    development-set cost ratio to the seed at RMSE 0.05: {ratio:.3f}
"""
from harness import circuits

LAYOUT = {layout!r}
LAYOUT_SEED = {layout_seed}
SCALE = {scale}
ORDER = {order}
SPEND = {spend}
CZ_PER_FUSED_GATE = 3
STEP_COST = {{1: 1, 2: 2, 4: 10}}


def layout_for(spec):
    n = spec["num_qubits"]
    if LAYOUT == "identity":
        return list(range(n))
    if LAYOUT == "time_of_flight":
        return circuits.time_of_flight_mapping(spec["terms"], n, spec["measurement_site"], spec["butterfly_site"])
    import random
    rng = random.Random(LAYOUT_SEED)
    others = [s for s in range(n) if s != spec["measurement_site"]]
    rng.shuffle(others)
    order = [spec["measurement_site"]] + others          # order[p] = spin at position p
    mapping = [0] * n
    for p, s in enumerate(order):
        mapping[s] = p
    return mapping


def generate(spec):
    n = spec["num_qubits"]
    mapping = layout_for(spec)
    cz_per_step = STEP_COST[ORDER] * 2 * CZ_PER_FUSED_GATE * n * (n - 1) // 2
    budget = spec.get("cz_budget")
    steps = 8 if budget is None else max(1, int(SPEND * (int(budget) // cz_per_step)))
    return circuits.network_artifact(spec["terms"], spec["times"], steps, mapping, spec["butterfly_site"], ORDER,
                                     f"control: {{LAYOUT}} layout, scale {{SCALE}}, order {{ORDER}}, spend {{SPEND}}, {{steps}} steps",
                                     scale=SCALE)
'''


def sample_config(rng: random.Random) -> dict:
    return {
        "layout": rng.choice(["time_of_flight", "identity", "random"]),
        "layout_seed": rng.randrange(10 ** 6),
        # a rescaling beyond a few percent converges to the wrong dynamics and can never meet
        # the 5 % target (the first three draws of a +-10 % range all missed), so +-3 %
        "scale": round(rng.uniform(0.97, 1.03), 4),
        "order": rng.choice([1, 1, 2, 2, 4]),
        "spend": rng.choice([1.0, 1.0, 0.75, 0.5]),
    }


def write_generator(path, config: dict, n_configs: int, search_seed: int, ratio: float) -> None:
    path.write_text(TEMPLATE.format(n_configs=n_configs, search_seed=search_seed, ratio=ratio, **config))


def in_process_runner(path):
    import importlib.util
    module_spec = importlib.util.spec_from_file_location("control_candidate", str(path))
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    def run(_, cell_spec):
        try:
            return {"ok": True, "artifact": module.generate(cell_spec)}
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": repr(error)}
    return run


def primary(cache, fp, name, seed_scores, instances):
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--instances", default=None)
    parser.add_argument("--out", default="baselines/control_random.py")
    args = parser.parse_args(argv)
    problem, registry, board_cache = load()
    fp = fingerprint(problem)
    instances = phase0_instances() if args.instances is None else args.instances.split(",")
    seed_scores = render_leaderboard.collect(registry, board_cache, fp).get("seed_p1", {})
    if not seed_scores:
        raise SystemExit("the seed is not on the board yet; run scripts/register_baselines.py first")
    cache = ScoreCache(SEARCH_CACHE)
    rng = random.Random(args.seed)
    record = json.loads(RECORD.read_text()) if RECORD.exists() else []
    tried = {json.dumps(r["config"], sort_keys=True) for r in record}
    scratch = ROOT / ".control_candidate.py"
    for k in range(args.configs):
        config = sample_config(rng)
        key = json.dumps(config, sort_keys=True)
        if key in tried:
            continue
        name = f"control:{args.seed}:{k}"
        write_generator(scratch, config, args.configs, args.seed, float("nan"))
        report = sweep_entry(problem, cache, fp, name, str(scratch), instances, in_process_runner(scratch), log=None)
        ratio = primary(cache, fp, name, seed_scores, instances)
        record.append({"name": name, "config": config, "ratio": ratio, "failed": [f["cell"] for f in report["failed"]]})
        RECORD.write_text(json.dumps(record, indent=1) + "\n")
        print(f"{name}: {config} -> ratio {ratio if ratio is None else round(ratio, 4)}", flush=True)
    valid = [r for r in record if r["ratio"] is not None and not r["failed"]]
    if not valid:
        raise SystemExit("no configuration met the target everywhere")
    best = min(valid, key=lambda r: r["ratio"])
    write_generator(ROOT / args.out, best["config"], len(record), args.seed, best["ratio"])
    scratch.unlink(missing_ok=True)
    print(f"best: {best['name']} ratio {best['ratio']:.4f} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
