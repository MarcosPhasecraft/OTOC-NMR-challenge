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

# The other tier-0 instances the seed brings to 10 % within 16 steps: the same regime as the
# board, never optimised on. A kept candidate is re-scored on a fresh draw from here
# (scripts/validation.py, CONTEXT.md §8) so a policy tuned to the 12 above costs points.
VALIDATION_POOL = (
    "instance_101_d_8", "instance_120_d_5", "instance_122_d_8", "instance_124_d_5", "instance_136_d_6",
    "instance_137_d_5", "instance_139_d_5", "instance_145_d_5", "instance_147_d_6", "instance_176_d_5",
    "instance_179_d_7", "instance_185_d_7", "instance_187_d_5", "instance_190_d_7", "instance_192_d_8",
    "instance_24_d_5", "instance_31_d_5", "instance_38_d_6", "instance_42_d_5", "instance_53_d_5",
    "instance_68_d_5", "instance_75_d_6", "instance_87_d_5", "instance_88_d_7", "instance_8_d_6",
    "instance_96_d_5",
)

# The tier-0 instances the seed cannot bring to 10 % within 16 steps: long tmax (1.8-20)
# with a weakly coupled carbon and a fast proton bath, needing 70-300 seed steps. A separate,
# unranked table on the leaderboard (CONTEXT.md §8); nobody optimises on them. Their caps
# come from a geometric search seeded by the error-bounds repo's step counts.
HARD_INSTANCES = (
    "instance_148_d_8", "instance_167_d_7",                       # N = 10
    "instance_175_d_8", "instance_68_d_13",                       # N = 11
    "instance_179_d_9", "instance_27_d_14", "instance_57_d_14", "instance_59_d_8",   # N = 12
)


def phase0_instances() -> list[str]:
    manifest = spec.load_manifest()
    for group in (PHASE0_INSTANCES, VALIDATION_POOL, HARD_INSTANCES):
        missing = [i for i in group if i not in manifest]
        assert not missing, missing
    return list(PHASE0_INSTANCES)


def fresh_draw(generation: int, size: int = 4) -> list[str]:
    """`size` validation instances for a generation of the loop: a deterministic draw from the
    pool, different each generation, spread over the three sizes (at least one per size)."""
    import random
    manifest = spec.load_manifest()
    rng = random.Random(f"otoc-nmr-validation-{generation}")
    by_size: dict[int, list[str]] = {}
    for iid in VALIDATION_POOL:
        by_size.setdefault(manifest[iid]["num_qubits"], []).append(iid)
    draw = [rng.choice(group) for _, group in sorted(by_size.items())][:size]
    rest = [i for i in VALIDATION_POOL if i not in draw]
    rng.shuffle(rest)
    return sorted(draw + rest[:max(0, size - len(draw))], key=list(manifest).index)


def leaderboard_cells() -> list[str]:
    """Every (instance, budget) id on the Phase 0 leaderboard, in ladder order."""
    return spec.parse_instances(",".join(phase0_instances()))


LEADERBOARD_INSTANCES = leaderboard_cells()

if __name__ == "__main__":
    print(",".join(LEADERBOARD_INSTANCES))
    sys.exit(0)
