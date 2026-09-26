"""The instance sets: disjoint, all in tier 0, and the validation draws behave."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import instance_set  # noqa: E402

from harness import spec  # noqa: E402


def test_sets_are_disjoint_and_cover_tier0():
    manifest = spec.load_manifest()
    dev, pool, hard = set(instance_set.PHASE0_INSTANCES), set(instance_set.VALIDATION_POOL), set(instance_set.HARD_INSTANCES)
    assert not (dev & pool) and not (dev & hard) and not (pool & hard)
    tier0 = {k for k, v in manifest.items() if v["tier"] == "tier0"}
    assert dev | pool | hard == tier0
    assert len(dev) == 12 and len(hard) == 8


def test_fresh_draw_is_deterministic_spread_and_changes_with_generation():
    manifest = spec.load_manifest()
    a, b, c = instance_set.fresh_draw(1), instance_set.fresh_draw(1), instance_set.fresh_draw(2)
    assert a == b and a != c and len(a) == 4
    assert set(a) <= set(instance_set.VALIDATION_POOL)
    assert {manifest[i]["num_qubits"] for i in a} == {10, 11, 12} or len({manifest[i]["num_qubits"] for i in a}) >= 2
