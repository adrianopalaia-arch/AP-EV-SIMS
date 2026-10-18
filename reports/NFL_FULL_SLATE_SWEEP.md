# NFL full-slate sweep

Sunday 2026-10-18; captured 2026-10-18T04:05:30.538307+00:00. All selections PASS; CORE disabled.

Schedule: nflverse cross-checked against ESPN, independently of odds. Both are secondary sources; no direct NFL league feed authority is claimed.

Win percentages below are raw research probabilities conditional on no tie; separate tie mass is retained in JSON. They are not betting confidence.

| Game | Kickoff UTC | Away / home win | Home margin | Props | Main / prop prices | Fresh / quotes | Availability confirmed / roster |
|---|---|---|---:|---:|---|---:|---:|
| Houston Texans @ Jacksonville Jaguars | 2026-10-18T13:30:00+00:00 | 47.0% / 53.0% | 0.99 | 124 | FETCHED / SCANNED | 0 / 296 | 0 / 121 |
| Baltimore Ravens @ Cleveland Browns | 2026-10-18T17:00:00+00:00 | 60.0% / 40.0% | -3.31 | 130 | FETCHED / SCANNED | 0 / 228 | 0 / 118 |
| Carolina Panthers @ Philadelphia Eagles | 2026-10-18T17:00:00+00:00 | 40.4% / 59.6% | 3.15 | 153 | FETCHED / SCANNED | 0 / 210 | 0 / 123 |
| Chicago Bears @ Atlanta Falcons | 2026-10-18T17:00:00+00:00 | 50.4% / 49.6% | -0.14 | 106 | FETCHED / SCANNED | 0 / 248 | 0 / 121 |
| New Orleans Saints @ New York Giants | 2026-10-18T17:00:00+00:00 | 44.2% / 55.8% | 1.89 | 131 | FETCHED / SCANNED | 0 / 254 | 0 / 128 |
| New York Jets @ New England Patriots | 2026-10-18T17:00:00+00:00 | 30.0% / 70.0% | 6.81 | 120 | FETCHED / SCANNED | 0 / 242 | 0 / 123 |
| Pittsburgh Steelers @ Tampa Bay Buccaneers | 2026-10-18T17:00:00+00:00 | 42.8% / 57.2% | 2.36 | 105 | FETCHED / SCANNED | 0 / 224 | 0 / 114 |
| Tennessee Titans @ Indianapolis Colts | 2026-10-18T17:00:00+00:00 | 30.7% / 69.3% | 6.57 | 129 | FETCHED / SCANNED | 0 / 238 | 0 / 117 |
| Arizona Cardinals @ Los Angeles Rams | 2026-10-18T20:05:00+00:00 | 30.5% / 69.5% | 6.65 | 135 | FETCHED / SCANNED | 0 / 252 | 0 / 114 |
| Buffalo Bills @ Las Vegas Raiders | 2026-10-18T20:25:00+00:00 | 62.6% / 37.4% | -4.17 | 140 | FETCHED / SCANNED | 0 / 206 | 0 / 122 |
| Los Angeles Chargers @ Kansas City Chiefs | 2026-10-18T20:25:00+00:00 | 32.1% / 67.9% | 6.05 | 97 | FETCHED / SCANNED | 0 / 290 | 0 / 116 |
| Dallas Cowboys @ Green Bay Packers | 2026-10-19T00:20:00+00:00 | 40.5% / 59.5% | 3.13 | 124 | FETCHED / SCANNED | 0 / 258 | 0 / 123 |

## Chronological game-model evaluation

| Model | Games | Margin MAE | RMSE | Brier | Log loss |
|---|---:|---:|---:|---:|---:|
| ridge | 1951 | 10.4191 | 13.4062 | 0.230669 | 0.653371 |
| home_field | 1951 | 11.0790 | 14.2776 | 0.249606 | 0.692373 |
| elo | 1951 | 10.4112 | 13.4214 | 0.229924 | 0.651758 |

Regular-season rolling weekly folds; 48-hour outcome embargo. Fixed ridge policy; no odds, target-game QB, weather or final season stats enter features. Historical revisions are reconstructed, not proven as published at each historical kickoff.

