# Playbook: working with this template

This is a step-by-step guide. Follow it in order — each step assumes the
previous one is done. Nothing here is specific to any one problem; if you
want a worked example to look at while you read this, open
[fermionic-encoding-challenge](https://github.com/MarcosPhasecraft/fermionic-encoding-challenge)
in another tab. It's a finished instance of exactly this pattern.

## The idea

Someone (a person or an AI) submits a *program* that takes a description of
a problem instance and produces a candidate solution. A second piece of
code — one you write once, trust, and then never change to accommodate a
submission — checks whether that solution is actually valid. A third piece
of code scores it, but only if it passed the check. Over time, many
candidate programs pile up, and you keep the best one(s). The checker (verifier) is
the whole point: it has to be something you'd trust even if you didn't
trust whoever wrote the submission.

## Steps and stages

This file counts in **steps**; `PLAN.md` and `CLAUDE.md` gate work in
**stages**. They're the same road at two resolutions:

- **Stage 1** is Steps 1-4: write down the contract, then build the
  checker and scorer and prove them against known-good answers, then
  freeze them. It ends at a sign-off, and nothing editable exists yet.
- **Stage 2** is Steps 5-6: a `generate(spec)` submission appears in the
  one editable directory, and other people's submissions come in through
  the inbox pipeline.

Step 0 is before both. The split matters because Stage 2 must not start
until Stage 1's tests pass -- see Step 3.

## Step 0: pick your problem

Any problem that fits the shape described in `PROBLEMS.md` works — that
file has a few starting points, so bring your own idea if
you have one. Once you've picked something, `PROBLEMS.md` has done its
job; you don't need to keep it in sync with what you actually build.

## Step 1: write down the contract

Before writing any checker code, answer three questions in plain language,
and write the answers into `CONTEXT.md` (copy the template from
`_templates/CONTEXT.md`):

- **What is a "problem instance"?** This is your `spec`. It has to *fully*
  describe one instance — every parameter a solution could possibly need,
  with nothing implicit and nothing passed in some other way. If your
  checker or your solution-writer ever needs an argument that isn't in
  `spec`, put it in `spec` instead. (The fermion project's `spec` is a
  dict with mode count, lattice shape, edges, and coordinates — everything
  a mapping could need to know about the lattice.)
- **What is the "artifact"?** This is the object a submission produces —
  a circuit, a matrix, a polynomial, a mapping, a rewrite rule, whatever
  your problem is actually about. Write down its exact data format now
  (field names, types, shapes) — you'll paste this into `verify.py`'s
  docstring later. Make it plain-JSON-serializable (dicts, lists,
  strings, numbers, booleans) — a submission's `generate()` runs inside
  a sandboxed container (Step 6, `isolation/`) and its result has to
  cross that boundary as JSON, never as a pickle.
- **What does a submission actually look like?** It should be a _function_,
  not a table of numbers: `generate(spec) -> artifact`. A raw artifact is
  an *instance* — it can't be diffed against another good solution, almost
  any edit to it breaks validity, and it doesn't transfer to a different
  instance size. A function is an *idea*, and ideas are what you actually
  want to accumulate.

Also write down, in the same file: why this problem matters, what's
already known about it (best published results, if any), and what's
genuinely open. One or two paragraphs each is enough — this file is meant
to be read once by someone new to the project, not to be a literature
review.

## Step 2: figure out what kind of checker you're building

This matters because it tells you how hard the checker is to get right
and what tools it needs. Most problems fall into one of these shapes:

- **Exact truth-table / functional equivalence** — simulate over every
  input, or compare matrices directly. No randomness, no sampling.
- **Exact algebra over a finite field** (e.g. GF(2)) — the check is a
  linear-algebra condition, no simulation at all. This is what the
  fermion project does.
- **Exact rewrite/identity check, with a library as output** — the
  submission is a *set of rules*, not one instance; each rule is checked
  as an exact identity.
- **Symbolic order-condition check** — an algebraic identity from a
  series expansion, checked symbolically, not numerically.
- **Certified continuous-domain bound** — a claim like "this polynomial
  stays within epsilon of the target function on this whole interval,"
  checked with rigorous interval arithmetic, not by sampling points.
- **Exhaustive small-instance fault enumeration** — enumerate every
  low-order fault on a small circuit and check a property holds for all
  of them.
- **Exact resource accounting, no reject path** — almost any submission
  is "valid"; the only real question is its cost. Here the verifier is
  nearly trivial and the scorer is where the actual work is.
- **Two-layer: structural validity, then a perturbative claim** — a
  structural check (e.g. stabilizer algebra) followed by a separate
  claim about behavior under noise or in some limit.

Knowing which bucket you're in tells you what Step 3 actually involves —
"exact resource accounting" problems get a much easier Step 3 than
"certified continuous-domain bound" ones.

## Step 3: build the checker and scorer, against known answers only

This is the stage where **no AI-written solution exists yet.** You are
building the referee and then proving to yourself that it's trustworthy, using
solutions you already know are correct. Do not skip ahead to Step 5 before
this is solid — if the referee is wrong, everything built on top of it is
wrong too, and you won't find out until much later.

1. Write `verify(spec, artifact) -> result`, where `result` is a
   structured dict describing what passed and what didn't
   (`{"passed": bool, "checks": {...}}`). **It must never raise an
   exception** — a malformed or adversarial artifact is an expected input,
   not a bug. Whatever condition you check should be *exact*, not sampled:
   checking a handful of random cases and calling it verified means a
   submission only has to survive your specific sample, which is a much
   weaker guarantee than it looks like.
2. Write `score(spec, artifact) -> metrics`, which runs *only* if
   `verify` passed. Report a **vector** of metrics (total cost, max cost,
   qubit count, whatever's relevant) — never collapse them into one
   number. A single combined score always means inventing an exchange
   rate between things that don't actually trade off 1:1, and it becomes
   impossible to change later without invalidating every past result.
3. Write 2-3 reference solutions you already know are correct, each as a
   `generate(spec) -> artifact` function — never hand-write a big artifact
   directly. If you don't have "known good" reference constructions
   for your problem, that's a sign you need to find one in the
   literature before writing any code.
4. Write tests, **in this order**:
   - **An analytic sanity test that depends on nothing external.** Some
     small case where you can work out the right answer by hand, and
     check your checker/scorer agrees. If this fails, nothing else you
     build matters until it's fixed — fix this first, always.
   - **Rejection tests.** Deliberately feed the checker broken input
     (wrong size, wrong format, an artifact that's *almost* valid but
     violates the one condition that matters) and confirm it rejects
     correctly, with a useful diagnostic, not just a generic failure.
   - **Reproduction of a published result, if one exists.** This is the
     real gate. If your field has a paper with a table of best-known
     numbers, reproduce enough of it to trust your scorer's numbers
     against the outside world. If no such table exists, skip this one.
5. Only once all of the above passes, write it down as done in
   `PLAN.md` (copy `_templates/PLAN.md`) and move on. This checkpoint
   is the entire reason Step 3 is separate from Step 4 — if a problem
   ever shows up in a submission later, it can only be the submission's
   fault, because the referee was already validated independently.

## Step 4: freeze the referee

Once Step 3 passes, the checker, scorer, and reference solutions become
**frozen**. Nobody edits them to make a submission pass — that defeats the
entire point of having a referee anyone can trust. From here on:

- If you find yourself wanting to change the checker because some new
  candidate solution fails it, stop and ask: is this a genuine bug in the
  checker (rare, and worth confirming very carefully), or is the
  candidate solution trying to get around the check (assume this first)?
- Keep one directory of frozen code (checker + scorer + reference
  solutions) and one directory that's the only thing anyone is allowed
  to edit going forward (the candidate solution). Write this down
  explicitly in `CLAUDE.md` (copy `_templates/CLAUDE.md`) so it's not
  just a convention someone has to remember.
- Any way a scalar cost metric can be optimized, it will be — including
  by degenerate tricks that satisfy the letter of the check while
  missing the point. (The canonical cautionary tale: a submission to
  ecdsa.fail contained a hardcoded 13-digit nonce found by brute-force
  GPU search, plus a pair of gates that cancel out and exist only to
  shift which test inputs got sampled.) Assume this will be tried against
  your checker too, and design accordingly — this is exactly why Step 3's
  checks need to be exact conditions, not statistical ones.

## Step 5: open it up to a generator

The thin wrapper that ties it together is already built — see
`toolkit/evaluate.py`:

```python
def evaluate(problem, spec, generate_fn):
    artifact = generate_fn(spec)
    return evaluate_artifact(problem, spec, artifact)

def evaluate_artifact(problem, spec, artifact):
    result = problem.verify(spec, artifact)
    if not result["passed"]:
        return result
    return {**result, **problem.score(spec, artifact)}
```

(`problem` comes from `toolkit.problem.load_problem()`, Step 6 below —
it's just `verify`/`score` bundled with a bit of validation, so a fork
this early can just as well call its own `verify`/`score` directly
instead of loading a `Problem` for this.)

The submission is now one file containing one function,
`generate(spec) -> artifact`, sitting in the one directory anyone is
allowed to edit. This is the thing that gets iterated on — by you, by a
friend, or by an AI agent given the checker's error messages as feedback.

One rule to enforce here, and it's usually enforced by testing rather than
by reading the code: **a submission must be one uniform rule**, not a
lookup table keyed to specific problem sizes. Test this by evaluating on
instance sizes the submission-writer didn't specifically optimize for.

## Step 6: let other people submit things

Once Step 5 works for your own submissions, other people (or their AI
agents) can propose solutions without needing write access to your
checker.

**Before anything else: `generate()` is arbitrary code someone else
wrote, not data.** `verify()` only ever sees what `generate()` returns —
by the time it runs, whatever code was in the submission has already
executed with whatever access the machine running it had. A frozen,
exact verifier stops the leaderboard from being gamed; it does nothing
to stop a malicious or merely careless submission from doing damage on
its way there, and those are genuinely different problems. **Never call
a submission's `generate()` directly. Always run it through
`isolation/run_isolated()`** — a disposable, network-less Docker
container with no filesystem access beyond the submission file and a
read-only copy of `harness/`, capped CPU/memory/processes/wall clock,
and a plain-JSON boundary for the result. See `isolation/README.md` for
the exact setup, its defaults, and what it doesn't cover. If Docker
itself isn't available, that helper raises rather than silently falling
back to running the submission unsandboxed — never work around that by
calling `generate()` directly "just this once."

The shape that works for the rest of it:

- A submission is a self-contained folder: the `generate(spec)` file, a
  small manifest (name, human-readable label, which inputs it claims to
  work at), and optionally a folder of free-text notes on what was tried.
  Regular files and directories only, within modest size and count
  limits — the inbox rejects anything else on sight, because the code
  that copies a submission out of that folder runs on your machine,
  unsandboxed, and follows whatever it is pointed at.
- One script processes a folder like that: run `verify()` on every instance
  claimed, and only register it (add it to a registry file, update a
  leaderboard) if everything passes. No manual judgment calls, no partial
  credit.
- Keep the free-text notes clearly separate from anything that's actually
  been checked — they're useful for the next person, but they're
  unverified prose someone chose to write, not something the checker
  looked at.

This part (the inbox script, the registry, the leaderboard renderer, a
cache keyed to "has the checker itself changed") doesn't need to be
rewritten per problem — it's the same shape regardless of what you're
actually checking, and it's built: `toolkit/`. It's a small, separate
contract between your problem and this shared plumbing (four functions
and a list of filenames — `build_spec`, `parse_instances`, `verify`,
`score`, `FROZEN_GLOBS`, see `TOOLKIT.md`), on top of the `spec`/
`artifact` contract from Steps 1-5 — your `harness/` package just needs
to expose all five under those names.

Two things to know before wiring it up, both of which cost a real fork
an afternoon:

- **`inbox/` has to exist.** `process_inbox()` reads it rather than
  creating it, so that a mistyped path can't look like an empty inbox.
  The template ships one with a placeholder README.
- **A submitted or registered file must stand alone.** The sandbox mounts
  that one file and `harness/`, nothing else, so anything shared between
  baselines belongs in `harness/` and is imported as `harness.<module>`.
  Importing a sibling works locally and fails only in the container.

To actually wire it up (save something like this as your own
`scripts/process_inbox.py`):

```python
from toolkit.problem import load_problem
from toolkit.registry import Registry
from toolkit.cache import ScoreCache
from toolkit.inbox import process_inbox
from toolkit.leaderboard import render_leaderboard
from isolation.run_isolated import ensure_available, run_isolated

ensure_available()  # stop now if Docker is down or the image isn't built

problem = load_problem("harness")
registry = Registry("baselines/registry.json")
cache = ScoreCache(".score_cache.json")

for report in process_inbox(
    problem, inbox_dir="inbox", baselines_dir="baselines",
    registry=registry, cache=cache, run_generate=run_isolated,
):
    status = "accepted" if report["accepted"] else f"rejected: {report['reason']}"
    print(report["folder"], "->", status)

print(render_leaderboard(problem, registry, cache, metric_key="your_metric_name"))
```

If you ever do change a frozen file — a real checker bug, or just a typo
in a docstring — every cached score is invalidated by design, and
`render_leaderboard` will refuse to draw an empty table and tell you to
recompute. That's what `toolkit/rescore.py` is for:

```python
from toolkit.rescore import rescore, summarize

print(summarize(rescore(
    problem, registry, cache,
    baselines_dir="baselines", run_generate=run_isolated,
)))
```

It re-runs each registered baseline only where the current fingerprint
has no cached score. Note the same `run_generate=run_isolated`: by this
point `baselines/` holds other people's accepted submissions, so
rescoring re-runs untrusted code and goes through the sandbox exactly
like the inbox does. Anything that no longer verifies is reported and
left registered — what to do about a baseline your corrected referee now
rejects is your call to make deliberately.

`run_generate=run_isolated` is not optional and has no default on
purpose — see `isolation/README.md`'s hard rule above. `ensure_available()`
is worth the one line: without it, a stopped Docker daemon makes every
submission look like it failed verification, so a whole inbox gets
rejected and nothing tells you the sandbox never ran once. Only the
progress-over-time chart (`TOOLKIT.md` item 10) was skipped, as lowest
priority; everything else in `toolkit/` is built and tested (see
`toolkit/tests/README.md`).

## The four key documents

Keep four separate markdown files at the root, and don't blur what goes
where:

- **`CONTEXT.md`** — the problem, why it matters, what's known, what's
  open. Written once, rarely touched again.
- **`PLAN.md`** — what to build, in what order, the exact data formats
  and function signatures. Keep this short enough to skim. If you're
  about to write a paragraph explaining *why* something is the way it is,
  or documenting a bug you just found, it belongs in `NOTES.md` instead —
  leave only a one-line pointer in `PLAN.md`.
- **`NOTES.md`** — the investigation log. Free to grow without limit.
  Organize by topic, not by date, and write it as a clean summary of what
  you found, not a transcript of "first I thought X, then Y."
- **`CLAUDE.md`** — durable rules that should shape behavior in every
  future session: which directories are frozen, which traps have already
  been hit once, project-specific conventions. Not a plan, not a log —
  just the rules a past mistake produced.

This split earns its keep specifically because an AI agent (or a person
six months later) will read these cold, with no memory of how the project
got here. Don't let `PLAN.md` absorb the other two — it's happened before
in the reference project, and it makes the actual plan hard to find under
an accumulated log.

## Checklist

- [ ] Picked a problem, worked out which checker archetype it is (Step 2)
- [ ] `CONTEXT.md` written: spec, artifact, why it matters, what's known
- [ ] `verify()` written, never raises, checks an exact condition
- [ ] `score()` written, returns a vector, never a single combined number
- [ ] 2-3 known-good reference solutions written as `generate(spec)`
- [ ] Analytic sanity test passes
- [ ] Rejection tests pass
- [ ] Published-table reproduction passes (if applicable)
- [ ] Frozen/editable boundary written down in `CLAUDE.md`
- [ ] `harness/` exposes all five of `build_spec`, `parse_instances`,
      `verify`, `score`, `FROZEN_GLOBS` (instance ids are ints or strings)
- [ ] `isolation/` image built (`docker build`), `generate()` never called directly
- [ ] First from-scratch candidate solution runs through the pipeline
