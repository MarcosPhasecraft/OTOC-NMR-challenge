# Leaderboard

Generated 2026-09-26 13:44 UTC by `scripts/render_leaderboard.py` from `baselines/registry.json` and `.score_cache.json` (referee fingerprint `4c8615512ea7`). Do not edit by hand.

Development set: 12 tier-0 instances (N = 10-12), exact scoring. Each entry is called once per instance and budget rung (11 rungs, x0.25 to x8 of the seed-calibrated cap, ratio sqrt 2); every call is one measured (CZ, RMSE) point (CONTEXT.md §8).

## 1. Cost at the target error (RMSE <= 0.05) -- ranks the board

CZ count of the cheapest measured point under the target, per instance; `ratio` is the geometric mean over instances of (entry CZ / seed CZ), lower is better. `miss` = the target was not met at any rung.

| rank | entry | ratio to seed | met | mean CZ | instance_35_d_5 | instance_4_d_5 | instance_63_d_5 | instance_48_d_5 | instance_93_d_5 | instance_26_d_7 | instance_179_d_5 | instance_132_d_9 | instance_154_d_5 | instance_42_d_6 | instance_123_d_5 | instance_74_d_9 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | seed: first-order fused swap network | 1.000 | 12/12 | 4988 | 5400 (x4) | 2160 (x1.4142) | 4320 (x1) | 3630 (x1.4142) | 5280 (x2) | 5280 (x1) | 5280 (x1) | 1584 (x1.4142) | 3168 (x1.4142) | 6336 (x2) | 8712 (x1.4142) | 8712 (x1.4142) |
| 2 | second-order fused swap network | 1.500 | 12/12 | 8120 | 3780 (x2.8284) | 6480 (x4) | 2700 (x0.7071) | 5280 (x2) | 5280 (x2) | 5280 (x1) | 5280 (x1) | 6336 (x5.6569) | 12672 (x5.6569) | 12672 (x4) | 25344 (x4) | 6336 (x1) |
| 3 | fourth-order fused swap network | — | 11/12 | 19500 | 10800 (x8) | 10800 (x8) | 8100 (x2) | 13200 (x5.6569) | 19800 (x8) | 19800 (x4) | 13200 (x2.8284) | miss | 11880 (x5.6569) | 23760 (x8) | 35640 (x5.6569) | 47520 (x8) |

## 2. Error at the Google-comparable budget (x1 of the seed-calibrated cap)

RMSE at the rung where the plain seed sits at ~10 % mean error, per instance, and the geometric-mean improvement factor over the seed (AlphaEvolve on DMBP: 10.4 % -> 0.82 % mean error, 12.7x; its 792-CZ budget was one step of a 15-spin seed). An over-budget cell is invalid at this rung and shown as `over`.

| entry | improvement over seed | mean RMSE | instance_35_d_5 | instance_4_d_5 | instance_63_d_5 | instance_48_d_5 | instance_93_d_5 | instance_26_d_7 | instance_179_d_5 | instance_132_d_9 | instance_154_d_5 | instance_42_d_6 | instance_123_d_5 | instance_74_d_9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| seed: first-order fused swap network | 1.00x | 0.0816 | 0.1017 | 0.1036 | 0.0459 | 0.0500 | 0.1209 | 0.0372 | 0.0465 | 0.1441 | 0.0699 | 0.1075 | 0.0584 | 0.0941 |
| second-order fused swap network | 0.85x | 0.1189 | 0.2425 | 0.1702 | 0.0176 | 0.1164 | 0.1781 | 0.0372 | 0.0465 | 0.1154 | 0.1348 | 0.2313 | 0.1167 | 0.0195 |
| fourth-order fused swap network | — | 0.1692 | over | over | 0.0573 | over | over | 0.0826 | 0.0830 | over | over | over | 0.3551 | 0.2678 |

## 3. Pareto frontiers per instance

Nondominated (CZ, RMSE) points over every entry and rung; lower is better on both. A point dominates another if it is no worse on both and better on one.


