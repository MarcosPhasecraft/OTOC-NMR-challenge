# The shared toolkit

`PLAYBOOK.md` Step 6 mentions a shared toolkit for the parts that are the
same regardless of what problem you're checking: the inbox pipeline, the
registry, the leaderboard, a cache keyed to "has the checker changed."
This file is the design *and* the build plan for that toolkit, written
before most of it is coded, so every piece has a clear place to land and
every fork of this template knows what it'll eventually plug into.

Status: everything is built except item 10, a progress-over-time chart,
which is deliberately left to a fork — it would need a plotting
dependency this project otherwise doesn't have, and the acceptance
timestamps it needs are now recorded so it stays possible (see item 10
below). `isolation/` (item 11) and
items 0-9 (`problem.py`, `evaluate.py`, `results_log.py`, `cache.py`,
`registry.py`, `cli.py` + `_templates/run.py`, `held_out.py`,
`submission.py`, `inbox.py`, `leaderboard.py`), plus `jsonable.py`
(item 12) and `rescore.py` (item 13), are all built and tested
— see `toolkit/tests/README.md`. If item 10 is ever wanted,
[fermionic-encoding-challenge](https://github.com/MarcosPhasecraft/fermionic-encoding-challenge)'s
`scripts/progress_chart.py` is a working example to adapt by hand.

## The second contract

`PLAYBOOK.md` Steps 1-5 define the contract between a *submission* and
*your problem*: `spec`, `artifact`, `generate(spec) -> artifact`. That
contract is between two things you both write (the checker, and whatever
submission gets thrown at it).

The toolkit needs a second, smaller contract — between *your problem* and
*the shared plumbing* — so that generic code never has to know anything
about fermions, unitaries, or whatever else your problem actually is.
Concretely, your problem exposes a handful of things under fixed names,
and every shared piece below is written only against those names:

- `verify(spec, artifact) -> {"passed": bool, "checks": {...}}` — you
  already wrote this in Step 3.
- `score(spec, artifact) -> dict` — same, already written.
- `build_spec(instance_id) -> spec` — turns one opaque instance
  identifier into a full spec. An "instance identifier" is whatever makes
  sense for your problem — the toolkit never looks inside it — but it
  **must be an int or a string**, and that is enforced. Ids are written
  into `registry.json` and read back, they key dicts, and they form the
  score cache key via JSON, so anything else misbehaves three ways at
  once: a tuple returns as a list and `build_spec()` sees a different
  type on later passes, a list can't be a dict key at all, and the cache
  key it forms stops matching what wrote it. Spell a composite id as a
  string — `"8x4"`, not `(8, 4)`. `parse_instances` exists precisely so
  your problem can choose that spelling.
- `parse_instances(claim: str) -> list[instance_id]` — turns the
  `"sizes"` string from a submission's manifest (e.g. `"3-15"`, or
  `"8x4,15x15"`, or whatever grammar your problem needs) into a list of
  instance identifiers. This is the one place the "sizes grammar" lives;
  it's genuinely different per problem (a grid side length isn't a
  circuit width isn't a polynomial degree), so the toolkit takes it as
  given rather than trying to invent one grammar that fits everything.
  Returning a generator is fine — the toolkit materialises it once, up
  front, rather than passing it along to be consumed twice.
- `FROZEN_GLOBS` — a list of file globs identifying "the referee" for
  your problem (e.g. `["harness/*.py"]`), used to fingerprint the cache.

Four functions and one list. Everything below is written only in terms
of those, via one more piece that sits in front of all of them:

## The pieces

0. **A problem loader — built, see `toolkit/problem.py`.** Imports a fork's
   `harness/`, checks that `build_spec`, `parse_instances`, `verify`,
   `score`, and `FROZEN_GLOBS` all exist, and hands them back as one
   object. Not in the original sketch of this toolkit — it turned up
   while planning the build order, as the thing everything else below
   needs instead of each piece re-discovering the contract on its own.
   Fails loudly and specifically ("your harness has no `parse_instances`")
   rather than letting a missing piece surface as a confusing error three
   layers up.

1. **`evaluate` — built, see `toolkit/evaluate.py`.** The combinator
   sketched in `PLAYBOOK.md` Step 5: run `generate`, then `verify`, then
   `score` if it passed. Split into `evaluate()` (calls a `generate_fn`
   directly — for your own trusted code) and `evaluate_artifact()` (an
   artifact already exists — for the inbox pipeline, item 8, once it has
   one back from `isolation.run_isolated()`), so the isolation boundary
   doesn't have to be smuggled into this function's own contract.

2. **A results log — built, see `toolkit/results_log.py`.** Append-only,
   one entry per run. Written as JSONL (one JSON object per line:
   timestamp, note, instance id, whatever `score` returned) rather than
   the fermion project's TSV, specifically because a fixed set of TSV
   columns assumes every problem's metrics look alike, and they don't.

