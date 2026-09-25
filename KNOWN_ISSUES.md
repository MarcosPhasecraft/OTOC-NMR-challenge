# Known issues

State of play after twelve passes, the last of which built a real
problem on this template rather than auditing it. 364 tests pass
(`pytest` from the repo root, no Docker needed), plus 7 container tests
behind `-m docker`. All of it runs on every push.

**There are no known open defects.** Everything found across those passes
is fixed, mutation-checked, and documented. What follows is the residual
risk surface: gaps that are real but were judged acceptable, and coverage
that doesn't exist.

Passes six to eight are described in "The recurring failure class" below,
because what they found bears directly on how the earlier passes were
being run. Passes nine and ten -- CI, and the container tests -- are under
"Continuous integration", along with the four things building them turned
up, three of which were hollow tests rather than broken code.

## Open gaps

One, and it is conditional on a change nobody has made yet.

### 1. Concurrent runs can corrupt the cache or registry

`ScoreCache._save()` and `Registry._save()` both write to a fixed
`<name>.tmp` beside the target before renaming. The rename is atomic, so
a crash is safe — that was the point — but two processes writing the same
file at once share that one temp path, and one can rename the other's
half-written content into place.

Nothing in the toolkit runs concurrently today, and a single maintainer
processing an inbox will not hit it. It becomes real if a fork ever
parallelises `rescore()` across baselines, which is an obvious thing to
want since each cell is an independent sandboxed run.

Fix: include the pid or a random suffix in the temp name, or take a lock
file. The random suffix is the smaller change and enough for the failure
above.

If it ever does happen, the damage is now legible rather than silent:
both files are validated when they are read, so a half-written one is
refused by name with a message saying what to do, instead of surfacing as
a bare traceback several layers up.

## Continuous integration

`.github/workflows/tests.yml`, on every push and pull request. Three jobs:

- **pytest** across Python 3.9-3.13 on Linux, plus 3.12 on macOS, since
  the template is developed on macOS and Linux-only CI would miss a
  difference between them. 3.9 is the floor because the code uses nothing
  newer, and 3.8 is end-of-life.
- **the suite needs no Docker**, which three documents claim and nothing
  checked. `docker` on `PATH` is replaced by a shim that records being
  called and fails, and the job fails if it was ever reached. This is
  stronger than hiding the binary: it proves no test so much as reaches
  for the daemon.
- **the sandbox really confines a submission**: builds the image, then
  runs `pytest -m docker` -- seven tests that each start a real container
  and check its behaviour from inside. A CI runner has Docker where a
  laptop may not, which is the whole reason this belongs here rather than
  in the default suite. `ensure_available()` runs as a separate step
  first, because the container tests *skip* when the sandbox is missing
  and a skip exits 0; the job also fails if anything skipped, so "Docker
  wasn't working" can't come out green.

The workflow travels into every fork, so it hardcodes no branch name, no
repository, and no badge URL -- add a badge to your fork's `README.md`
once it has a home.

Two things turned up while writing it, and both are worth knowing about:

- `testpaths` in `pyproject.toml` covered only `toolkit` and `isolation`,
  so a fork's own `tests/` -- its Step 3 referee tests, the ones
  `PLAYBOOK.md` calls the entire reason Step 3 is separate from Step 4 --
  were never collected by `pytest`. Every fork's CI would have been green
  having run none of them. `tests` is in `testpaths` now.
- The `no-docker` job failed on its first run, and correctly.
  `test_missing_docker_binary_raises_and_never_falls_back` patched
  `subprocess.run`, but pass six moved `run_isolated()` onto
  `subprocess.Popen` (the cap has to drain both pipes while the process
  is alive, which `subprocess.run` cannot do). The patch stopped
  intercepting anything: with no docker binary the test passed because
  the real `Popen` raised `FileNotFoundError` by itself, and with one it
  spawned an actual container and passed via a later branch. Green either
  way, testing neither. It patches `Popen` now and asserts exactly one
  spawn attempt, of `docker`.

  Worth drawing the general lesson, because mutation-checking did not
  catch this and could not have: it asks "does reverting the fix fail a
  test", not "does the test still reach the code it names". A test can go
  hollow without ever going red.

Pass ten then wrote the container tests (`isolation/tests/test_container.py`),
and the same lesson arrived twice more. All seven passed on the first run
against a real daemon. Mutating the *actual sandbox* -- dropping
`--network none`, `--read-only`, `--user`, making the harness mount
writable, removing the post-timeout `docker rm`, disabling the output cap
-- showed two of them proved nothing:

- **the read-only filesystem test** asserted only that writes outside
  `/tmp` failed. They fail without `--read-only` too, because the
  container runs as an unprivileged user who owns none of those
  directories: `EACCES` rather than `EROFS`. Asserting "it failed" could
  not tell the two protections apart, and passed with `--read-only`
  removed entirely. It asserts `EROFS` specifically now.