**instance_35_d_5** (N = 10, cap = 1350 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 270 | 0.4592 | seed: first-order fused swap network | x0.25 |
| 270 | 0.4592 | seed: first-order fused swap network | x0.3536 |
| 540 | 0.3630 | second-order fused swap network | x0.5 |
| 540 | 0.3630 | second-order fused swap network | x0.7071 |
| 1080 | 0.2425 | second-order fused swap network | x1 |
| 1350 | 0.1017 | seed: first-order fused swap network | x1 |
| 1890 | 0.0621 | seed: first-order fused swap network | x1.4142 |
| 3780 | 0.0204 | second-order fused swap network | x2.8284 |
| 10800 | 0.0133 | fourth-order fused swap network | x8 |

**instance_4_d_5** (N = 10, cap = 1620 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 270 | 0.6720 | seed: first-order fused swap network | x0.25 |
| 540 | 0.2713 | second-order fused swap network | x0.3536 |
| 540 | 0.2713 | second-order fused swap network | x0.5 |
| 810 | 0.1790 | seed: first-order fused swap network | x0.5 |
| 1080 | 0.1366 | seed: first-order fused swap network | x0.7071 |
| 1620 | 0.1036 | seed: first-order fused swap network | x1 |
| 2160 | 0.0494 | seed: first-order fused swap network | x1.4142 |
| 6480 | 0.0337 | second-order fused swap network | x4 |

**instance_63_d_5** (N = 10, cap = 4320 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1080 | 0.3849 | second-order fused swap network | x0.25 |
| 1080 | 0.3849 | second-order fused swap network | x0.3536 |
| 1350 | 0.2969 | seed: first-order fused swap network | x0.3536 |
| 2160 | 0.1071 | second-order fused swap network | x0.5 |
| 2700 | 0.0381 | second-order fused swap network | x0.7071 |
| 4320 | 0.0176 | second-order fused swap network | x1 |

**instance_48_d_5** (N = 11, cap = 2640 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 660 | 0.5677 | second-order fused swap network | x0.25 |
| 660 | 0.5677 | second-order fused swap network | x0.3536 |
| 1320 | 0.4519 | seed: first-order fused swap network | x0.5 |
| 1650 | 0.4015 | seed: first-order fused swap network | x0.7071 |
| 2640 | 0.0500 | seed: first-order fused swap network | x1 |
| 3630 | 0.0459 | seed: first-order fused swap network | x1.4142 |
| 5280 | 0.0316 | second-order fused swap network | x2 |
| 13200 | 0.0280 | fourth-order fused swap network | x5.6569 |

**instance_93_d_5** (N = 11, cap = 2640 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 660 | 0.4538 | second-order fused swap network | x0.25 |
| 660 | 0.4538 | second-order fused swap network | x0.3536 |
| 1320 | 0.2990 | seed: first-order fused swap network | x0.5 |
| 1650 | 0.2103 | seed: first-order fused swap network | x0.7071 |
| 2640 | 0.1209 | seed: first-order fused swap network | x1 |
| 3300 | 0.1063 | second-order fused swap network | x1.4142 |
| 3630 | 0.0611 | seed: first-order fused swap network | x1.4142 |
| 5280 | 0.0189 | seed: first-order fused swap network | x2 |

**instance_26_d_7** (N = 11, cap = 5280 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1320 | 0.2460 | second-order fused swap network | x0.25 |
| 1320 | 0.2460 | second-order fused swap network | x0.3536 |
| 2640 | 0.2000 | seed: first-order fused swap network | x0.5 |
| 3300 | 0.0826 | fourth-order fused swap network | x0.7071 |
| 3300 | 0.0826 | fourth-order fused swap network | x1 |
| 3630 | 0.0698 | seed: first-order fused swap network | x0.7071 |
| 5280 | 0.0372 | second-order fused swap network | x1 |
| 19800 | 0.0106 | fourth-order fused swap network | x4 |

**instance_179_d_5** (N = 11, cap = 5280 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1320 | 0.4682 | second-order fused swap network | x0.25 |
| 1320 | 0.4682 | second-order fused swap network | x0.3536 |
| 1650 | 0.4043 | seed: first-order fused swap network | x0.3536 |
| 2640 | 0.3521 | seed: first-order fused swap network | x0.5 |
| 3300 | 0.0830 | fourth-order fused swap network | x0.7071 |
| 3300 | 0.0830 | fourth-order fused swap network | x1 |
| 5280 | 0.0465 | second-order fused swap network | x1 |
| 13200 | 0.0369 | fourth-order fused swap network | x2.8284 |

**instance_132_d_9** (N = 12, cap = 1188 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 396 | 0.6346 | seed: first-order fused swap network | x0.3536 |
| 396 | 0.6346 | seed: first-order fused swap network | x0.5 |
| 792 | 0.1154 | second-order fused swap network | x0.7071 |
| 792 | 0.1154 | second-order fused swap network | x1 |
| 1584 | 0.0478 | seed: first-order fused swap network | x1.4142 |
| 6336 | 0.0157 | second-order fused swap network | x5.6569 |

**instance_154_d_5** (N = 12, cap = 2376 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 396 | 0.6034 | seed: first-order fused swap network | x0.25 |
| 792 | 0.2833 | second-order fused swap network | x0.3536 |
| 792 | 0.2833 | second-order fused swap network | x0.5 |
| 1188 | 0.2831 | seed: first-order fused swap network | x0.5 |
| 1584 | 0.1531 | seed: first-order fused swap network | x0.7071 |
| 2376 | 0.0699 | seed: first-order fused swap network | x1 |
| 3168 | 0.0387 | seed: first-order fused swap network | x1.4142 |
| 11880 | 0.0372 | fourth-order fused swap network | x5.6569 |
| 12672 | 0.0330 | second-order fused swap network | x5.6569 |

**instance_42_d_6** (N = 12, cap = 3168 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 792 | 0.4800 | second-order fused swap network | x0.25 |
| 792 | 0.4800 | second-order fused swap network | x0.3536 |
| 1584 | 0.3682 | seed: first-order fused swap network | x0.5 |
| 3168 | 0.1075 | seed: first-order fused swap network | x1 |
| 4356 | 0.0642 | seed: first-order fused swap network | x1.4142 |
| 6336 | 0.0481 | seed: first-order fused swap network | x2 |
| 12672 | 0.0349 | second-order fused swap network | x4 |
| 23760 | 0.0190 | fourth-order fused swap network | x8 |

**instance_123_d_5** (N = 12, cap = 6336 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1584 | 0.1617 | second-order fused swap network | x0.25 |
| 1584 | 0.1617 | second-order fused swap network | x0.3536 |
| 3960 | 0.1149 | second-order fused swap network | x0.7071 |
| 6336 | 0.0584 | seed: first-order fused swap network | x1 |
| 8712 | 0.0247 | seed: first-order fused swap network | x1.4142 |

**instance_74_d_9** (N = 12, cap = 6336 CZ)

| CZ | RMSE | entry | rung |
|---:|---:|---|---|
| 1584 | 0.2463 | seed: first-order fused swap network | x0.25 |
| 3168 | 0.1319 | seed: first-order fused swap network | x0.5 |
| 6336 | 0.0195 | second-order fused swap network | x1 |

## 4. Validation on unseen instances

Each kept entry is re-scored, next to the seed, on a fresh draw of four instances from the validation pool (tier-0 instances never on the board; `scripts/validation.py`). `holds` means it beats the seed there and its cost ratio is within 25 % of its development-set ratio. Baselines are exempt: they are the reference, not candidates.

| entry | generation | draw | dev ratio | validation ratio | holds |
|---|---:|---|---:|---:|---|
| (none yet) | | | | | |

## 5. Hard set (unranked)

Tier-0 instances with long tmax and a weakly coupled carbon, where the seed needs 70-300 steps for 10 % error. Nobody optimises on them; cost at the target and error at x1 are reported for every entry that has been run there, as a second generalisation axis. Empty until calibrated.

### Cost at the target error (RMSE <= 0.05) -- hard set, not ranked

CZ count of the cheapest measured point under the target, per instance; `ratio` is the geometric mean over instances of (entry CZ / seed CZ), lower is better. `miss` = the target was not met at any rung.

| rank | entry | ratio to seed | met | mean CZ | instance_148_d_8 | instance_167_d_7 | instance_175_d_8 | instance_68_d_13 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | second-order fused swap network | 0.916 | 4/4 | 63570 | 24300 (x0.3536) | 138240 (x2) | 84480 (x2) | 7260 (x0.7071) |
| 2 | seed: first-order fused swap network | 1.000 | 4/4 | 57495 | 69120 (x1) | 69120 (x1) | 84480 (x2) | 7260 (x0.7071) |
| 3 | fourth-order fused swap network | 2.175 | 4/4 | 132750 | 67500 (x1) | 97200 (x1.4142) | 336600 (x8) | 29700 (x2.8284) |
