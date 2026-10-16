# Prospective market research

Generated UTC: 2026-10-16T15:02:00.207814+00:00.

Early watchlist entries are conditional research estimates, not locked plays. Calibration and prospective price-relative performance are not established. All betting decisions are PASS.
244 side/line/book comparisons; 8 distinct positive conditional-EV research entries; 0 currently fresh ranked prices.
Both sides are evaluated. Integer lines preserve push mass. No p_low or calibrated probability is manufactured.
Original forecasts are immutable. Each price/news update is separately frozen before kickoff and links to the prior comparison.

| Sport | Comparisons | Paired quotes | Reported injuries | Confirmed roles |
|---|---:|---:|---:|---:|
| NFL | 112 | 116 | 27 | 0 |
| NBA | 32 | 53 | 1 | 0 |
| NHL | 56 | 45 | 0 | 0 |
| MLB | 44 | 27 | 0 | 0 |

NFL correction: models that lost to their predefined recent-average benchmark are rejected from rankings. New baseline-reference forecasts form a separate prospective cohort; this is not a claim of a newly validated NFL model.
NBA rebounds/assists and NHL shots/saves retain historical benchmark advantages. MLB hitter-hit/total-bases evidence is recomputed from the current expanded cohort; inspect benchmark_reports for counts and confidence intervals. Current-roster survivor selection, multiple comparisons, historical revisions and appearance-only selection remain limitations.
NBA/NFL injury sources are ESPN aggregations, not full official clearance. NHL league goalie leaders are not starter confirmations. MLB requires a full official batting order to mark a listed lineup. No projected minutes or ice time is labeled confirmed.
NHL/MLB bookmaker start conflicts block probability/EV association with those prices. Stale prices remain historical diagnostics and cannot authorize execution.
CFB score-model code and forecasts are preserved. See execution reports for its separate model evidence.

Machine-readable files: early_watchlist.json, prospective_price_comparisons.json, market_research_passes.json, market_research_status.json, nfl_baseline_reference.json and per-sport availability files.

## Early numerical watchlist

All prices below are archived, not current executable quotes. Probabilities are raw model estimates, and EV assumes participation, projected workload and standard settlement. Large numerical EV can reflect model error; no prospective betting advantage has been demonstrated. The $22 unit is a reference only.

| Player / market | Side / line | Book / odds | Raw win probability | Conditional EV | 10th / 50th / 90th outcome percentiles | Quote UTC |
|---|---|---|---:|---:|---|---|
| Ausar Thompson / rebounds | Under 6.5 | draftkings -106 | 67.3% | +30.8% | [3, 5, 9] | 2026-10-16T05:18:50Z |
| Jalen Duren / assists | Over 1.5 | draftkings -179 | 81.7% | +27.3% | [1, 3, 6] | 2026-10-16T05:18:50Z |
| Cade Cunningham / assists | Under 9.5 | fanduel -138 | 68.6% | +18.3% | [7, 9, 12] | 2026-10-16T05:19:15Z |
| Jayson Tatum / assists | Under 5.5 | draftkings +113 | 54.0% | +15.0% | [4, 5, 8] | 2026-10-16T05:18:50Z |
| Ausar Thompson / assists | Over 3.5 | draftkings +121 | 51.1% | +12.9% | [2, 4, 7] | 2026-10-16T05:18:50Z |
| Cade Cunningham / rebounds | Under 5.5 | draftkings -124 | 62.3% | +12.5% | [2, 5, 9] | 2026-10-16T05:18:50Z |
| Derrick White / rebounds | Over 3.5 | draftkings -102 | 56.5% | +11.9% | [2, 4, 8] | 2026-10-16T05:18:50Z |
| Jalen Duren / rebounds | Over 9.5 | draftkings -128 | 59.0% | +5.1% | [8, 10, 14] | 2026-10-16T05:18:50Z |

MLB expanded-cohort results: hits MAE 0.7096 versus 0.7296; RMSE 0.8803 versus 0.9056. Total-bases MAE 1.2646 versus 1.2947; RMSE 1.6787 versus 1.7247. Each has 5,410 chronological evaluation observations, with 55 weekly bootstrap blocks. These are conditional-on-appearance historical diagnostics, subject to current-roster selection and provider revisions.

Source commands:
```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_prices --root . --priority
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_market_research --root .
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_settlement --root . --sport all
```


Checkpoint delivery 2026-10-16T15:09:08.948370+00:00: 316 tests passed, 0 failed. Safe source, tests and results saved in commit `bb0f5d98dc44bd0c1b5c721985ad188de7d8595e`. Push failed: `GITHUB_AUTHENTICATION_UNAVAILABLE`. Remote branch verified at `6db215e00b5d42b8d7f94b556985a97f44104d75`; new results are local only. No force push or reset was used.
