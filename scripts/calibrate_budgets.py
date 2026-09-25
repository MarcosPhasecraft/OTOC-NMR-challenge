"""Seed-calibrated caps (CONTEXT.md §8): for each instance, `cap_i` = CZ count of the seed at
the smallest step count whose mean absolute error on the instance's grid is <= 0.10 -- the
error level Google's seed started from (10.4 %). Written to `harness/data/budgets.json`,
frozen with the referee.

    python scripts/calibrate_budgets.py tier0

The seed's largest circuit uses all `steps` steps, so its echo costs 3N(N-1) x steps CZ
exactly; only the error needs computing. Existing entries are kept, so the run resumes.
Each entry records the step count and the seed's error at it, for the record.
"""
import argparse
import json
import os
import sys

from _common import ROOT  # noqa: F401

from baselines import seed_p1
from harness import spec
from harness.score import score

TARGET_MEAN_ERROR = 0.10
MAX_STEPS = 256


def seed_error_at(instance_id: str, steps: int) -> dict:
    instance_spec = spec.build_spec(instance_id)
    instance_spec["cz_budget"] = None
    n = instance_spec["num_qubits"]
    cz_per_step = 3 * n * (n - 1)
    artifact = seed_p1.generate({**instance_spec, "cz_budget": cz_per_step * steps})
    result = score(instance_spec, artifact)
    assert result["cz_count"] == cz_per_step * steps, (result["cz_count"], cz_per_step * steps)
    return result


def calibrate(instance_id: str) -> dict:
    steps = 1
    while steps <= MAX_STEPS:
        result = seed_error_at(instance_id, steps)
        if result["mean_abs"] <= TARGET_MEAN_ERROR:
            return {"cap": result["cz_count"], "seed_steps": steps,
                    "seed_mean_abs": result["mean_abs"], "seed_rmse": result["rmse"]}
        steps = steps + 1 if steps < 8 else steps * 2
    raise RuntimeError(f"{instance_id}: the seed never reaches mean error {TARGET_MEAN_ERROR} by {MAX_STEPS} steps")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("claim")
    args = parser.parse_args()
    budgets = spec.load_budgets()
    details_path = spec.BUDGETS_PATH.replace("budgets.json", "budgets_detail.json")
    details = json.load(open(details_path)) if os.path.exists(details_path) else {}
    instances = sorted({spec.split_instance_id(i)[0] for i in spec.parse_instances(args.claim)},
                       key=list(spec.load_manifest()).index)
    for instance_id in instances:
        if instance_id in budgets:
            continue
        entry = calibrate(instance_id)
        budgets[instance_id] = entry["cap"]
        details[instance_id] = entry
        os.makedirs(os.path.dirname(spec.BUDGETS_PATH), exist_ok=True)
        json.dump(dict(sorted(budgets.items())), open(spec.BUDGETS_PATH, "w"), indent=1)
        json.dump(dict(sorted(details.items())), open(details_path, "w"), indent=1)
        print(f"{instance_id}: cap={entry['cap']} (seed {entry['seed_steps']} steps, "
              f"mean_abs={entry['seed_mean_abs']:.4f}, rmse={entry['seed_rmse']:.4f})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