- **the unprivileged-user test** still passed with `--user 65532:65532`
  dropped, because the Dockerfile's `USER 65532:65532` sets the same uid.
  That one turned out to be real redundancy rather than a hollow test --
  with *both* removed it fails, as it should -- so it stands, with a
  docstring saying what it does and doesn't pin down. The argv assertion
  in `test_isolation.py` is what pins the flag.

The general form, and the thing to carry forward: **a test that passes is
not necessarily a test that discriminates.** Every check here now has a
recorded mutation that turns it red, and for the sandbox those mutations
weaken the real container rather than the code that describes it.

### A note on where tests are put

`toolkit/tests/test_jsonable.py` takes a module-level
`pytest.importorskip("numpy")`, so all 27 of its tests are skipped
wherever numpy isn't installed -- which includes CI, since
`requirements-dev.txt` installs only pytest. Counting the five individual
numpy cases elsewhere, **32 tests pass locally and never run in CI**.

That is not a defect in the toolkit, and the skip is deliberate: the
module exists because of numpy and testing it against a stand-in would
prove nothing. But it is a trap for anyone adding tests, because a test
put in that file silently stops running in CI. `load_json_object` lives
in `jsonable.py` and its tests are in `test_state_files.py` for exactly
this reason.

Fix, if wanted: add `numpy` to `requirements-dev.txt`. The toolkit itself
stays pure standard library -- this would be a dependency of the *test
suite*, not of `toolkit/` -- but it does contradict the "only development
dependency is pytest" line in `TOOLKIT.md` and `toolkit/README.md`, so it
is a deliberate call rather than an oversight to be tidied.

## What building a real problem on it found

Passes one to eleven audited the machinery. Pass twelve used it: cloned
the template as `PLAYBOOK.md`'s README describes, and built a diagonal
unitary synthesis problem (phase polynomials over `{CNOT, Rz}`, scored by
CNOT count) from Step 0 through to a submission accepted from an inbox
and a rendered leaderboard.

The machinery held. The fork bootstrap worked as written, the CLI's two
subcommands worked from a real fork root, the sandbox built and rescored
21 baseline cells in four seconds, the inbox accepted one submission and
rejected another, and `assert_registered_implies_verified()` held on a
real project. Three things did not, and all three are fixed here:

| What broke | Where it hid |
|---|---|
| `load_problem()` registers under the literal global name `harness` and deletes the previous one, so this suite's throwaway fixture displaced the fork's own harness. 43 of the fork's tests failed in the full suite, passed when run alone, and every error named a file in the fork | the interaction between `load_problem()`'s documented behaviour and `testpaths` running `toolkit/` before `tests/` -- a combination that only exists once a fork has tests of its own |
| `PLAYBOOK.md` Step 6's wiring snippet crashed on a fresh fork: it passes `inbox_dir="inbox"`, the template shipped no such directory, and `process_inbox()` creates `baselines/` but not `inbox/` | a snippet nobody had run end to end |
| a registered baseline that imports a sibling in `baselines/` dies in the sandbox with `No module named 'baselines'`. The container mounts one file plus `harness/`, and the error says nothing about mounts | stated only as a bullet in `isolation/README.md`'s list of what is mounted |

The first is the one worth dwelling on, because it was *created* by an
earlier fix. Pass nine put `tests` into `testpaths` so that a fork's own
Step 3 tests would actually run -- without which every fork's CI would
have been green having run none of them. That fix is what made the
`sys.modules` collision reachable at all. Closing a hole where tests
silently did not run exposed a latent one where they ran and interfered.

Nothing here was found by reading the code again. Two of the three needed
a fork to exist, and the third needed one to have tests.

## Accepted non-goals

These are decided, not pending. They are listed so a fresh reader does
not re-derive them as findings.

- **The progress-over-time chart** (`TOOLKIT.md` item 10) will not be
  built here. It needs a plotting dependency, and `toolkit/` and
  `isolation/` are otherwise pure standard library. `register()` now
  stamps `registered_at`, which is the part that cannot be reconstructed
  later, so a fork can plot it however it likes.
- **Container escape** is out of the threat model. `isolation/README.md`
  says so, and says what to do instead (a disposable VM) if the project
  ever opens to submitters nobody vouches for.
- **A submission can choose what comes back over the sandbox boundary.**
  By writing its own JSON to the real fd 1 and calling `os._exit()`, a
  submission controls `run_isolated()`'s return value completely. This
  buys it nothing — the artifact it forges still has to pass `verify()`,
  exactly as if `generate()` had returned it — so the boundary is not a
  place to add attestation. What it did buy was a crash: the pipelines
  indexed that value directly, and a malformed one took down the whole
  batch. That is fixed (`checked_run_generate`); the forgery itself is
  not a threat and is left alone.
