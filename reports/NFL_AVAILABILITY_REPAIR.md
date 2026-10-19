# NFL availability forecast repair

Executed: 2026-10-19T04:37:26.104945+00:00. Policy: nfl-availability-policy-v1.

This is an offline replay of archived pregame inputs, performed after the events. It is not a new prospective prediction or proof of improved accuracy.

The game freeze now consumes availability before publication. The player forecast path attaches a bound availability review and an append-only revision. Current roster status, event injury status, starter confirmation and projected workload are separate. A reported-out player has no eligible prop probability/EV; an unsupported QB change retains the baseline and blocks approval.

Reviewed 12 games, 1494 prop forecasts and 1312 actual archived side comparisons. Suppressed 8 previously displayed conditional EV values with unsupported participation/role evidence. All 2238 checked original forecast files are byte-identical. No odds API requests, new simulations or new prospective forecasts.

Availability states: {"QUESTIONABLE": 65, "REPORTED_OUT": 75, "UNKNOWN": 1354}

| Existing numerical benchmark | OOS games | Win accuracy | MAE | RMSE | Brier | Log loss | Calibration ECE |
|---|---:|---:|---:|---:|---:|---:|---:|
| ridge | 1951 | 0.6250 | 10.4191 | 13.4062 | 0.230669 | 0.653371 | 0.037423 |
| home_field | 1951 | 0.5319 | 11.0790 | 14.2776 | 0.249606 | 0.692373 | 0.012175 |
| elo | 1951 | 0.6152 | 10.4112 | 13.4214 | 0.229924 | 0.651758 | 0.068739 |

These are the previously inspected, chronologically evaluated samples. No coefficients changed. They are not an untouched test of the new eligibility policy. Ridge still fails to beat Elo consistently. Calibration bins in the JSON are descriptive; no calibrated probabilities are fitted.

Historical availability snapshots preceding an existing OOS fold: 0. Injury-adjusted evaluation N=0; untouched N=0; matched historical execution-price N=0. Cover accuracy, CLV and ROI remain null rather than invented.

## Real archived examples

| Player / market | Baseline mean | Baseline workload | Evidence state | Eligible workload | Decision |
|---|---:|---:|---|---|---|
| Lamar Jackson / passing_yards | 209.622 | 26.829 | REPORTED_OUT | unavailable | PASS |
| Quinshon Judkins / receiving_yards | 19.658 | 3.207 | QUESTIONABLE | unavailable | PASS |
| Dylan Sampson / receiving_yards | 16.206 | 2.369 | REPORTED_OUT | unavailable | PASS |
| Quinshon Judkins / receptions | 2.701 | 3.643 | QUESTIONABLE | unavailable | PASS |
| Dylan Sampson / receptions | 1.777 | 2.376 | REPORTED_OUT | unavailable | PASS |
| Quinshon Judkins / rushing_attempts | 14.874 | 14.874 | QUESTIONABLE | unavailable | PASS |

Baseline numerical values are retained for audit, not relabeled injury-adjusted. Source timestamps/hashes and original forecast/comparison hashes are in the JSON.

## Reproduce

`python -m ap_evsims.nfl_news_replay --root .` (offline; requires existing local immutable data).

## Remaining limitations

- No new injury-adjusted numerical model; original means and distributions remain conditional historical baselines
- ESPN reports are secondary; no official active/starter or workload feed is implemented
- No replacement-QB model or supported scenario probabilities; NEWS_ADJUSTMENT_UNAVAILABLE
- Old/stale reports and roster active status cannot prove current gameday participation
- All October 18 games have begun; this replay cannot be counted as newly frozen prospective evidence
- No untouched injury-adjusted evaluation cohort or authenticated historical execution-price cohort
