# toolkit/

Problem-agnostic plumbing shared by every fork of this template: the
`evaluate()` combinator, the results log, the registry, the inbox
pipeline, the rescore path, the leaderboard renderer, and so on. See
`TOOLKIT.md` at the repo root for the full design, the build order, and
current status.

Both this package and `isolation/` are pure standard library — nothing to
install to use them. Your problem's own dependencies are its business, and
the sandbox image's are pinned in `isolation/Dockerfile`.

`isolation/` (Docker sandboxing for submitted code) lives one level up,
not inside this package — see `isolation/README.md`. `toolkit/inbox.py`
and `toolkit/rescore.py` both take it as a required argument; nothing in
`toolkit/` runs a submission any other way.

## Testing this package

`toolkit/tests/` exercises every piece here against a deliberately
trivial, throwaway problem (`toolkit/tests/fixtures/fake_problem/`) built
only to test this code — never a real benchmark. See
`toolkit/tests/README.md` for what's tested so far.

`isolation/tests/` covers the sandbox boundary itself — the JSON
contract, stdout isolation, and the host-side failures that must never
be mistaken for a bad submission. Neither suite needs Docker.

```bash
pip install -r requirements-dev.txt
pytest
```