3. **A fingerprint + score cache — built, see `toolkit/cache.py`.**
   A cache entry means "this verified under this referee", and `get()`
   enforces that on read: a stored value that isn't a dict, or one whose
   `passed` isn't true, is a miss rather than a score. `.score_cache.json`
   is committed, so it is as much a bad-merge casualty as the registry,
   and a miss is always safe — the worst case is one recomputation. A
   file that can't be read *at all* is refused by name, with the way
   back (delete it and `rescore()`); it is never quietly treated as
   empty, which would look identical to a cold cache.
   Hashes the files matched by `FROZEN_GLOBS` (skipping anything a glob
   matches that isn't actually a file); that hash plus (baseline name,
   instance id) is the cache key for a computed score. A fingerprint
   mismatch is treated as a cache miss, never as a stale hit — recompute
   only when the referee itself changes, not on every run, and never
   silently serve a score computed under an older referee. `forget()` and
   `forget_baseline()` drop entries a run has contradicted, or a
   de-registered baseline's whole history: a cache entry means "this
   verified under this fingerprint", and one that outlives that meaning
   goes on being published.

4. **A baseline registry — built, see `toolkit/registry.py`.**
   `registry.json` maps a name to a module filename, a label, and the
   *already-resolved* instance ids it's been verified at (not the raw
   manifest claim string — the registry records what actually passed,
   not what was asked for), plus a loader that turns any entry, or all
   of them, into callable `generate` functions. Entries are validated on
   read as well as on write, ids included, because hand-editing
   `registry.json` is a supported way to correct it and bypasses
   `register()` entirely — including a file that won't parse, which is
   refused by name and pointed at version control, because unlike the
   cache a registry cannot be rebuilt. `remove()` de-registers one; pair
   it with `ScoreCache.forget_baseline()`, since cached scores are keyed
   by name and would otherwise outlive the entry and reappear if the name
   were reused.

5. **A CLI — built, see `toolkit/cli.py` and `_templates/run.py`.**
   `evaluate` (loads a `generate` function from a file path, builds spec
   via the problem's own `build_spec`, runs `evaluate()`, always logs a
   row — pass or fail) and `verify` (a debug path: checks a hand-written
   artifact from a JSON file directly against `verify()`, no `generate()`
   call, nothing logged — for trying a rejection case by hand before
   writing a whole solution). Both default to reading `harness/` and
   writing `results.jsonl` relative to wherever you run it from.

6. **A held-out-instance test helper — built, see `toolkit/held_out.py`.**
   `PLAYBOOK.md` Step 5's "must be one uniform rule, not a lookup table"
   is enforced by testing at instance ids the submission didn't target.
   `check_generalizes()` runs a `generate` function at a list of
   held-out instance ids and returns a `{instance_id: verify_result}`
   report — including turning a crash on one instance into a failed
   result rather than aborting the rest of the check, so a fork's own
   test sees every failure at once. `build_spec()` is inside that guard
   too: a held-out id is by definition one nobody chose deliberately, so
   it is the likeliest place for a problem to refuse a size it doesn't
   support. Can't prove uniformity (no finite
   test can); catches the obvious failure, a lookup table that breaks
   outside the sizes it was tuned on.

7. **Submission manifest parsing — built, see `toolkit/submission.py`.**
   Validates `submission.json` (`name` against the same
   `^[a-z][a-z0-9_]*$` pattern the fermion project used, a non-empty
   `label`, a `sizes` string resolved via the problem's own
   `parse_instances`, and an optional `generated_by`) and returns the
   resolved instance list, not the raw claim string — the same
   distinction `toolkit/registry.py`'s own docstring draws.

