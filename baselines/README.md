# baselines/

Reference solutions you already know are correct, each written as
`generate(spec) -> artifact` — never a hand-written artifact directly.
These are what you validate the checker/scorer against in Step 3, before
any AI-written submission exists. See PLAYBOOK.md Step 3.

Frozen alongside `harness/` once Stage 1 is signed off.

**Each one must stand alone.** A registered baseline is re-run through
the sandbox by `toolkit.rescore`, and the container mounts exactly two
things: that one file, and `harness/` read-only. A baseline that imports
a sibling here — `from baselines.helpers import ...` — works when you
test it locally and fails inside the container with `No module named
'baselines'`. Shared constructions go in `harness/` and are imported as
`harness.<module>`; `isolation/README.md` calls this the
`harness.constructors` pattern.

Nothing here yet. Delete this file once real content replaces it.
