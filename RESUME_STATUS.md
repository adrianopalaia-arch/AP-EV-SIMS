# Resume checkpoint

Updated: 2026-10-14T22:12:18.238444+00:00

Repository: `C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS`. Branch: `ap-evisims-live`.
Resumed from 69c1428df9545de1709581f3006d5ea7b9d39160 with a clean checkout; no local work was discarded.
The prior session ended around 02:38 America/Chicago on October 14 with a partial build. Historical odds and qualifying feature data blocked empirical validation; independent implementation gaps also remained. Tests were not the reason for stopping.

Full suite: 171 passed, 0 failed, 0 skipped. Original 155 tests preserved; all 18 frozen Phase 1 files match their baseline hashes.
Both credentials are accessible. CFBD games, Odds sports and current CFB odds returned HTTP 200 on this resume. Historical entitlement was not retested; the last probe returned HTTP 401. .env remains ignored and untracked.

## Completed after resuming

- Explicit CFBD year/week refresh with a one-hour default cooldown, failed-request throttling, immutable response revisions and schema rejection.
- Verified local as-of result selection; ambiguous/duplicate scores, impossible final timestamps, source tampering and changed event starts fail closed.
- Offline append-only reconciliation against existing frozen real-prediction ledgers; cash/exposure settlement remains separate and incomplete.
- Phase 2 bridge rejects feature/context mismatches, preserves disagreement, and enforces PASS for unapproved p_low coverage. A caller flag cannot approve a bound.

## Real data and evidence

- 896 unique CFBD games, 295 currently final; sampled year/week queries: [(2025, 6), (2026, 7), (2026, 8)], not complete seasons.
- 33 accepted source snapshots; 9390 source rows including revisions.
- 12 sportsbook response snapshots; 16990 market-side quote observations, including repeated captures.
- CFB identities: 61 matched, 1 unmatched. Hash failures: 0; schema/identity conflicts: 0.
- The new week-8 game capture resolves Marshall/South Alabama. Minnesota/Iowa remains excluded because CFBD does not confirm its start time. No placeholder time is treated as verified.
- Historical sportsbook snapshots: 0. Qualifying historical/prospective model evaluation observations: 0. Synthetic observations in real metrics: 0.
- No approved model, betting recommendation, profitability claim, automatic wager or model promotion.

## Unfinished implementation and data dependencies

| Area | Remaining work |
|---|---|
| Historical data | Timestamp-authentic two-sided odds; complete eligible-game universe; verified feature availability and historical identity revisions. Paid Odds history remains blocked at its last probe. |
| CFB spread, total, moneyline | Complete feature construction and mapping into unchanged Phase 1 requirements, including honest EPA/PPA definitions; preregister experiments; fit, calibrate and run rolling-origin and prospective evaluations. Moneyline and integer-line eligibility cannot bypass existing Phase 1 restrictions. |
| NHL SOG, goalie saves, ML, totals | Contracts exist; statistics/role/goalie/player identity ingestion, fitted opportunity/distribution models, prices and empirical calibration are unfinished. |
| NFL spread, total, receptions, rushing, receiving, passing | Contracts exist; sport ingestion, player usage/availability history, fitted predictors and empirical calibration are unfinished. |
| MLB pitcher K, outs, hits allowed; hitter hits, total bases | Contracts exist; starter/lineup/player data, opportunity models, distribution fits and empirical calibration are unfinished. |
| NBA spread, total, points, rebounds, assists, threes | Contracts exist; minutes/role/availability data, predictors and empirical calibration are unfinished. |
| Calibration / p_low / promotion | Calibration mechanics exist; unseen calibration evidence, conservative-bound coverage, authenticated approval, prospective comparisons and full experiment-runner coupling remain incomplete. No automatic promotion. |
| Settlement / exposure | Actual book-rule versions, external balances/open positions, automatic result polling and integrated cash/exposure correction reconciliation remain incomplete. |
| Local warehouse / collector | Existing storage and collectors are preserved. Concurrent-writer locking, schedule/closing revision policy and full historical mapping availability remain incomplete. |
| Diagnostics / red team | Empirical ablations, realistic execution replay, clustered ROI intervals, role/coach regimes, tail reconstructions and prospective diagnostics are unfinished. Previous readiness audit has 13 critical and 22 high unresolved categories; new unit tests alone do not clear them. |
| Live / parlays / promotions | Live models and synchronized state feeds are absent. Parlays require approved singles and validated joint outcomes/payouts. Promotion arithmetic exists, but real terms/bonus conversion and approved recommendations do not. |
| GitHub | Local checkpoints are committed; write authentication is unavailable in this session. No reset or force push is used. |

## Dependency order

1. Keep the historical-odds blocker explicit. Continue bounded prospective captures; do not invent earlier information.
2. Next independent implementation: audit the CFB eligible-game universe and finish verifiable feature-to-Phase1 mapping, preserving every missing-input PASS.
3. Complete experiment-runner and authenticated approval integration; evaluate only when data qualifies.
4. Complete settlement/account reconciliation from explicit rules and reconciled inputs.
5. Proceed through CFB total/moneyline, NHL, NFL, MLB and NBA as source/provenance dependencies qualify. Keep live/parlays blocked until their components qualify.

Every deliverable retains its files, tests, real/synthetic sample sizes, blocker and next action in TASK_STATE.json.

## Manual push

Run in normal PowerShell:

```powershell
& 'C:\Users\adria\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```
