"""
Puts the repo root on sys.path so `toolkit.*` and `isolation.*` import the
same way under pytest as they do from a fork's own run.py, no matter which
directory pytest was invoked from.

Also stops one test's harness leaking into the next -- see the fixture.
"""
import sys
from pathlib import Path

import pytest

ROOT = str(Path(__file__).parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _loaded_harness() -> dict:
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "harness" or name.startswith("harness.")
    }


@pytest.fixture(autouse=True)
def _isolate_loaded_harness():
    """
    Restores sys.modules' "harness" entries after every test.

    toolkit.problem.load_problem() registers whatever harness it loaded
    under the literal global name "harness", deleting any previously
    loaded one. That is deliberate and documented: a fork's baselines
    import it under exactly that name in production, so loading it under
    any other name would test something different from what runs.

    The cost falls on a fork. This suite loads a throwaway fixture harness
    dozens of times, and testpaths runs toolkit/ before tests/ -- so
    without this, a fork's own tests find the fixture sitting under the
    name their harness should have. Anything importing `harness.something`
    after collection then fails with "No module named
    'harness.something'", naming the fork's file rather than this one, and
    only in the full suite: the same tests pass when run alone. That is
    close to the worst way to find out.

    Found by building a real problem on this template; see KNOWN_ISSUES.md.
    """
    saved = _loaded_harness()
    try:
        yield
    finally:
        for name in list(_loaded_harness()):
            del sys.modules[name]
        sys.modules.update(saved)
