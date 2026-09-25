#!/usr/bin/env python3
"""Register the frozen baselines on the leaderboard and score them through the sandbox.

    python3 scripts/register_baselines.py

Idempotent: `register()` keeps the original `registered_at`, and `rescore()` only recomputes
cells the current referee fingerprint is missing. Run it again after any change to a frozen
file. Exits non-zero if a baseline fails to verify anywhere; a reference that does not verify
is a finding, not a blank cell. Re-renders LEADERBOARD.md on success.

The baselines are trusted code we wrote, and they still go through `run_isolated`: by the
time rescore runs, `baselines/` also holds other people's accepted submissions (CLAUDE.md).
"""
import sys

from _common import BASELINES_DIR, load
from instance_set import LEADERBOARD_INSTANCES
import render_leaderboard

from isolation.run_isolated import ensure_available, run_isolated
from toolkit.rescore import rescore, summarize

#: name -> (module file in baselines/, label shown on the leaderboard)
BASELINES = {
    "seed_p1": ("seed_p1.py", "seed: first-order fused swap network"),
    "fused_p2": ("fused_p2.py", "second-order fused swap network"),
    "fused_p4": ("fused_p4.py", "fourth-order fused swap network"),
}


def main():
    ensure_available()
    problem, registry, cache = load()
    for name, (module, label) in BASELINES.items():
        registry.register(name, module=module, label=label, instances=LEADERBOARD_INSTANCES)
    reports = rescore(problem, registry, cache, baselines_dir=BASELINES_DIR,
                      run_generate=run_isolated, names=list(BASELINES))
    print(summarize(reports))
    bad = [r for r in reports if r["failed"] or r["unusable"]]
    for r in bad:
        print(f"\n{r['baseline']}: unusable={r['unusable']!r}", file=sys.stderr)
        for f in r["failed"]:
            print(f"  {f['instance_id']}: {f['result'].get('reason')}", file=sys.stderr)
    if bad:
        return 1
    return render_leaderboard.main([])


if __name__ == "__main__":
    sys.exit(main())