8. **The inbox pipeline — built, see `toolkit/inbox.py`.** For every
   folder directly under `inbox/`: validate its manifest (7), then run
   `generate` at every claimed instance through a `run_generate`
   callable the caller must supply explicitly — no default, so
   "sandboxed" can never be an accident of a default argument nobody
   looked at. In production that callable is
   `isolation.run_isolated.run_isolated`; toolkit's own tests pass a
   local stub instead, so this suite doesn't need Docker to run. Only
   registers the submission (adds it to the registry, copies its file
   into `baselines/`, copies an optional `memory/` folder alongside as
   `<name>.memory/`, caches every instance's score) if *all* claimed
   instances pass — one failing instance rejects the whole submission,
   and nothing about it is registered or cached, not even the instances
   that did pass. Never deletes or moves a rejected submission's inbox
   folder; that stays a maintainer's own call.

   Everything it touches on the way is attacker-supplied: the folder is
   walked before anything is copied out of it, and a manifest is a parsed
   document rather than a trusted object. Both are tested by property
   rather than by example — `toolkit/tests/generators.py` builds random
   submission folders and `test_inbox_generated.py` asserts the pipeline
   never raises, never registers what it did not verify, and never copies
   a byte from outside the folder, whatever was planted in it. See
   `toolkit/tests/README.md`.

9. **A leaderboard renderer — built, see `toolkit/leaderboard.py`.**
   Given the registry and the cache, ranks baselines by the mean of a
   chosen metric across whatever instances each has a cached score for
   (excluding a missing cell from that mean rather than treating it as
   zero; a baseline with no cached score at all sorts last instead of
   crashing) and renders a markdown table — instance columns default to
   the sorted union of every cached instance, or an explicit list in
   whatever order actually makes sense for a problem whose instance ids
   aren't naturally orderable (e.g. `"8x4"`-style strings). Doesn't rank
   *within* a column (no per-cell "winner" highlighting) — a deliberate
   simplification, not an oversight; that's presentation polish a
   maintainer can add on top, not something the generic renderer needs
   to get right on its own.

10. **A progress-over-time chart — deliberately not built.** Two
    reasons, and the second only became clear on review. First, plotting
    means a plotting library, and `toolkit/` and `isolation/` are
    otherwise pure standard library; spending that on the piece always
    ranked lowest is a bad trade. Second, and more to the point, the data
    wasn't there: `results.jsonl` is timestamped but only `cli.py` writes
    it, so it holds a maintainer's own local runs and never a submission,
    and registry entries carried no timestamp at all — so "the best value
    over time" across the leaderboard's baselines had nothing behind it.
    `register()` now stamps `registered_at` when a name is first
    registered, because that is the one part which cannot be
    reconstructed later. Rendering it is a fork's own call: read
    `registry.json` and the score cache, and plot with whatever you
    already depend on.

11. **An isolation helper for running submitted code — built, see
    `isolation/`.** The fermion project's README carries a prose warning
    ("if you're running someone else's submission, do it somewhere
    isolated") but no actual tooling for it. That's not enough: `verify()`
    only ever sees `generate()`'s *output*, so by the time it runs,
    arbitrary code has already executed with whatever access the machine
    running it has. A frozen, exact verifier defends the leaderboard
    against being gamed; it does nothing to defend the machine running
    it, and those are genuinely different problems. `isolation/` runs
    `generate(spec)` inside a disposable, network-less Docker container
    (no filesystem access beyond the submission file and a read-only copy
    of `harness/`, an unprivileged user, capped CPU/memory/processes/wall
    clock, and a plain-JSON — never pickle — boundary for the result) and
    fails closed if Docker itself isn't available, rather than silently
    running the submission unsandboxed. Built ahead of the rest, because
    it's a safety requirement rather than a convenience. Tested from both
    sides: `isolation/tests/test_isolation.py` asserts the `docker run`
    argument list without needing a daemon, and
    `isolation/tests/test_container.py` starts real containers and checks
    Docker honours it — deselected by default, run by CI.

12. **A JSON coercion helper — built, see `toolkit/jsonable.py`.** Not
    in the original sketch; it turned up because the obvious way to
    write a scorer for a numerical problem returns numpy values, and
    those aren't JSON-serializable. `np.float64` happens to pass (it
    subclasses `float`) while `np.int64`, `np.bool_`, and `np.ndarray`
    raise, so a scorer can look fine in testing and fail the first time
    a metric comes back as an integer — and fail *late*, after the
    expensive work, in `results_log` (losing the run) or in `cache`
    (after `inbox` already wrote the registry, leaving a submission
    registered with no scores and its name permanently taken).
    `to_jsonable()` converts what it can and raises, naming the type and
    its position, for anything ambiguous — a silently lossy log is worse
    than a loud failure when the numbers are the point. Two strictness
    levels: stored data (cached scores, the results log, registry
    instance ids) converts strictly and raises; a report meant for a
    human to read passes `fallback=repr`, so an odd value in a
    diagnostic can't stop the report being printed or saved. Use
    `dumps()` rather than `json.dumps()` anywhere harness-derived data
    gets serialized — conversion has to happen at every such point, and
    missing one just moves the crash a line earlier.

13. **A rescore path — built, see `toolkit/rescore.py`.** The half of
    item 3 that was missing. `cache.py` only recomputes when the referee
    changes, but nothing recomputed at all: `inbox.py` writes the cache
    once per accepted submission and never again, so any edit to a file
    matched by `FROZEN_GLOBS` invalidated every cached score and left the
    leaderboard rendering empty cells with no way back short of reverting
    the edit byte for byte. `rescore()` re-runs each registered baseline
    at the instances it's registered at and fills in whatever the current
    fingerprint is missing. It takes the same mandatory `run_generate`
    callable as `inbox.py` and for the same reason: `baselines/` holds
    accepted submissions from other people, so rescoring re-runs
    untrusted code and must go through the sandbox. A baseline the new
    referee rejects is reported and left registered — de-registering is a
    maintainer's call, not the pipeline's, and `Registry.remove()` plus
    `ScoreCache.forget_baseline()` are how that call gets carried out. A
    cached score the re-run *contradicts* is a different matter and is
    dropped, listed in the report's `dropped`: that only arises under
    `force=True`, which exists precisely to catch a baseline that isn't
    deterministic, and leaving the old entry would let the leaderboard go
    on publishing a score the run had just rejected. Two kinds of problem are
    deliberately handled differently: a name in `names=` that isn't
    registered raises immediately, before any work, because that is the
    caller's typo rather than a result; a baseline that can't be run at
    all — module file gone, registry entry malformed — is reported per
    baseline as `unusable` and doesn't cost the others their run.

    Its input is the project itself -- a `registry.json` that gets
    hand-edited, a `baselines/` that accumulates, a committed cache -- so
    all three are validated on read, and the whole surface is tested by
    property: `generators.build_project()` and
    `test_rescore_generated.py`. See `toolkit/tests/README.md`.

## What still lives per-problem

Everything the second contract lists as an input, plus your reference
solutions and your tests: `build_spec`, `parse_instances`, `verify`,
`score`, `FROZEN_GLOBS`, `baselines/`, `tests/`, and the four documents
(`CONTEXT.md`/`PLAN.md`/`NOTES.md`/`CLAUDE.md`). None of that moves into
the toolkit — it's the actual content of your benchmark, not plumbing.

One more per-problem piece, specific to item 11: `isolation/Dockerfile`'s
pinned dependencies. The sandboxing mechanism is shared; which packages
your problem's code actually needs baked into the image is not.

## How a fork gets the toolkit: vendored, not a package

Decided (was open in an earlier draft of this file): a fork gets the
toolkit the same way it already gets `isolation/`, `_templates/`, and
everything else — by cloning this template repo. No separate package,
no submodule.

The alternative was a small pip-installable package: cleaner imports,
and a fix propagates to every fork at once instead of needing to be
copied in by hand. That's real, and worth reconsidering if this grows
past a handful of people working somewhat independently. But it's
packaging and versioning overhead this project doesn't need yet, and it
would break the "clone it, remove origin, it's yours now" flow the
README already describes. Vendoring costs are (a) a fix to the toolkit
doesn't reach a fork unless someone copies it over by hand, and (b) two
forks can end up on different toolkit versions without anyone noticing —
acceptable for now, worth watching if it starts causing real pain.

## Module layout

```
toolkit/
  problem.py          # item 0 -- load_problem()
  evaluate.py         # item 1
  results_log.py      # item 2
  cache.py            # item 3
  registry.py         # item 4
  cli.py              # item 5 (invoked by a fork's own run.py)
  held_out.py         # item 6
  submission.py       # item 7
  inbox.py            # item 8 (calls isolation.run_isolated())
  leaderboard.py      # item 9
  jsonable.py         # item 12
  rescore.py          # item 13
  tests/
    fixtures/fake_problem/   # throwaway problem, used only to test the toolkit itself
    invariants.py            # properties asserted from many tests, not checked once
    generators.py            # random submission folders, for the property tests
    test_*.py
isolation/                # item 11
  run_isolated.py        # runs on the host
  run_generate.py         # runs inside the container
  Dockerfile
  tests/
_templates/
  run.py                 # the couple of lines a fork copies to its own root
```

## Validating the toolkit before any real fork depends on it

Same discipline `PLAYBOOK.md` asks of every problem's own Stage 1:
validate the referee against known answers before trusting it, one level
up. `toolkit/tests/fixtures/fake_problem/` is a deliberately trivial,
throwaway problem built only to exercise the toolkit's own code — for
example: an artifact is a pair of integers, `verify` checks they sum to
a target carried in `spec`, `score` is their product. Not a real
quantum problem, never referenced from any real fork. Every piece below
gets a test written against this fixture as it's built, rather than
tests bolted on at the end once everything already "seems to work."

## Build order (finished; kept for the reasoning)

The toolkit was built bottom-up, each piece tested against the
fake-problem fixture as it landed rather than tests bolted on at the
end: the fixture and a skeleton suite first, then the independent
low-risk pieces (`problem.py`, `evaluate.py`, `results_log.py`,
`cache.py`), then `registry.py` and the CLI, `held_out.py`, then
`submission.py` and `inbox.py` wired to the sandbox, and
`leaderboard.py` last.

Everything on that list is done. `jsonable.py` and `rescore.py` came
later, from problems found in review rather than from this plan. Item 10
is the only piece never built, and is now a deliberate non-goal rather
than a gap.
