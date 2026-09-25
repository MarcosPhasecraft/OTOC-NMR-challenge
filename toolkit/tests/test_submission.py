"""
Tests toolkit/submission.py against fixtures/fake_problem/.
"""
from pathlib import Path

import pytest

from toolkit.problem import load_problem
from toolkit.submission import ManifestError, validate_manifest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fake_problem"


def _problem():
    return load_problem(FIXTURE_ROOT / "harness")


def test_valid_manifest_resolves_instances():
    resolved = validate_manifest(
        {"name": "alice_trivial", "label": "Alice's Trivial", "sizes": "3,5-7"},
        _problem(),
    )
    assert resolved == {
        "name": "alice_trivial",
        "label": "Alice's Trivial",
        "instances": [3, 5, 6, 7],
        "generated_by": None,
    }


@pytest.mark.parametrize("missing", ["name", "label", "sizes"])
def test_missing_required_field_raises(missing):
    manifest = {"name": "alice", "label": "Alice", "sizes": "3-5"}
    del manifest[missing]
    with pytest.raises(ManifestError, match=missing):
        validate_manifest(manifest, _problem())


@pytest.mark.parametrize("bad_name", ["Alice", "1alice", "alice-x", "", "al ice"])
def test_bad_name_pattern_raises(bad_name):
    manifest = {"name": bad_name, "label": "Alice", "sizes": "3-5"}
    with pytest.raises(ManifestError, match="name"):
        validate_manifest(manifest, _problem())


def test_empty_label_raises():
    manifest = {"name": "alice", "label": "   ", "sizes": "3-5"}
    with pytest.raises(ManifestError, match="label"):
        validate_manifest(manifest, _problem())


def test_unparseable_sizes_raises():
    manifest = {"name": "alice", "label": "Alice", "sizes": "not-a-valid-claim"}
    with pytest.raises(ManifestError, match="could not be parsed"):
        validate_manifest(manifest, _problem())


def test_sizes_resolving_to_no_instances_raises():
    manifest = {"name": "alice", "label": "Alice", "sizes": "1-0"}  # inverted range -> []
    with pytest.raises(ManifestError, match="no instances"):
        validate_manifest(manifest, _problem())


def test_generated_by_absent_by_default():
    resolved = validate_manifest({"name": "alice", "label": "Alice", "sizes": "3"}, _problem())
    assert resolved["generated_by"] is None


def test_generated_by_carried_through_when_present():
    resolved = validate_manifest(
        {"name": "alice", "label": "Alice", "sizes": "3", "generated_by": "human"}, _problem()
    )
    assert resolved["generated_by"] == "human"


def test_generated_by_must_be_a_string_if_given():
    manifest = {"name": "alice", "label": "Alice", "sizes": "3", "generated_by": 42}
    with pytest.raises(ManifestError, match="generated_by"):
        validate_manifest(manifest, _problem())


def test_non_scalar_instance_ids_are_rejected_with_a_usable_message():
    """
    A tuple id looks like it should work, and then silently misbehaves in
    three places: build_spec() sees a list after the first round-trip, the
    leaderboard can't use it as a dict key, and the cache key it forms
    stops matching what wrote it. Refuse it at the boundary instead.
    """
    class TupleProblem:
        parse_instances = staticmethod(lambda claim: [(8, 4)])

    with pytest.raises(ManifestError) as excinfo:
        validate_manifest(
            {"name": "a", "label": "A", "sizes": "8x4"}, TupleProblem()
        )
    message = str(excinfo.value)
    assert "must be an int or a str" in message
    assert '"8x4"' in message  # says what to do instead


def test_string_and_int_instance_ids_are_both_fine():
    class MixedProblem:
        parse_instances = staticmethod(lambda claim: [3, "8x4"])

    resolved = validate_manifest(
        {"name": "a", "label": "A", "sizes": "whatever"}, MixedProblem()
    )
    assert resolved["instances"] == [3, "8x4"]


def test_a_generator_of_instances_is_materialized_not_consumed():
    """
    Validating a generator by iterating it consumes it. The caller was
    left with an exhausted one -- silently zero instances rather than the
    ones just checked -- and downstream a submission got registered
    having verified nothing.
    """
    class GeneratorProblem:
        parse_instances = staticmethod(lambda claim: (int(x) for x in claim.split(",")))

    resolved = validate_manifest(
        {"name": "a", "label": "A", "sizes": "3,5,10"}, GeneratorProblem()
    )
    assert resolved["instances"] == [3, 5, 10]


def test_a_generator_yielding_nothing_is_refused():
    """`if not instances` is always False for a generator, empty or not."""
    class EmptyGenerator:
        parse_instances = staticmethod(lambda claim: (i for i in []))

    with pytest.raises(ManifestError, match="no instances at all"):
        validate_manifest({"name": "a", "label": "A", "sizes": "x"}, EmptyGenerator())
