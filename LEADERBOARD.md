# Leaderboard

Generated 2026-09-26 05:58 UTC by `scripts/render_leaderboard.py` from `baselines/registry.json` and `.score_cache.json` (referee fingerprint `9628f1f14ff7`). Do not edit by hand.

Development set: 12 tier-0 instances (N = 10-12), exact scoring. Each entry is called once per instance and budget rung (11 rungs, x0.25 to x8 of the seed-calibrated cap, ratio sqrt 2); every call is one measured (CZ, RMSE) point (CONTEXT.md §8).

## 1. Cost at the target error (RMSE <= 0.05) -- ranks the board

CZ count of the cheapest measured point under the target, per instance; `ratio` is the geometric mean over instances of (entry CZ / seed CZ), lower is better. `miss` = the target was not met at any rung.

| rank | entry | ratio to seed | met | mean CZ | instance_35_d_5 | instance_4_d_5 | instance_63_d_5 | instance_48_d_5 | instance_93_d_5 | instance_26_d_7 | instance_179_d_5 | instance_132_d_9 | instance_154_d_5 | instance_42_d_6 | instance_123_d_5 | instance_74_d_9 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | second-order fused swap network | — | 0/12 | — | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss |
| 2 | seed: first-order fused swap network | — | 0/12 | — | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss | miss |

## 2. Error at the Google-comparable budget (x1 of the seed-calibrated cap)

RMSE at the rung where the plain seed sits at ~10 % mean error, per instance, and the geometric-mean improvement factor over the seed (AlphaEvolve on DMBP: 10.4 % -> 0.82 % mean error, 12.7x; its 792-CZ budget was one step of a 15-spin seed). An over-budget cell is invalid at this rung and shown as `over`.

| entry | improvement over seed | mean RMSE | instance_35_d_5 | instance_4_d_5 | instance_63_d_5 | instance_48_d_5 | instance_93_d_5 | instance_26_d_7 | instance_179_d_5 | instance_132_d_9 | instance_154_d_5 | instance_42_d_6 | instance_123_d_5 | instance_74_d_9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| second-order fused swap network | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| seed: first-order fused swap network | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

## 3. Pareto frontiers per instance

Nondominated (CZ, RMSE) points over every entry and rung; lower is better on both. A point dominates another if it is no worse on both and better on one.


**instance_35_d_5** (N = 10, cap = 1350 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_4_d_5** (N = 10, cap = 1620 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_63_d_5** (N = 10, cap = 4320 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_48_d_5** (N = 11, cap = 2640 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_93_d_5** (N = 11, cap = 2640 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_26_d_7** (N = 11, cap = 5280 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_179_d_5** (N = 11, cap = 5280 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_132_d_9** (N = 12, cap = 1188 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_154_d_5** (N = 12, cap = 2376 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_42_d_6** (N = 12, cap = 3168 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

**instance_123_d_5** (N = 12, cap = 6336 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1584 | 0.1968 | seed: first-order fused swap network | x0.25 |
| 1980 | 0.1857 | seed: first-order fused swap network | x0.3536 |
| 4356 | 0.1213 | seed: first-order fused swap network | x0.7071 |

**instance_74_d_9** (N = 12, cap = 6336 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|

## 4. Validation on unseen instances

Each kept entry is re-scored, next to the seed, on a fresh draw of four instances from the validation pool (tier-0 instances never on the board; `scripts/validation.py`). `holds` means it beats the seed there and its cost ratio is within 25 % of its development-set ratio. Baselines are exempt: they are the reference, not candidates.

| entry | generation | draw | dev ratio | validation ratio | holds |
|---|---:|---|---:|---:|---|
| (none yet) | | | | | |

## 5. Hard set (unranked)

Tier-0 instances with long tmax and a weakly coupled carbon, where the seed needs 70-300 steps for 10 % error. Nobody optimises on them; cost at the target and error at x1 are reported for every entry that has been run there, as a second generalisation axis. Empty until calibrated.

_no hard-set cells scored yet_
