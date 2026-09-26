"""
Runs on the HOST. Calls generate(spec) from an untrusted submission file
inside a disposable, network-less Docker container, and returns its
result as a plain dict.

Fails closed: if Docker itself isn't available, this raises rather than
falling back to running the submission unsandboxed. There is no fallback
path, on purpose -- see README.md's hard rule.

Fails loudly, too. A stopped Docker daemon or an image that was never
built used to come back looking exactly like a submission that crashed,
so a maintainer running the inbox pipeline with Docker off would reject
every legitimate submission and never learn the sandbox hadn't run once.
Host-side problems raise SandboxUnavailable; only the submission's own
behaviour returns {"ok": False}.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid

IMAGE = os.environ.get("SAGECRAFT_IMAGE", "sagecraft-runner:latest")
HARNESS_DIR = os.path.join(os.path.dirname(__file__), "..", "harness")

DEFAULTS = dict(
    timeout_s=30,
    memory="2g",              # CONTEXT.md §4: 2 GB per generate call
    cpus="1",
    pids=64,
    tmp_size="256m",
    max_output_bytes=200_000_000,   # ~500 bytes per gate: 400k gates; the x8 rung at tier 1 is ~100k
)


class SandboxUnavailable(RuntimeError):
    """
    The sandbox could not be used. Never raised for anything a submission
    did -- only for Docker being absent, its daemon being down, or the
    image not being built. Callers should stop, not skip the submission.
    """


def ensure_available():
    """
    Checks Docker is usable and the image exists, raising
    SandboxUnavailable with the command that fixes it if not.

    Call this once before processing a batch, so a stopped daemon fails
    immediately instead of after every submission has been marked failed.
    """
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise SandboxUnavailable(
            "Docker isn't installed -- refusing to run a submission unsandboxed. "
            "See isolation/README.md."
        ) from None
    except subprocess.TimeoutExpired:
        raise SandboxUnavailable("`docker info` timed out; is the daemon healthy?") from None

    if info.returncode != 0:
        raise SandboxUnavailable(
            "Docker is installed but its daemon isn't reachable -- refusing to run "
            f"a submission unsandboxed. Start Docker and retry.\n{info.stderr.strip()}"
        )

    image = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True, text=True, timeout=60,
    )
    if image.returncode != 0:
        raise SandboxUnavailable(
            f"The sandbox image {IMAGE!r} doesn't exist locally. Build it first:\n"
            "    cd isolation && docker build -t sagecraft-runner:latest ."
        )


# How much stderr is kept to quote back in an error message. Everything
# past this is read and discarded, not buffered -- a submission's stderr is
# a diagnostic, and the first few KB of it is all a rejection needs.
STDERR_KEEP_BYTES = 4096


def _drain(stream, keep: int, budget):
    """
    Reads `stream` to EOF, keeping at most `keep` bytes and counting the
    rest. Stops early and returns over=True the moment more than `budget`
    bytes have arrived.

    Reading in fixed chunks is the point: it bounds what is ever held at
    once regardless of how much the submission produces, so the cap is a
    real limit rather than a measurement taken after the damage is done.
    """
    kept = bytearray()
    total = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            return bytes(kept), total, False
        total += len(chunk)
        if len(kept) < keep:
            kept.extend(chunk[: keep - len(kept)])
        if total > budget:
            return bytes(kept), total, True


def _run_capped(cmd, timeout_s, max_output_bytes, stderr_keep):
    """
    Runs `cmd`, draining both pipes concurrently with the process rather
    than after it. Returns (proc, stdout_bytes, stderr_bytes, over_cap).

    Concurrently matters twice over. Draining stdout to completion first
    would deadlock as soon as a submission filled the stderr pipe buffer
    (~64KB) -- it would block writing while nothing was reading -- and the
    whole point of the cap is that the reader keeps up with a stream it
    refuses to store.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    captured = {}
    blown = threading.Event()

    def drain(key, stream, keep):
        try:
            captured[key] = _drain(stream, keep, max_output_bytes)
        finally:
            if captured.get(key, (None, None, False))[2]:
                blown.set()
            stream.close()

    threads = [
        threading.Thread(target=drain, args=("out", proc.stdout, max_output_bytes + 1)),
        threading.Thread(target=drain, args=("err", proc.stderr, stderr_keep)),
    ]
    for thread in threads:
        thread.daemon = True
        thread.start()

    # Waiting on the process alone isn't enough: once a reader stops, the
    # pipe fills, the container blocks on write and never exits, and a
    # submission that blew the cap in the first second would still cost the
    # full wall clock -- and be reported as a timeout rather than as what
    # it was. Kill on either condition, whichever comes first.
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            if proc.poll() is not None:
                break
            if blown.is_set():
                proc.kill()
                proc.wait()
                break
            if time.monotonic() >= deadline:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd, timeout_s)
            time.sleep(0.02)
    except BaseException:
        proc.kill()
        for thread in threads:
            thread.join(timeout=5)
        raise
    for thread in threads:
        thread.join(timeout=5)

    stdout_bytes, _, out_over = captured.get("out", (b"", 0, False))
    stderr_bytes, _, err_over = captured.get("err", (b"", 0, False))
    return proc, stdout_bytes, stderr_bytes, out_over or err_over


