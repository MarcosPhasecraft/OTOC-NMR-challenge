"""
The baseline registry: registry.json maps a baseline name to its module
file, label, the instance ids it's actually been verified at, and when it
was first registered.
Registered by toolkit.inbox (item 8) once a submission
passes verify() at every claimed instance, or by hand for your own
baselines during Stage 1 -- never edited to make an unverified baseline
appear registered.

If a registered module imports anything from your problem's harness/
(e.g. `from harness.constructors import ...`), call
toolkit.problem.load_problem() before loading that baseline -- this
module doesn't do that for you.
"""
import importlib.util
import json
import os
import time
from pathlib import Path, PurePath
from typing import Callable, Optional

from toolkit.jsonable import load_json_object, to_jsonable
from toolkit.problem import InstanceIdError, check_instance_ids

# Every entry register() writes has these. A file that has been
# hand-edited, merged badly, or truncated might not.
REQUIRED_ENTRY_FIELDS = ("module", "label", "instances")


class RegistryError(Exception):
    """
    Raised for an unknown baseline name, a malformed registry entry, or a
    module missing generate().
    """


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        return load_json_object(
            self.path,
            error=RegistryError,
            what="registry",
            recovery=(
                "Restore it from version control, or repair the merge by hand: a "
                "registry maps a baseline name to its entry, and it is the only "
                "record of which baselines passed and at which instances -- "
                "registered_at in particular cannot be reconstructed afterwards. "
                "It is deliberately not reset to empty, which would drop every "
                "accepted submission without saying so."
            ),
        )

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename, so an interrupted run can't leave a truncated
        # registry.json that every later run fails to parse.
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def register(
        self,
        name: str,
        *,
        module: str,
        label: str,
        instances: list,
        generated_by: Optional[str] = None,
    ):
        """
        Adds or overwrites one entry. `module` is a filename relative to
        the baselines/ directory (e.g. "trivial.py"). `instances` is the
        already-resolved list from problem.parse_instances(), not the
        raw manifest claim string -- the registry records what's
        actually been verified, not what was merely asked for.

        Stamps `registered_at` (epoch seconds) the first time a name is
        registered, and preserves it if the entry is later rewritten --
        the interesting moment is when a baseline first passed, not when
        its row was last touched. Nothing else records this, and it can't
        be reconstructed after the fact.
        """
        # instances came from the fork's parse_instances(); they are
        # stored data, so they convert strictly -- a numpy id that only
        # half round-tripped would silently stop matching its cache key.
        # Checked here too, not just in the inbox: baselines you register
        # by hand during Stage 1 take this path and would otherwise be the
        # one way a bad id gets in.
        instances = check_instance_ids(instances, "register(instances=...)")
        # Deduplicated, first occurrence kept. parse_instances() is the
        # fork's own code and is nowhere required to return distinct ids --
        # a "3,3" claim, or a grammar that expands two ranges that overlap,
        # legitimately produces repeats. Stored as-is they cost a second
        # full sandboxed run per repeat in rescore(), which is the most
        # expensive thing this toolkit does, and put one instance in two
        # buckets of the same report. The registry records *which*
        # instances verified, so a repeat carries no information.
        instances = list(dict.fromkeys(instances))
        existing = self._data.get(name) or {}
        entry = {
            "module": module,
            "label": label,
            "instances": to_jsonable(instances, "instances"),
            "registered_at": existing.get("registered_at", time.time()),
        }
        if generated_by is not None:
            entry["generated_by"] = generated_by
        self._data[name] = entry
        self._save()

    def get(self, name: str) -> dict:
        """
        One entry, checked for shape. registry.json is a plain file people
        do edit by hand, and a missing field would otherwise surface as a
        bare KeyError from whichever reader happened to touch it first.
        """
        if name not in self._data:
            raise RegistryError(f"no baseline registered under {name!r}")

        entry = self._data[name]
        if not isinstance(entry, dict):
            raise RegistryError(
                f"entry {name!r} in {self.path} is a {type(entry).__name__}, "
                "not an object"
            )
        missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in entry]
        if missing:
            raise RegistryError(
                f"entry {name!r} in {self.path} is missing {', '.join(missing)}. "
                "Entries are written by register(); if this file was edited by "
                "hand, every entry needs module, label, and instances."
            )
        module = entry["module"]
        # A module name has to stay inside baselines/, and pathlib will not
        # keep it there on its own: `Path("baselines") / "/etc/hosts"` is
        # `/etc/hosts`, because a Path join discards everything to the left
        # of an absolute right-hand side. rescore() then hands that path to
        # run_generate(), which in production bind-mounts it into the
        # container as the submission and runs it; load_generate() imports
        # it into *this* process.
        #
        # register() only ever writes f"{name}.py" with name matching
        # ^[a-z][a-z0-9_]*$, so nothing the toolkit writes can do this. The
        # exposure is a hand-edited or badly merged registry.json, which is
        # a supported way to correct the file -- so read is where it has to
        # be checked, exactly as for instance ids above.
        if not isinstance(module, str) or not module.strip():
            raise RegistryError(
                f"entry {name!r} in {self.path} has module {module!r}; it must be a "
                "non-empty filename relative to baselines/, e.g. \"alice.py\""
            )
        module_path = PurePath(module)
        if module_path.is_absolute() or module_path.anchor or ".." in module_path.parts:
            raise RegistryError(
                f"entry {name!r} in {self.path} has module {module!r}, which does not "
                "stay inside baselines/. A module is a relative filename with no "
                "'..' segments, e.g. \"alice.py\"."
            )

        if not isinstance(entry["instances"], list):
            raise RegistryError(
                f"entry {name!r} in {self.path} has instances of type "
                f"{type(entry['instances']).__name__}, not a list"
            )
        # The ids too, not just the list around them. register() enforces
        # this on the way in, but hand-editing registry.json is a supported
        # way to correct the file, and it bypasses register() entirely --
        # so read is the only place a hand-written id is ever seen. An id
        # that isn't a scalar reaches build_spec() as a list and forms a
        # cache key nothing reads back, which is exactly what the
        # restriction exists to prevent.
        try:
            check_instance_ids(entry["instances"], f"entry {name!r} in {self.path}")
        except InstanceIdError as e:
            raise RegistryError(str(e)) from e
        return entry

    def remove(self, name: str) -> dict:
        """
        De-registers one baseline and returns the entry that was removed.
        Raises RegistryError if it isn't registered.

        toolkit.rescore reports a baseline the current referee rejects and
        deliberately leaves it registered, because what to do about it is a
        maintainer's judgement call. This is how that call gets made. The
        baseline's cached scores are keyed by name and are *not* touched
        here -- pass the same name to ScoreCache.forget_baseline(), or they
        linger and reappear if the name is ever reused.
        """
        if name not in self._data:
            raise RegistryError(f"no baseline registered under {name!r}")
        entry = self._data.pop(name)
        self._save()
        return entry

    def names(self) -> list:
        return list(self._data)

    def entries(self) -> dict:
        return dict(self._data)

    def load_generate(self, name: str, baselines_dir) -> Callable:
        """
        Dynamically imports the registered module and returns its
        generate(spec) function.

        This executes the module IN THIS PROCESS. Once submissions are
        being accepted, baselines/ holds other people's code, so use this
        only for baselines you wrote yourself. Anything that re-runs
        registered baselines in bulk -- toolkit.rescore -- goes through
        the sandbox instead and never calls this.
        """
        entry = self.get(name)
        module_path = Path(baselines_dir) / entry["module"]
        module_spec = importlib.util.spec_from_file_location(f"baseline_{name}", module_path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        if not hasattr(module, "generate"):
            raise RegistryError(f"{module_path} has no generate(spec) function")
        return module.generate

    def build_baselines(self, baselines_dir) -> dict:
        """name -> generate callable, for every registered baseline."""
        return {name: self.load_generate(name, baselines_dir) for name in self.names()}
