# P0 freshness and settlement delivery

Checkpoint UTC: 2026-10-17T02:30:04.867982+00:00. Branch: ap-evisims-live.

Full tests: 351 passed, 0 failed. Original 389 forecasts and timestamps preserved; 18 protected Phase 1 files unchanged.
This priority refresh generated zero new forecasts and zero new Monte Carlo draws. Prior completed model/data improvements remain versioned alongside the original forecasts.

| Sport | DK/FD side comparisons | Identity matched | Fresh at comparison | Min / max quote age at comparison (s) |
|---|---:|---:|---:|---|
| NFL | 112 | 112 | 0 | 250.5 / 280.5 |
| NBA | 32 | 32 | 0 | 250.4 / 276.4 |
| NHL | 16 | 16 | 0 | 274.0 / 274.0 |
| MLB | 48 | 0 | 0 | 250.8 / 250.8 |
| CFB | 0 | 0 | 0 | 75077.1 / 75103.1 |

These ages refer to each recorded comparison timestamp. Quotes expire after 180 seconds. Cached math does not authorize execution; current ages and PASS reasons are in p0_passes.json.

NHL crosswalk: unique NJD at Washington matchup, matching league schedule and gamecenter IDs, official start 17:00 UTC and bookmaker start 17:10 UTC on October 17. Both clocks are preserved. The earlier 17:00 cutoff is enforced. This is research identity evidence, not Phase 1 betting authority.

MLB remains rejected: the official ALCS makeup-game record documents a postponement and an incompatible sportsbook start. No silent timestamp correction or regular-season-to-postseason promotion.

## Prospective evidence

1012 append-only comparison update records; 164 first fresh identity-verified side/book/line observations. Updates do not inflate sample size; books and opposing sides are correlated.
Settled observations: 0. Pending: 164. Reasons: {"EVENT_NOT_STARTED": 164}.
No qualified calibration, market-relative Brier/log loss, CLV, hypothetical ROI or drawdown is available. The settlement implementation scores authentic outcomes when available; a fixture test is not an empirical result.

## Real chronological research diagnostics

| Market | Evaluation outcomes | Model MAE | Recent-average baseline MAE |
|---|---:|---:|---:|
| NHL shots_on_goal | 96,796 | 1.0351 | 1.0587 |
| NHL goalie_saves | 5,622 | 5.9078 | 6.0861 |
| NBA rebounds | 52,029 | 1.9272 | 1.9662 |
| NBA assists | 52,029 | 1.3600 | 1.3864 |
| MLB hitter_hits | 12,183 | 0.6861 | 0.7177 |
| MLB total_bases | 12,183 | 1.2819 | 1.3241 |

These are reconstructed, chronological outcome forecasts on previously inspected evaluation seasons. They are not prospective sportsbook edge evidence. See P0_MEASURED_RESULTS.md and p0_measured_results.json for full training counts, before/after paired samples, RMSE and diagnostic probability scores.

NFL simple baseline references remain available; no automatic challenger or CORE promotion. The existing CFB model and original forecast timestamps remain unchanged.

## Exact remaining blockers

- Historical sportsbook endpoint HTTP 401; zero qualifying historical price backtest observations.
- Zero settled prospective priced comparisons; calibration, qualified market-relative scores, CLV and hypothetical ROI are not established.
- No confirmed player roles in this cohort. NBA/NFL reported injuries are secondary-aggregator evidence; NHL/MLB injury coverage is incomplete.
- MLB ALCS game 849817 is postponed/rescheduled: official Oct 18 21:00 UTC versus sportsbook Oct 18 00:00 UTC; regular-season model does not establish postseason validity.
- NHL target game has FanDuel SOG only; DraftKings and goalie-saves quotes were not returned.
- CFB score forecasts preserved; this prop-priority refresh does not refresh or qualify CFB prices.
- Exact bookmaker void, participation and postponement settlement terms remain unverified; no assumed cash returns.
- NFL rushing probability diagnostics and NBA threes fail their respective baselines; MLB pitcher-outs advantage is inconclusive.
- Historical outcome data are currently captured revisions, not proven historical availability. Inspected evaluation seasons are exploratory, not untouched holdouts.
- MLB player coverage is a documented limited cohort. No verified complete historical injury/role histories or shared-game joint simulations.

## Reproduce this refresh only

```powershell
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -m ap_evsims.p0_refresh --root .
# Add --collect for an explicit quota/cooldown-controlled quote refresh (default daily cap 24).
# This checkpoint used a bounded daily cap 36 and retained a 350-credit account reserve.
```
