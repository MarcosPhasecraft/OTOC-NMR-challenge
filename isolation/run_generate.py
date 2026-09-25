"""
Runs INSIDE the sandbox container only -- never import this on the host.

Reads a spec and a path to an untrusted generate.py, calls generate(spec),
and writes the result to stdout as a single line of JSON. A submission's
exception never becomes a bare traceback on stdout; it always becomes
{"ok": false, "error": ...} instead, so the host side (run_isolated.py)
has exactly one format to parse regardless of what the submission did.

Stdout is reserved for that one line and nothing else. Two things
protect it, and both are needed:

- While the submission's code runs, fd 1 is swapped for fd 2, so an
  ordinary debug print() -- or a direct os.write(1, ...) -- lands on
  stderr instead of in the middle of the result.
- The result itself is written with os.write() to fd 1, not print(),
  because a submission is free to rebind sys.stdout during import and
  would otherwise carry the result away with it.

Without either one, a submission that merely logs its progress is
rejected for "non-JSON output".
"""
import importlib.util
import json
import os
import sys


def load_and_generate(generate_path: str, spec):
    module_spec = importlib.util.spec_from_file_location("submission", generate_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)  # the untrusted code runs here

    if not hasattr(module, "generate"):
        raise AttributeError("submission has no generate(spec) function")
    return module.generate(spec)


def main(generate_path: str, spec_path: str) -> dict:
    with open(spec_path) as f:
        spec = json.load(f)

    # Swap fd 1 for fd 2 while the submission runs. Redirecting sys.stdout
    # alone would not be enough: a submission can rebind sys.stdout or
    # write to fd 1 directly, and either would land in the middle of the
    # result line.
    saved_stdout_fd = os.dup(1)
    try:
        sys.stdout.flush()
        os.dup2(2, 1)
        try:
            artifact = load_and_generate(generate_path, spec)
        finally:
            sys.stdout.flush()
            os.dup2(saved_stdout_fd, 1)
    finally:
        os.close(saved_stdout_fd)

    return {"ok": True, "artifact": artifact}


def encode(result: dict) -> str:
    """
    Serializes the result, turning a non-JSON-serializable artifact into a
    reported error rather than a traceback. numpy is the usual cause:
    np.int64, np.bool_, and np.ndarray all fail here even though
    np.float64 happens to pass, so a generate() can look fine right up
    until one value comes back as an integer.
    """
    try:
        return json.dumps(result)
    except (TypeError, ValueError) as e:
        return json.dumps({
            "ok": False,
            "error": (
                f"generate() returned something that isn't JSON-serializable: {e}. "
                "An artifact must be plain data -- dicts, lists, strings, numbers, "
                "booleans. Convert numpy values with .item() or .tolist() first."
            ),
        })


def describe(e: BaseException) -> str:
    """
    The error text a submission's failure comes back as.

    A ModuleNotFoundError gets an extra line, because it is the one
    failure whose cause is invisible from inside the container: only the
    submission file itself and harness/ are mounted, so a baseline that
    imports a sibling -- `from baselines.helpers import ...`, which works
    perfectly well outside -- fails here with a bare "No module named
    'baselines'" that points at nothing. Shared constructions belong in
    harness/, which is mounted; see isolation/README.md.
    """
    text = f"{type(e).__name__}: {e}"
    if isinstance(e, ModuleNotFoundError):
        text += (
            ". Only this file and harness/ are mounted in the sandbox, along "
            "with the packages pinned in isolation/Dockerfile -- nothing else "
            "from the project is importable. Put shared code in harness/ and "
            "import it as harness.<module>."
        )
    return text


if __name__ == "__main__":
    try:
        result = main(sys.argv[1], sys.argv[2])
    except Exception as e:
        result = {"ok": False, "error": describe(e)}
    # os.write, not print: the submission may have rebound sys.stdout,
    # and the result must reach the real fd 1 regardless.
    os.write(1, (encode(result) + "\n").encode())
