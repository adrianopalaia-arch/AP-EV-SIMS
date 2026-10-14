# AP EV/SIMS Phase 2 progress

Updated: 2026-10-14T06:55:36.539492+00:00

This is the single reconciled execution checklist. Scope is frozen. COMPLETE describes tested implementation, not empirical model approval.

Current task: FOUNDATION.odds_archive. Next dependency: FOUNDATION.historical_replay.
Full suite: 103 passed; 0 failed.

Real model evaluation sample: 0. All sport/market models remain UNVALIDATED.
Historical odds: BLOCKED_BY_HISTORICAL_ODDS_ACCESS. Current CFBD/Odds authentication is verified.
No real wagers, automatic promotions, purchases, or account changes.

| Deliverable | Status | Next action / blocker |
|---|---|---|
| FOUNDATION.provider_authentication | COMPLETE | Reuse verified current access; monitor quota. Historical access remains a separate blocker. |
| FOUNDATION.historical_provider_access | BLOCKED | Do not retry until entitlement changes; accumulate owned current snapshots. Blocker: BLOCKED_BY_HISTORICAL_ODDS_ACCESS; authenticated current access succeeds but historical HTTP 401 |
| FOUNDATION.local_warehouse | COMPLETE | Use local DuckDB/Parquet for remaining work. Preserve immutable versions. |
| FOUNDATION.historical_replay | IN_PROGRESS | Finish universal frozen prediction/reveal ledger; retain chronological CFB evaluation. Blocker: No qualifying historical sportsbook dataset |
| FOUNDATION.odds_archive | IN_PROGRESS | Finish collect_odds command, persistent cadence/cache, and normalized quote exports. |
| FOUNDATION.calibration | COMPLETE | Keep fit/selection/evaluation chronologically separate; attach only to exact fitted artifact. |
| FOUNDATION.p_low | TESTING | Add coverage diagnostics; do not claim a verified production confidence bound. Blocker: Empirical interval coverage untested |
| FOUNDATION.champion_challenger | NOT_STARTED | Implement immutable experiment/holdout ledger and comparison gate; no automatic promotion. |
| FOUNDATION.red_team_tests | IN_PROGRESS | Map all 50 audit modes to evidence; add adversarial regressions and explicit unresolved gates. Blocker: Empirical execution, bias, drift and tails untested |
| FOUNDATION.GitHub_handoff | IN_PROGRESS | Implement atomic publish_handoff CLI, safe secret-scanned checkpoints; verify current push access. |
| FOUNDATION.canonical_identity | IN_PROGRESS | Bind stable provider IDs, exact market/period/rules; reject ambiguous aliases and reschedules. Blocker: Current CFB aliases and schedule revisions not yet reconciled |
| FOUNDATION.settlement_accounting | IN_PROGRESS | Add append-only corrections, confirmed cash/bonus transactions, and explicit unknown-rule PASS. Blocker: Book-specific settlement rule registry absent |
| FOUNDATION.feature_source_audits | IN_PROGRESS | Persist feature/source availability and ablation experiments; exclude unverifiable fields. Blocker: CFBD historical publication/revision availability unproven |
| CFB.spread | BLOCKED | Keep CFBSpreadModel research implementation; collect future provenance and evaluate when eligible data exists. No real model fitted. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| CFB.total | BLOCKED | Keep CFBTotalModel research implementation; collect future provenance and evaluate when eligible data exists. No real model fitted. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| CFB.moneyline | BLOCKED | Keep CFBWinModel research implementation; collect future provenance and evaluate when eligible data exists. No real model fitted. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| NHL.SOG | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NHL.goalie_saves | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NHL.ML | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NHL.totals | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.spread | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.total | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.receptions | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.rushing | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.receiving | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NFL.passing | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| MLB.pitcher_K | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| MLB.pitcher_outs | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| MLB.hits_allowed | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| MLB.hitter_hits | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| MLB.total_bases | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.spread | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.total | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.points | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.rebounds | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.assists | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| NBA.threes | NOT_STARTED | Implement separate simple sport/market research contract after core replay/settlement; validate on real data before promotion. Blocker: No eligible local sport-specific training dataset; historical odds unavailable |
| OTHER.live_models | NOT_STARTED | Keep separate live state/model identities; no pregame model reuse. |
| OTHER.parlays | NOT_STARTED | Gate on validated singles and real joint payout; no automatic construction. |
| OTHER.promotions | NOT_STARTED | Separate payoff math from model probability and cash/bonus accounting. |
| OTHER.tail_event_stress | NOT_STARTED | Retain extreme events; implement outcome-independent stress selectors and report missing real samples. |
| OTHER.diagnostics | NOT_STARTED | Publish health, selection-bias, latency, regime, miss and drift reports without invented metrics. |
| OTHER.local_first_data_storage | IN_PROGRESS | Finish sync_data, collect_odds, data_health and offline research_cycle; no network in historical work. |

## Dependency and evidence policy

1. Preserve the completed Phase 1, access checks, warehouse foundation, and calibration implementation.
2. Finish the owned odds archive and local-only replay/settlement foundation.
3. Complete research governance, holdout, execution and red-team gates, then safe handoff commands.
4. Resume CFB spread, total, moneyline in order; block empirical claims until provenance and prices qualify.
5. Build independently testable sport contracts in NHL, NFL, MLB, NBA order. Do not mark implementations validated from fixtures.
6. Live and parlay eligibility depend on separately validated component markets. Promotions affect payoff only.
7. Run all tests, update this checklist and TASK_STATE, scan safe files, commit and attempt push at major checkpoints.
8. A failed GitHub push does not stop independent local work. Preserve a committed local checkpoint.

## Requirements retained from all prior directives

- Local-first immutable raw archives, DuckDB/Parquet, content hashing, query cache, quota ledger, bounded collection cadence, offline network prohibition.
- Stable event/player/market identities, schedule revisions, exact line plus price, synchronous no-vig pairs, known settlement and executable-quote evidence.
- Chronological training/calibration/selection/test; untouched holdout; experiment count; negative controls; source and feature ablation; no future revisions.
- Derived uncertainty, calibrated tails, simple-model preference, opportunity-first prop families, role stability and explicit disagreement.
- Persistent cash/bonus/exposure accounting, corrected settlement, CLV kept separate, cluster bootstrap, slippage and bankroll stress.
- Champion/challenger and shadow forecasts, no auto-promotion; postmortem hypotheses, drift/regime diagnostics and daily/longitudinal reports.
- Current edges require Phase 1 gates and fresh executable prices; PASS records retained; no fabricated bankroll, price, feature or performance.
- Complete all 50 red-team audit categories before readiness. Untested critical conditions block READY_FOR_SMALL_STAKES.
- Case reconstructions require actual historical snapshots; otherwise INSUFFICIENT_HISTORICAL_SNAPSHOT.

Detailed per-item files, tests, real and synthetic sample sizes are in TASK_STATE.json.
