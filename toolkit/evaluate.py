"""
The combinator sketched in PLAYBOOK.md Step 5: run a generator, then
verify, then score if it passed. Takes a Problem (toolkit.problem) so it
never has to know anything about a specific problem beyond the second
contract.
"""
from typing import Callable

from toolkit.problem import Problem


class ScoreCollisionError(Exception):
    """Raised when score() returns a key that would overwrite verify()'s."""


def evaluate_artifact(problem: Problem, spec: dict, artifact) -> dict:
    """
    Runs verify(spec, artifact), then score(spec, artifact) only if
    verification passed. Use this directly when an artifact already
    exists (e.g. one that came back from isolation.run_isolated()) --
    evaluate() below is for the common case of also calling generate_fn.
    """
    result = problem.verify(spec, artifact)
    if not result["passed"]:
        return result

    metrics = problem.score(spec, artifact)
    # score() is the fork's own code and returns whatever metric names its
    # problem uses. A metric named "passed" or "checks" would land on top
    # of verify()'s verdict in the merge below -- turning a verified
    # artifact into a failed one, or replacing the record of what was
    # actually checked -- and every caller downstream reads result["passed"]
    # to decide whether to register, cache, and publish it.
    clobbered = sorted(set(result) & set(metrics))
    if clobbered:
        raise ScoreCollisionError(
            f"score() returned metric name(s) {clobbered}, which would overwrite "
            f"verify()'s own {sorted(result)}. Rename the metric in your harness."
        )
    return {**result, **metrics}


def evaluate(problem: Problem, spec: dict, generate_fn: Callable) -> dict:
    """
    Runs generate_fn(spec), then evaluate_artifact() on the result.

    generate_fn is called directly here -- this is for your own trusted
    code (Step 5: testing your own solution/encode.py locally). Never
    use this to run someone else's submission; the inbox pipeline
    (toolkit.inbox, Step 6) calls isolation.run_isolated() instead and
    only reaches evaluate_artifact() once a sandboxed artifact already
    exists.
    """
    artifact = generate_fn(spec)
    return evaluate_artifact(problem, spec, artifact)


def evaluate_artifact_guarded(problem: Problem, spec: dict, artifact) -> dict:
    """
    evaluate_artifact(), but a harness that raises becomes a failed result
    instead of propagating.

    verify() is contractually required never to raise (PLAYBOOK.md Step 3),
    but that is a rule the fork's own author has to keep, and an
    adversarial artifact is exactly what breaks it. Any pipeline running
    over a batch -- toolkit.inbox, toolkit.rescore -- uses this so one bad
    artifact can't abort the run partway through, after earlier work has
    already been committed.

    The failure is marked harness_error so a caller can tell "this
    submission is bad" from "your referee has a bug"; those need very
    different responses. evaluate() and evaluate_artifact() are
    deliberately left unguarded -- when you're testing your own code you
    want the traceback.
    """
    try:
        return evaluate_artifact(problem, spec, artifact)
    except Exception as e:
        return {
            "passed": False,
            "harness_error": True,
            "checks": {
                "harness": {
                    "passed": False,
                    "error": f"verify()/score() raised {type(e).__name__}: {e}",
                }
            },
        }


def checked_run_generate(run_generate, generate_path: str, spec: dict) -> dict:
    """
    Calls run_generate() and returns a result guaranteed to have the shape
    the pipelines index into: {"ok": True, "artifact": ...} or
    {"ok": False, "error": str}.

    run_generate is a callable the caller supplies, and in production it is
    isolation.run_isolated.run_isolated -- which parses whatever JSON came
    back over the sandbox boundary and returns it as-is. A submission that
    writes its own line to the real fd 1 and then calls os._exit() controls
    that value completely, so `{"ok": true}` with no artifact, or a bare
    `5`, are both reachable. Indexing them directly raised KeyError or
    AttributeError out of the batch loop, taking down every remaining
    submission in the run along with the offending one.

    Nothing is gained by a submission returning a forged artifact this way
    -- it still has to pass verify(), exactly as if generate() had returned
    it -- so this is about the batch surviving, not about trust.
    """
    result = run_generate(generate_path, spec)

    if not isinstance(result, dict):
        return {
            "ok": False,
            "error": (
                f"run_generate returned a {type(result).__name__}, not a dict; "
                "expected {'ok': bool, 'artifact': ...}"
            ),
        }
    if not result.get("ok"):
        return result
    if "artifact" not in result:
        return {
            "ok": False,
            "error": "run_generate reported ok but returned no 'artifact' key",
        }
    return result
