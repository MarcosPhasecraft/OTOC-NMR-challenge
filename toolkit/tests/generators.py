"""
Builds random submission folders, for the property tests in
test_inbox_generated.py.

KNOWN_ISSUES.md's "recurring failure class" section asks for exactly this:
nearly every defect found across six audit passes was an assumption about
input that the contract does not guarantee, and each pass found the next
instance of the class in the previous pass's work. Enumerating hazards one
at a time never gets ahead of that, because the next one is by definition
the one nobody thought of. Generating them does -- a defect only has to be
reachable from the grammar below, not to have occurred to anyone.

Everything here is seeded: a failing case prints its seed, and re-running
with that seed reproduces the exact tree. No third-party dependency --
`random` is enough, and the suite stays pytest-only.

The grammar deliberately mixes independent axes, because the interesting
failures live at their intersections rather than in any one of them: a
manifest that is valid JSON but not an object, a folder whose hazard sits
three directories down, a `sizes` string that parses but resolves to
nothing, a name that is legal for a submission but not for a filename.
"""
import json
import os
import random
import shutil
from pathlib import Path

# generate.py bodies. All pure -- the honest stub in the test module runs
# these in-process, so nothing here may touch the filesystem or the
# network. Sandboxing is isolation/'s job and is tested there; what is
# being tested here is the host-side pipeline around it.
BODIES = {
    "correct": "def generate(spec):\n    return [0, spec['target']]\n",
    "correct_alt": "def generate(spec):\n    t = spec['target']\n    return [t // 2, t - t // 2]\n",
    "wrong_constant": "def generate(spec):\n    return [1, 1]\n",
    "wrong_type": "def generate(spec):\n    return 'not a list'\n",
    "wrong_length": "def generate(spec):\n    return [1, 2, 3]\n",
    "returns_none": "def generate(spec):\n    return None\n",
    "raises": "def generate(spec):\n    raise ValueError('boom')\n",
    "raises_on_import": "raise RuntimeError('bad import')\n",
    "no_generate": "x = 1\n",
    "correct_only_at_small": (
        "def generate(spec):\n"
        "    t = spec['target']\n"
        "    return [0, t] if t < 6 else [0, 0]\n"
    ),
}

# Manifest bodies, as raw file text. Split into "could plausibly be
# accepted" and "must be rejected"; the properties never assume which,
# but the test module uses the distinction to check the run isn't
# vacuously rejecting everything.
GOOD_SIZES = ["3", "5", "3,5", "5-7", "3,5-7", " 3 , 5 ", "1-4"]
BAD_SIZES = ["", "   ", "abc", "3-", "-", "3,,5", "5-3", "1-", "x-y", "3.5"]


def _manifest_text(rng, name, kind) -> str:
    """One submission.json's literal bytes, for the given failure kind."""
    if kind == "not_json":
        return rng.choice(["{", "", "not json at all", "{'name': 'x'}", "}{"])
    if kind == "json_scalar":
        # Valid JSON, but not an object. `"name" not in 5` is a TypeError,
        # not a missing field -- the shapes that are neither dict nor
        # container are the ones that bite.
        return rng.choice(["5", "true", "false", "null", "3.5"])
    if kind == "json_container":
        return rng.choice(['[1, 2]', '"a string"', '[]', '[{"name": "x"}]'])

    manifest = {"name": name, "label": f"Label for {name}", "sizes": rng.choice(GOOD_SIZES)}
    if kind == "valid":
        if rng.random() < 0.3:
            manifest["generated_by"] = rng.choice(["gpt-4", "a human", ""])
        if rng.random() < 0.2:
            manifest["extra_field_we_ignore"] = rng.choice([1, [2], {"a": 3}])
    elif kind == "missing_field":
        del manifest[rng.choice(["name", "label", "sizes"])]
    elif kind == "bad_name":
        manifest["name"] = rng.choice([
            "Uppercase", "9leading", "has-dash", "has space", "", "..",
            "../escape", "a/b", "a.b", 5, None, ["a"], "_leading",
        ])
    elif kind == "bad_label":
        manifest["label"] = rng.choice(["", "   ", "\n", 5, None, [], {}])
    elif kind == "nasty_label":
        # Legal by the contract -- a non-empty string -- and hostile to a
        # markdown table. The leaderboard, not the inbox, is what has to
        # survive these, but they have to get registered first.
        manifest["label"] = rng.choice([
            "A | 9999 | forged", "line\nbreak", "tab\there", "back\\slash",
            "|", "---", "<script>", "*emph*", "a" * 300,
        ])
    elif kind == "bad_sizes":
        manifest["sizes"] = rng.choice(BAD_SIZES + [5, None, [], {}, True])
    elif kind == "bad_generated_by":
        manifest["generated_by"] = rng.choice([5, [], {}, True])
    else:
        raise AssertionError(f"unknown manifest kind {kind!r}")

    return json.dumps(manifest)


