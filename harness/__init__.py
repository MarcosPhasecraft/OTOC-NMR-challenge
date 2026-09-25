"""The frozen referee, and the five names the shared toolkit needs (TOOLKIT.md)."""
from harness.artifact import verify
from harness.score import score
from harness.spec import build_spec, parse_instances

FROZEN_GLOBS = [
    "harness/*.py",
    "harness/vendor/*.py",
    "harness/data/references/*.json",
    "harness/data/*.json",
    "data/manifest.json",
]

__all__ = ["build_spec", "parse_instances", "verify", "score", "FROZEN_GLOBS"]