- **The toolkit is vendored, not packaged.** `TOOLKIT.md` argues this at
  length; `pyproject.toml` is config only and deliberately has no build
  system.
- **A corrupt state file is never repaired automatically.**
  `registry.json` and `.score_cache.json` are both refused by name, with a
  message saying what is wrong and what recovering costs -- the cache can
  be rebuilt with `rescore()`, the registry has to come back from version
  control because `registered_at` cannot be reconstructed. Starting from
  `{}` instead would turn one loud failure into a leaderboard that
  quietly lost rows, which is strictly worse.
- **Instance ids must be ints or strings**, enforced on write and now on
  read too. A composite id is spelled `"8x4"`. See `TOOLKIT.md`'s second
  contract for why.

Two things that used to be on this list are no longer:

- **Hard links in a submission folder** were an accepted gap for five
  passes, on the grounds that they need local filesystem access and so
  fall outside "a careless or moderately motivated submitter". Pass
  seven's generated suite plants them and asserts the canary property
  regardless, which made the gap a failing test rather than a paragraph,
  and it was closed: `_unsafe_path_reason()` now rejects any regular file
  with `st_nlink > 1`. The threat model in `isolation/README.md` is
  correspondingly a little wider than it was.
- **Most of "nothing ever runs the sandbox"**, which is now split: the
  argument list is asserted directly (pass six), and only actually
  executing a container remains (gap 3).

## The recurring failure class, and what passes six to eight did

Across the first five passes, nearly every defect found was an
**assumption about input that the contract does not guarantee**, and
after the first pass almost all of them were in code added *by the audit
itself*:

| Pass | What broke | The assumption |
|---|---|---|
| 1 | `shutil` followed a symlink out of a submission folder | folder contents are ordinary files |
| 2 | `.item()` collapsed `np.array([5])` to `5`; a submission rebinding `sys.stdout` swallowed its result | one-element arrays are scalars; stdout is `sys.stdout` |
| 3 | tuple instance ids cached under a key nothing read | ids survive a JSON round trip unchanged |
| 5 | a generator claim was consumed by validating it; a named pipe crashed the batch | iterables can be traversed twice; `is_file()` is the only alternative to a directory |

Pass five concluded that the way out was to stop auditing instance by
instance and **test the invariant instead**, and proposed two properties.

Pass six built the second one — `toolkit/tests/invariants.py`'s
`assert_registered_implies_verified()` — and found eight more defects:

| What broke | The assumption |
|---|---|
| the sandbox's 10MB output cap was applied when the stream was read *back*, after `subprocess.run` had collected all of it into a host tempfile — and it capped stdout, which is the one stream a submission never writes to, since `run_generate.py` swaps fd 1 for fd 2 while it runs. Measured at ~7GB in 3s onto the host disk, for the full 30s wall clock | output can be measured after it arrives; a limit on the documented stream is a limit on the real one |
| `rescore(force=True)` left a stale passing score cached for a baseline that had just failed | a re-run only ever *adds* to the cache |
| `inbox` fingerprinted the referee after `register()`, so a bad `FROZEN_GLOBS` registered a submission with no scores and aborted the batch | the fingerprint is always computable |
| `{"ok": true}` with no artifact, or a non-dict, crashed the whole batch out of `inbox` and `rescore` | the sandbox boundary returns the shape it documents |
| a submitter's `label` went unescaped into the markdown leaderboard, so a `\|` forged cells | a label is text, not markup |
| a metric named `note` silently replaced the results log's own column | a named parameter and a `**fields` key collide loudly |
| `build_spec()` sat outside `check_generalizes()`'s guard, so one unsupported held-out id discarded the whole report | only `generate()` raises |
| `score()` could return `passed` or `checks` and overwrite `verify()`'s verdict | a scorer's metric names don't collide with the referee's |

Pass seven built the first property — `toolkit/tests/generators.py` and
`test_inbox_generated.py`, which generate random submission folders and
assert `process_inbox` never raises and never registers anything it did
not fully verify. It found six more on its first run and its first soak:

