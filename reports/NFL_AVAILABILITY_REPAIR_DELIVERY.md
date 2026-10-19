# NFL availability repair delivery

The initial live Git check confirmed local and remote both at `f80ef8ddc2bf53b476d2b317403b46bd48fa8c30`. The earlier c1f06b6/push-failed metadata in last_update.json is stale; it does not describe that verified remote state.

Regression suite: 456 passed, zero failed; baseline was 428 including pre-existing uncommitted NFL live tests. Added 28 focused regression tests. Both supplied acceptance modes pass: 12 scheduled / 12 covered / 12 game forecasts / 12 prop-scanned games. The original 1,494-forecast sweep remains intact.

All 389 original cross-sport forecast identities/timestamps verified. All 18 protected Phase 1 files unchanged; all 2394 original local forecast hashes verified.

The replay report demonstrates changed eligibility and assumptions, not a trained injury-adjusted numerical forecast. No new forecasts were backdated, and no sportsbook credits were consumed.

## Files in this focused checkpoint

- src/ap_evsims/nfl_forecast_news.py
- src/ap_evsims/nfl_news_replay.py
- src/ap_evsims/nfl_game_model.py
- src/ap_evsims/nfl_schedule.py
- src/ap_evsims/nfl_sweep.py
- src/ap_evsims/prop_availability.py
- src/ap_evsims/challenger_delivery.py
- src/ap_evsims/prop_market_research.py
- tests/test_nfl_forecast_news.py
- outputs/nfl_availability_repair.json
- reports/NFL_AVAILABILITY_REPAIR.md
- outputs/nfl_availability_repair_delivery.json
- reports/NFL_AVAILABILITY_REPAIR_DELIVERY.md

## Existing uncommitted changes

The 14 initial modified files were copied to an ignored local preservation folder before editing. They were inspected but are outside this checkpoint. Recurring work may continue refreshing them.

| File | Disposition |
|---|---|
| outputs/book_rule_source_status.json | New source/status refresh; unrelated to this repair; preserved unstaged. |
| outputs/last_update.json | Mixed: newer results/publication hashes plus stale c1f06b6 push-failure metadata. Fresh remote verification supersedes that old failure. Preserved unstaged. |
| outputs/latest_passes.json | New expired-price/started-event PASS rows (198 to 1414 at inspection); preserved unstaged. |
| outputs/latest_predictions.json | Active future subset shrank from 380 to 169 at inspection as events started; original archives retained; preserved unstaged. |
| outputs/live_research_candidates.json | New candidate/status refresh; unrelated to pregame repair; preserved unstaged. |
| outputs/model_status.json | Same 47 market rows with refreshed evidence/status fields; not new validated models; preserved unstaged. |
| outputs/prospective_settlements.json | New settlement/reporting run with changed cohorts and source failures; needs separate reconciliation; preserved unstaged. |
| outputs/provider_status.json | New quota/collection status; no provider collection requested by this repair; preserved unstaged. |
| outputs/reliability_manifest.json | New hashes/timestamp for existing recurring pipeline; preserved unstaged. |
| outputs/reliability_status.json | New recurring collection/activity status; preserved unstaged. |
| outputs/validated_edges.json | Timestamp-only refresh, still no validated edges; preserved unstaged. |
| outputs/week_ahead_game_probabilities.json | Refreshed timing/sport status; preserved unstaged. |
| reports/DAILY_BETTING_DECISIONS.md | New event-expiry and source-failure status; preserved unstaged. |
| reports/MODEL_PERFORMANCE_SCOREBOARD.md | Refreshed scoreboard omits previously shown NHL cohorts; not evidence those original settlements disappeared; separate reconciliation needed. Preserved unstaged. |

Untracked NFL live/remaining-game source, tests, reports and work/ were left untouched. The full local suite includes those tests; their code is not part of this repair commit.

## Verification commands

- `python -m unittest discover -s tests`
- `python -m ap_evsims.nfl_news_replay --root .`
- `python scripts/nfl_sweep_acceptance.py outputs/nfl_sweep_status.json --expected 12`
- `python scripts/nfl_sweep_acceptance.py outputs/nfl_sweep_status.json --expected 12 --require-probabilities`

PowerShell environment for tests: set `$env:PYTHONPATH="src;."`, `$env:TEMP=(Resolve-Path data/evaluations/test_tmp).Path`, and `$env:TMP=$env:TEMP`; use `.\.venv\Scripts\python.exe` from the existing repository.

## Limitations

- No new injury-adjusted numerical model; original means and distributions remain conditional historical baselines
- ESPN reports are secondary; no official active/starter or workload feed is implemented
- No replacement-QB model or supported scenario probabilities; NEWS_ADJUSTMENT_UNAVAILABLE
- Old/stale reports and roster active status cannot prove current gameday participation
- All October 18 games have begun; this replay cannot be counted as newly frozen prospective evidence
- No untouched injury-adjusted evaluation cohort or authenticated historical execution-price cohort
