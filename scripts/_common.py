"""Shared setup for the maintainer scripts: repo root on sys.path, cwd at the root (the
toolkit's FROZEN_GLOBS are root-relative), and the three objects every script needs."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from toolkit.cache import ScoreCache  # noqa: E402
from toolkit.problem import load_problem  # noqa: E402
from toolkit.registry import Registry  # noqa: E402

BASELINES_DIR = "baselines"
REGISTRY_PATH = "baselines/registry.json"
CACHE_PATH = ".score_cache.json"


def load():
    """(problem, registry, cache) for this fork."""
    return load_problem("harness"), Registry(REGISTRY_PATH), ScoreCache(CACHE_PATH)