# Weighted, not uniform. Acceptance needs a valid manifest AND no hazard
# AND a body that verifies at every claimed instance, so uniform choice
# over three independent axes makes it vanishingly rare -- and every
# "if accepted then ..." property is vacuously true of a run that accepts
# nothing. The weights put acceptance somewhere around a quarter, so both
# branches get real traffic. test_the_generator_actually_reaches_both_outcomes
# is what stops this drifting back.
BODY_KINDS = (
    ["correct"] * 5 + ["correct_alt"] * 5 + ["correct_only_at_small"] * 2
    + [k for k in BODIES if k not in ("correct", "correct_alt", "correct_only_at_small")]
)

MANIFEST_KINDS = [
    "valid", "valid", "valid", "valid", "valid", "valid", "valid", "valid",
    "nasty_label", "nasty_label",
    "missing_field", "bad_name", "bad_label", "bad_sizes", "bad_generated_by",
    "not_json", "json_scalar", "json_container",
]

HAZARDS = [
    None, None, None, None, None, None, None, None,  # most folders are ordinary
    "symlink_file_outside",
    "symlink_file_inside",
    "symlink_dangling",
    "symlink_dir_outside",
    "symlink_as_generate",
    "symlink_as_manifest",
    "fifo",
    "fifo_nested",
    "empty_dir",
    "deep_nesting",
    "many_files",
    "big_file",
    "manifest_is_a_dir",
    "generate_is_a_dir",
    "manifest_not_utf8",
    "manifest_unreadable",
    "memory_is_a_file",
    "odd_filenames",
    "hard_link",
]


def _random_tree(rng, root: Path, depth: int, breadth: int):
    """A memory/-shaped subtree of ordinary files and directories."""
    root.mkdir(parents=True, exist_ok=True)
    for i in range(rng.randint(0, breadth)):
        (root / f"note{i}.md").write_text(
            rng.choice(["", "notes\n", "what I tried\n" * rng.randint(1, 20)])
        )
    if depth > 0:
        for i in range(rng.randint(0, 2)):
            _random_tree(rng, root / f"sub{i}", depth - 1, breadth)


def plant(
    folder: Path,
    rng: random.Random,
    *,
    name: str,
    canary: Path,
) -> dict:
    """
    Builds one submission folder and returns a record of what went into it:
    {"folder", "name", "manifest_kind", "body_kind", "hazard", "clean"}.

    "clean" means the folder contains no hazard and a valid manifest -- the
    only combination a caller may expect to be accepted, and then only if
    its generate body actually verifies at every claimed instance.
    """
    folder.mkdir(parents=True, exist_ok=True)
    manifest_kind = rng.choice(MANIFEST_KINDS)
    body_kind = rng.choice(BODY_KINDS)
    hazard = rng.choice(HAZARDS)

    (folder / "submission.json").write_text(_manifest_text(rng, name, manifest_kind))
    (folder / "generate.py").write_text(BODIES[body_kind])

    if rng.random() < 0.5:
        _random_tree(rng, folder / "memory", rng.randint(0, 2), 3)
    if rng.random() < 0.3:
        (folder / "README.md").write_text("hello\n")

    # Deletions first, hazards last. A hazard may make its own file
    # undeletable (manifest_unreadable chmods it to 000), and planting it
    # before the deletion step made the *generator* fail rather than the
    # pipeline -- which is a much more annoying bug to read.
    if rng.random() < 0.06:
        (folder / "generate.py").unlink(missing_ok=True)
    if rng.random() < 0.06:
        (folder / "submission.json").unlink(missing_ok=True)

    _plant_hazard(folder, rng, hazard, canary)

    return {
        "folder": folder.name,
        "name": name,
        "manifest_kind": manifest_kind,
        "body_kind": body_kind,
        "hazard": hazard,
        "clean": hazard is None and manifest_kind == "valid",
    }


