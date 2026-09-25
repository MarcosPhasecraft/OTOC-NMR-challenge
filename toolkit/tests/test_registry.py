"""
Tests toolkit/registry.py against fixtures/fake_problem/baselines/.
"""
import json
import time
from pathlib import Path

import pytest

from toolkit.problem import InstanceIdError
from toolkit.registry import Registry, RegistryError

FIXTURE_BASELINES = Path(__file__).parent / "fixtures" / "fake_problem" / "baselines"


def test_get_raises_for_an_unknown_name(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    with pytest.raises(RegistryError, match="alice"):
        registry.get("alice")


def test_register_then_get_round_trips(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[1, 5, 10])

    entry = registry.get("trivial")
    assert {k: entry[k] for k in ("module", "label", "instances")} == {
        "module": "trivial.py", "label": "Trivial", "instances": [1, 5, 10]
    }
    assert isinstance(entry["registered_at"], float)


def test_register_omits_generated_by_when_not_given(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[1])
    assert "generated_by" not in registry.get("trivial")


def test_register_includes_generated_by_when_given(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register(
        "trivial", module="trivial.py", label="Trivial", instances=[1], generated_by="human"
    )
    assert registry.get("trivial")["generated_by"] == "human"


def test_register_overwrites_an_existing_entry(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[1])
    registry.register("trivial", module="trivial.py", label="Trivial v2", instances=[1, 2])

    assert registry.get("trivial")["label"] == "Trivial v2"
    assert registry.get("trivial")["instances"] == [1, 2]


def test_names_and_entries(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[1])
    registry.register("bad", module="bad.py", label="Bad", instances=[1])

    assert set(registry.names()) == {"trivial", "bad"}
    assert set(registry.entries()) == {"trivial", "bad"}


def test_persists_to_disk_across_new_instances(tmp_path):
    path = tmp_path / "registry.json"
    Registry(path).register("trivial", module="trivial.py", label="Trivial", instances=[1])

    reloaded = Registry(path)
    assert reloaded.get("trivial")["label"] == "Trivial"


def test_load_generate_imports_and_returns_the_function(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[10])

    generate = registry.load_generate("trivial", FIXTURE_BASELINES)
    assert generate({"target": 10}) == [0, 10]


def test_load_generate_raises_when_module_has_no_generate(tmp_path):
    (tmp_path / "no_generate.py").write_text("x = 1\n")
    registry = Registry(tmp_path / "registry.json")
    registry.register("broken", module="no_generate.py", label="Broken", instances=[1])

    with pytest.raises(RegistryError, match="no_generate.py"):
        registry.load_generate("broken", tmp_path)


def test_build_baselines_returns_a_callable_dict_for_every_entry(tmp_path):
    registry = Registry(tmp_path / "registry.json")
    registry.register("trivial", module="trivial.py", label="Trivial", instances=[10])
    registry.register("bad", module="bad.py", label="Bad", instances=[10])

    baselines = registry.build_baselines(FIXTURE_BASELINES)

    assert set(baselines) == {"trivial", "bad"}
    assert baselines["trivial"]({"target": 10}) == [0, 10]
    assert baselines["bad"]({"target": 10}) == [1, 1]


def test_registering_a_non_scalar_instance_id_is_refused(tmp_path):
    """
    Hand-registered Stage 1 baselines don't go through the manifest, so
    this is the one other way a bad id could get in.
    """
    registry = Registry(tmp_path / "registry.json")
    with pytest.raises(InstanceIdError, match="must be an int or a str"):
        registry.register("a", module="a.py", label="A", instances=[(8, 4)])
    assert registry.names() == []


def test_get_reports_a_malformed_entry_instead_of_a_bare_keyerror(tmp_path):
    """
    registry.json gets hand-edited. A missing field used to surface as a
    KeyError from whichever reader touched it first, naming nothing useful.
    """
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"a": {"module": "a.py", "label": "A"}}))
    registry = Registry(path)

    with pytest.raises(RegistryError) as excinfo:
        registry.get("a")
    message = str(excinfo.value)
    assert "missing instances" in message
    assert "registry.json" in message


def test_get_rejects_an_entry_that_is_not_an_object(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"a": "not an entry"}))
    with pytest.raises(RegistryError, match="not an object"):
        Registry(path).get("a")


def test_get_rejects_instances_that_are_not_a_list(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"a": {"module": "a.py", "label": "A", "instances": 3}}))
    with pytest.raises(RegistryError, match="not a list"):
        Registry(path).get("a")


def test_register_stamps_when_a_baseline_first_passed(tmp_path):
    """
    Nothing else records this. The results log only sees the maintainer's
    own local runs, never submissions, so without this there is no way to
    know when a baseline was accepted -- and no way to recover it later.
    """
    before = time.time()
    registry = Registry(tmp_path / "registry.json")
    registry.register("a", module="a.py", label="A", instances=[3])

    stamped = registry.get("a")["registered_at"]
    assert before <= stamped <= time.time()


def test_rewriting_an_entry_keeps_its_original_timestamp(tmp_path):
    """The interesting moment is when it first passed, not when the row was touched."""
    registry = Registry(tmp_path / "registry.json")
    registry.register("a", module="a.py", label="A", instances=[3])
    first = registry.get("a")["registered_at"]

    registry.register("a", module="a.py", label="A, revised", instances=[3, 5])
    assert registry.get("a")["registered_at"] == first
    assert registry.get("a")["label"] == "A, revised"


