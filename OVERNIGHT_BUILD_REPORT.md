# AP EV/SIMS overnight build report

Generated: 2026-10-14T07:35:39.551799+00:00
**OVERNIGHT_COMPLETE: PARTIAL.** The local implementation checkpoint is saved; there is no validated betting model and no demonstrated profitability.

Full suite: **155 passed, 0 failed**. All 18 frozen Phase 1 source/test files match their original SHA256 hashes.
No automatic wager placement, automatic model promotion, account changes, API purchases or secret publication occurred.

## Completed in this checkpoint

- Immutable provider archives, payload hashes, DuckDB/Parquet storage, quota tracking, historical query caching, bounded prospective odds collection and offline research commands.
- CFB spread/total/win research predictors, separate calibration fit/selection windows, source-bound artifacts, discrete push-aware distributions and derived uncertainty diagnostics.
- CFB replay now freezes model/decision records before appending verified result revisions. Exposure controls and original Phase 1 tests remain intact.
- Exact event/market identities, Unicode/punctuation spelling normalization with unique source team IDs, stale/execution/role gates and 24 sport/market contracts.
- Cash/bonus journals, idempotent external transaction records, correction entries, push/void settlement and separate promotion payoff arithmetic.
- Experiment/holdout controls, manual champion/challenger review, noise/label-shuffle regressions, source/feature audit inventory, readiness gate, diagnostics and hypothetical bankroll stress.
- Atomic PASS-only handoff, generation hashes, complete checklist, safe full-test/scan/commit/push command and documented GitHub access blocker.

## Actual provider access

| Provider/check | Result | Safely reported quota |
|---|---|---|
| CFBD games, plays, teams, venues, advanced metrics, week-filtered Elo, lines | HTTP 200; credentials present | 985 calls remaining at last CFBD response |
| CFBD live plays probe | HTTP 401 | Live access unavailable in probe |
| Odds API sports/current NCAAF and current NFL/NHL/MLB/NBA featured markets | HTTP 200; credentials present; DK/FD returned | 467 remaining; 33 provider-used |
| Historical NCAAF odds, requested 2025-10-04 16:00 UTC | HTTP 401 | BLOCKED_BY_HISTORICAL_ODDS_ACCESS |

The historical failure is distinct from working current authentication. Earliest usable historical sportsbook date: **unknown**. No historical prices were fabricated. No historical sweep or paid player-prop download was attempted.
The local quota ledger records 18 credits; the first 15 provider-validation credits predate that ledger. Remaining quota comes from provider headers.

## Real ingestion, with units separated

- Unique CFBD games: 594; 2025 historical games: 292; completed games across captures: 295.
- Observed seasons: 2025 week 6 and 2026 week 7. This is sampled coverage across classifications, not full-season FBS history.
- Accepted source snapshots: 29; source rows including revisions: 8544.
- Sportsbook response snapshots: 11; historical sportsbook snapshots: **0**.
- Timestamped market-side quote observations: 13896. Distinct current events: 60 CFB, 28 NFL, 2 NHL, 2 MLB, 46 NBA.
- CFB joined current identities: 60/60; unmatched: 0. Matching does not make feature availability historical.
- Current capture range: 2026-10-14 06:19:23.928987+00:00 through 2026-10-14 07:31:17.755854+00:00.
- Accepted archive hash failures: 0; quote schema/identity conflicts: 0; raw error payloads excluded: 7.
- Data footprint: 37878010 logical bytes; hard links may be counted twice.
- Qualifying real model evaluation sample: **0**. Prospective model sample: **0**. Synthetic observations included in real metrics: **0**.

Execution evidence, actual book rules and a calibrated model are missing for 100% of archived quote candidates. Full historical-universe missingness and selection bias cannot yet be measured. Those values remain null, not zero.

## What remains unimplemented or unproven

- Real rolling-origin CFB backtesting, market advantage, empirical p_low coverage, prospective shadow performance and profitability: blocked by qualifying historical price/feature joins.
- Full verified CFB feature construction and mapping into unchanged Phase 1 contracts: incomplete. CFBD PPA is not relabeled EPA. Retrospective CORE/season-end ratings and unproven weather are excluded.
- NHL SOG/goalie saves/ML/totals; NFL spread/total/receptions/rushing/receiving/passing; MLB pitcher K/outs/hits allowed/hitter hits/total bases; NBA spread/total/points/rebounds/assists/threes: contracts implemented, fitted predictors not implemented or calibrated.
- Sport-specific historical statistics ingestion, timestamp-safe player/role/injury archives, actual book rule versions and executable-quote proof: absent. This report does not establish that buying an injury provider would improve results.
- Full integrated result polling/correction reconciliation, external account/exposure reconciliation, synchronized live models and approved correlated-parlay models: incomplete or disabled.
- Empirical source/feature ablations, structural role/coach-regime detection, realistic-versus-ideal strategy replay, clustered ROI intervals and extreme-game case reconstructions: no qualifying sample. Diagnostic primitives do not complete those studies.
- Collector serialization is procedural, not a distributed lock. Use one writer. Historical CFBD query cache needs an explicit revision-refresh policy for later settlement updates.
- Red-team readiness audit: 13 critical and 22 high categories remain unresolved. Passing unit tests cannot clear missing empirical evidence.

## Exact next Phase 2 plan

1. Earliest blocked dependency: obtain timestamp-authentic historical two-sided odds through entitled access or an authorized recorded export. While waiting, retain bounded prospective collection; no purchases or fabricated history.
2. Build the canonical CFB eligible-game universe and prior-completed-game features with proven available_at, audited identities, exact line/juice, rule versions, source hashes and exclusion reasons.
3. Pre-register one simple CFB spread experiment, lock final holdout, complete the verified feature bridge, and retain all attempted variants. No threshold tuning on the final test.
4. Run chronological fit/calibration/selection/evaluation, compare matched no-vig market proper scores, and test p_low conservatism, dependence, slippage, exclusion bias, noise/label shuffles, source ablations and tails.
5. Record prospective shadow predictions and wait for settled observations. Keep PASS unless all original and red-team gates qualify. Manual review is required for any promotion.
6. Repeat in order: CFB total and moneyline; NHL; NFL; MLB; NBA. Live and parlay work depends on separately validated components and synchronized/joint data.

## GitHub and files

Branch: `ap-evisims-live`. Remote: `https://github.com/adrianopalaia-arch/AP-EV-SIMS.git`.
The connection-test commit was verified remotely earlier. Subsequent local checkpoints could not push because this session lacks accessible GitHub write credentials. No force push, reset or remote overwrite was used.
The current publication records the source HEAD before its own commit. See Git HEAD for the final checkpoint commit.
Every changed file since the verified remote connection checkpoint is listed in FILES_CHANGED.md. Detailed per-item status, files, tests, samples, blocker and next action are in TASK_STATE.json.

Manual push from normal PowerShell:

```powershell
& 'C:\Users\adria\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```