## Existing player challengers

| Market | Training | OOS | MAE / recent-mean baseline | Admission |
|---|---:|---:|---|---|
| passing_yards | 2237 | 768 | 68.063 / 69.862 | RESEARCH_BENCHMARK_ADVANTAGE |
| receiving_yards | 18684 | 6307 | 16.099 / 16.427 | RESEARCH_BENCHMARK_ADVANTAGE |
| receptions | 18684 | 6307 | 1.246 / 1.266 | RESEARCH_BENCHMARK_ADVANTAGE |
| rushing_attempts | 18684 | 6307 | 1.109 / 1.141 | FAILED_DISTRIBUTION_BASELINE |
| rushing_yards | 18684 | 6307 | 6.415 / 6.555 | FAILED_DISTRIBUTION_BASELINE |

## Coverage and quota

Before: {"frozen_prop_records": 832, "nfl_scheduled_games_with_forecasts": 1}
After: {"game_forecasts": 12, "prop_forecasts": 1494, "main_market_games": 12, "prop_scanned_games": 12, "all_frozen_prop_records": 2202, "new_prop_records": 1370, "new_prop_records_this_execution": 0, "price_comparisons": 1600, "fresh_comparisons": 0}
Quota: {"credits_used": 82, "credits_used_this_sweep": 63, "daily_cap": 96, "remaining": 280, "reserved_balance": 50}

Quotes expire after 180 seconds from the provider timestamp. A successful request does not reset quote age. Each game retains all requested, returned and budget-deferred markets in nfl_sweep_status.json.

## Research rankings

No fresh candidate meets the research ranking gates. This does not remove stale or rejected comparisons from the audit output.

## Remaining blockers

- No prospective NFL game-model calibration or price-relative validation
- Game ridge does not beat Elo on every metric
- Roster membership and reported injuries do not confirm participation or workload
- Historical outcome revisions are reconstructed; historical book prices remain unverified
- NFL TD and total outcome models unavailable; totals shown as price evidence only
- Book settlement rules unverified; conditional EV cannot authorize cash

Rejections: {"INSUFFICIENT_PRIOR_PLAYER_HISTORY": 5706, "MISSING_PROP_COUNTERPART": 12, "NO_MATCHED_TRAINED_PLAYER_FORECAST": 123}

Reproduce: `python -m ap_evsims.nfl_sweep --date 2026-10-18 --collect --daily-cap 96 --reserve 50`. This explicitly raises the one-run daily ceiling; the default stays 24. Actual header costs and the shared ledger control requests. No cash is committed.

## Delivery verification

404 full-suite tests passed; both supplied acceptance commands passed on actual outputs. The supplied verifier was copied unchanged. All original 389 forecasts and 18 protected Phase 1 files remain intact. No additional Monte Carlo draws.

The first publication had 1,600 fresh comparisons; the final archived recalculation correctly rejects expired prices. It spends no new odds credits and does not relabel archived prices as fresh.

NFL game settlement integration, prospective calibration, verified participation/workload, authentic closing captures, and sportsbook settlement-rule verification remain unfinished. The default NFL challenger and refresh paths now process the entire canonical slate; an unscoped single-event NFL input is rejected. The default command was executed on all 12 games with 1,494 forecasts, 1,312 prop comparisons, zero new forecasts, zero simulation draws and no new sportsbook requests.

## Git delivery

Implementation commit: `144405405150ee3254e260610369cea6b0532e36`. Verified remote: `c1f06b6611ad85badc02b3ab0672bae852045a56`. All five required files are committed locally; none is present at the current remote commit.

Push blocked: Windows credential-store enumeration returns 0x5 Access is denied, and the configured GitHub CLI helper cannot create an MSYS named object (0xC0000022) inside this session. No credentials were exposed, replaced or reset. No additional sportsbook requests were made to address Git.

Run from normal PowerShell:

```powershell
& 'C:\Program Files\Git\cmd\git.exe' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```

If normal PowerShell also requires sign-in, use the installed Git Credential Manager browser flow:

```powershell
& 'C:\Program Files\Git\cmd\git.exe' credential-manager github login --browser
```