def _plant_hazard(folder: Path, rng, hazard, canary: Path):
    if hazard is None:
        return

    if hazard == "symlink_file_outside":
        target = folder / rng.choice(["memory", "."]) / "leak.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(canary)
    elif hazard == "symlink_file_inside":
        (folder / "alias.py").symlink_to(folder / "generate.py")
    elif hazard == "symlink_dangling":
        (folder / "gone.md").symlink_to(folder / "nothing-here")
    elif hazard == "symlink_dir_outside":
        (folder / "escape").symlink_to(canary.parent, target_is_directory=True)
    elif hazard == "symlink_as_generate":
        (folder / "generate.py").unlink(missing_ok=True)
        (folder / "generate.py").symlink_to(canary)
    elif hazard == "symlink_as_manifest":
        (folder / "submission.json").unlink(missing_ok=True)
        (folder / "submission.json").symlink_to(canary)
    elif hazard == "fifo":
        os.mkfifo(folder / "pipe")
    elif hazard == "fifo_nested":
        nested = folder / "memory" / "deep"
        nested.mkdir(parents=True, exist_ok=True)
        os.mkfifo(nested / "pipe")
    elif hazard == "empty_dir":
        (folder / "empty").mkdir(exist_ok=True)
    elif hazard == "deep_nesting":
        deep = folder
        for i in range(rng.randint(3, 8)):
            deep = deep / f"d{i}"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "buried.md").write_text("deep\n")
    elif hazard == "many_files":
        many = folder / "memory"
        many.mkdir(parents=True, exist_ok=True)
        for i in range(rng.randint(25, 60)):
            (many / f"n{i}.md").write_text("x")
    elif hazard == "big_file":
        (folder / "big.bin").write_bytes(b"x" * rng.randint(3000, 9000))
    elif hazard == "manifest_is_a_dir":
        # Exists, is not a symlink, and never appears in os.walk's
        # filenames -- so it reaches read_text() as a directory.
        (folder / "submission.json").unlink(missing_ok=True)
        (folder / "submission.json").mkdir()
    elif hazard == "generate_is_a_dir":
        (folder / "generate.py").unlink(missing_ok=True)
        (folder / "generate.py").mkdir()
        (folder / "generate.py" / "inner.py").write_text("x = 1\n")
    elif hazard == "manifest_not_utf8":
        # A manifest saved in cp1252, or with any stray high byte.
        (folder / "submission.json").write_bytes(
            rng.choice([b'{"name": "\xff\xfe"}', b"\x80\x81\x82", b'{"label": "caf\xe9"}'])
        )
    elif hazard == "manifest_unreadable":
        manifest = folder / "submission.json"
        if manifest.is_file():
            os.chmod(manifest, 0o000)
    elif hazard == "memory_is_a_file":
        memory = folder / "memory"
        if memory.is_dir():
            shutil.rmtree(memory)
        memory.write_text("notes, but not a folder\n")
    elif hazard == "odd_filenames":
        odd = folder / "memory"
        odd.mkdir(parents=True, exist_ok=True)
        for filename in rng.sample(
            [".hidden", "with space.md", "dots.in.name.md", "\u00e9\u00e8.md",
             "-leading-dash", "tab\tname", "quote'name", 'double"name'],
            k=rng.randint(1, 4),
        ):
            try:
                (odd / filename).write_text("odd\n")
            except OSError:
                pass  # some names the host filesystem simply won't take
    elif hazard == "hard_link":
        # Inside memory/, because memory/ is the subtree that gets copied
        # into baselines/. A hard link anywhere else is never read, so
        # planting it at the top level would test nothing.
        memory = folder / "memory"
        memory.mkdir(parents=True, exist_ok=True)
        os.link(canary, memory / "note.md")
    else:
        raise AssertionError(f"unknown hazard {hazard!r}")


