"""
The CLI a fork's own run.py calls into (see _templates/run.py). Two
subcommands:

  run.py evaluate --instance 10 --solution solution/generate.py --note "..."
      The primary path: loads generate(spec) from --solution, builds
      spec via the problem's own build_spec(instance), runs it through
      evaluate(), prints the result, and always appends a row to the
      results log (--results, default ./results.jsonl) -- whether or
      not it passed, so failed attempts are visible too.

  run.py verify --instance 10 --artifact artifact.json
      A debug path for hand-written test cases: checks a artifact
      you already have as JSON directly against verify(), with no
      generate() call and nothing written to the results log. Useful
      for trying a rejection case by hand without writing a whole
      generate() first.

Both default --harness to ./harness, resolved relative to the current
directory -- run this from your fork's own repo root.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from toolkit.evaluate import evaluate
from toolkit.jsonable import dumps
from toolkit.problem import load_problem
from toolkit.results_log import RESERVED_FIELDS, append_result, reserved_collisions


def _load_generate(path):
    module_spec = importlib.util.spec_from_file_location("solution", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not hasattr(module, "generate"):
        raise SystemExit(f"{path} has no generate(spec) function")
    return module.generate


def _coerce_instance(raw: str):
    """Instance ids are usually ints; falls back to the raw string for e.g. an "8x4"-style id."""
    try:
        return int(raw)
    except ValueError:
        return raw


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="run.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="run a generate(spec) function through the full pipeline"
    )
    evaluate_parser.add_argument("--instance", required=True)
    evaluate_parser.add_argument("--harness", default="harness")
    evaluate_parser.add_argument("--solution", default="solution/generate.py")
    evaluate_parser.add_argument("--note", default="")
    evaluate_parser.add_argument("--results", default="results.jsonl")

    verify_parser = subparsers.add_parser(
        "verify", help="check a hand-written artifact directly -- a debug path, no generate() involved"
    )
    verify_parser.add_argument("--instance", required=True)
    verify_parser.add_argument("--harness", default="harness")
    verify_parser.add_argument("--artifact", required=True, help="path to a JSON file containing the artifact")

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    problem = load_problem(args.harness)
    instance_id = _coerce_instance(args.instance)
    spec = problem.build_spec(instance_id)

    if args.command == "verify":
        artifact = json.loads(Path(args.artifact).read_text())
        result = problem.verify(spec, artifact)
        # dumps(), not json.dumps(): a harness returning numpy in checks
        # would otherwise turn a finished run into a traceback here.
        print(dumps(result, "verify result", fallback=repr, indent=2))
        return 0 if result["passed"] else 1

    generate_fn = _load_generate(args.solution)
    result = evaluate(problem, spec, generate_fn)
    print(dumps(result, "evaluate result", fallback=repr, indent=2))

    collisions = reserved_collisions(result)
    if collisions:
        raise SystemExit(
            f"cannot log this run: verify()/score() returned {collisions}, which "
            f"collide with the results log's own columns {list(RESERVED_FIELDS)}. "
            "Rename the metric in your harness."
        )
    append_result(args.results, instance_id=instance_id, note=args.note, **result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
