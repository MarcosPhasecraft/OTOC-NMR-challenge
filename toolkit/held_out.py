"""
Enforces PLAYBOOK.md Step 5's "must be one uniform rule, not a lookup
table": runs generate(spec) at instance ids it wasn't specifically
written for, and reports whether it still produces something that
verifies. This can't prove uniformity -- no finite test can -- but it
catches the obvious failure: a submission that special-cases the sizes
it was tuned on and breaks everywhere else.

Meant to be called from a fork's own test suite against its own
solution/generate.py, e.g.:

    def test_generalizes_to_held_out_instances():
        problem = load_problem("harness")
        report = check_generalizes(problem, generate, held_out_instances=[11, 13, 14])
        failures = {k: v for k, v in report.items() if not v["passed"]}
        assert not failures, failures
"""
from typing import Callable, Iterable

from toolkit.problem import Problem


def check_generalizes(problem: Problem, generate_fn: Callable, held_out_instances: Iterable) -> dict:
    """
    Runs generate_fn at every held-out instance id and returns
    {instance_id: verify_result}. If generate_fn itself raises for a
    given instance (e.g. an edge case it wasn't tuned for), that's
    recorded as a failed result too, rather than stopping the whole
    check -- so the report shows every failure at once, not just
    whichever one happens to crash first.
    """
    results = {}
    for instance_id in held_out_instances:
        # build_spec() is inside the guard too. A held-out id is by
        # definition one nobody chose deliberately, so it is the likeliest
        # place for a problem's own build_spec() to refuse a size it does
        # not support -- and that raising here used to abort the whole
        # check, discarding the results already computed for every earlier
        # instance and never reaching the later ones.
        try:
            spec = problem.build_spec(instance_id)
            artifact = generate_fn(spec)
            result = problem.verify(spec, artifact)
        except Exception as e:
            result = {
                "passed": False,
                "checks": {"generate": {"passed": False, "error": f"{type(e).__name__}: {e}"}},
            }
        results[instance_id] = result
    return results
