"""The frozen referee, and the five names the shared toolkit needs (TOOLKIT.md)."""
import os

# The referee parallelises over time points with one process per point; a multithreaded
# BLAS inside each of them oversubscribes the cores several times over (measured: 5-10x
# slower). Pin the linear algebra to one thread per process. Must run before numpy is
# imported, which is why it sits here, at the top of the package.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

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
