# P0 reliable engine — executed delivery

Generated UTC: 2026-10-18T03:24:07.788450+00:00. Branch ap-evisims-live. Source checkpoint before this work: 2b44864.

**CORE remains disabled. No validated betting edge or authorized stake.**

## Before and after

| Evidence | Before | After |
|---|---:|---:|
| Scored frozen forecast records | 0 | 161 |
| Distinct games | 0 | 45 |
| Price-matched fixed-Over results | 0 | 8 |
| Settled independent-consensus observations | 0 | 0 |
| Validated edges | 0 | 0 |

Forecast records include multiple CFB versions on the same games and correlated NHL player outcomes. They are not independent games; see distinct-game counts. Prior historical training and evaluation samples are unchanged. No retraining or new Monte Carlo draws occurred. The original 389 forecasts, their issue times, and all 18 protected Phase 1 files are unchanged.

## Measured prospective forecasting accuracy

| Model / market | N | Games | Model MAE / RMSE | Same-sample baseline MAE / RMSE |
|---|---:|---:|---|---|
| CFB game_margin cfb-score-ridge-v1 | 43 | 43 | 11.7073 / 13.4953 | 12.4357 / 14.7122 |
| CFB game_margin cfb-score-ridge-v1.1 | 43 | 43 | 11.7073 / 13.4953 | 12.4357 / 14.7122 |
| NHL goalie_saves causal-opportunity-ridge-v2 | 2 | 1 | 3.5543 / 3.5580 | 4.1000 / 4.1110 |
| NHL goalie_saves opportunity-partial-pool-v1 | 2 | 1 | 6.1998 / 6.3518 | 6.8000 / 6.8731 |
| NHL shots_on_goal causal-opportunity-ridge-v2 | 35 | 1 | 0.9855 / 1.2449 | 0.9171 / 1.1819 |
| NHL shots_on_goal opportunity-partial-pool-v1 | 36 | 1 | 0.9305 / 1.3912 | 0.9491 / 1.3242 |

CFB v1.1 raw Brier = 0.24127; log loss = 0.67553. Descriptive game-cluster MAE difference interval: [-1.9323069063467975, 0.43677842132360056]. The current NHL shots model loses its simple baseline on the first prospective game; it is not promoted.

Eight original FanDuel shots Over observations: raw Brier 0.17216 vs entry-book 0.21580; log loss 0.52834 vs 0.62371. These eight players share one game. The entry book is not independent consensus. The fixed-Over reporting policy was adopted after these results; the forecasts were pregame, but this is exploratory evaluation, not untouched confirmatory evidence. Opposite sides and repeated quotes are not added as extra wins.

Raw calibration-bin counts and paired uncertainty are in prospective_settlements.json. Calibrated probabilities, p_low, qualified CLV, hypothetical ROI, return intervals and drawdown remain null. Missing DNP, void and settlement rules are never treated as zero-stat losses. Authentic near-start closing snapshots were not archived for these entries.

## All-sport current coverage

Quote ages are evaluated at 2026-10-18T03:23:38.015034+00:00; they are not renewed by this report.

| Sport | Future forecasts | Exact side comparisons | Fresh at publication | Priced settled | Failed history projections |
|---|---:|---:|---:|---:|---:|
| CFB | 45 | 16 | 0 | 0 | 0 |
| MLB | 38 | 0 | 0 | 0 | 91 |
| NBA | 124 | 64 | 0 | 0 | 16 |
| NFL | 124 | 96 | 48 | 0 | 481 |
| NHL | 49 | 22 | 0 | 8 | 1 |

MLB retains 38 forecasts but price matching remains blocked by a postponed canonical start, provider timestamp conflict and a postseason/regular-season model-domain mismatch. NBA and NFL upcoming outcomes are not yet available; their dedicated live official-result adapters still need completion. NBA role/long-layoff uncertainty and failed NFL distribution benchmarks remain explicit rejections. NHL cross-source event resolution preserves both starts and uses the earlier cutoff; verified identity is never permission to waive the Phase 1 gates.

## Implemented and executed

- Official NHL final-box settlement with exact player/team/event/start verification, DNP exclusion, immutable source revisions and game-separated model cohorts.
- CFB outcomes scored from canonical final results; seven-day forecasts reuse the preserved trained artifact. 34 new CFB forecasts and 49 new NHL forecasts were frozen; these are not new simulations.
- Consensus excludes the entry book and requires at least two other contemporaneous exact-line books. Large disagreement is an investigation flag. Raw win/push/loss, EV, fair prices and line sensitivity remain research-only.
- Closing quotes are invalidated by a subsequent changed line or scoped empty/suspended response. Post-start fetches cannot become historical closes.
- Quota-aware fixed-market collection reserves closing capacity, records real request times, and enforces overlap locks. NFL refresh prioritizes receptions and receiving yards.
- Public bookmaker rule documents were archived and hashed locally at actual fetch time. Jurisdiction/market applicability remains unverified; no historical backdating.
- Future calibration, selection and untouched holdout phases are frozen separately. Earlier inspected results remain exploratory. No calibrator or uncertainty bound has been fitted from this small sample.

## Scheduling and reproducible commands

