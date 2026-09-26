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


# Hard instances (scripts/instance_set.py): the seed needs 70-300 steps, so a search from one
# step would cost hours per instance. Start from the error-bounds repo's swapnet first-order
# step count for RMS 0.1 (r_targets.csv, `r_interp_0.1`; identity layout, 20-sample Haar, so
# only a guide) rounded to a power of two, and search geometrically: halve while the target is
# met, double until it is. Resolution is a factor of two, recorded in `search`.
HARD_START = {"instance_148_d_8": 64, "instance_167_d_7": 128, "instance_175_d_8": 128, "instance_68_d_13": 64,
              "instance_179_d_9": 128, "instance_27_d_14": 16, "instance_57_d_14": 64, "instance_59_d_8": 32}
MAX_HARD_STEPS = 2048


def calibrate(instance_id: str) -> dict:
    if instance_id in HARD_START:
        return calibrate_geometric(instance_id, HARD_START[instance_id])
    steps = 1
    while steps <= MAX_STEPS:
        result = seed_error_at(instance_id, steps)
        if result["mean_abs"] <= TARGET_MEAN_ERROR:
            return {"cap": result["cz_count"], "seed_steps": steps, "search": "linear-then-doubling",
                    "seed_mean_abs": result["mean_abs"], "seed_rmse": result["rmse"]}
        steps = steps + 1 if steps < 8 else steps * 2
    raise RuntimeError(f"{instance_id}: the seed never reaches mean error {TARGET_MEAN_ERROR} by {MAX_STEPS} steps")


def calibrate_geometric(instance_id: str, start: int) -> dict:
    probes = {}

    def met(steps):
        if steps not in probes:
            probes[steps] = seed_error_at(instance_id, steps)
            print(f"  {instance_id} @ {steps} steps: mean_abs={probes[steps]['mean_abs']:.4f}", flush=True)
        return probes[steps]["mean_abs"] <= TARGET_MEAN_ERROR

    steps = start
    if met(steps):
        while steps > 1 and met(steps // 2):
            steps //= 2
    else:
        while not met(steps):
            steps *= 2
            if steps > MAX_HARD_STEPS:
                raise RuntimeError(f"{instance_id}: the seed never reaches mean error {TARGET_MEAN_ERROR} by {MAX_HARD_STEPS} steps")
    result = probes[steps]
    return {"cap": result["cz_count"], "seed_steps": steps, "search": f"geometric from {start}",
            "seed_mean_abs": result["mean_abs"], "seed_rmse": result["rmse"],
            "probes": {str(k): round(v["mean_abs"], 4) for k, v in sorted(probes.items())}}


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
