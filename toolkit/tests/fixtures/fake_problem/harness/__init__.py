"""
A deliberately trivial, throwaway problem used only to test toolkit/'s
own code. Never referenced from a real fork.

The "problem": an instance is a target integer. An artifact is a pair of
integers that must sum to it. Score is their product and their absolute
difference -- two independent metrics, kept as a vector on purpose, the
same way a real problem's score() would.
"""

FROZEN_GLOBS = ["harness/*.py"]


def build_spec(instance_id: int) -> dict:
    return {"target": instance_id}


def parse_instances(claim: str) -> list:
    """
    "3,5-7,10" -> [3, 5, 6, 7, 10]. A plain int, or an inclusive "a-b"
    range, comma-separated. Order preserved, duplicates dropped (keeping
    the first occurrence).
    """
    seen = []
    for part in claim.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            for n in range(int(lo), int(hi) + 1):
                if n not in seen:
                    seen.append(n)
        else:
            n = int(part)
            if n not in seen:
                seen.append(n)
    return seen


def verify(spec: dict, artifact) -> dict:
    """Never raises. artifact must be a list of exactly two ints summing to spec["target"]."""
    checks = {}

    well_formed = (
        isinstance(artifact, list)
        and len(artifact) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) for x in artifact)
    )
    checks["well_formed"] = {"passed": well_formed}
    if not well_formed:
        checks["well_formed"]["issue"] = "artifact must be a list of exactly two ints"
        return {"passed": False, "checks": checks}

    a, b = artifact
    total = a + b
    sums_correctly = total == spec["target"]
    checks["sums_to_target"] = {
        "passed": sums_correctly,
        "got": total,
        "want": spec["target"],
    }

    return {"passed": sums_correctly, "checks": checks}


def score(spec: dict, artifact) -> dict:
    """Runs only if verify() passed. Two independent metrics, never combined."""
    a, b = artifact
    return {"product": a * b, "abs_diff": abs(a - b)}
