#!/usr/bin/env python3
"""Render LEADERBOARD.md from the registry and the score cache (CONTEXT.md §8).

    python3 scripts/render_leaderboard.py

Reads only: every number comes from `.score_cache.json` under the current referee
fingerprint, so a stale cell after a frozen-file change shows as missing rather than as an
old number. Each registered entry was called once per (instance, budget rung) and every call
gave one measured (CZ, RMSE) point. Three views of those points:

1. **Cost at the target error** (primary, ranks the board): per instance, the CZ count of the
   cheapest valid point with RMSE <= TARGET_RMSE, and its ratio to the seed's; entries are
   ranked by the geometric mean of that ratio over the development instances. An entry that
   never meets the target on an instance has no cell there and ranks below every entry that
   meets it everywhere.
2. **Error at the Google-comparable budget** (secondary): RMSE at the x1 rung, where the
   plain seed sits at ~10 % mean error, and the improvement factor over the seed (Google's
   AlphaEvolve: 10.4 % -> 0.82 % at fixed budget, 12.7x).
3. Per instance, the nondominated (CZ, RMSE) points over every entry and rung -- the Pareto
   frontier, with the entry and rung that produced each point.

Nothing is interpolated between rungs; a cost at target is always a measured point.
"""
import datetime as dt
import json
import math
import sys

from _common import ROOT, load
from instance_set import HARD_INSTANCES, LEADERBOARD_INSTANCES, phase0_instances

from harness import spec
from toolkit.cache import fingerprint

OUT_MD = ROOT / "LEADERBOARD.md"
SEED = "seed_p1"


def collect(registry, cache, fp, cells_wanted=None):
    """entry -> {cell id -> score dict}, cached under the current fingerprint only."""
    scores = {}
    for name in registry.names():
        cells = {}
        for cell in (LEADERBOARD_INSTANCES if cells_wanted is None else cells_wanted):
            hit = cache.get(fp, name, cell)
            if hit is not None:
                cells[cell] = hit
        scores[name] = cells
    return scores


def rungs(instance):
    return [f"{instance}@{spec.format_multiplier(m)}" for m in spec.LADDER]


def valid_points(cell_scores, instance):
    """The measured (cz, rmse, rung) points of one entry on one instance, over-budget ones excluded."""
    out = []
    for cell, s in cell_scores.items():
        base, mult = spec.split_instance_id(cell)
        if base == instance and not s.get("over_budget"):
            out.append((int(s["cz_count"]), float(s["rmse"]), spec.format_multiplier(mult)))
    return out


def cost_at_target(cell_scores, instance, target):
    hits = [p for p in valid_points(cell_scores, instance) if p[1] <= target]
    return min(hits) if hits else None


def geo_mean(values):
    return math.exp(sum(math.log(v) for v in values) / len(values)) if values else None


def label_of(registry, name):
    return registry.get(name).get("label", name)


def target_table(registry, scores, instances) -> str:
    target = spec.TARGET_RMSE
    seed_cost = {i: cost_at_target(scores.get(SEED, {}), i, target) for i in instances}
    lines = [f"\n## 1. Cost at the target error (RMSE <= {target:g}) -- ranks the board\n",
             "CZ count of the cheapest measured point under the target, per instance; `ratio` is the "
             "geometric mean over instances of (entry CZ / seed CZ), lower is better. `miss` = the target "
             "was not met at any rung.\n",
             "| rank | entry | ratio to seed | met | mean CZ | " + " | ".join(instances) + " |",
             "|---:|---|---:|---:|---:|" + "---:|" * len(instances)]
    rows = []
    for name, cell_scores in scores.items():
        costs = {i: cost_at_target(cell_scores, i, target) for i in instances}
        ratios = [costs[i][0] / seed_cost[i][0] for i in instances if costs[i] and seed_cost[i]]
        met = sum(1 for i in instances if costs[i])
        ratio = geo_mean(ratios) if met == len(instances) and ratios else None
        mean_cz = sum(costs[i][0] for i in instances if costs[i]) / met if met else None
        rows.append((0 if ratio is not None else 1, -met, ratio if ratio is not None else float("inf"), name, costs, met, mean_cz, ratio))
    for rank, (_, _, _, name, costs, met, mean_cz, ratio) in enumerate(sorted(rows), 1):
        cells = " | ".join(f"{costs[i][0]} (x{costs[i][2]})" if costs[i] else "miss" for i in instances)
        ratio_s = "—" if ratio is None else f"{ratio:.3f}"
        cz_s = "—" if mean_cz is None else f"{mean_cz:.0f}"
        lines.append(f"| {rank} | {label_of(registry, name)} | {ratio_s} | {met}/{len(instances)} | {cz_s} | {cells} |")
    return "\n".join(lines)