The exact runner script executed successfully (exit 0). Native Windows Task Scheduler installation failed: CIM resource access unavailable. No native task is claimed installed. A standalone local Codex task, ap-ev-sims-verified-research-cycle, runs every 20 minutes. Two scheduled executions completed at 02:43 and 03:04 UTC with exit 0, but provider access was blocked in their separate execution sessions. Local archive scoring worked; unattended live network collection is NOT verified. It requires this computer and the desktop app running. The slower fallback does not guarantee closing observations. The native two-minute task requires an awake, signed-in Windows session and does not need an open Codex conversation.

Run the tested cycle in PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONIOENCODING = 'utf-8'
& '.\.venv\Scripts\python.exe' -m ap_evsims.reliable_engine --root . --collect --daily-cap 24 --reserve 50
```

Install the native schedule from a normal PowerShell window:

```powershell
& 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS\scripts\install_reliable_task.ps1' -Repository 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
```

The collector never writes Git or places bets. Concurrent runs are locked. Quota exhaustion and asleep/offline periods produce gaps, not fabricated prices. Scheduled failures are sanitized in outputs/reliability_failure.json.

## Remaining blockers, in betting-readiness order

1. No sufficiently powered, preregistered prospective calibration/selection/holdout evidence; current NHL shots has not beaten its baseline prospectively. All CORE gates remain closed.
2. Pregame participation, complete injuries, confirmed roles, starters and workload uncertainty remain incomplete. Role-conditioned probabilities are not unconditional cash-bet probabilities.
3. Exact bookmaker settlement/void terms and jurisdiction applicability are not established before entries. Rule-source collection is implemented; interpretation/applicability and ROI settlement are unfinished.
4. Authentic closing captures and independent consensus are missing for settled observations. Native scheduler installation is blocked at CIM; fallback sessions lack working provider network access. Persistent unattended live collection remains unfinished. Fallback latency and finite quote quota also limit coverage.
5. NBA/NFL/MLB official live result adapters and prospective role validation are unfinished. MLB postponement/postseason identity conflict still blocks comparisons. The NHL result path conservatively waits until the next UTC date under existing finality controls.
6. Historical odds entitlement remains previously observed HTTP 401; no new entitlement claimed. Historical source revision timing is unverified, so reconstructed backtests are not authentic historical execution evidence.
7. GitHub push result is recorded in last_update.json after the final attempt; no reset or force-push is permitted.

## Verification

378 tests passed, 0 failed. No synthetic observations in empirical metrics. Original 389 forecast hashes/timestamps and 18 Phase 1 file hashes verified. New outputs are listed in reliability_manifest.json; secrets/raw data/databases are excluded from staging.

## Files changed

- .gitignore
- PHASE2_PROGRESS.md
- TASK_STATE.json
- TEST_RESULTS.txt
- outputs/book_rule_source_status.json
- outputs/last_update.json
- outputs/latest_passes.json
- outputs/latest_predictions.json
- outputs/live_research_candidates.json
- outputs/mlb_availability.json
- outputs/mlb_challenger_prospective.json
- outputs/model_status.json
- outputs/nba_availability.json
- outputs/nba_challenger_prospective.json
- outputs/nfl_availability.json
- outputs/nfl_challenger_prospective.json
- outputs/nhl_availability.json
- outputs/nhl_challenger_prospective.json
- outputs/p0_preservation_audit.json
- outputs/prospective_settlements.json
- outputs/provider_status.json
- outputs/reliability_manifest.json
- outputs/reliability_status.json
- outputs/reliable_delivery.json
- outputs/scheduler_status.json
- outputs/validated_edges.json
- outputs/week_ahead_game_probabilities.json
- reports/DAILY_BETTING_DECISIONS.md
- reports/MODEL_PERFORMANCE_SCOREBOARD.md
- reports/P0_RELIABLE_DELIVERY.md
- scripts/install_reliable_task.ps1
- scripts/run_reliable_cycle.ps1
- src/ap_evsims/book_rule_evidence.py
- src/ap_evsims/cfb_frozen_board.py
- src/ap_evsims/challenger_delivery.py
- src/ap_evsims/checkpoint.py
- src/ap_evsims/operations.py
- src/ap_evsims/prop_market_research.py
- src/ap_evsims/prop_price_evidence.py
- src/ap_evsims/prop_prices.py
- src/ap_evsims/reliable_engine.py
- src/ap_evsims/reliable_handoff.py
- src/ap_evsims/reliable_results.py
- tests/test_reliable_engine.py

## Git evidence

Tested code/results commit: 23be499b9adeb83b80f63badd958b4aa494bd23d. All staged files passed the secret scan; .env and raw data were excluded. Git push failed because this session cannot access Git credentials. GitHub connector also returned HTTP 403 (resource not accessible by integration). Verified origin/ap-evisims-live: 2b448643c128b14e49c0ae7acaf6cacb990e598b at 2026-10-18T03:25:20.527967+00:00. No force-push or reset. The following local status checkpoint records this result.

Manual PowerShell push:

```powershell
& 'C:\\Program Files\\Git\\cmd\\git.EXE' -C 'C:\\Users\\adria\\Documents\\Codex\\2026-10-13\\files-mentioned-by-the-user-ap\\outputs\\AP-EV-SIMS' push -u origin ap-evisims-live
```
