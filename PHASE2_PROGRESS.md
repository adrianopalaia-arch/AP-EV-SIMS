# AP EV/SIMS Phase 2 progress

Updated: 2026-10-15T00:37:33.660267+00:00

This is the single reconciled execution checklist. Scope is frozen. COMPLETE describes tested implementation, not empirical model approval.

Current task: M1_M3_PRODUCT_SLICE_IMPLEMENTED. Next dependency: CFB verified prior-game feature coverage; M1 browser acceptance from normal PowerShell.
Full suite: 195 passed; 0 failed.

Real model evaluation sample: 0. All sport/market models remain UNVALIDATED.
Historical odds: BLOCKED_BY_HISTORICAL_ODDS_ACCESS. Current CFBD/Odds authentication is verified.
No real wagers, automatic promotions, purchases, or account changes.

| Deliverable | Status | Next action / blocker |
|---|---|---|
| CFB.moneyline | BLOCKED | Keep CFBWinModel research implementation; collect future provenance and evaluate when eligible data exists. No real model fitted. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| CFB.spread | BLOCKED | Expand verified prior-game play coverage and complete required CFB features; historical model fitting remains blocked. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| CFB.total | BLOCKED | Keep CFBTotalModel research implementation; collect future provenance and evaluate when eligible data exists. No real model fitted. Blocker: No timestamp-authentic joined historical odds/features dataset; zero empirical model observations |
| FOUNDATION.GitHub_handoff | BLOCKED | Run the documented single push command from normal authenticated PowerShell; preserve local commits and remote history. Blocker: Remote read works; local Git push failed authentication/permission; GitHub connector write returned HTTP 403. |
| FOUNDATION.calibration | COMPLETE | Keep fit/selection/evaluation chronologically separate; attach only to exact fitted artifact. |
| FOUNDATION.canonical_identity | BLOCKED | Collect timestamp-safe roster and schedule revision archives; preserve uniquely mapped source team IDs. Blocker: Current CFB identity: 61/62 matched; 1 unmatched. Other-sport player identity and historical mapping proof remain absent. |
| FOUNDATION.champion_challenger | BLOCKED | Register the first real experiment before fitting; preserve one-use final holdout and manual promotion. Blocker: No real champion, challenger or prospective holdout observations. |
| FOUNDATION.feature_source_audits | BLOCKED | Enable only provenance-proven features; run pre-registered matched source/feature ablations on unseen samples. Blocker: Inventory is complete; historical coverage, full-universe missingness and incremental value remain unmeasured. |
| FOUNDATION.historical_provider_access | BLOCKED | Do not retry until entitlement changes; accumulate owned current snapshots. Blocker: BLOCKED_BY_HISTORICAL_ODDS_ACCESS; authenticated current access succeeds but historical HTTP 401 |
| FOUNDATION.historical_replay | BLOCKED | Resume real CFB spread replay when historical odds and timestamp-authentic joined features exist; then extend the same ledger to calibrated sport models. Blocker: CFB replay now freezes decisions before verified result reveals; no qualifying historical dataset; other fitted sport models not implemented. |
| FOUNDATION.local_warehouse | COMPLETE | Use local DuckDB/Parquet for remaining work. Preserve immutable versions. |
| FOUNDATION.odds_archive | COMPLETE | Continue bounded prospective collection; cached history is immutable. No paid historical entitlement. |
| FOUNDATION.p_low | BLOCKED | Evaluate aggregate conservatism and clustered coverage diagnostics on untouched real predictions before approval. Blocker: Empirical coverage and independently authenticated approval are absent. The bridge now enforces P_LOW_COVERAGE_UNVERIFIED even if a caller asserts coverage_validated=true. |
| FOUNDATION.provider_authentication | COMPLETE | Reuse verified current access; monitor quota. Historical access remains a separate blocker. |
| FOUNDATION.red_team_tests | BLOCKED | Clear each unresolved critical/high category with actual evidence and targeted tests; never equate unit-test count with readiness. Blocker: All 50 categories audited; unresolved data/execution/model evidence keeps every market RESEARCH_ONLY. |
| FOUNDATION.settlement_accounting | BLOCKED | Complete verified book-rule and external account/exposure reconciliation; explicit CFBD refresh and local replay result revisions are implemented. Blocker: Actual book rules and reconciled account/open-position inputs are absent. Automatic result polling and cash/exposure correction integration remain incomplete. |
| MLB.game_total | NOT_STARTED | Implement only after required role/price evidence exists. Blocker: No fitted predictor or qualifying evaluation |
| MLB.hits_allowed | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| MLB.hitter_hits | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| MLB.pitcher_K | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| MLB.pitcher_outs | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| MLB.total_bases | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.assists | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.points | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.rebounds | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.spread | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.threes | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NBA.total | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.passing | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.receiving | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.receptions | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.rushing | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.rushing_attempts | NOT_STARTED | Implement only after required role/price evidence exists. Blocker: No fitted predictor or qualifying evaluation |
| NFL.spread | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NFL.total | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NHL.ML | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NHL.SOG | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NHL.goalie_saves | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| NHL.totals | BLOCKED | Implement and fit the specified opportunity/distribution model only after source and timestamp audits; then chronological calibration and priced evaluation. Blocker: Feature/role/unit contract implemented; fitted predictor, timestamp-safe sport data, historical exact prices and empirical calibration are absent. |
| OTHER.diagnostics | BLOCKED | Populate proper-score, inclusion-bias, latency, regime, source-ablation and p_low reports from frozen real predictions. Blocker: No calibrated real forecasts or settled strategy observations; all performance remains null. |
| OTHER.live_models | BLOCKED | Require separately calibrated live probability, synchronized state/price and latency evidence; retain pregame/live separation. Blocker: No live model or synchronized live feed; CFBD live endpoint probe returned 401. |
| OTHER.local_first_data_storage | COMPLETE | Keep historical research offline and import source archives before feature computation. |
| OTHER.parlays | BLOCKED | Do not build candidate slips until validated singles, fitted joint distributions and actual offered payouts exist. Blocker: No approved single-market models or empirical joint distribution; legacy parlay arithmetic is research only. |
| OTHER.promotions | COMPLETE | Keep promotion payoff separate; real terms/bonus conversion still required and no recommendation authority is granted. |
| OTHER.tail_event_stress | BLOCKED | Run registered extreme-game and clustered bankroll stress on real out-of-sample decisions. Blocker: Hypothetical stress mechanics pass; real tail cases lack qualifying historical snapshots. |
| PRODUCT.M1_local_application | TESTING | Launch from normal PowerShell and complete browser visual acceptance. No model approval is implied. Blocker: Loopback HTTP and browser access timed out in this Codex session. Server starts and real-data Streamlit AppTest passes. |
| PRODUCT.M2_first_real_model_output | BLOCKED | Accumulate verified prior-game plays and join eligible prices before fitting the first real CFB model. Never train on fixture observations. Blocker: Zero qualifying timestamp-authentic training/evaluation rows and zero complete real feature sets. |
| PRODUCT.M3_daily_card | COMPLETE | Preserve PASS-first daily publication; integrate an approved model only through existing Phase 1 controls after M2. |
| PRODUCT.M4_historical_validation | BLOCKED | Use owned prospective snapshots; enable historical evaluations only when real entitled timestamp-safe data exists. Blocker: Historical Odds API access returned HTTP 401; historical feature publication times are also unverified. |
| PRODUCT.M5_remaining_sports | BLOCKED | Continue NHL SOG/saves first, then NFL, MLB and NBA in dependency order. Do not promote the 26 display entries as implemented models. Blocker: Featured prices are available; sport predictors, prop prices, role features and empirical calibration are incomplete. |
| PRODUCT.M6_research_cycle_and_delivery | IN_PROGRESS | Keep verified local result reconciliation and KEEP_CHAMPION behavior. Add data-backed diagnostics/challengers only after samples qualify. Blocker: Real prediction/settlement evaluation samples are zero; local Git authentication/permission fails and GitHub connector returns HTTP 403. |

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

## Product delivery checkpoint

- 195 tests passed; 0 failed; original 171 preserved; 18 frozen Phase 1 files unchanged.
- Local Streamlit application and PASS-first daily card implemented. Clean virtual-environment installation passed.
- Real-data Streamlit AppTest passed. Server starts at http://127.0.0.1:8501; HTTP/browser loopback access timed out in this session. Browser visual acceptance remains unfinished.
- All five sports have current featured-market observations; all 26 requested market categories remain visible. No empirical model is approved.
- Historical access rechecked: HTTP 401. No historical prices fabricated. Raw full-season CFBD response with 3 invalid lower-division results was excluded; separate FBS query passed.
- CFB schedule-first coverage and source-recomputed rolling integration implemented for captured queries. Complete real feature sets remain zero; multi-query rolling assembly is unfinished.
- Product milestones and their exact blockers are in TASK_STATE.json / PRODUCT. No private balances, datasets or credentials are published.
- GitHub read works, but local Git push fails authentication/permission and connector write returns HTTP 403. Remote work is unchanged. Clean installed-package suite also passes all 195 tests.