def build_inbox(inbox_dir: Path, seed: int, count: int, *, canary: Path) -> list:
    """
    Builds `count` submission folders under inbox_dir. Names collide on
    purpose about a fifth of the time, so the duplicate-name path is
    exercised both within one batch and against an earlier run.
    """
    rng = random.Random(seed)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    planted = []
    for i in range(count):
        name = f"sub{i}" if rng.random() > 0.2 else f"sub{rng.randint(0, count)}"
        planted.append(plant(
            inbox_dir / f"folder{i:02d}", rng, name=name, canary=canary,
        ))
    return planted


# ---------------------------------------------------------------------
# Project states, for the rescore property tests.
#
# rescore()'s untrusted input is not a submission folder -- it is the
# project itself: a registry.json that people hand-edit and merge badly
# (KNOWN_ISSUES.md gap 1 says a bad merge is the realistic corruption
# path, and gap 2's fix is "edit the file"), a baselines/ directory that
# accumulates across layouts and moves, and a committed score cache. So
# the grammar below generates *states* rather than folders.
# ---------------------------------------------------------------------

MODULE_BODIES = {
    "correct": "def generate(spec):\n    return [0, spec['target']]\n",
    "correct_alt": "def generate(spec):\n    t = spec['target']\n    return [t // 2, t - t // 2]\n",
    "wrong": "def generate(spec):\n    return [1, 1]\n",
    "raises": "def generate(spec):\n    raise ValueError('boom')\n",
    "raises_on_import": "raise RuntimeError('bad import')\n",
    "no_generate": "x = 1\n",
    "empty": "",
    "not_python": "this is not python at all !!\n",
    # Passes the first time it is run and fails after -- the case force=
    # exists to catch, and the one that makes a stale cache entry visible.
    "flaky": (
        "import pathlib\n"
        "STAMP = pathlib.Path(__file__).with_name('.stamp')\n"
        "def generate(spec):\n"
        "    if STAMP.exists():\n"
        "        return [0, spec['target'] + 1]\n"
        "    STAMP.write_text('x')\n"
        "    return [0, spec['target']]\n"
    ),
}

MODULE_BODY_KINDS = (
    ["correct"] * 6 + ["correct_alt"] * 4 + ["flaky"] * 2
    + [k for k in MODULE_BODIES if k not in ("correct", "correct_alt", "flaky")]
)

# How each registry entry is malformed, if at all. Weighted so most
# baselines are ordinary and the run has real work to do.
ENTRY_KINDS = (
    ["valid"] * 12
    + ["module_missing", "module_is_a_dir", "module_absolute", "module_traversal",
       "module_not_a_string", "module_empty", "missing_field", "entry_not_a_dict",
       "instances_not_a_list", "instances_non_scalar", "instances_empty",
       "instances_duplicated", "label_not_a_string", "extra_fields"]
)

CACHE_KINDS = (
    ["none"] * 5
    + ["current_passing", "current_failing", "other_fingerprint",
       "unregistered_instance", "unregistered_name", "not_a_dict"]
)


