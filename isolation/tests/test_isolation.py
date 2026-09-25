"""
Tests isolation/ -- the security-critical half of this template, and the
part a fork is least likely to test itself.

Everything here runs without Docker. run_generate.py is exercised as a
subprocess (which is how it actually runs, and the only way to observe
the stdout/stderr split it exists to guarantee); run_isolated.py is
exercised on the paths that never reach `docker run`.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from isolation.run_generate import encode
from isolation.run_isolated import (
    SandboxUnavailable,
    _run_capped,
    ensure_available,
    run_isolated,
)

RUNNER = Path(__file__).resolve().parents[1] / "run_generate.py"


def _run(tmp_path, source, spec=None):
    """Runs run_generate.py over a submission, the way the container does."""
    generate_path = tmp_path / "generate.py"
    generate_path.write_text(source)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"target": 5} if spec is None else spec))
    return subprocess.run(
        [sys.executable, str(RUNNER), str(generate_path), str(spec_path)],
        capture_output=True, text=True,
    )


# --- the JSON boundary ------------------------------------------------


def test_result_is_the_only_thing_on_stdout(tmp_path):
    """
    A submission that logs progress must still be readable. Debug prints
    are ordinary; before stdout was isolated they corrupted the result
    line and a working submission was rejected for "non-JSON output".
    """
    proc = _run(tmp_path, (
        "import sys, os\n"
        "print('progress: searching')\n"
        "sys.stdout.write('more chatter\\n')\n"
        "os.write(1, b'raw fd-1 write\\n')\n"
        "def generate(spec):\n"
        "    print('inside generate')\n"
        "    return [1, spec['target'] - 1]\n"
    ))

    assert json.loads(proc.stdout) == {"ok": True, "artifact": [1, 4]}
    assert proc.stdout.count("\n") == 1  # exactly one line, nothing else
    # The chatter isn't discarded, just moved out of the way.
    assert "progress: searching" in proc.stderr
    assert "raw fd-1 write" in proc.stderr  # even a direct fd write


def test_a_submission_that_raises_becomes_a_json_error(tmp_path):
    proc = _run(tmp_path, "def generate(spec):\n    raise ValueError('nope')\n")
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert "ValueError: nope" in result["error"]


def test_a_submission_that_crashes_on_import_becomes_a_json_error(tmp_path):
    proc = _run(tmp_path, "raise RuntimeError('bad import')\n")
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert "RuntimeError: bad import" in result["error"]


def test_a_submission_with_no_generate_function_is_reported_clearly(tmp_path):
    proc = _run(tmp_path, "x = 1\n")
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert "no generate(spec) function" in result["error"]


def test_unserializable_artifact_is_an_error_not_a_traceback(tmp_path):
    """
    The realistic version of this is numpy (np.int64 and np.ndarray both
    fail json.dumps even though np.float64 passes), but any object does.
    It must come back through the same {"ok": false} channel as anything
    else, not as a traceback the host can only report as "non-JSON".
    """
    proc = _run(tmp_path, "def generate(spec):\n    return {1, 2, 3}\n")
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert "isn't JSON-serializable" in result["error"]


def test_encode_passes_serializable_results_through_unchanged():
    assert json.loads(encode({"ok": True, "artifact": [1, 2]})) == {
        "ok": True, "artifact": [1, 2]
    }


# --- host-side failures are never mistaken for submission failures ----


def test_missing_harness_raises_rather_than_letting_docker_create_it(tmp_path, monkeypatch):
    """
    Docker creates a missing bind-mount source on the host as root, so a
    wrong layout would silently produce a root-owned harness/ directory.
    """
    monkeypatch.setattr("isolation.run_isolated.HARNESS_DIR", str(tmp_path / "absent"))
    generate_path = tmp_path / "generate.py"
    generate_path.write_text("def generate(spec):\n    return []\n")

    with pytest.raises(SandboxUnavailable, match="harness/ not found"):
        run_isolated(str(generate_path), {"target": 5})


def test_missing_docker_binary_raises_and_never_falls_back(tmp_path, monkeypatch):
    """
    The hard rule: no Docker means no run at all, not an unsandboxed one.

    Patches Popen, not subprocess.run, because Popen is what run_isolated
    actually reaches for -- _run_capped() has to drain both pipes while the
    process is still alive, which subprocess.run cannot do. This test used
    to patch subprocess.run, which stopped intercepting anything when that
    changed: on a machine with no docker binary it still passed, because
    the real Popen raised FileNotFoundError by itself, and on a machine
    with one it spawned an actual container and passed via a later branch.
    Green either way, testing neither.
    """
    monkeypatch.setattr("isolation.run_isolated.HARNESS_DIR", str(tmp_path))

    spawned = []

    def no_docker(cmd, *args, **kwargs):
        spawned.append(cmd)
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "Popen", no_docker)
    generate_path = tmp_path / "generate.py"
    generate_path.write_text("def generate(spec):\n    return []\n")

    with pytest.raises(SandboxUnavailable, match="isn't installed"):
        run_isolated(str(generate_path), {"target": 5})

    # It tried exactly once, and it tried to run docker -- not something else.
    assert len(spawned) == 1 and spawned[0][0] == "docker"


def test_ensure_available_raises_when_the_daemon_is_unreachable(monkeypatch):
    """
    The failure that used to be invisible: with the daemon down every
    submission came back looking like it had failed verification, so a
    whole inbox was rejected and nothing said the sandbox never ran.
    """
    def daemon_down(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "cannot connect to the daemon")

    monkeypatch.setattr(subprocess, "run", daemon_down)
    with pytest.raises(SandboxUnavailable, match="daemon isn't reachable"):
        ensure_available()


def test_ensure_available_raises_with_the_build_command_when_image_is_missing(monkeypatch):
    def daemon_up_no_image(cmd, **kwargs):
        code = 0 if "info" in cmd else 1
        return subprocess.CompletedProcess(cmd, code, "24.0.0", "No such image")

    monkeypatch.setattr(subprocess, "run", daemon_up_no_image)
    with pytest.raises(SandboxUnavailable, match="docker build"):
        ensure_available()


def test_ensure_available_is_quiet_when_docker_is_healthy(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "24.0.0", ""),
    )
    ensure_available()  # must not raise


def test_a_submission_that_rebinds_stdout_cannot_swallow_the_result(tmp_path):
    """
    Redirecting fd 1 isn't enough on its own: a submission is free to
    rebind sys.stdout during import, and the result -- written last --
    would go wherever it pointed. Writing to fd 1 with os.write() is what
    makes the boundary hold.
    """
    proc = _run(tmp_path, (
        "import sys, io\n"
        "sys.stdout = io.StringIO()\n"
        "def generate(spec):\n"
        "    return [1, spec['target'] - 1]\n"
    ))
    assert json.loads(proc.stdout) == {"ok": True, "artifact": [1, 4]}


def test_a_non_serializable_spec_is_a_host_error_not_a_submission_failure(tmp_path, monkeypatch):
    """
    build_spec() is the fork's own code, so numpy reaches the boundary
    from this direction too. That's the maintainer's bug, and it must not
    look like the submission failed.
    """
    monkeypatch.setattr("isolation.run_isolated.HARNESS_DIR", str(tmp_path))
    generate_path = tmp_path / "generate.py"
    generate_path.write_text("def generate(spec):\n    return []\n")

    class Unserializable:
        pass

    with pytest.raises(SandboxUnavailable, match="build_spec"):
        run_isolated(str(generate_path), {"target": Unserializable()})


# --- the container's argument list ------------------------------------
#
# KNOWN_ISSUES.md item 4 records that nothing here ever runs Docker, and
# proposes a @pytest.mark.docker test that really builds the image. That
# is still worth having. But most of what item 4 is afraid of -- a
# misspelled --pids-limit, a dropped --cap-drop ALL, a wrong mount path --
# is a property of the argument list, and needs no daemon to check. These
# assert it directly, so a silent weakening of the sandbox fails the
# default suite rather than waiting for a Docker-enabled runner.


def _captured_cmd(tmp_path, monkeypatch, **overrides):
    """Runs run_isolated() far enough to build the argv, and returns it."""
    monkeypatch.setattr("isolation.run_isolated.HARNESS_DIR", str(tmp_path))
    generate_path = tmp_path / "generate.py"
    generate_path.write_text("def generate(spec):\n    return []\n")
    seen = {}

    def fake_run_capped(cmd, timeout_s, max_output_bytes, stderr_keep):
        seen["cmd"] = cmd
        seen["timeout_s"] = timeout_s
        return subprocess.CompletedProcess(cmd, 0), b'{"ok": true, "artifact": []}', b"", False

    monkeypatch.setattr("isolation.run_isolated._run_capped", fake_run_capped)
    result = run_isolated(str(generate_path), {"target": 5}, **overrides)
    assert result == {"ok": True, "artifact": []}
    return seen


def test_the_container_is_confined(tmp_path, monkeypatch):
    cmd = _captured_cmd(tmp_path, monkeypatch)["cmd"]

    def flag(name):
        return cmd[cmd.index(name) + 1]

    assert cmd[:3] == ["docker", "run", "--rm"]
    assert flag("--network") == "none"          # no network at all
    assert "--read-only" in cmd                 # no writes outside the tmpfs
    assert flag("--cap-drop") == "ALL"
    assert flag("--security-opt") == "no-new-privileges"
    assert flag("--user") == "65532:65532"      # never root
    assert flag("--pids-limit") == "64"         # blocks fork bombs
    assert flag("--memory") == "512m"
    assert flag("--memory-swap") == "512m"      # no swap beyond the limit
    assert flag("--cpus") == "1"
    assert flag("--tmpfs").startswith("/tmp:size=64m")


def test_only_the_submission_and_harness_are_mounted_and_both_read_only(tmp_path, monkeypatch):
    cmd = _captured_cmd(tmp_path, monkeypatch)["cmd"]

    mounts = [cmd[i + 1] for i, token in enumerate(cmd) if token == "-v"]

    assert len(mounts) == 3
    assert all(m.endswith(":ro") for m in mounts), mounts
    targets = sorted(m.split(":")[-2] for m in mounts)
    assert targets == ["/harness", "/spec.json", "/submission/generate.py"]


def test_overrides_reach_the_container(tmp_path, monkeypatch):
    seen = _captured_cmd(tmp_path, monkeypatch, memory="2g", pids=8, timeout_s=5)
    cmd = seen["cmd"]

    assert cmd[cmd.index("--memory") + 1] == "2g"
    assert cmd[cmd.index("--memory-swap") + 1] == "2g"
    assert cmd[cmd.index("--pids-limit") + 1] == "8"
    assert seen["timeout_s"] == 5


# --- output caps ------------------------------------------------------


def _spewer(tmp_path, fd, seconds=30):
    path = tmp_path / f"spew{fd}.py"
    path.write_text(
        "import os, time\n"
        "buf = b'x' * 65536\n"
        f"end = time.time() + {seconds}\n"
        f"while time.time() < end:\n    os.write({fd}, buf)\n"
    )
    return [sys.executable, str(path)]


def test_unbounded_stdout_is_capped_and_the_process_killed_at_once(tmp_path):
    """
    The cap used to be applied when the stream was read *back*, after
    subprocess.run had already collected all of it into a host tempfile --
    several GB per second, for the full 30s wall clock, onto the
    maintainer's disk. It has to bound what arrives, not measure it after.
    """
    started = time.monotonic()
    proc, stdout, stderr, over = _run_capped(
        _spewer(tmp_path, 1), 30, 1_000_000, 4096
    )

    assert over is True
    assert len(stdout) <= 1_000_001
    assert time.monotonic() - started < 10  # not the full 30s wall clock


def test_unbounded_stderr_is_capped_too(tmp_path):
    """
    Stderr needs this at least as much as stdout: run_generate.py swaps
    fd 1 for fd 2 while the submission runs, so *all* submission output
    arrives on stderr and stdout carries only the wrapper's result line.
    Capping stdout alone left the stream that actually carries submission
    output completely unbounded.
    """
    proc, stdout, stderr, over = _run_capped(
        _spewer(tmp_path, 2), 30, 1_000_000, 4096
    )

    assert over is True
    assert len(stderr) <= 4096


def test_a_quiet_process_is_read_in_full_and_not_flagged(tmp_path):
    path = tmp_path / "quiet.py"
    path.write_text("import sys\nsys.stdout.write('hello')\nsys.stderr.write('note')\n")

    proc, stdout, stderr, over = _run_capped(
        [sys.executable, str(path)], 30, 1_000_000, 4096
    )

    assert over is False
    assert stdout == b"hello"
    assert stderr == b"note"
    assert proc.returncode == 0


def test_a_process_that_never_exits_still_times_out(tmp_path):
    path = tmp_path / "hang.py"
    path.write_text("import time\ntime.sleep(60)\n")

    with pytest.raises(subprocess.TimeoutExpired):
        _run_capped([sys.executable, str(path)], 1, 1_000_000, 4096)


def test_a_submission_importing_a_sibling_is_told_why_it_cannot(tmp_path):
    """
    The sandbox mounts the submission file and harness/, nothing else. A
    baseline that imports a sibling in baselines/ works perfectly outside
    and dies here with "No module named 'baselines'", which points at
    nothing and reads like the file is missing.

    Found by building a real problem on this template: a reference
    solution shared a helper through baselines/_ladder.py, every instance
    failed in the sandbox, and the error said nothing about mounts.
    """
    proc = _run(tmp_path, (
        "from baselines.helpers import ladder\n"
        "def generate(spec):\n"
        "    return []\n"
    ))

    result = json.loads(proc.stdout)

    assert result["ok"] is False
    assert "No module named 'baselines'" in result["error"]
    assert "Only this file and harness/ are mounted" in result["error"]
    assert "harness.<module>" in result["error"]


def test_an_ordinary_error_is_not_padded_with_mount_advice(tmp_path):
    """The hint is for the one failure it explains, not every failure."""
    proc = _run(tmp_path, "def generate(spec):\n    raise ValueError('nope')\n")

    result = json.loads(proc.stdout)

    assert result["error"] == "ValueError: nope"
