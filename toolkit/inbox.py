"""
Processes every submission folder under inbox/: validates its manifest,
runs generate() at every claimed instance -- always through the
run_generate callable given, never called any other way -- and only
registers a submission (adds it to the registry, copies its file into
baselines/, caches its scores) if every single claimed instance passes.
No manual flags, no partial credit: one failing instance rejects the
whole submission, and nothing about it is cached or registered, even
for the instances that did pass.

Never deletes or moves a rejected submission's inbox folder -- that's a
maintainer's own call, not something this pipeline does automatically.

Everything here runs on the HOST, outside the sandbox: an inbox folder is
attacker-controlled input to ordinary filesystem code, so it is checked
for symlinks and size before anything is copied out of it. Sandboxing
generate() is not enough on its own if the surrounding file handling will
happily follow a link out of the submission folder.
"""
import json
import os
import shutil
from pathlib import Path

from toolkit.cache import FrozenGlobsError, ScoreCache, fingerprint
from toolkit.evaluate import checked_run_generate, evaluate_artifact_guarded
from toolkit.jsonable import NotJSONSerializable, to_jsonable
from toolkit.problem import Problem
from toolkit.registry import Registry
from toolkit.submission import ManifestError, validate_manifest

# A submission is one generate.py plus a folder of free-text notes. Both
# caps are generous for that and small enough that copying one out can't
# fill the disk. The file count matters separately from the byte total:
# a million one-byte files costs almost nothing to produce and passes any
# size limit, while still being expensive to walk and copy.
MAX_SUBMISSION_BYTES = 10_000_000
MAX_SUBMISSION_FILES = 1_000


def process_inbox(
    problem: Problem,
    *,
    inbox_dir,
    baselines_dir,
    registry: Registry,
    cache: ScoreCache,
    run_generate,
) -> list:
    """
    run_generate(generate_path: str, spec: dict) -> {"ok": bool,
    "artifact": ...} or {"ok": False, "error": ...}. In production, pass
    isolation.run_isolated.run_isolated -- never call a submission's
    generate() any other way.

    Returns one report per folder directly under inbox_dir:
    {"folder": str, "accepted": bool, "harness_error": bool,
     "reason": str or None, "per_instance": {instance_id: verify_result}}.

    harness_error distinguishes "this submission is bad" from "your
    verify()/score() raised", which need very different responses.
    """
    inbox_dir = Path(inbox_dir)
    baselines_dir = Path(baselines_dir)
    baselines_dir.mkdir(parents=True, exist_ok=True)

    # Not created the way baselines/ is, and the asymmetry is deliberate:
    # an inbox this function invented would process nothing and report
    # nothing, which is indistinguishable from an inbox that happened to
    # be empty -- so a typo in the path would look like a quiet success.
    # Reading a missing one used to raise FileNotFoundError from
    # Path.iterdir() several frames down, naming neither the argument nor
    # what to do; PLAYBOOK.md Step 6's own wiring snippet hit exactly that
    # on a fresh fork, because the template ships no inbox/ of its own.
    if not inbox_dir.is_dir():
        raise FileNotFoundError(
            f"no inbox directory at {inbox_dir}. process_inbox() reads submission "
            "folders from it rather than creating it, so that a mistyped path "
            "cannot look like an empty inbox. Create it and put one folder per "
            "submission inside."
        )

    # is_dir() follows symlinks, so check is_symlink() first -- otherwise a
    # symlinked directory in inbox/ would be walked as if it were a
    # submission folder.
    folders = sorted(
        p for p in inbox_dir.iterdir() if p.is_dir() and not p.is_symlink()
    )
    return [
        _process_one(problem, folder, baselines_dir, registry, cache, run_generate)
        for folder in folders
    ]


