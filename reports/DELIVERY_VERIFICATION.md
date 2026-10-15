# AP EV/SIMS delivery verification

Verified October 14, 2026, 07:41 PM America/Chicago. Data timestamps remain in UTC.

## Repository and preservation

Repository: `C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS`

Branch: `ap-evisims-live`. Source checkpoint before this delivery: `7197152feae091358239c1dbe1f0940844ba6dda`.
Commit `6b20b15` remains an ancestor. All 194 requested passing tests are preserved; the actual full suite is **195 passed, 0 failed, 0 skipped**. All 18 frozen Phase 1 files match their baseline hashes. No feature code changed during this delivery operation. No reset or force-push was used.

## Exact Windows commands

Open normal PowerShell and run:

```powershell
Set-Location -LiteralPath 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
.\.venv\Scripts\python.exe -m ap_evsims dashboard
```

Keep that window open, then visit **http://127.0.0.1:8501/**. The server startup succeeds in Codex, but its loopback connection times out. The Codex test server has been stopped to avoid a competing instance. Browser visual acceptance still needs the normal-PowerShell launch; a running local server is required for the URL to work.

In a second PowerShell window, generate the daily card:

```powershell
Set-Location -LiteralPath 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
.\.venv\Scripts\python.exe -m ap_evsims daily_card --sports CFB,NHL,NFL,MLB,NBA --force-refresh
```

This obeys the default 24-credit daily ceiling, 50-credit reserve and 60-second refresh cooldown. To rebuild without any provider requests:

```powershell
.\.venv\Scripts\python.exe -m ap_evsims daily_card --offline
```

Dependencies are already installed. If reinstalling is necessary, from the repository run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Provider/data verification

- Both credential values are present locally; neither was displayed or written to reports.
- CFBD games: HTTP 200, quota remaining 979 at its recorded check.
- Odds sports and current CFB odds: HTTP 200; DraftKings and FanDuel returned.
- Historical NCAAF odds: HTTP 401. **BLOCKED_BY_HISTORICAL_ODDS_ACCESS**. Earliest usable historical date remains unknown.
- Current CFB data was captured at 2026-10-15T00:40:26.523966+00:00; NHL/NFL/MLB/NBA current snapshots refreshed in the same verification run. The CFB re-request was correctly skipped within its 60-second cooldown.
- Odds API quota remaining: 431; provider-used credits: 69.
- Card generated 2026-10-15T00:40:59.766110+00:00: 159 events, 5780 quote sides, 1622 DK/FD sides. No refresh failures. Captured prices may become stale; the UI rechecks age.
- One previously archived all-division CFBD snapshot remains excluded for schema failure: three completed games had missing scores. Raw evidence retained; no fabricated results.
- CFB schedule audit: 1666 games in captured queries. Real qualifying model evaluation sample: **0**. Every model remains UNVALIDATED; **NO QUALIFYING BETS**.
- No synthetic observation is reported as real performance. No wagers were placed.

## Delivered outputs and remaining work

`TASK_STATE.json`, `PHASE2_PROGRESS.md`, `outputs/latest_predictions.json`, `latest_edges.json`, `latest_passes.json`, `model_status.json`, `provider_status.json`, `cfb_universe.json`, `last_update.json`, and `reports/MORNING_CARD.md` are saved locally. Publication hashes were verified.

Remaining: normal-PowerShell browser acceptance; GitHub write access; complete verified CFB feature sets and real historical/prospective model validation; remaining sport predictors/props; empirical diagnostics; validated live/parlay/correlation eligibility. Detailed dependency order and the prior build's changed-file inventory remain in `reports/PRODUCT_DELIVERY.md`. This operation adds no new feature scope.

## Manual Git push

If the session push remains blocked, run this exact single command in authenticated PowerShell:

```powershell
& 'C:\Program Files\Git\cmd\git.EXE' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```

This preserves existing remote history and sends the local committed checkpoints. Never add `--force`.

## Push outcome

The delivery checkpoint `c9417070005dae448e750a503c064164ab1e3a74` was committed locally after the staged-secret scan passed. The push was blocked. Session GitHub write access remains unavailable; the prior connector check returned HTTP 403. Use the authenticated PowerShell push command above. A final push is attempted after saving this outcome. The final local commit and push result are reported in chat. No secrets, raw datasets, or databases were staged.
