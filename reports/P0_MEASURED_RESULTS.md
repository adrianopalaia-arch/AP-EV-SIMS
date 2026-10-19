# P0 measured forecasting delivery

Generated UTC: 2026-10-17T02:10:39.996006+00:00.

Completed execution, with real data. All CORE and cash recommendations remain disabled. Historical diagnostics are reconstructed and previously inspected; no prospective betting edge is established.

| Sport | Before player-game observations | After | Athletes after | Seasons after |
|---|---:|---:|---:|---|
| NFL | 13,842 | 25,657 | 1085 | 2022, 2023, 2024, 2025, 2026 |
| NBA | 79,632 | 131,618 | 1032 | 2022, 2023, 2024, 2025, 2026 |
| NHL | 153,778 | 253,759 | 1679 | 2022, 2023, 2024, 2025, 2026, 2027 |
| MLB | 8,766 | 27,090 | 131 | 2023, 2024, 2025, 2026 |

CFB completed FBS-vs-FBS games: 2,600 → 3,334. Model code/version preserved.

## Identical-sample before / after MAE

| Sport / market | Paired outcomes | Previous model | Challenger | Current benchmark gate |
|---|---:|---:|---:|---|
| NFL passing_yards | 733 | 68.2564 | 67.2461 | RESEARCH_BENCHMARK_ADVANTAGE |
| NFL receiving_yards | 6,152 | 16.7496 | 16.2456 | RESEARCH_BENCHMARK_ADVANTAGE |
| NFL receptions | 6,152 | 1.2836 | 1.2527 | RESEARCH_BENCHMARK_ADVANTAGE |
| NFL rushing_attempts | 6,152 | 1.3720 | 1.1128 | FAILED_DISTRIBUTION_BASELINE |
| NFL rushing_yards | 6,152 | 7.4874 | 6.4778 | FAILED_DISTRIBUTION_BASELINE |
| NBA assists | 51,938 | 1.3797 | 1.3598 | RESEARCH_BENCHMARK_ADVANTAGE |
| NBA points | 51,938 | 4.7637 | 4.6681 | RESEARCH_BENCHMARK_ADVANTAGE |
| NBA rebounds | 51,938 | 1.9531 | 1.9274 | RESEARCH_BENCHMARK_ADVANTAGE |
| NBA threes | 51,938 | 0.9159 | 0.9111 | FAILED_SIMPLE_BASELINE |
| NHL goalie_saves | 5,597 | 5.9885 | 5.9077 | RESEARCH_BENCHMARK_ADVANTAGE |
| NHL shots_on_goal | 96,525 | 1.0375 | 1.0356 | RESEARCH_BENCHMARK_ADVANTAGE |
| MLB hits_allowed | 540 | 1.1717 | 1.1322 | RESEARCH_BENCHMARK_ADVANTAGE |
| MLB hitter_hits | 5,410 | 0.7096 | 0.6965 | RESEARCH_BENCHMARK_ADVANTAGE |
| MLB pitcher_outs | 540 | 2.1340 | 1.9053 | BENCHMARK_ADVANTAGE_INCONCLUSIVE |
| MLB pitcher_strikeouts | 540 | 1.2913 | 1.2774 | RESEARCH_BENCHMARK_ADVANTAGE |
| MLB total_bases | 5,410 | 1.2646 | 1.2552 | RESEARCH_BENCHMARK_ADVANTAGE |

## Current chronological evaluation versus recent-average baseline