def _unsafe_path_reason(folder: Path):
    """
    Why this submission folder can't be copied from, or None if it's fine.

    Rejects any symlink anywhere in the tree. shutil.copy and
    shutil.copytree both follow symlinks by default, so a submission
    containing `memory/notes.md -> ~/.ssh/id_rsa` would have that file's
    *contents* copied into baselines/<name>.memory/ -- a directory that is
    normally committed and published with the leaderboard. No code has to
    run for that to happen, so the sandbox never sees it.

    Rejects a hard link too, for the same reason with the link already
    resolved: `stat` cannot tell one from an ordinary file by type, and
    st_nlink > 1 is the only signal. See the comment at that check.

    Anything that isn't a regular file or a directory is rejected for the
    same reason. A named pipe in memory/ makes shutil.copytree raise, and
    that landed mid-batch: after generate.py had already been copied into
    baselines/, before the registry was written, with every later
    submission in the run never reached.

    A legitimate submission has no reason to contain either, so this
    rejects them outright rather than trying to classify which ones are
    dangerous.

    Walks lazily and stops at the first thing that disqualifies the
    folder, so a pathological submission costs the time to reach its
    first bad entry rather than the time to enumerate all of it.
    os.walk does not descend into symlinked directories, and they are
    rejected on sight along with symlinked files.
    """
    total_bytes = 0
    total_files = 0

    for dirpath, dirnames, filenames in os.walk(folder):
        # Sorted in place so the walk order -- and therefore which entry a
        # rejection names -- is deterministic.
        dirnames.sort()
        filenames.sort()

        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                return (
                    f"{path.relative_to(folder)} is a symlink; submissions must "
                    "contain only regular files and directories"
                )

        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_file():
                # A FIFO, socket, or device node. is_file() is False for
                # all of them, so they'd otherwise slip past the counters
                # below and reach shutil.
                return (
                    f"{path.relative_to(folder)} is not a regular file; "
                    "submissions must contain only regular files and directories"
                )
            # A hard link is indistinguishable from an ordinary file by
            # stat type -- same inode, no flag saying so -- and st_nlink is
            # the only thing that gives it away. It is the symlink problem
            # with the link already resolved: shutil.copy reads the inode
            # and writes those bytes into baselines/<name>.memory/, which
            # is normally committed and published.
            #
            # link() needs no read permission on the target, only on the
            # containing directory, so on a shared machine this lets
            # someone who cannot read a file have the maintainer's own copy
            # step extract it for them. Hard links don't survive tar, zip
            # or git, so a mailed submission cannot carry one; a folder
            # handed over on the same filesystem can.
            if path.stat().st_nlink > 1:
                return (
                    f"{path.relative_to(folder)} is a hard link (st_nlink="
                    f"{path.stat().st_nlink}); submissions must contain only "
                    "regular files with a single name"
                )
            total_files += 1
            if total_files > MAX_SUBMISSION_FILES:
                return (
                    f"submission folder has more than {MAX_SUBMISSION_FILES} "
                    "files"
                )
            total_bytes += path.stat().st_size
            if total_bytes > MAX_SUBMISSION_BYTES:
                return (
                    "submission folder is over the "
                    f"{MAX_SUBMISSION_BYTES}-byte limit"
                )

    return None


