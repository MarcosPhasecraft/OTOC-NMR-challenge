# Implementation plan

Read `CONTEXT.md` first. See PLAYBOOK.md for the staged approach this
follows — this file is the concrete version of that for your specific
problem.

Keep this file short. If you're about to write a paragraph explaining
*why*, or documenting something you found out along the way, put it in
`NOTES.md` instead and leave a one-line pointer here.

## Scope for now

[What's in scope for a first working version, and what's explicitly
deferred? e.g. "single-qubit gates only, multi-qubit deferred" or
"square lattices only, other topologies deferred."]

## Stage 1 — verifier and scorer

### Data format

```python
spec = {
  # [every field a solution could need — nothing implicit]
}

artifact = {
  # [the exact shape of what a solution produces]
}
```

### Verifier — `harness/`

[The exact condition(s) checked, as a numbered list if there's more than
one. State which single condition (if any) carries the whole correctness
argument, the way "Majorana pairwise anticommutation" does for the
fermion project.]

### Scorer

[The metric(s), as a vector. State explicitly that they're not combined
into one number, and why not, if that's not obvious for this problem.]

### The toolkit contract

[`toolkit/` is built (see TOOLKIT.md) and plugs into your problem via
`build_spec(instance_id) -> spec`, `parse_instances(claim) -> list[instance_id]`,
and `FROZEN_GLOBS`, alongside `verify`/`score` above — all five need to
be importable from your top-level `harness/` package. Define these now;
they're also useful on their own as the one place your "instance
identifier" format and grammar live.]

### Tests, in this order

1. **Analytic sanity test** — [some small case worked out by hand].
2. **Rejection tests** — [specific broken inputs the checker must catch].
3. **Published-result reproduction** — [if applicable; otherwise, note
   there's no external table to check against].

**Stage 1 is complete when these pass.** Report results and stop before
starting Stage 2.

## Stage 2 — a generator becomes the submission

Nothing above changes. `toolkit.evaluate` is the wrapper; add one
editable directory (`solution/`) — see PLAYBOOK.md Step 5.

## Layout

```
[your-repo]/
  CONTEXT.md   PLAN.md   NOTES.md   CLAUDE.md
  run.py              copied from _templates/run.py — see TOOLKIT.md / toolkit/cli.py
  harness/            FROZEN — verify(), score(), build_spec(), parse_instances(), FROZEN_GLOBS
  baselines/          FROZEN — reference solutions, plus accepted submissions
  tests/              your problem's own tests
  solution/           EDITABLE — Stage 2 only
  toolkit/            shared plumbing, from the template — see TOOLKIT.md
  isolation/          the sandbox submitted code runs in — see isolation/README.md
  inbox/              Step 6 only: one folder per incoming submission
  scripts/            Step 6 only: your own process_inbox.py — see PLAYBOOK.md Step 6
```

`toolkit/` and `isolation/` come with the template and aren't yours to
rewrite; `inbox/` and `scripts/` don't exist until you reach Step 6.

## Deferred, deliberately

- [Anything explicitly out of scope for now, so it doesn't get
  half-implemented by accident later.]

## Traps

[Empty until you hit one. When you do, add it here as a one-line entry
with a pointer into NOTES.md for the full story — don't write the full
story in this file.]
