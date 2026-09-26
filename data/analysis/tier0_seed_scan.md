# Tier-0 seed scan (2026-09-26)

Plain seed (first-order fused swap network, time-of-flight layout) scored exactly at 1, 2, 4, 8, 16 steps
on every tier-0 instance, stopping at the first step count with mean |error| <= 0.10 (the cap anchor,
CONTEXT.md §8). Values: (mean_abs, rmse, wall seconds with 4 workers; the timings mix the old and the
current engine). Source: `data/analysis/tier0_seed_scan.json`, produced by a scratch script equivalent to
`scripts/calibrate_budgets.py` with the step ladder capped at 16.

| N | instance | tmax | steps to 10 % | mean / rms there | 1-step mean err |
|---:|---|---:|---:|---|---:|
| 10 | instance_35_d_5 | 0.50 | 8 | 0.058 / 0.066 | 0.40 |
| 10 | instance_4_d_5 | 0.43 | 8 | 0.044 / 0.049 | 0.58 |
| 10 | instance_63_d_5 | 0.43 | 16 | 0.040 / 0.046 | 0.59 |
| 10 | instance_148_d_8 | 9.89 | >16 | — | 0.63 |
| 10 | instance_167_d_7 | 3.81 | >16 | — | 0.64 |
| 11 | instance_145_d_5 | 0.58 | 8 | 0.040 / 0.056 | 0.57 |
| 11 | instance_190_d_7 | 1.13 | 8 | 0.089 / 0.105 | 0.58 |
| 11 | instance_38_d_6 | 3.75 | 8 | 0.093 / 0.121 | 0.14 |
| 11 | instance_42_d_5 | 0.83 | 8 | 0.071 / 0.080 | 0.48 |
| 11 | instance_48_d_5 | 0.48 | 8 | 0.042 / 0.050 | 0.46 |
| 11 | instance_87_d_5 | 0.71 | 8 | 0.070 / 0.080 | 0.49 |
| 11 | instance_93_d_5 | 0.69 | 8 | 0.093 / 0.121 | 0.56 |
| 11 | instance_96_d_5 | 0.89 | 8 | 0.060 / 0.068 | 0.52 |
| 11 | instance_137_d_5 | 0.75 | 16 | 0.013 / 0.018 | 0.43 |
| 11 | instance_179_d_5 | 0.65 | 16 | 0.034 / 0.046 | 0.56 |
| 11 | instance_26_d_7 | 0.56 | 16 | 0.021 / 0.037 | 0.55 |
| 11 | instance_75_d_6 | 0.68 | 16 | 0.017 / 0.021 | 0.47 |
| 11 | instance_175_d_8 | 7.02 | >16 | — | 0.63 |
| 11 | instance_68_d_13 | 3.23 | >16 | — | 0.45 |
| 12 | instance_120_d_5 | 0.71 | 4 | 0.082 / 0.114 | 0.41 |
| 12 | instance_132_d_9 | 0.81 | 4 | 0.042 / 0.048 | 0.54 |
| 12 | instance_176_d_5 | 1.01 | 4 | 0.096 / 0.123 | 0.46 |
| 12 | instance_187_d_5 | 0.50 | 4 | 0.042 / 0.047 | 0.44 |
| 12 | instance_24_d_5 | 0.58 | 4 | 0.099 / 0.155 | 0.52 |
| 12 | instance_31_d_5 | 0.46 | 4 | 0.074 / 0.092 | 0.53 |
| 12 | instance_88_d_7 | 1.64 | 4 | 0.064 / 0.074 | 0.51 |
| 12 | instance_122_d_8 | 0.67 | 8 | 0.057 / 0.067 | 0.55 |
| 12 | instance_136_d_6 | 0.74 | 8 | 0.035 / 0.041 | 0.50 |
| 12 | instance_154_d_5 | 0.52 | 8 | 0.033 / 0.039 | 0.51 |
| 12 | instance_185_d_7 | 0.78 | 8 | 0.013 / 0.015 | 0.51 |
| 12 | instance_192_d_8 | 0.68 | 8 | 0.027 / 0.038 | 0.44 |
| 12 | instance_42_d_6 | 0.91 | 8 | 0.089 / 0.107 | 0.47 |
| 12 | instance_53_d_5 | 0.77 | 8 | 0.023 / 0.033 | 0.45 |
| 12 | instance_68_d_5 | 1.39 | 8 | 0.062 / 0.080 | 0.29 |
| 12 | instance_8_d_6 | 0.58 | 8 | 0.056 / 0.067 | 0.54 |
| 12 | instance_101_d_8 | 0.70 | 16 | 0.026 / 0.032 | 0.54 |
| 12 | instance_123_d_5 | 1.14 | 16 | 0.049 / 0.058 | 0.49 |
| 12 | instance_124_d_5 | 1.00 | 16 | 0.070 / 0.078 | 0.53 |
| 12 | instance_139_d_5 | 0.48 | 16 | 0.057 / 0.070 | 0.44 |
| 12 | instance_147_d_6 | 0.81 | 16 | 0.044 / 0.050 | 0.34 |
| 12 | instance_179_d_7 | 1.40 | 16 | 0.028 / 0.032 | 0.48 |
| 12 | instance_74_d_9 | 1.55 | 16 | 0.085 / 0.094 | 0.51 |
| 12 | instance_179_d_9 | 19.56 | >16 | — | 0.31 |
| 12 | instance_27_d_14 | 1.77 | >16 | — | 0.37 |
| 12 | instance_57_d_14 | 4.20 | >16 | — | 0.66 |
| 12 | instance_59_d_8 | 5.18 | >16 | — | 0.61 |
