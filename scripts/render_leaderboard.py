#!/usr/bin/env python3
"""Render LEADERBOARD.md from the registry and the score cache (CONTEXT.md §8).

    python3 scripts/render_leaderboard.py

Reads only: every number comes from `.score_cache.json` under the current referee
fingerprint, so a stale cell after a frozen-file change shows as missing rather than as an
old number. Two views of the same cells:

1. one table per budget rung (x0.5, x1, x2, x4 of the seed-calibrated cap): each registered
   entry's mean RMSE and mean CZ count over the development instances, with the count of
   cells that are over budget (an over-budget cell is invalid at that rung and is not
   averaged in);
2. per instance, the nondominated (CZ, RMSE) points over every entry and rung -- the Pareto
   frontier, with the entry that produced each point.

Nothing is interpolated between rungs.
"""
import datetime as dt
import sys
from collections import defaultdict

from _common import ROOT, load
from instance_set import LEADERBOARD_INSTANCES, phase0_instances

from harness import spec
from toolkit.cache import fingerprint

OUT_MD = ROOT / "LEADERBOARD.md"


def collect(registry, cache, fp):
    """entry -> {cell id -> score dict}, cached under the current fingerprint only."""
    scores = {}
    for name in registry.names():
        cells = {}
        for cell in LEADERBOARD_INSTANCES:
            hit = cache.get(fp, name, cell)
            if hit is not None:
                cells[cell] = hit
        scores[name] = cells
    return scores


def rung_tables(registry, scores) -> str:
    lines = []
    for mult in spec.LADDER:
        tag = f"@{spec.format_multiplier(mult)}"
        cells = [c for c in LEADERBOARD_INSTANCES if c.endswith(tag)]
        lines.append(f"\n### Budget x{spec.format_multiplier(mult)} of the seed-calibrated cap\n")
        lines.append("| entry | mean RMSE | mean CZ | valid cells | over budget | missing |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        rows = []
        for name, cell_scores in scores.items():
            valid = [cell_scores[c] for c in cells if c in cell_scores and not cell_scores[c].get("over_budget")]
            over = sum(1 for c in cells if c in cell_scores and cell_scores[c].get("over_budget"))
            missing = sum(1 for c in cells if c not in cell_scores)
            mean_rmse = sum(s["rmse"] for s in valid) / len(valid) if valid else None
            mean_cz = sum(s["cz_count"] for s in valid) / len(valid) if valid else None
            rows.append((mean_rmse if mean_rmse is not None else float("inf"), name, mean_rmse, mean_cz, len(valid), over, missing))
        for _, name, mean_rmse, mean_cz, nvalid, over, missing in sorted(rows):
            label = registry.get(name).get("label", name)
            rmse_s = "—" if mean_rmse is None else f"{mean_rmse:.4f}"
            cz_s = "—" if mean_cz is None else f"{mean_cz:.0f}"
            lines.append(f"| {label} | {rmse_s} | {cz_s} | {nvalid}/{len(cells)} | {over} | {missing} |")
    return "\n".join(lines)


def frontier_tables(registry, scores) -> str:
    lines = ["\n## Pareto frontiers per instance\n",
             "Nondominated (CZ, RMSE) points over every entry and rung; lower is better on both. "
             "A point dominates another if it is no worse on both and better on one.\n"]
    budgets = spec.load_budgets()
    for instance in phase0_instances():
        points = []
        for name, cell_scores in scores.items():
            for cell, s in cell_scores.items():
                if spec.split_instance_id(cell)[0] == instance and not s.get("over_budget"):
                    points.append((s["cz_count"], s["rmse"], registry.get(name).get("label", name), cell.split("@")[1]))
        frontier = [p for p in points if not any((q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1])) for q in points)]
        frontier.sort()
        n = spec.load_manifest()[instance]["num_qubits"]
        lines.append(f"\n**{instance}** (N = {n}, cap = {budgets.get(instance, '?')} CZ)\n")
        lines.append("| CZ | RMSE | entry | rung |")
        lines.append("|---:|---:|---|---|")
        for cz, rmse, label, rung in frontier:
            lines.append(f"| {cz} | {rmse:.4f} | {label} | x{rung} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    problem, registry, cache = load()
    fp = fingerprint(problem)
    scores = collect(registry, cache, fp)
    if not any(scores.values()):
        print("no cached scores under the current referee fingerprint; run scripts/register_baselines.py", file=sys.stderr)
        return 1
    head = [f"# Leaderboard\n",
            f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by `scripts/render_leaderboard.py` "
            f"from `baselines/registry.json` and `.score_cache.json` (referee fingerprint `{fp[:12]}`). Do not edit by hand.\n",
            f"Development set: {len(phase0_instances())} tier-0 instances (N = 10-12), exact scoring, "
            f"budget ladder x0.5, x1, x2, x4 of each instance's seed-calibrated cap (CONTEXT.md §8).\n",
            "## By budget rung\n"]
    OUT_MD.write_text("\n".join(head) + rung_tables(registry, scores) + "\n" + frontier_tables(registry, scores) + "\n")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
