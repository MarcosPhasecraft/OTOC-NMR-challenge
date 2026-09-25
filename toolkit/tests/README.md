# toolkit/tests/

Tests `toolkit/`'s own code, using `fixtures/fake_problem/` — a
deliberately trivial problem (an artifact is a pair of ints that must
sum to a target) that exists only to exercise the toolkit, never as a
real benchmark. See `TOOLKIT.md`'s "Validating the toolkit before any
real fork depends on it" for why this exists.

`fixtures/fake_problem/baselines/` has two reference solutions:
`trivial.py` (always correct, for testing the happy path) and `bad.py`
(deliberately wrong, for testing that later pieces — the inbox pipeline
especially — actually reject a bad submission instead of crashing or
silently accepting it).

One test file gets added per toolkit module as it's built, following
`TOOLKIT.md`'s build order:

- [x] `test_fake_problem.py` — validates the fixture itself (the "known
      answers" every later test builds on), loaded via `load_problem()`
- [x] `test_problem.py` — `problem.py`'s `load_problem()`: the happy
      path, both ways a harness/ can fail the contract, and that
      repeated calls never leak a stale module from one loaded problem
      into the next
- [x] `test_evaluate.py` — `evaluate()`/`evaluate_artifact()`: runs
      generate then verify then score, skips score on a failed or
      malformed artifact
- [x] `test_results_log.py` — JSONL append/read round-trip, ordering,
      missing-file handling
- [x] `test_cache.py` — `fingerprint()` reacts only to matched files
      changing (not unrelated files, not directories the glob happens
      to match) and `ScoreCache` treats a fingerprint change as a miss
- [x] `test_registry.py` — register/get/overwrite, persistence across
      instances, loading a registered module's `generate`, and the two
      ways that can fail (unknown name, module missing `generate`)
- [x] `test_cli.py` — both subcommands end to end against the fixture:
      `evaluate` logs a run whether it passed or failed, `verify` checks
      a hand-written artifact with no `generate()` call and no log entry,
      and default paths resolve relative to the current directory
- [x] `test_held_out.py` — a genuinely uniform rule passes at any held-out
      instance, a lookup table fails exactly on the instances it doesn't
      cover, and a crash on one instance doesn't stop the rest of the
      check from running
- [x] `test_submission.py` — manifest field validation (name pattern,
      non-empty label, resolvable and non-empty `sizes`), `generated_by`
      optional-but-typed, non-scalar instance ids refused, and a
      generator of instances materialised rather than consumed
- [x] `test_inbox.py` — accept/reject end to end: no partial credit (a
      submission passing at some instances but not all is rejected and
      nothing about it is registered or cached, not even the passing
      instances), duplicate names (within one batch and against a
      prior run), a missing file or broken manifest, an isolation
      failure recorded as a failed instance rather than a crash, the
      `memory/` folder copied on acceptance, deterministic folder
      order; and the untrusted-folder rules -- symlinks (file, directory,
      or in place of generate.py), special files like a named pipe, and
      the size and file-count caps -- each rejected without disturbing
      the rest of the batch. Uses a local stub in place of `isolation.run_isolated` so
      this suite doesn't need Docker -- production code must pass the
      real one.
- [x] `test_leaderboard.py` — column ordering (explicit and the default
      sorted-union), ranking ascending/descending by a chosen metric's
      mean, a missing cached cell (and a baseline that never claimed an
      instance at all) both rendering as "—", a baseline with no cached
      scores at all sorting last rather than crashing, and the
      empty-registry edge case

- [x] `test_rescore.py` — `rescore()`: that a changed referee really
      does leave nothing cached (the gap this closes), that rescoring
      refills it and the leaderboard comes back, that current entries
      are skipped unless `force`, that a baseline which no longer
      verifies is reported but neither cached nor de-registered, and
      that a sandbox failure, a raising harness, a vanished module file
      or a malformed registry entry are all recorded rather than
      aborting the run, and that an unregistered name in `names=` raises
      before anything is run
- [x] `test_jsonable.py` — `to_jsonable()`: numpy scalars and arrays
      converted, `np.bool_` staying a bool rather than becoming 1/0,
      nested structures reached, and an unrepresentable value raising
      with its type and position named instead of being coerced to a
      string

`test_inbox_generated.py` and `generators.py` are the property half of
this suite. `generators.py` is a grammar for random submission folders --
manifests that are absent, unparseable, valid JSON but not an object, or
valid with any one field wrong; `memory/` subtrees of random depth;
symlinks out of the folder, symlinked parent directories, hard links,
named pipes, directories standing where a file belongs, unreadable and
non-UTF-8 files, odd filenames, size and count overruns. The test module
then asserts *relational* properties -- if accepted then every claimed
instance passed and the copied module is byte-identical; if rejected then
nothing persisted; and, over every folder however hazardous, that no byte
of a file outside it ever reaches `baselines/`. Restating the
implementation as an oracle would only test that it agrees with itself.

Seeds are explicit, so a failure names the tree that produced it and
re-running reproduces it. Two guards keep the suite from going hollow:
`test_the_generator_actually_reaches_both_outcomes` (every "if accepted
then ..." property is vacuously true of a run that accepts nothing) and
`test_every_hazard_and_manifest_kind_is_actually_reached` (a branch of
the grammar that stops being produced says so, rather than quietly
shrinking the suite). Both modules carry the same two guards, and
`test_rescore_generated.py` adds a third that every bucket of the report
is actually reached. Adding a hazard or an entry kind is the cheapest
useful contribution here -- see `KNOWN_ISSUES.md` for what the last two
rounds of them turned up.

`test_rescore_generated.py` is the same idea against the other pipeline
that runs untrusted code, and its input surface is different: not a
submission folder someone hands you, but the *project* -- a
`registry.json` people hand-edit and merge badly, a `baselines/` that
accumulates across layouts and moves, and a committed score cache. So
`generators.build_project()` generates whole states: entries with a
module that is missing, a directory, absolute, `..`-escaping, not a
string or empty; instances that aren't a list, aren't scalars, or repeat;
entries that aren't objects at all; and a cache pre-filled as current,
stale, contradictory, or not even a dict. The properties are about what
the leaderboard ends up publishing -- every registered instance lands in
exactly one of `rescored`/`already_current`/`failed`, a failure never
leaves a cache entry behind, an unusable baseline changes nothing,
`rescore()` never writes to the registry, and no path outside
`baselines/` is ever handed to `run_generate()` whatever `registry.json`
claims.

`test_state_files.py` covers `jsonable.load_json_object()`, the reader
behind `registry.json` and `.score_cache.json`. It is a separate file on
purpose: `test_jsonable.py` takes a module-level
`pytest.importorskip("numpy")`, so everything in it is skipped wherever
numpy isn't installed -- which includes CI, where `requirements-dev.txt`
installs only pytest. Put a non-numpy test in that file and it silently
stops running where it matters most. See `KNOWN_ISSUES.md`, "A note on
where tests are put".

`invariants.py` holds properties asserted from many tests rather than
checked in one: `assert_registered_implies_verified()` is the pipeline's
soundness property in a line — every registered baseline has, at every
instance it is registered at, a cached score under the current referee
that passed. `test_inbox.py` and `test_rescore.py` both call it. See
`KNOWN_ISSUES.md`'s "recurring failure class" for why a property beats
another instance-by-instance pass.

That's every piece in `TOOLKIT.md`'s build order except the
progress-over-time chart (item 10), which is a deliberate non-goal — see
TOOLKIT.md for why.

`isolation/` has its own suite in `isolation/tests/`, covering the
sandbox boundary: that a submission's debug `print()` (or a raw write to
fd 1) can't corrupt the result line, that a crash or an
unserializable artifact comes back through the same `{"ok": false}`
channel, and that Docker being unavailable raises `SandboxUnavailable`
instead of looking like a failed submission. It doesn't need Docker
either.

`isolation/tests/test_container.py` is the other half: seven tests that
each start a real container and check what it can actually do -- the uid
it runs as, that there is no route out, that every write outside `/tmp`
fails with `EROFS` and not merely with "permission denied", that a
timed-out container is removed rather than left running, and that the
output cap fires. Marked `docker` and deselected by default (`pytest -m
docker` runs them, after `docker build -t sagecraft-runner:latest
isolation`). The availability check lives in a fixture rather than at
module level on purpose: at module level it would run `docker info`
during collection, so even a default run would touch the daemon.

It also asserts the container's argument list directly — `--network
none`, `--read-only`, `--cap-drop ALL`, `--user 65532:65532`,
`--pids-limit`, the memory and swap caps, and that the only three mounts
are the submission, the spec, and `harness/`, all read-only. That needs
no daemon, and it means a silently weakened sandbox fails the default
suite rather than waiting for a Docker-enabled runner. The two halves are complementary and both are
mutation-checked: dropping a flag turns the argv test red without a
daemon, and weakening the real container turns the behaviour test red
with one.

```bash
pip install -r requirements-dev.txt
pytest
```