def test_an_entry_predating_the_timestamp_still_loads(tmp_path):
    """registered_at is additive; a registry written before it stays valid."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"a": {"module": "a.py", "label": "A", "instances": [3]}}))
    entry = Registry(path).get("a")
    assert entry["instances"] == [3]
    assert "registered_at" not in entry


# --- hand-edited registry.json, and the de-registration path ---------


def test_a_hand_written_non_scalar_instance_id_is_refused_on_read(tmp_path):
    """
    register() enforces the int-or-string rule on the way in, but editing
    registry.json by hand is a supported way to correct the file and
    bypasses register() entirely -- so read is the only place a
    hand-written id is ever seen. A list id reaches build_spec() as a list
    and forms a cache key nothing reads back.
    """
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(
        {"a": {"module": "a.py", "label": "A", "instances": [[8, 4]]}}
    ))

    with pytest.raises(RegistryError, match="ids must be an int or a str"):
        Registry(path).get("a")


def test_a_registry_file_that_is_not_an_object_is_refused(tmp_path):
    """names() used to return a list's elements as if they were baselines."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(["a", "b"]))

    with pytest.raises(RegistryError, match="not an object"):
        Registry(path)


def test_remove_de_registers_a_baseline_and_persists(tmp_path):
    """
    rescore() reports a baseline the current referee rejects and leaves it
    registered on purpose. This is how a maintainer makes that call -- the
    documented workflow used to end in an action the toolkit had no way to
    perform.
    """
    registry = Registry(tmp_path / "registry.json")
    registry.register("alice", module="alice.py", label="Alice", instances=[3])
    registry.register("bob", module="bob.py", label="Bob", instances=[3])

    removed = registry.remove("alice")

    assert removed["label"] == "Alice"
    assert registry.names() == ["bob"]
    assert Registry(tmp_path / "registry.json").names() == ["bob"]
    with pytest.raises(RegistryError, match="no baseline registered"):
        registry.remove("alice")


# --- found by the rescore property tests (pass eight) -----------------


@pytest.mark.parametrize("module", ["/etc/hosts", "/tmp/anything.py"])
def test_an_absolute_module_path_is_refused_on_read(tmp_path, module):
    """
    `Path("baselines") / "/etc/hosts"` is `/etc/hosts` -- a Path join
    discards everything left of an absolute right-hand side. rescore()
    then hands that path to run_generate(), which in production
    bind-mounts it into the container as the submission and runs it;
    load_generate() imports it into this process. register() can't write
    one (it always writes f"{name}.py"), so a hand-edited or badly merged
    registry.json is the way in -- which makes read the place to check.
    """
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(
        {"a": {"module": module, "label": "A", "instances": [3]}}
    ))

    with pytest.raises(RegistryError, match="does not stay inside baselines/"):
        Registry(path).get("a")


def test_a_module_path_escaping_with_dotdot_is_refused_on_read(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(
        {"a": {"module": "../../secrets.py", "label": "A", "instances": [3]}}
    ))

    with pytest.raises(RegistryError, match="does not stay inside baselines/"):
        Registry(path).get("a")


@pytest.mark.parametrize("module", [5, None, ["a.py"], {"x": 1}, "", "   "])
def test_a_module_that_is_not_a_usable_filename_is_refused_on_read(tmp_path, module):
    """A non-string used to raise TypeError from `baselines_dir / 5`, out of rescore()."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(
        {"a": {"module": module, "label": "A", "instances": [3]}}
    ))

    with pytest.raises(RegistryError, match="module"):
        Registry(path).get("a")


def test_an_ordinary_module_name_is_still_accepted(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({
        "a": {"module": "alice.py", "label": "A", "instances": [3]},
        "b": {"module": "sub/bob.py", "label": "B", "instances": [3]},
    }))

    registry = Registry(path)
    assert registry.get("a")["module"] == "alice.py"
    assert registry.get("b")["module"] == "sub/bob.py"  # relative, stays inside


def test_register_deduplicates_instances(tmp_path):
    """
    parse_instances() is the fork's own code and is nowhere required to
    return distinct ids -- "3,3", or a grammar whose ranges overlap,
    legitimately repeats. A repeat costs a second full sandboxed run per
    rescore and puts one instance in two buckets of the same report.
    """
    registry = Registry(tmp_path / "registry.json")

    registry.register("a", module="a.py", label="A", instances=[3, 5, 3, 5, 3])

    assert registry.get("a")["instances"] == [3, 5]  # order preserved, first kept


def test_a_corrupt_registry_file_says_which_file_and_what_it_costs(tmp_path):
    """
    registry.json is committed and hand-edited, so a bad merge is how it
    realistically breaks. Unlike the cache it cannot be rebuilt -- it is
    the only record of which baselines passed, and registered_at cannot be
    reconstructed -- so the message points at version control rather than
    at deleting it.
    """
    path = tmp_path / "registry.json"
    path.write_text("{oops")

    with pytest.raises(RegistryError) as caught:
        Registry(path)

    message = str(caught.value)
    assert str(path) in message
    assert "version control" in message
    assert path.exists()  # refused, not silently reset


def test_a_missing_registry_file_is_still_just_an_empty_registry(tmp_path):
    assert Registry(tmp_path / "absent.json").names() == []