def build_project(root: Path, seed: int, count: int, *, outside: Path) -> dict:
    """
    Builds a whole project state under `root`: harness/, baselines/, a
    registry.json and a score cache, each entry independently malformed or
    not. Returns {"planted": [...], "root": ..., "harness": ...}.

    `outside` is a path outside baselines/ that no run may ever reach --
    the rescore equivalent of the inbox suite's canary.
    """
    rng = random.Random(seed)
    baselines = root / "baselines"
    baselines.mkdir(parents=True, exist_ok=True)

    registry_data = {}
    planted = []
    for i in range(count):
        name = f"base{i}"
        kind = rng.choice(ENTRY_KINDS)
        body_kind = rng.choice(MODULE_BODY_KINDS)
        instances = rng.choice([[3], [3, 5], [3, 5, 10], [5, 7], [1, 2, 3, 4]])

        entry = {
            "module": f"{name}.py",
            "label": f"Baseline {i}",
            "instances": list(instances),
            "registered_at": 1700000000.0 + i,
        }
        (baselines / f"{name}.py").write_text(MODULE_BODIES[body_kind])

        if kind == "module_missing":
            (baselines / f"{name}.py").unlink()
        elif kind == "module_is_a_dir":
            (baselines / f"{name}.py").unlink()
            (baselines / f"{name}.py").mkdir()
        elif kind == "module_absolute":
            # `Path("baselines") / "/etc/hosts"` is `/etc/hosts`.
            entry["module"] = str(outside)
        elif kind == "module_traversal":
            entry["module"] = f"../{outside.name}"
        elif kind == "module_not_a_string":
            entry["module"] = rng.choice([5, None, ["a.py"], {"x": 1}])
        elif kind == "module_empty":
            entry["module"] = rng.choice(["", "   "])
        elif kind == "missing_field":
            del entry[rng.choice(["module", "label", "instances"])]
        elif kind == "entry_not_a_dict":
            entry = rng.choice([5, "a string", ["a", "list"], None])
        elif kind == "instances_not_a_list":
            entry["instances"] = rng.choice([3, "3,5", {"3": 1}, None])
        elif kind == "instances_non_scalar":
            entry["instances"] = rng.choice([[[8, 4]], [{"n": 3}], [None], [3, [5]]])
        elif kind == "instances_empty":
            entry["instances"] = []
        elif kind == "instances_duplicated":
            entry["instances"] = list(instances) + list(instances)
        elif kind == "label_not_a_string":
            entry["label"] = rng.choice([5, None, [], {"a": 1}])
        elif kind == "extra_fields":
            entry["notes"] = "something a fork added"
            entry["generated_by"] = rng.choice(["gpt-4", 5, None])
        elif kind != "valid":
            raise AssertionError(f"unknown entry kind {kind!r}")

        registry_data[name] = entry
        planted.append({
            "name": name, "kind": kind, "body_kind": body_kind,
            "instances": list(instances), "cache_kind": rng.choice(CACHE_KINDS),
        })

    (root / "registry.json").write_text(json.dumps(registry_data, indent=2))
    return {"planted": planted, "root": root, "baselines": baselines}


def prefill_cache(cache, planted: list, fp: str, seed: int):
    """
    Puts the score cache into a random prior state. A committed cache is
    as much a merge casualty as a committed registry, and rescore()'s
    "already current" short-circuit reads it without looking inside.
    """
    rng = random.Random(seed + 1)
    for row in planted:
        kind = row["cache_kind"]
        if kind == "none":
            continue
        if kind == "current_passing":
            for instance_id in row["instances"]:
                cache.set(fp, row["name"], instance_id,
                          {"passed": True, "product": 0, "abs_diff": instance_id})
        elif kind == "current_failing":
            # Only a hand-edit or an older toolkit writes one of these --
            # the pipeline never does. It is here because "already
            # current" trusts the entry's existence, not its contents.
            for instance_id in row["instances"]:
                cache.set(fp, row["name"], instance_id,
                          {"passed": False, "checks": {"x": {"passed": False}}})
        elif kind == "other_fingerprint":
            for instance_id in row["instances"]:
                cache.set("0" * 64, row["name"], instance_id, {"passed": True, "product": 1})
        elif kind == "unregistered_instance":
            cache.set(fp, row["name"], rng.randint(900, 999), {"passed": True, "product": 2})
        elif kind == "unregistered_name":
            cache.set(fp, f"ghost_{row['name']}", 3, {"passed": True, "product": 3})
        elif kind == "not_a_dict":
            cache.set(fp, row["name"], row["instances"][0], rng.choice([5, "s", [1], None]))
        else:
            raise AssertionError(f"unknown cache kind {kind!r}")
