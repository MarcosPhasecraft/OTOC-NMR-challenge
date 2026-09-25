"""
Loads a fork's harness/ package and validates it exposes the "second
contract" from TOOLKIT.md: build_spec, parse_instances, verify, score,
and FROZEN_GLOBS. Every other toolkit piece takes a Problem from here
instead of rediscovering the contract itself.
"""
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

REQUIRED_NAMES = ("build_spec", "parse_instances", "verify", "score", "FROZEN_GLOBS")

# An instance id must be a plain JSON scalar. This is a real restriction
# and it is worth stating why, because a tuple looks like it should work:
#
#   - Ids are written into registry.json and read back, so a tuple
#     returns as a list and build_spec() would see a different type on
#     every pass after the first.
#   - They key dicts in several places (the leaderboard's columns, the
#     held-out report), and a list can't be a dict key at all.
#   - They form the score cache key via JSON, so anything whose JSON
#     form isn't stable silently stops matching what it wrote.
#
# A composite id has a natural scalar spelling -- "8x4" rather than
# (8, 4) -- and parse_instances() exists precisely so a problem can
# choose that spelling. Enforcing it here turns three subtle,
# late-surfacing failures into one clear error at the boundary.
INSTANCE_ID_TYPES = (int, str)


class InstanceIdError(Exception):
    """Raised when an instance id isn't a plain JSON scalar."""


def check_instance_ids(instances, source: str):
    """
    Raises InstanceIdError unless every id is an int or a str, and
    returns them as a list. `source` names where they came from, e.g.
    "parse_instances()".

    Materialises first, and callers must use the returned list. Validating
    a generator by iterating it consumes it, so the caller would be left
    holding something already exhausted -- silently zero instances rather
    than the ones it just checked.
    """
    instances = list(instances)
    for instance_id in instances:
        # bool is an int subclass but is never a sensible instance id.
        if isinstance(instance_id, bool) or not isinstance(instance_id, INSTANCE_ID_TYPES):
            raise InstanceIdError(
                f"{source} produced instance id {instance_id!r} of type "
                f"{type(instance_id).__name__}; ids must be an int or a str. "
                "A composite id should be spelled as a string -- \"8x4\" rather "
                "than (8, 4) -- because ids round-trip through registry.json, "
                "key dicts, and form the score cache key. See TOOLKIT.md's "
                "'second contract'."
            )
    return instances


class ProblemContractError(Exception):
    """Raised when a harness/ directory doesn't satisfy the second contract."""


@dataclass
class Problem:
    build_spec: Callable
    parse_instances: Callable
    verify: Callable
    score: Callable
    frozen_globs: List[str]
    root: Path  # the directory containing harness/ -- FROZEN_GLOBS is relative to this


def load_problem(harness_dir) -> Problem:
    """
    harness_dir: path to a harness/ package (a directory with
    __init__.py) that re-exports build_spec, parse_instances, verify,
    score, and FROZEN_GLOBS at its top level.

    Loaded from the exact file path given, and registered in
    sys.modules under the literal name "harness" -- the same name a
    fork's own solution/baselines import it under in production (e.g.
    `from harness.constructors import ...`) -- so relative and absolute
    imports inside harness/ behave exactly as they would for real. Any
    previously loaded "harness" package (and its submodules) is
    discarded first, and the new one is located by its exact path, never
    by searching sys.path -- so repeated calls in the same process (e.g.
    a test suite loading several different harness/ directories one
    after another) never see a stale or wrong module, regardless of
    what's already sitting on sys.path.
    """
    harness_dir = Path(harness_dir).resolve()
    init_file = harness_dir / "__init__.py"
    if not init_file.exists():
        raise ProblemContractError(
            f"{harness_dir} is not a Python package (no __init__.py) -- "
            "load_problem() expects a harness/ package. See TOOLKIT.md's "
            "'second contract'."
        )

    for name in list(sys.modules):
        if name == "harness" or name.startswith("harness."):
            del sys.modules[name]

    module_spec = importlib.util.spec_from_file_location(
        "harness", init_file, submodule_search_locations=[str(harness_dir)],
    )
    module = importlib.util.module_from_spec(module_spec)
    sys.modules["harness"] = module  # registered before exec, so internal imports resolve
    module_spec.loader.exec_module(module)

    missing = [name for name in REQUIRED_NAMES if not hasattr(module, name)]
    if missing:
        raise ProblemContractError(
            f"{harness_dir} is missing required contract member(s): "
            f"{', '.join(missing)}. See TOOLKIT.md's 'second contract' for "
            "what harness/__init__.py must expose."
        )

    # Types too, not just presence. The point of loading through here is
    # that a contract slip fails immediately and says what's wrong,
    # instead of surfacing as something baffling several layers up --
    # FROZEN_GLOBS given as a plain string used to iterate character by
    # character and reach the caller as "Non-relative patterns are
    # unsupported".
    not_callable = [
        name for name in REQUIRED_NAMES[:4] if not callable(getattr(module, name))
    ]
    if not_callable:
        raise ProblemContractError(
            f"{harness_dir} exposes {', '.join(not_callable)} but they aren't "
            "callable. build_spec, parse_instances, verify, and score must all "
            "be functions. See TOOLKIT.md's 'second contract'."
        )

    frozen_globs = module.FROZEN_GLOBS
    if isinstance(frozen_globs, str) or not isinstance(frozen_globs, (list, tuple)):
        raise ProblemContractError(
            f"{harness_dir} has FROZEN_GLOBS = {frozen_globs!r}, but it must be a "
            "list of glob strings, e.g. [\"harness/*.py\"] -- a single string "
            "would be read one character at a time."
        )
    bad = [g for g in frozen_globs if not isinstance(g, str)]
    if bad:
        raise ProblemContractError(
            f"{harness_dir} has non-string entries in FROZEN_GLOBS: {bad!r}."
        )

    return Problem(
        build_spec=module.build_spec,
        parse_instances=module.parse_instances,
        verify=module.verify,
        score=module.score,
        frozen_globs=list(frozen_globs),
        root=harness_dir.parent,
    )