def _force_remove(container_name):
    """Best-effort cleanup of a container the client stopped waiting for."""
    try:
        subprocess.run(
            ["docker", "rm", "--force", container_name],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass  # nothing useful to do; the caller is already reporting a failure


def run_isolated(generate_path: str, spec: dict, **overrides) -> dict:
    """
    Returns {"ok": True, "artifact": ...} or {"ok": False, "error": ...}.

    A crash, a timeout, a too-large or non-JSON output is the
    submission's own doing and comes back as {"ok": False}. Docker being
    unavailable raises SandboxUnavailable instead, so a host-side problem
    can never be mistaken for a bad submission.
    """
    opts = {**DEFAULTS, **overrides}
    container_name = f"sagecraft-{uuid.uuid4().hex}"

    with tempfile.TemporaryDirectory() as tmp:
        spec_path = os.path.join(tmp, "spec.json")
        # The spec crosses the same JSON boundary as the artifact, in the
        # other direction, and build_spec() is the fork's own code -- so
        # numpy gets in here too. Say so plainly instead of letting a
        # TypeError from json escape into the caller's batch loop.
        try:
            with open(spec_path, "w") as f:
                json.dump(spec, f)
        except TypeError as e:
            raise SandboxUnavailable(
                f"build_spec() returned something that isn't JSON-serializable: {e}. "
                "A spec has to cross the sandbox boundary as plain data -- dicts, "
                "lists, strings, numbers, booleans. Convert numpy values with "
                ".tolist() first."
            ) from None

        harness_dir = os.path.abspath(HARNESS_DIR)
        if not os.path.isdir(harness_dir):
            # Docker would otherwise create this path on the host as root.
            raise SandboxUnavailable(
                f"harness/ not found at {harness_dir}. run_isolated() expects to be "
                "called from a fork laid out with isolation/ and harness/ as siblings."
            )

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--read-only",
            "--tmpfs", f"/tmp:size={opts['tmp_size']},mode=1777",
            "--user", "65532:65532",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(opts["pids"]),
            "--memory", opts["memory"],
            "--memory-swap", opts["memory"],  # no swap beyond the memory limit
            "--cpus", opts["cpus"],
            "-e", "PYTHONPATH=/",
            "-v", f"{os.path.abspath(generate_path)}:/submission/generate.py:ro",
            "-v", f"{spec_path}:/spec.json:ro",
            "-v", f"{harness_dir}:/harness:ro",
            IMAGE,
            "/submission/generate.py", "/spec.json",
        ]

        # Both streams are read incrementally and capped *as they arrive*,
        # never collected first and measured after.
        #
        # Collecting into a file (or into host memory, which
        # subprocess.run(capture_output=True) would do) means the whole
        # volume is already somewhere before any size check can run. A
        # submission that prints in a loop writes as fast as a pipe will
        # carry it -- measured at several GB per second into a host
        # tempfile -- so over the 30s default wall clock a careless
        # `for ... print(...)` fills the maintainer's disk long before the
        # timeout fires.
        #
        # Stderr needs the cap at least as much as stdout does, because
        # run_generate.py deliberately swaps fd 1 for fd 2 while the
        # submission runs: *all* submission output arrives on stderr, and
        # stdout carries only the wrapper's own single result line. Capping
        # stdout alone left the stream that actually carries submission
        # output completely unbounded.
        try:
            proc, stdout_bytes, stderr_bytes, over_cap = _run_capped(
                cmd, opts["timeout_s"], opts["max_output_bytes"], STDERR_KEEP_BYTES,
            )
        except subprocess.TimeoutExpired:
            # subprocess only kills the docker *client*; the container
            # runs in the daemon and would otherwise keep burning a
            # CPU core and its memory allowance indefinitely.
            _force_remove(container_name)
            return {"ok": False, "error": f"timed out after {opts['timeout_s']}s"}
        except FileNotFoundError:
            raise SandboxUnavailable(
                "Docker isn't installed -- refusing to run a submission "
                "unsandboxed. See isolation/README.md."
            ) from None
        except BaseException:
            _force_remove(container_name)  # Ctrl-C, and anything else unexpected
            raise

        if over_cap:
            _force_remove(container_name)
            return {"ok": False, "error": "output exceeded size cap"}

        # errors="replace": a submission writing raw bytes shouldn't crash
        # the host with a UnicodeDecodeError.
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # An empty stdout with a non-zero exit usually means the
            # container never started -- daemon down, image missing. Ask
            # Docker directly rather than blaming the submission for it.
            if proc.returncode != 0 and not stdout.strip():
                ensure_available()
            return {
                "ok": False,
                "error": (
                    f"non-JSON output (exit {proc.returncode}): "
                    f"{stdout[:500]!r} / stderr: {stderr[:500]!r}"
                ),
            }
