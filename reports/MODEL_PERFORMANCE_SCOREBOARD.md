# Model performance scoreboard

Generated UTC: 2026-10-18T03:23:38.015034+00:00. Actual frozen prospective outcomes; no model promoted.

| Sport / market / model | Settled forecasts | Distinct games | MAE | Frozen simple baseline MAE | RMSE |
|---|---:|---:|---:|---:|---:|
| CFB / game_margin / cfb-score-ridge-v1 | 43 | 43 | 11.7073 | 12.4357 | 13.4953 |
| CFB / game_margin / cfb-score-ridge-v1.1 | 43 | 43 | 11.7073 | 12.4357 | 13.4953 |
| NHL / goalie_saves / causal-opportunity-ridge-v2 | 2 | 1 | 3.5543 | 4.1000 | 3.5580 |
| NHL / goalie_saves / opportunity-partial-pool-v1 | 2 | 1 | 6.1998 | 6.8000 | 6.3518 |
| NHL / shots_on_goal / causal-opportunity-ridge-v2 | 35 | 1 | 0.9855 | 0.9171 | 1.2449 |
| NHL / shots_on_goal / opportunity-partial-pool-v1 | 36 | 1 | 0.9305 | 0.9491 | 1.3912 |

Model versions are separate cohorts. CFB versions can score the same game; player outcomes within a game are correlated. Do not sum these rows as independent games.

| Priced model | N (Over only) | Distinct games | Model Brier / log loss | Entry-book Brier / log loss | Independent consensus N |
|---|---:|---:|---|---|---:|
| causal-opportunity-ridge-v2 | 8 | 1 | 0.1722 / 0.5283 | 0.2158 / 0.6237 | 0 |

The initial forecasts were frozen before play, but the current reporting/selection policy was registered after those games. These results are exploratory, not an untouched confirmatory holdout.
The entry sportsbook is a descriptive baseline, not independent consensus. Calibration-band counts are in prospective_settlements.json. No calibrated probability or p_low is fitted from these small samples.
Qualified CLV, hypothetical ROI, return uncertainty and drawdown remain unavailable: pre-entry rule evidence and authentic near-start closing captures are missing. Unknown DNP/void outcomes are not zero-valued losses.

Historical training/evaluation counts are retained in each challenger_status.json and P0_MEASURED_RESULTS.md. No training run or extra simulation draws occurred in this cycle.

Separate future calibration, selection and untouched holdout windows are fixed by the immutable evidence policy. Existing inspected seasons remain exploratory. Power and multiplicity requirements remain unmet.
