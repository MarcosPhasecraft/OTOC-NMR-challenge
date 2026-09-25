"""
That loading a harness in one test does not change what "harness" means
in the next.

These two tests are deliberately order-dependent -- the second checks what
the first left behind -- because that is the shape of the bug. pytest runs
them in file order, and the point is the interaction, which no single test
can observe.

Without conftest.py's _isolate_loaded_harness fixture, the second test
fails: sys.modules["harness"] is still the fixture problem the first one
loaded. In a fork that is 40-odd failures in the fork's own tests, all
naming the fork's files, and all of them passing when that file is run on
its own.
"""
import sys
from pathlib import Path

from toolkit.problem import load_problem

FIXTURE_HARNESS = Path(__file__).parent / "fixtures" / "fake_problem" / "harness"

_loaded_by_the_first_test = {}


def test_one_loading_a_harness_makes_it_importable_under_that_name():
    problem = load_problem(FIXTURE_HARNESS)

    assert problem.build_spec(3) == {"target": 3}
    assert sys.modules["harness"].__file__ == str(FIXTURE_HARNESS / "__init__.py")
    _loaded_by_the_first_test["module"] = sys.modules["harness"]


def test_two_does_not_inherit_the_harness_the_first_test_loaded():
    assert _loaded_by_the_first_test, "the first test must run before this one"

    leaked = sys.modules.get("harness")

    assert leaked is not _loaded_by_the_first_test["module"], (
        "the harness loaded by the previous test is still registered under "
        "the global name 'harness'; a fork's own harness has been displaced "
        "by this suite's throwaway fixture"
    )