def google_table(registry, scores, instances) -> str:
    tag = "@1"
    lines = ["\n## 2. Error at the Google-comparable budget (x1 of the seed-calibrated cap)\n",
             "RMSE at the rung where the plain seed sits at ~10 % mean error, per instance, and the "
             "geometric-mean improvement factor over the seed (AlphaEvolve on DMBP: 10.4 % -> 0.82 % "
             "mean error, 12.7x; its 792-CZ budget was one step of a 15-spin seed). An over-budget "
             "cell is invalid at this rung and shown as `over`.\n",
             "| entry | improvement over seed | mean RMSE | " + " | ".join(instances) + " |",
             "|---|---:|---:|" + "---:|" * len(instances)]
    seed_cells = scores.get(SEED, {})

    def at_x1(cell_scores, instance):
        s = cell_scores.get(f"{instance}{tag}")
        if s is None:
            return None
        return "over" if s.get("over_budget") else float(s["rmse"])

    rows = []
    for name, cell_scores in scores.items():
        values = {i: at_x1(cell_scores, i) for i in instances}
        numeric = [v for v in values.values() if isinstance(v, float)]
        factors = [at_x1(seed_cells, i) / values[i] for i in instances
                   if isinstance(values[i], float) and isinstance(at_x1(seed_cells, i), float) and values[i] > 0]
        factor = geo_mean(factors) if len(factors) == len(instances) else None
        mean_rmse = sum(numeric) / len(numeric) if numeric else None
        rows.append((mean_rmse if mean_rmse is not None else float("inf"), name, values, factor, mean_rmse))
    for _, name, values, factor, mean_rmse in sorted(rows):
        cells = " | ".join("—" if v is None else v if isinstance(v, str) else f"{v:.4f}" for i, v in values.items())
        f_s = "—" if factor is None else f"{factor:.2f}x"
        m_s = "—" if mean_rmse is None else f"{mean_rmse:.4f}"
        lines.append(f"| {label_of(registry, name)} | {f_s} | {m_s} | {cells} |")
    return "\n".join(lines)


def frontier_tables(registry, scores, instances) -> str:
    lines = ["\n## 3. Pareto frontiers per instance\n",
             "Nondominated (CZ, RMSE) points over every entry and rung; lower is better on both. "
             "A point dominates another if it is no worse on both and better on one.\n"]
    budgets = spec.load_budgets()
    manifest = spec.load_manifest()
    for instance in instances:
        points = []
        for name, cell_scores in scores.items():
            for cz, rmse, rung in valid_points(cell_scores, instance):
                points.append((cz, rmse, label_of(registry, name), rung))
        frontier = [p for p in points if not any((q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1])) for q in points)]
        frontier.sort()
        lines.append(f"\n**{instance}** (N = {manifest[instance]['num_qubits']}, cap = {budgets.get(instance, '?')} CZ)\n")
        lines.append("| CZ | RMSE | entry | rung |")
        lines.append("|---:|---:|---|---|")
        for cz, rmse, label, rung in frontier:
            lines.append(f"| {cz} | {rmse:.4f} | {label} | x{rung} |")
    return "\n".join(lines)


def validation_table(registry) -> str:
    path = ROOT / "validation.json"
    lines = ["\n## 4. Validation on unseen instances\n",
             "Each kept entry is re-scored, next to the seed, on a fresh draw of four instances from the "
             "validation pool (tier-0 instances never on the board; `scripts/validation.py`). `holds` "
             "means it beats the seed there and its cost ratio is within 25 % of its development-set "
             "ratio. Baselines are exempt: they are the reference, not candidates.\n",
             "| entry | generation | draw | dev ratio | validation ratio | holds |", "|---|---:|---|---:|---:|---|"]
    if not path.exists():
        lines.append("| (none yet) | | | | | |")
        return "\n".join(lines)
    data = json.loads(path.read_text())
    for name, v in sorted(data.items()):
        label = registry.get(name).get("label", name) if name in registry.names() else name
        dev = "—" if v.get("dev_ratio") is None else f"{v['dev_ratio']:.3f}"
        val = "—" if v.get("validation_ratio") is None else f"{v['validation_ratio']:.3f}"
        lines.append(f"| {label} | {v.get('generation')} | {', '.join(v.get('draw', []))} | {dev} | {val} | "
                     f"{'yes' if v.get('holds') else 'no'} |")
    return "\n".join(lines)


def hard_table(registry, cache, fp) -> str:
    cells = [c for i in HARD_INSTANCES for c in rungs(i)]
    scores = collect(registry, cache, fp, cells)
    lines = ["\n## 5. Hard set (unranked)\n",
             "Tier-0 instances with long tmax and a weakly coupled carbon, where the seed needs 70-300 steps "
             "for 10 % error. Nobody optimises on them; cost at the target and error at x1 are reported for "
             "every entry that has been run there, as a second generalisation axis. Empty until calibrated.\n"]
    budgets = spec.load_budgets()
    calibrated = [i for i in HARD_INSTANCES if i in budgets]
    if not calibrated or not any(scores.values()):
        lines.append("_no hard-set cells scored yet_")
        return "\n".join(lines)
    return "\n".join(lines) + target_table(registry, scores, calibrated).replace("## 1. Cost at the target error", "### Cost at the target error") \
        .replace("-- ranks the board", "-- hard set, not ranked")


def main(argv=None) -> int:
    problem, registry, cache = load()
    fp = fingerprint(problem)
    scores = collect(registry, cache, fp)
    if not any(scores.values()):
        print("no cached scores under the current referee fingerprint; run scripts/register_baselines.py", file=sys.stderr)
        return 1
    instances = phase0_instances()
    head = ["# Leaderboard\n",
            f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/render_leaderboard.py` "
            f"from `baselines/registry.json` and `.score_cache.json` (referee fingerprint `{fp[:12]}`). Do not edit by hand.\n",
            f"Development set: {len(instances)} tier-0 instances (N = 10-12), exact scoring. Each entry is called "
            f"once per instance and budget rung ({len(spec.LADDER)} rungs, x{spec.format_multiplier(spec.LADDER[0])} to "
            f"x{spec.format_multiplier(spec.LADDER[-1])} of the seed-calibrated cap, ratio sqrt 2); every call is one "
            f"measured (CZ, RMSE) point (CONTEXT.md §8).\n"]
    body = target_table(registry, scores, instances) + "\n" + google_table(registry, scores, instances) + "\n" \
        + frontier_tables(registry, scores, instances) + "\n" + validation_table(registry) + "\n" \
        + hard_table(registry, cache, fp) + "\n"
    OUT_MD.write_text("\n".join(head) + body)
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
