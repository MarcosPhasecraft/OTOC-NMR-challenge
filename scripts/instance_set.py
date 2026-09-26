"""The scored instance sets (CONTEXT.md §3): which (instance, budget) cells the leaderboard
shows. Phase 0 = the tier-0 development subset: 12 instances chosen from the tier-0 seed scan
(`data/analysis/tier0_seed_scan.md`) to spread over the difficulty range while staying where
exact scoring is fast: seed caps of 4, 8 and 16 steps at every size, easy and hard members of
each group, tmax 0.4-1.6. The 11 tier-0 instances the seed cannot bring to 10 % mean error
within 16 steps (long tmax, weakly coupled carbon) are not scored here; they remain
unscored screening material and a later "hard" check.

    python scripts/instance_set.py          # prints the claim string for a submission manifest
"""
import sys

from _common import ROOT  # noqa: F401  (puts the root on sys.path)

from harness import spec

PHASE0_INSTANCES = (
    # N = 10: every instance the seed brings to 10 % within 16 steps (caps 8, 8, 16)
    "instance_35_d_5", "instance_4_d_5", "instance_63_d_5",
    # N = 11: two at cap 8 (easiest and hardest of that group), two at cap 16
    "instance_48_d_5", "instance_93_d_5", "instance_26_d_7", "instance_179_d_5",
    # N = 12: one at cap 4, two at cap 8, two at cap 16
    "instance_132_d_9", "instance_154_d_5", "instance_42_d_6", "instance_123_d_5", "instance_74_d_9",
)


def phase0_instances() -> list[str]:
    manifest = spec.load_manifest()
    missing = [i for i in PHASE0_INSTANCES if i not in manifest]
    assert not missing, missing
    return list(PHASE0_INSTANCES)


def leaderboard_cells() -> list[str]:
    """Every (instance, budget) id on the Phase 0 leaderboard, in ladder order."""
    return spec.parse_instances(",".join(phase0_instances()))


LEADERBOARD_INSTANCES = leaderboard_cells()

if __name__ == "__main__":
    print(",".join(LEADERBOARD_INSTANCES))
    sys.exit(0)
