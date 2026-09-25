# [Problem name]: problem and context

Fill this in once, at the start. See PLAYBOOK.md Step 1.

## 1. The setup

[What physical/mathematical object is this about? Define the objects,
notation, and any convention (signs, indexing, branch choices) that later
code will depend on.]

## 2. Why the choice matters

[What varies between good and bad solutions, and why does anyone care?
What's the cost that's actually being minimized?]

## 3. The optimization problem, precisely

> [One or two sentences: given X, find Y minimizing/maximizing Z.]

[If there's more than one cost metric and they don't agree with each
other, say so explicitly here — this is important enough to state early.]

## 4. What is known, and what is not

**Known:**

- [Best published results, if any. Cite them.]

**Open:**

- [What hasn't been tried, or is believed to be hard.]

## 5. What we are building

A generator/verifier/scorer harness: a program proposes a solution, and
frozen code checks and scores it.

- **Generator** — submits a *program* that, given a problem instance,
  produces a candidate solution.
- **Verifier** — frozen, deterministic. Checks [the condition that fully
  determines validity].
- **Scorer** — frozen, deterministic. Computes [cost metric(s)]. Runs
  only if verification passes.

### Why this problem

[What makes verification here trustworthy — exact at any instance size,
cheap to compute, no sampling/approximation? If it's *not* exact — e.g.
this is one of the "no reject path" problems — say so plainly instead of
overclaiming.]

## 6. References

[Primary source(s) for the problem definition and any baseline you're
implementing. Verify specific numbers/theorem statements against the
actual source rather than trusting a secondhand description — see
fermionic-encoding-challenge's NOTES.md for an example of a published
paper's own code disagreeing with its own equations.]
