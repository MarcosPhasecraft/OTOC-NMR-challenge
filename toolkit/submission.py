"""
Validates a submission's manifest (submission.json) and resolves its
"sizes" claim into an actual list of instance ids via the problem's own
parse_instances(). Doesn't touch the filesystem beyond the manifest
dict itself -- toolkit.inbox (item 8) is what reads submission.json off
disk and checks for generate.py / memory/ alongside it.
"""
import re

from toolkit.problem import InstanceIdError, check_instance_ids

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ManifestError(Exception):
    """Raised for a malformed or incomplete submission.json."""


def validate_manifest(manifest: dict, problem) -> dict:
    """
    Checks `manifest` (already-parsed JSON) against the required shape
    and resolves its "sizes" claim via problem.parse_instances().
    Returns {"name", "label", "instances", "generated_by"}. Raises
    ManifestError, with a specific reason, on anything wrong -- a
    missing field, a bad name, a "sizes" string parse_instances() itself
    can't make sense of, or ids that aren't plain JSON scalars.
    """
    # A JSON document is not necessarily a JSON *object*. "5", "true" and
    # "null" are all nine bytes or fewer of entirely valid JSON, and
    # `"name" not in 5` is a TypeError rather than a missing field -- which
    # escaped toolkit.inbox's `except ManifestError` and took down the
    # whole batch, every later submission included. A string or a list
    # happens to survive the `in` test and land on the missing-field error
    # below; that it did was luck, not design.
    if not isinstance(manifest, dict):
        raise ManifestError(
            f"submission.json contains a {type(manifest).__name__}, not an object; "
            'it must be a JSON object like {"name": ..., "label": ..., "sizes": ...}'
        )

    for field in ("name", "label", "sizes"):
        if field not in manifest:
            raise ManifestError(f"submission.json is missing required field {field!r}")

    name = manifest["name"]
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise ManifestError(
            f"name {name!r} must match {NAME_PATTERN.pattern} "
            "(lowercase, starts with a letter, only letters/digits/underscore)"
        )

    label = manifest["label"]
    if not isinstance(label, str) or not label.strip():
        raise ManifestError("label must be a non-empty string")

    sizes = manifest["sizes"]
    if not isinstance(sizes, str) or not sizes.strip():
        raise ManifestError("sizes must be a non-empty string")

    try:
        # list() here, not later: parse_instances() may reasonably return a
        # generator, and "if not instances" is always False for one -- so an
        # empty claim would sail through and, worse, whatever consumed the
        # generator next would find it already exhausted.
        instances = list(problem.parse_instances(sizes))
    except Exception as e:
        raise ManifestError(f"sizes {sizes!r} could not be parsed: {type(e).__name__}: {e}") from e

    if not instances:
        raise ManifestError(f"sizes {sizes!r} resolved to no instances at all")

    try:
        instances = check_instance_ids(instances, "parse_instances()")
    except InstanceIdError as e:
        raise ManifestError(str(e)) from e

    generated_by = manifest.get("generated_by")
    if generated_by is not None and not isinstance(generated_by, str):
        raise ManifestError("generated_by must be a string if given")

    return {
        "name": name,
        "label": label,
        "instances": instances,
        "generated_by": generated_by,
    }
