# isolation/

Runs an untrusted submission's `generate(spec)` inside a disposable,
network-less Docker container instead of directly in your own process.

This exists because `verify()`/`score()` only ever see the *output* of
`generate()` — by the time they run, arbitrary code has already
executed. A frozen, exact verifier protects your leaderboard from being
gamed; it does nothing to protect the machine running it. Those are two
different problems (see `TOOLKIT.md` item 11), and this directory is the
answer to the second one.

**Hard rule: never run a submission's `generate()` any other way.** If
Docker isn't available, `run_isolated()` raises `SandboxUnavailable`
rather than falling back to running the submission directly — fail
closed, not open. This is already written into `CLAUDE.md`'s template;
keep it there.

That exception is also how a host-side problem stays distinguishable
from a bad submission. A stopped daemon or an unbuilt image otherwise
looks exactly like a submission that crashed, which would silently
reject an entire inbox. Call `ensure_available()` once before processing
a batch to fail immediately instead.

## One-time setup

```bash
cd isolation
docker build -t sagecraft-runner:latest .
```

Rebuild whenever you change the Dockerfile's pinned dependencies below.

The image name defaults to `sagecraft-runner:latest`. If two forks share a
machine and need different pinned dependencies, give each its own image
and set `SAGECRAFT_IMAGE` to match, so one fork's rebuild can't quietly
change what the other runs.

## Using it

```python
from isolation.run_isolated import run_isolated

result = run_isolated("inbox/alice_submission/generate.py", spec)
if not result["ok"]:
    ...  # treat like a verify() failure -- log it, don't crash the pipeline
artifact = result["artifact"]
```

## The one thing that's per-problem: pinned dependencies

`Dockerfile` installs exactly the packages your baselines and solution
actually import (`numpy`, by default). Add to that list only when a real
baseline or submission genuinely needs it, and treat any addition the
same way you'd treat a change to the frozen harness: something a
maintainer decides, not something a submission can request. Runtime
network access is disabled when the container runs, so a submission has
no way to `pip install` anything itself — if it isn't in this image, it
isn't available to it.

## Defaults

| limit | default | why |
|---|---|---|
| wall clock | 30s | generous for one `generate(spec)` call; raise per-problem if legitimate solutions need more. On expiry the container is force-removed — killing the `docker` client alone would leave it running in the daemon |
| memory | 512MB | |
| CPUs | 1 | |
| processes (pids) | 64 | blocks fork bombs |
| scratch space | 64MB, tmpfs, wiped on exit | for a submission that needs to write temporary files |
| output size | 10MB | a submission can't wedge an oversized payload back through stdout. Both streams are read in fixed chunks and capped *as they arrive*, and the container is killed the moment either goes over -- so unbounded output can exhaust neither host memory nor host disk. Stderr is capped for the same budget but only its first 4KB is kept, enough to quote in a rejection |

All adjustable via keyword arguments to `run_isolated()`, per problem or
per call.

Separately, `toolkit/inbox.py` checks the submission *folder* before any
of this runs: at most 10MB and 1000 files, and nothing but singly-linked
regular files and directories — no symlinks, no hard links, no named
pipes or device nodes, and nothing where a directory stands in for a file
the pipeline expects to read. Those guard host-side file handling rather
than the sandbox, because `shutil` follows a symlink, copies a hard
link's contents, and chokes on a pipe long before any submitted code
runs. See that module.

## The boundary is plain JSON, never pickle

`generate()`'s return value crosses the sandbox boundary as one line of
JSON on stdout. Your `artifact` format must therefore be
JSON-serializable — plain dicts, lists, strings, numbers, booleans (see
`PLAYBOOK.md` Step 1). numpy is the usual way to get this wrong:
`np.float64` happens to survive because it subclasses `float`, but
`np.int64`, `np.bool_`, and `np.ndarray` do not, so call `.item()` or
`.tolist()` before returning. That failure is reported as an ordinary
`{"ok": false}` error naming the offending type.

The spec crosses the same boundary in the other direction, and
`build_spec()` is your own code, so numpy gets in from that side too.
That raises `SandboxUnavailable` rather than `{"ok": false}` — it's your
bug, not the submission's, and shouldn't look like a failed submission.

Stdout is reserved for that one line, protected two ways because either
alone is insufficient. While the submission runs, fd 1 is swapped for
fd 2, so a debug `print()` or a direct write to fd 1 lands on stderr.
And the result itself is written with `os.write()` rather than `print()`,
because a submission can rebind `sys.stdout` during import and would
otherwise carry the result away with it. Submission output still reaches
you on stderr either way.

That swap is also why the output cap has to cover stderr and not just
stdout: for the whole time a submission is running, stderr is where
*all* of its output goes, and stdout carries only the wrapper's own
result line. A cap on stdout alone would sit on the one stream a
submission never writes to.

Neither stream is collected and measured afterwards. A `while True:
print(...)` produces output as fast as a pipe will carry it -- several
GB per second -- so anywhere it is buffered first, whether host memory
or a host tempfile, it has already done its damage by the time a cap is
consulted. Both are drained in fixed chunks by a reader that keeps at
most the cap, and the container is killed as soon as one goes over.

Never switch this to `pickle` for convenience:
deserializing a pickle is itself arbitrary code execution, which would
quietly undo the entire point of sandboxing `generate()` in the first
place.

## What's mounted into the container, and what isn't

- The submission's `generate.py` — read-only, and only that one file.
  Nothing else from the project is importable, so a submission or a
  registered baseline that imports a sibling fails here and only here.
  Shared code goes in `harness/`.
- `harness/` — read-only, so a submission can import shared, trusted
  primitives (e.g. `harness.constructors`) the same way it could outside
  the sandbox.
- Nothing else. No access to `baselines/`, `solution/`, `.git/`,
  environment secrets, or the rest of the filesystem.

## Checking it actually works

`isolation/tests/test_container.py` starts real containers and checks
their behaviour from inside: an unprivileged uid, no route out and no
DNS, `EROFS` on every write outside `/tmp`, a container that is killed
*and removed* at the wall clock, and the output cap firing on a
submission that floods stderr. The rest of the suite checks the `docker
run` arguments, which needs no daemon; these check that Docker honours
them.

They are marked `docker` and deselected by default, so the suite stays
Docker-free:

```bash
docker build -t sagecraft-runner:latest .
pytest -m docker
```

CI runs them on every push, where a runner always has Docker.

## What this doesn't cover

Docker's container isolation is a real barrier, not a perfect one — a
kernel-level container-escape exploit is a thing that has existed in the
past. The threat model here is a careless or moderately motivated
submitter (a friend's mistake, a compromised account, an LLM that wrote
something it shouldn't have), not a determined attacker with a zero-day.
The host-side folder checks in `toolkit/inbox.py` reach a little wider
than that — they also stop someone with a shell on the same machine
using a hard link to have the maintainer's own copy step read a file for
them — but the container itself is scoped to the model above.
If this project ever opens up to submissions from people you don't know
or trust at all, add a layer underneath this one too — run the whole
pipeline inside a disposable VM or cloud sandbox, not just inside a
container on your own machine — rather than assuming Docker alone is
enough at that point.