def _process_one(problem, folder, baselines_dir, registry, cache, run_generate) -> dict:
    manifest_path = folder / "submission.json"
    generate_path = folder / "generate.py"

    unsafe = _unsafe_path_reason(folder)
    if unsafe:
        return _rejected(folder.name, unsafe)

    # is_file(), not exists(): a *directory* named submission.json or
    # generate.py exists, isn't a symlink, and doesn't appear in os.walk's
    # filenames -- so it passes _unsafe_path_reason() and then raises
    # IsADirectoryError out of the read or the copy below, mid-batch.
    for path, label in ((manifest_path, "submission.json"), (generate_path, "generate.py")):
        if not path.exists():
            return _rejected(folder.name, f"no {label}")
        if not path.is_file():
            return _rejected(folder.name, f"{label} is not a regular file")

    try:
        # read_bytes + explicit decode, and OSError caught alongside: a
        # manifest saved in cp1252, or one nobody has permission to read,
        # raised UnicodeDecodeError or PermissionError -- neither of which
        # is a JSONDecodeError, so both escaped this handler and took the
        # whole batch down with them. Every one of these is a fact about
        # one submission, so every one is a rejection.
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except json.JSONDecodeError as e:
        return _rejected(folder.name, f"submission.json is not valid JSON: {e}")
    except UnicodeDecodeError as e:
        return _rejected(folder.name, f"submission.json is not valid UTF-8: {e}")
    except OSError as e:
        return _rejected(folder.name, f"submission.json could not be read: {e}")

    try:
        resolved = validate_manifest(manifest, problem)
    except ManifestError as e:
        return _rejected(folder.name, str(e))

    name = resolved["name"]
    if name in registry.names():
        return _rejected(folder.name, f"name {name!r} is already registered")

    if not resolved["instances"]:
        # Belt and braces. validate_manifest already refuses an empty
        # claim, but acceptance below is "every claimed instance passed",
        # which is vacuously true of none of them -- so a submission that
        # verified nothing would be registered. The one property this
        # pipeline exists to guarantee should not rest on a check made
        # somewhere else.
        return _rejected(folder.name, "resolved to no instances; nothing would be verified")

    per_instance = {}
    all_passed = True
    for instance_id in resolved["instances"]:
        spec = problem.build_spec(instance_id)
        run_result = checked_run_generate(run_generate, str(generate_path), spec)
        if not run_result.get("ok"):
            per_instance[instance_id] = {
                "passed": False,
                "checks": {"generate": {"passed": False, "error": run_result.get("error")}},
            }
            all_passed = False
            continue
        result = evaluate_artifact_guarded(problem, spec, run_result["artifact"])
        per_instance[instance_id] = result
        if not result.get("passed"):
            all_passed = False

    if not all_passed:
        harness_error = any(r.get("harness_error") for r in per_instance.values())
        # fallback=repr: this is a report for a human, and a diagnostic
        # carrying an odd value must not stop it being printed or saved.
        # The strict conversion below is the one that guards stored data.
        per_instance = to_jsonable(per_instance, "per_instance", fallback=repr)
        return {
            "folder": folder.name,
            "accepted": False,
            "harness_error": harness_error,
            "reason": (
                "harness raised while checking this submission -- see per_instance; "
                "verify() must never raise (PLAYBOOK.md Step 3)"
                if harness_error
                else "failed verification at one or more claimed instances"
            ),
            "per_instance": per_instance,
        }

    # Convert before touching anything on disk, and strictly: these
    # results are about to be cached, so an approximated value would
    # become a permanent wrong number. Failing here rather than after
    # registry.register() keeps the submission resubmittable.
    # Values only, leaving the keys as the original instance ids. Passing
    # the whole dict through would stringify any non-scalar key, and the
    # cache would then be written under a key nothing ever reads back.
    # Ids are checked to be scalars upstream, so this is belt and braces.
    try:
        per_instance = {
            instance_id: to_jsonable(result, "score")
            for instance_id, result in per_instance.items()
        }
    except NotJSONSerializable as e:
        return _rejected(folder.name, f"score() returned unwritable values: {e}")

    # Before anything is written to disk, for the same reason the strict
    # conversion above is: fingerprint() raises when FROZEN_GLOBS matches
    # no files, and raising after register() would leave this submission
    # registered with no cached scores and its name permanently taken --
    # the exact end state TOOLKIT.md item 12 describes and this ordering
    # exists to prevent. It also aborts the batch, so every later folder
    # goes unprocessed too.
    try:
        fp = fingerprint(problem)
    except FrozenGlobsError as e:
        return _rejected(folder.name, f"cannot fingerprint the referee: {e}")

    dest_module = f"{name}.py"
    dest_path = baselines_dir / dest_module
    # shutil.copy() into an existing *directory* copies the file inside it
    # rather than over it, so the submission would be accepted and
    # registered with a "module" that names a directory -- rescore() then
    # reports it unusable forever and load_generate() cannot import it.
    # baselines/ is a committed directory that hand-tidying and older
    # layouts have been through, so what is already at that path is not a
    # given. Refuse loudly; it is the maintainer's mess to clear, not
    # something to silently overwrite.
    if dest_path.is_symlink() or (dest_path.exists() and not dest_path.is_file()):
        return _rejected(
            folder.name,
            f"cannot write baselines/{dest_module}: something is already there "
            "and it is not a regular file",
        )
    shutil.copy(generate_path, dest_path)

    memory_src = folder / "memory"
    if memory_src.is_dir():
        memory_dest = baselines_dir / f"{name}.memory"
        # A leftover at that path is not necessarily a directory -- a
        # previous run under a different layout, or a hand-tidied
        # baselines/. rmtree() on a plain file raises NotADirectoryError,
        # and it raised here: after generate.py had already been copied,
        # before the registry was written.
        if memory_dest.is_symlink() or (memory_dest.exists() and not memory_dest.is_dir()):
            memory_dest.unlink()
        elif memory_dest.exists():
            shutil.rmtree(memory_dest)
        # symlinks=True preserves a link as a link instead of copying
        # whatever it points at; _unsafe_path_reason() has already rejected
        # any submission containing one, so this is the second of two locks.
        shutil.copytree(memory_src, memory_dest, symlinks=True)

    registry.register(
        name,
        module=dest_module,
        label=resolved["label"],
        instances=resolved["instances"],
        generated_by=resolved["generated_by"],
    )

    for instance_id, result in per_instance.items():
        cache.set(fp, name, instance_id, result)

    return {
        "folder": folder.name,
        "accepted": True,
        "harness_error": False,
        "reason": None,
        "per_instance": per_instance,
    }


def _rejected(folder_name: str, reason: str) -> dict:
    return {
        "folder": folder_name,
        "accepted": False,
        "harness_error": False,
        "reason": reason,
        "per_instance": {},
    }