| Sport / market | Train examples | Eval outcomes | MAE / baseline | RMSE / baseline | Brier / baseline | Outcome NLL / baseline |
|---|---:|---:|---|---|---|---|
| NFL passing_yards | 2,237 | 768 | 68.0630 / 69.8621 | 85.0640 / 89.2582 | 0.2454 / 0.2496 | 6.1942 / 6.2703 |
| NFL receiving_yards | 18,684 | 6,307 | 16.0985 / 16.4268 | 23.1948 / 23.7158 | 0.2275 / 0.2302 | 4.3403 / 4.3483 |
| NFL receptions | 18,684 | 6,307 | 1.2463 / 1.2656 | 1.6924 / 1.7324 | 0.2280 / 0.2308 | 1.6814 / 1.6993 |
| NFL rushing_attempts | 18,684 | 6,307 | 1.1091 / 1.1414 | 2.4957 / 2.6128 | 0.1379 / 0.1405 | 1.2304 / 1.2452 |
| NFL rushing_yards | 18,684 | 6,307 | 6.4148 / 6.5554 | 15.4793 / 15.9101 | 0.1643 / 0.1527 | 2.6063 / 2.5967 |
| NBA assists | 126,582 | 52,029 | 1.3600 / 1.3864 | 1.8458 / 1.8935 | 0.2346 / 0.2404 | 1.7951 / 1.8176 |
| NBA points | 126,582 | 52,029 | 4.6669 / 4.7593 | 6.1139 / 6.2605 | 0.2421 / 0.2482 | 3.0809 / 3.1139 |
| NBA rebounds | 126,582 | 52,029 | 1.9272 / 1.9662 | 2.5335 / 2.5982 | 0.2385 / 0.2443 | 2.2094 / 2.2349 |
| NBA threes | 126,582 | 52,029 | 0.9105 / 0.9099 | 1.2545 / 1.2829 | 0.2163 / 0.2181 | 1.3801 / 1.3933 |
| NHL goalie_saves | 13,380 | 5,622 | 5.9078 / 6.0861 | 7.6407 / 7.8379 | 0.2379 / 0.2502 | 3.4566 / 3.5013 |
| NHL shots_on_goal | 232,366 | 96,796 | 1.0351 / 1.0587 | 1.3355 / 1.3716 | 0.2308 / 0.2376 | 1.5616 / 1.5839 |
| MLB hits_allowed | 3,169 | 1,515 | 1.0982 / 1.1383 | 1.4806 / 1.5366 | 0.2336 / 0.2412 | 1.5846 / 1.5994 |
| MLB hitter_hits | 23,206 | 12,183 | 0.6861 / 0.7177 | 0.8577 / 0.8943 | 0.2274 / 0.2322 | 1.1678 / 1.1838 |
| MLB pitcher_outs | 3,169 | 1,515 | 1.5614 / 1.5952 | 2.4724 / 2.5830 | 0.2237 / 0.2279 | 1.9973 / 2.0176 |
| MLB pitcher_strikeouts | 3,169 | 1,515 | 1.0742 / 1.1051 | 1.4803 / 1.5097 | 0.2289 / 0.2356 | 1.5782 / 1.5948 |
| MLB total_bases | 23,206 | 12,183 | 1.2819 / 1.3241 | 1.6965 / 1.7663 | 0.2214 / 0.2282 | 1.5750 / 1.6354 |

Brier/log loss above use a fixed pregame-history diagnostic line, not a bookmaker line. See JSON for CRPS, coverage, per-season metrics and week-block uncertainty. NFL history/model ablation separates data expansion from algorithm changes.

New challenger forecasts: 333. Marginal simulations executed: 393; total draws: 15,720,000; sampling-convergence failures: 0.
Historical endpoint HTTP 401; qualified historical price backtest rows: 0. Real prospective paired-offer snapshots: 648.

## Remaining blockers

- Historical outcome revisions captured now are reconstruction, not timestamp-authentic historical features.
- Existing evaluation seasons were already inspected; all comparisons remain exploratory and multiply tested.
- DNP/role selection, traded-player histories, conditional-on-appearance modeling and sampled MLB cohorts limit generalization.
- Probability scores use fixed prior-mean diagnostic lines, not historical sportsbook prices.
- Intervals and Monte Carlo convergence are not uncertainty-qualified EV or proof of profitability.
- No shared-game joint simulation, verified book settlement terms or prospective price-relative performance yet.
- NHL unique-event offset now has source-bound research evidence with the earlier deadline retained; MLB postponement/start mismatch remains blocked. See P0_FRESHNESS_DELIVERY.md.
- Official starters/goalies/roles and participation conditions are not fully verified. Quotes expire after 180 seconds.
- Historical odds entitlement still returns 401. Prospective outcomes must elapse before calibration, CLV and ROI can be measured.
- Full league-wide MLB coverage, opponent context, verified historical injuries, role-transition models, calibrated uncertainty and shared-game joint simulations remain unfinished.

## Reproduce

```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -m ap_evsims.history_expansion --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_challenger --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.challenger_delivery --root . --sport all --draws 20000
& '.\.venv\Scripts\python.exe' -m ap_evsims.p0_results --root . --nfl-control
```
