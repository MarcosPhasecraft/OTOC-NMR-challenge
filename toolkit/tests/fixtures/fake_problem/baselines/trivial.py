"""
A known-correct reference solution for the fake_problem fixture: always
returns [0, target], which trivially sums to target. Used only to test
toolkit/'s own code (registry, inbox, leaderboard) -- never a real
benchmark result.
"""


def generate(spec: dict) -> list:
    return [0, spec["target"]]
