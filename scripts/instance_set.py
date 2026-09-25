"""The scored instance sets (CONTEXT.md §3): which (instance, budget) cells the leaderboard
shows. Phase 0 = the tier-0 development subset: 12 instances, four per size at N = 10, 11,
12, the first of each size in manifest order, times the four-rung budget ladder.

    python scripts/instance_set.py          # prints the claim string for a submission manifest
"""
import sys

from _common import ROOT  # noqa: F401  (puts the root on sys.path)

from harness import spec

PHASE0_PER_SIZE = 4
PHASE0_SIZES = (10, 11, 12)


def phase0_instances() -> list[str]:
    manifest = spec.load_manifest()
    chosen = []
    for size in PHASE0_SIZES:
        chosen.extend([k for k, v in manifest.items() if v["num_qubits"] == size][:PHASE0_PER_SIZE])
    return chosen


def leaderboard_cells() -> list[str]:
    """Every (instance, budget) id on the Phase 0 leaderboard, in ladder order."""
    return spec.parse_instances(",".join(phase0_instances()))


LEADERBOARD_INSTANCES = leaderboard_cells()

if __name__ == "__main__":
    print(",".join(LEADERBOARD_INSTANCES))
    sys.exit(0)
