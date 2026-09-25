"""
The only tests here that start a real container.

Everything in test_isolation.py checks the *arguments* -- that the argv
says --network none, --cap-drop ALL, --read-only and so on. That catches a
flag being dropped or misspelled, and it needs no daemon. What it cannot
catch is a flag that is spelled correctly, accepted by Docker, and doesn't
do what we think it does; a broken image; or an entrypoint that no longer
matches the arguments passed to it. These run one real `run_isolated()`
call each and check the container's actual behaviour from inside it.

Marked `docker` and deselected by default (see pyproject.toml's addopts),
because the suite is documented as needing no Docker and CI proves it. To
run them:

    docker build -t sagecraft-runner:latest isolation
    pytest -m docker

The availability check is deliberately inside a fixture rather than at
import time. Module-level it would run `docker info` during *collection*,
so a plain `pytest` -- which deselects these -- would still touch the
daemon, and the "suite needs no Docker" CI job would fail on it.
"""
import subprocess

import pytest

from isolation.run_isolated import SandboxUnavailable, ensure_available, run_isolated

pytestmark = pytest.mark.docker


@pytest.fixture(scope="session")
def sandbox():
    """Skips the whole file unless Docker is up and the image is built."""
    try:
        ensure_available()
    except SandboxUnavailable as e:
        pytest.skip(f"sandbox unavailable: {e}")


@pytest.fixture
def submission(tmp_path):
    """Writes a generate.py and returns its path."""
    def write(body):
        path = tmp_path / "generate.py"
        path.write_text(body)
        return str(path)
    return write


def test_a_submission_really_runs_in_a_container(sandbox, submission):
    """
    The end-to-end smoke test: the image builds a working Python, the
    entrypoint matches the arguments run_isolated passes, the spec crosses
    in, and the artifact crosses back out as JSON.
    """
    result = run_isolated(
        submission("def generate(spec):\n    return [0, spec['target']]\n"),
        {"target": 7},
    )

    assert result == {"ok": True, "artifact": [0, 7]}


def test_the_container_runs_as_an_unprivileged_user(sandbox, submission):
    """
    Root in the container is the difference between a contained mistake
    and a mounted-volume one.

    Note what this does and doesn't pin down. The uid is set twice over --
    by `--user 65532:65532` on the command line and by `USER 65532:65532`
    in the Dockerfile -- so this still passes with either one removed.
    That redundancy is deliberate and worth having, but it means this test
    verifies the *property*, not the flag; the argv assertion in
    test_isolation.py is what pins the flag itself.
    """
    result = run_isolated(
        submission(
            "import os\n"
            "def generate(spec):\n"
            "    return {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid()}\n"
        ),
        {"target": 1},
    )

    assert result["ok"] is True, result
    assert result["artifact"] == {"uid": 65532, "euid": 65532, "gid": 65532}


def test_the_container_has_no_network(sandbox, submission):
    """
    --network none, observed from inside. A submission that can reach the
    network can exfiltrate whatever it was given and pull in whatever it
    likes, which is the single thing the sandbox most needs to prevent.

    Checks a raw IP as well as a name, so a pass can't come from DNS
    merely being unconfigured while routing still works.
    """
    result = run_isolated(
        submission(
            "import socket\n"
            "def _try(fn):\n"
            "    try:\n"
            "        fn()\n"
            "        return 'REACHED'\n"
            "    except Exception as e:\n"
            "        return type(e).__name__\n"
            "def generate(spec):\n"
            "    return {\n"
            "        'ip': _try(lambda: socket.create_connection(('1.1.1.1', 80), timeout=5)),\n"
            "        'dns': _try(lambda: socket.getaddrinfo('example.com', 80)),\n"
            "    }\n"
        ),
        {"target": 1},
        timeout_s=25,
    )

    assert result["ok"] is True, result
    assert result["artifact"]["ip"] != "REACHED", result["artifact"]
    assert result["artifact"]["dns"] != "REACHED", result["artifact"]


def test_the_filesystem_is_read_only_except_tmp(sandbox, submission):
    """
    --read-only plus a --tmpfs at /tmp, observed from inside. The mounts
    matter as much as the root filesystem: harness/ is the fork's frozen
    referee and the submission file is another person's code, and a
    submission that can rewrite either has defeated the point of freezing
    them.
    """
    result = run_isolated(
        submission(
            "import errno\n"
            "def _write(path):\n"
            "    try:\n"
            "        with open(path, 'w') as f:\n"
            "            f.write('x')\n"
            "        return 'WROTE'\n"
            "    except OSError as e:\n"
            "        return e.errno\n"
            "def generate(spec):\n"
            "    return {\n"
            "        'root': _write('/evidence'),\n"
            "        'etc': _write('/etc/evidence'),\n"
            "        'harness': _write('/harness/evidence'),\n"
            "        'submission': _write('/submission/evidence'),\n"
            "        'tmp': _write('/tmp/evidence'),\n"
            "        'EROFS': errno.EROFS,\n"
            "    }\n"
        ),
        {"target": 1},
    )

    assert result["ok"] is True, result
    written = result["artifact"]
    assert written["tmp"] == "WROTE", written  # scratch space has to work

    # EROFS specifically, not merely "it failed". Without --read-only these
    # writes still fail, because the container runs as an unprivileged user
    # who owns none of these directories -- with EACCES rather than EROFS.
    # Asserting only that the write failed cannot tell the two protections
    # apart, and passes with --read-only removed entirely.
    erofs = written["EROFS"]
    for where in ("root", "etc", "harness", "submission"):
        assert written[where] == erofs, (
            f"{where}: expected EROFS ({erofs}), got {written[where]!r} -- "
            "a write that fails for the wrong reason means the read-only "
            "root, or a read-only mount, is not doing the work"
        )


def test_a_submission_over_the_wall_clock_is_killed_and_the_container_removed(
    sandbox, submission
):
    """
    The timeout kills the docker *client*; the container runs in the
    daemon and would otherwise keep its CPU and memory allowance
    indefinitely. Nothing but a real run can check the container actually
    goes away -- which is the whole reason this file exists.
    """
    before = _sagecraft_containers()

    result = run_isolated(
        submission("import time\ndef generate(spec):\n    time.sleep(60)\n"),
        {"target": 1},
        timeout_s=3,
    )

    assert result == {"ok": False, "error": "timed out after 3s"}
    assert _sagecraft_containers() <= before, "a container was left running"


def test_output_beyond_the_cap_is_refused(sandbox, submission):
    """
    The pass-six rewrite drains both pipes as they arrive rather than
    collecting first and measuring after. This is that path through a real
    container, on stderr -- where run_generate.py sends everything a
    submission prints while it runs.
    """
    result = run_isolated(
        submission(
            "import sys\n"
            "def generate(spec):\n"
            "    for _ in range(10000):\n"
            "        sys.stderr.write('x' * 4096)\n"
            "    return [0, spec['target']]\n"
        ),
        {"target": 1},
        max_output_bytes=200_000,
        timeout_s=25,
    )

    assert result == {"ok": False, "error": "output exceeded size cap"}


def test_a_crash_inside_the_container_comes_back_as_a_json_error(sandbox, submission):
    """The {"ok": false} channel, over the real boundary rather than a pipe."""
    result = run_isolated(
        submission("def generate(spec):\n    raise ValueError('nope')\n"),
        {"target": 1},
    )

    assert result["ok"] is False
    assert "ValueError: nope" in result["error"]


def _sagecraft_containers() -> set:
    """Names of any sagecraft-* containers the daemon still knows about."""
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=sagecraft-", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    return {line for line in proc.stdout.split() if line}
