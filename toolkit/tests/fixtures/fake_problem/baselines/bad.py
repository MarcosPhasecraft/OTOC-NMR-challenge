"""
A deliberately invalid "solution," used to test that the toolkit's
pipeline actually rejects a bad submission rather than crashing or
silently accepting it.
"""


def generate(spec: dict) -> list:
    return [1, 1]  # only sums correctly when spec["target"] == 2