| What broke | The assumption |
|---|---|
| a `submission.json` containing `5`, `true` or `null` raised TypeError out of `validate_manifest` — nine bytes of valid JSON, and the whole batch was gone | a JSON document is a JSON *object* |
| a manifest saved in cp1252, or one nobody could read, raised `UnicodeDecodeError` / `PermissionError` past `except json.JSONDecodeError` | a decode failure is a JSON failure |
| a *directory* named `submission.json` or `generate.py` passed every check in `_unsafe_path_reason()` — it never appears in `os.walk`'s filenames — and reached `read_text()` as a directory | `exists()` implies a file |
| a stale `baselines/<name>.memory` that was a plain file made `rmtree` raise, after `generate.py` had already been copied and before the registry was written | what is at a path is what the last run left there |
| `shutil.copy` into an existing *directory* at `baselines/<name>.py` copied the file inside it, registering a module that wasn't where the registry said | `copy()` overwrites its destination |
| hard links in `memory/` were copied out by content — a five-pass accepted gap the canary property simply failed on | a threat model exempts you from a property |

Two observations, and the second is the useful one.

First, all six are the same class again, and pass eight's four are too.
The class is now well enough understood to name in one line: **a path is
not the kind of thing you assume it is, and neither is a parsed
document.** Every committed file this toolkit reads — `registry.json`,
`.score_cache.json`, a submission's `submission.json` — is now validated
where it is read, rather than trusted because of who wrote it.

Second — and this is what changed — every one of the six was in code that
predated pass six. None was introduced by the audit. That breaks the
pattern the table at the top of this section describes, where each pass
kept finding its own previous pass's mistakes, and it breaks it for a
structural reason: a hand audit reads the diff it just wrote, while a
property tests the whole surface every time it runs. Five passes of
careful reading did not reach a nine-byte `submission.json`; the grammar
reached it on the first seed.

The honest limitation, recorded so nobody over-reads the above: a
property only checks what the grammar can produce. Both of pass seven's
own bugs were in the generator rather than the pipeline, and widening
`HAZARDS` is what found the last three defects. So
`test_every_hazard_and_manifest_kind_is_actually_reached` exists to stop
the grammar quietly shrinking, and adding to it is the cheapest useful
work anyone can do here.

Pass eight applied the same treatment to `rescore()`, whose untrusted
input is not a submission folder but the project: a `registry.json` people
hand-edit, a `baselines/` that accumulates, a committed score cache.
`generators.build_project()` generates those states and
`test_rescore_generated.py` asserts what the leaderboard ends up
publishing. Four more, in the two committed files that had never been
validated on read:

| What broke | The assumption |
|---|---|
| an absolute `module` in `registry.json` escaped `baselines/` entirely — `Path("baselines") / "/etc/hosts"` is `/etc/hosts` — so `rescore()` handed an arbitrary host file to `run_generate()`, which bind-mounts it into the container and runs it, and `load_generate()` imported it into this process | a path join keeps you where you started |
| a non-string `module` raised `TypeError` out of the whole run; an empty one resolved to `baselines/` itself | a field that is present is a field you can use |
| a cached entry saying `passed: False` — a bad merge, or an older toolkit — was reported "already current", never recomputed, and its metrics published as a real result | an entry's existence is its meaning |
| a cached entry that wasn't a dict crashed the leaderboard with `TypeError: 'int' object is not iterable` | a committed file holds what you last wrote |

Plus one that is waste rather than a defect: duplicate instance ids in an
entry cost a second full sandboxed run each — the most expensive thing
this toolkit does — and put one instance in two buckets of the same
report. `parse_instances()` is the fork's own code and is nowhere required
to return distinct ids, so `register()` and `rescore()` both deduplicate now.

**Both properties from pass five are built, and both pipelines have one.**
There is no third queued. The honest next step is not another property but
the two gaps above it: nothing executes a container (gap 3), and nothing
runs any of this on push (gap 4).

## Verifying the current state

```bash
pytest                      # 364 tests, no Docker required
pytest -m docker            # 7 more, needs the image built
```

CI runs both on every push and pull request, plus the thing a laptop
can't reliably do: proving the suite never reaches for Docker. See
"Continuous integration" above.

Every fix here is mutation-checked -- reverting it fails a named test --
and for the sandbox the mutation weakens the real container, not the code
that describes it. If you change something and the suite still passes,
break the fix on purpose first and confirm the test you expected to
protect it actually goes red. Two failure modes that a green suite hides,
both of which happened here:

- a test that no longer *reaches* the code it names (the `no-docker`
  note above), and
- a test that reaches it but doesn't *discriminate* -- it would pass with
  the protection removed, because something else was doing the work (the
  pass-ten note above).

Neither is visible from the test result. Only mutation shows them, and
only if the mutation is of the thing the test claims to be about.

One practical trap when doing that, learned the hard way: **invalidate
bytecode when you restore the file.** A mutation the same length as what
it replaced -- `is_dir()` for `exists()` -- restores to a file whose size
still matches the `.pyc`'s recorded size, and if both writes land in the
same mtime tick Python keeps running the *mutated* bytecode afterwards.
A test then failed against code that was no longer on disk, and reading
the source explained nothing. Delete `__pycache__` after each restore.
