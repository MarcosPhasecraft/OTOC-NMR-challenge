# Example problems

Many problems that fit the shape below work
with this template, including ones nobody's thought of yet — pick your
own idea if you have one. The examples here exist to show the range of
what fits and to give people a starting point, not to define the set of
things worth building.

## Does your idea fit?

Ask these four questions:

1. Can you describe a "problem instance" completely, with nothing
   implicit? (This becomes `spec`.)
2. Does a solution produce some definite object that can be checked
   against a real condition — not just "does this look plausible"? (This
   becomes `artifact` + `verify`.)
3. Is that check exact, or at least rigorously certifiable — not
   something you'd only sample and hope? If your honest answer is "we'd
   simulate a bunch of random cases and call it good," look for a real
   exact condition instead; if none exists, you're probably in the
   archetype where the checker barely rejects anything and the scorer
   carries the weight (see `PLAYBOOK.md` Step 2) — a valid thing to
   build, just a different shape of project.
4. Is there a cost worth minimizing, separate from validity? (This
   becomes `score`.)

If yes to all four, it fits — whether or not it's anywhere below.

## Worked example

- **Fermion-to-qubit mappings.** Done. See
  [fermionic-encoding-challenge](https://github.com/MarcosPhasecraft/fermionic-encoding-challenge).
  Read this one regardless of what you build; it's the concrete example
  `PLAYBOOK.md` keeps referring back to.

## A few starting points

- **Small-unitary (1-3 qubit) synthesis.** Check a candidate circuit's
  unitary against a target, exactly or to machine precision. Clean,
  high-precision check, good first project.
- **Magic-state / stabilizer decompositions.** Verification is linear
  algebra over GF(2) — closest sibling to the fermion project above,
  good second project if you want to reuse that intuition.
- **Circuit rewrite discovery.** The submission is a *set of rewrite
  rules*, not one circuit — each rule checked as an exact identity. One
  good rule applies everywhere, so the leverage is unusually high.
- **Product-formula discovery** (Trotter-type formulas). Verified by a
  symbolic order-condition identity, not a numerical check at all.

Plenty of other shapes fit just as well — arithmetic circuits, QROM
lookup tables, fault-tolerant state preparation and flag circuits (both
checked by exhaustively enumerating faults on a small circuit),
distillation protocols, pebbling strategies, and anything else that
answers yes to the four questions above.
