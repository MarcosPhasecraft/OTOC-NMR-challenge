"""The loader: manifest, spec contents, sizes grammar, and the Hamiltonian sign convention."""
import json
import os

import numpy as np
import pytest

from harness import spec


def test_manifest_matches_tmax_table():
    manifest = spec.load_manifest()
    rebuilt = spec.build_manifest()
    assert manifest == rebuilt
    assert len(manifest) == 788
    assert all(v["tmax"] > 0 for v in manifest.values())
    assert all(v["tier"] in spec.TIERS for v in manifest.values())


def test_spec_is_complete_and_json_serialisable():
    instance_spec = spec.build_spec("instance_4_d_5", cz_budget=600)
    assert instance_spec["num_qubits"] == 10
    assert instance_spec["chain"] == list(range(10))
    assert instance_spec["measurement_site"] == 0 and instance_spec["butterfly_site"] == 1
    assert len(instance_spec["times"]) == spec.NUM_TIMES
    assert instance_spec["times"][-1] == pytest.approx(spec.load_manifest()["instance_4_d_5"]["tmax"])
    assert instance_spec["cz_budget"] == 600
    json.dumps(instance_spec)  # must cross the sandbox boundary as JSON
    assert "instance" not in instance_spec  # the candidate is not told which instance it is


def test_sign_convention_matches_vendored_orderings():
    """het bond -> ZZ +d ; hom bond -> XX -d and YY +d, per harness/vendor/gen_orderings.py."""
    matrix = spec.load_coupling_matrix("instance_4_d_5")
    terms = {(i, j, p): c for i, j, p, c in spec.build_spec("instance_4_d_5")["terms"]}
    n = matrix.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            d = float(matrix[i, j])
            if d == 0.0:
                continue
            if (i < spec.NUM_CARBONS) ^ (j < spec.NUM_CARBONS):
                assert terms[(i, j, "ZZ")] == d
                assert (i, j, "XX") not in terms
            else:
                assert terms[(i, j, "XX")] == -d and terms[(i, j, "YY")] == d
                assert (i, j, "ZZ") not in terms


def test_parse_instances_grammar():
    manifest = spec.load_manifest()
    assert spec.parse_instances("tier0") == [k for k, v in manifest.items() if v["tier"] == "tier0"]
    assert len(spec.parse_instances("N=10")) == 5
    assert spec.parse_instances("instance_4_d_5, instance_4_d_5") == ["instance_4_d_5"]
    with pytest.raises(ValueError):
        spec.parse_instances("instance_does_not_exist")
    with pytest.raises(KeyError):
        spec.build_spec("instance_does_not_exist")


def test_excluded_instances_are_not_loadable():
    # instance_104_d_13 (N=6) never reached C=0.1 and has no tmax; it must not be in play
    assert "instance_104_d_13" not in spec.load_manifest()
    assert os.path.isfile(os.path.join(spec.DATA_DIR, "instances", "instance_104_d_13",
                                       "hamiltonian_projected.npy"))  # data kept, instance excluded
