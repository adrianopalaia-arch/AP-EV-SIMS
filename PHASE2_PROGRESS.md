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

## Delivery verification 2026-10-14 19:41 America/Chicago

195 tests pass; 6b20b15 preserved; 18 frozen files unchanged. Current CFBD/Odds access verified; historical odds HTTP 401. Current card: 159 events. No feature code changed. Exact launch and push commands: reports/DELIVERY_VERIFICATION.md.

Delivery checkpoint `c941707` committed safely; push blocked. Manual push command saved in reports/DELIVERY_VERIFICATION.md. Final metadata checkpoint follows; no feature changes.

## Focused audit and pregame refresh checkpoint 2026-10-15T03:44:43.053319+00:00

- 197 passed, 0 failed, 0 skipped; original 195 preserved. All 18 frozen Phase 1 files and ancestor 6b20b15 preserved.
- Dated October 14 public audit saved. Three event outcomes verified; one pending canonical final status. No confirmed model forecasts existed to score. Original recommendation timestamps/receipts remain blockers; private wager records are ignored and excluded from publication.
- Optional pregame price refresh added to the active dashboard session, using existing cadence/quota/locking. Started games and impossible timestamps are withheld even with cached data. Failure retry backoff tested.
- CFB/NHL real current-price payloads refreshed. NFL/MLB request budget exhausted; NBA cached by cadence. No API cap increased. Advanced-stat, availability and starter feeds remain unavailable; model evaluation sample zero.
- Real-data Streamlit AppTest passed. Reload and enable the sidebar price-refresh switch. Details: reports/PREGAME_REFRESH.md. This is a focused display/price update, not an additional model build.
- Next dependencies: verified advanced-stat/availability feeds, original audit evidence, canonical pending result; historical odds entitlement and feature availability still block empirical validation.

## Probability/EV display checkpoint 2026-10-15T05:04:30.209901+00:00

- Completed strict same-book/snapshot/period/line pairing, market break-even/no-vig probability, push-aware market EV, explicit conditional EV, and separate AP research columns.
- Recalculate is local-only; Refresh Quotes retains quota/cooldown controls. Stale prices keep historical calculations and PASS. Missing sides retain only valid single-price math.
- Real demonstration: 5852 paired sides, 4388 unconditional market EV values, 1464 unknown push masses. No API calls; zero AP forecasts or real evaluation observations.
- Existing trained-artifact display requires provider-backed training reproduction and verified current features. Calibration provenance is separately checked. No probability/EV bypasses Phase 1; no fake p_low.
- Full suite: 208 passed, 0 failed, 0 skipped; 18 frozen files and 6b20b15 preserved. Real-data Streamlit AppTest passed.
- Unfinished: sufficient timestamp-safe real training data/features before the first AP baseline fit; calibrated OOS evaluation and uncertainty coverage. Detailed report: reports/PROBABILITY_EV_DELIVERY.md.


## CFB verified training-data checkpoint 2026-10-16T01:59:33.344672+00:00

- 228 tests passed; 0 failed; original 208 tests and all 18 frozen Phase 1 files preserved.
- CFBD authentication succeeded. Six 2026 weekly play queries saved immutable payloads and hashes; 142879 raw play rows. Remaining CFBD quota: 970. No Odds API requests or purchases.
- Multi-query revision-aware assembly and replayable feature recipes completed. 57,978 eligible prior plays across 448 games; typed JSONL/Parquet stored locally.
- 211 upcoming matchups have the four-feature research baseline. Complete Phase 1 feature sets remain zero. PPA is not EPA.
- 383 completed FBS games remain in the eligibility denominator. Two have qualifying archived DK prices; both lack sufficient prequote play history. The other 381 have no qualifying archived price.
- Existing walk-forward runner attempted a real-provider dataset and correctly blocked at zero training rows. No model fitted, forecasts produced, or empirical metrics invented.
- Earliest dependency: actual pregame feature/price snapshots with settled outcomes. Historical odds last returned 401; restoring odds alone would not establish historical feature publication times.
- Report and commands: reports/CFB_TRAINING_VALIDATION.md. Raw data, databases and .env remain local and ignored.

Implementation checkpoint `7d991e6` saved and secret-scanned. Real archived-data Streamlit AppTest passed. Push attempt failed; no local work was lost. A delivery-metadata checkpoint and final non-force push follow.


## Predictive edge checkpoint 2026-10-15T23:38:13.921005-05:00

249 tests passed; 0 failed; 18 frozen Phase 1 files unchanged. Existing commits preserved.

Completed: paper candidate/rejection ledger, ex-DK consensus, separate price stages, strict near-start CLV, revision-aware paper settlement, paired diagnostic scores, model feed repairs, three report views, dashboard paper panel and current quota reporting.

Real capture: 8 candidates across 3 games; 816 versioned quote/model observations, including repeated quotes after freshness changed. Zero settlements, forecasts, calibrated forecasts and validated models. $22 reference; $0 cash committed; all PASS.

Fresh CFBD/current odds: HTTP 200; DK and FD present. Historical odds: HTTP 401, no historical date established. Odds credits remaining: 419. One pre-existing malformed CFBD games snapshot remains excluded.

Next dependency: actual pregame feature/price joins and settled prospective evidence. GitHub Actions data collection is blocked on private durable execution/storage and is not running. Full delivery and alternative historical-source findings: reports/PREDICTIVE_EDGE_DELIVERY.md. Git push/PR outcome follows after the safety scan.

Push result: local Git authentication unavailable. Connector code writes and PR #1 update both HTTP 403. Feature checkpoint de85f9751b732d351f00479b2f3d4c1c27f9c098 remains safely committed locally; existing PR does not contain it yet. Manual push command is in reports/PREDICTIVE_EDGE_DELIVERY.md.


## Multi-sport real-model checkpoint 2026-10-16T05:23:02.576787+00:00

283 tests pass; 18 frozen Phase 1 hashes unchanged. CFB trained on 1,442 prior scores, evaluated 1,086 games, MAE 14.5269 versus 16.2073; 59 future forecasts frozen. Real NFL/NBA/NHL/MLB opportunity models executed; per-market results and failures are in reports/MULTISPORT_PROP_EVIDENCE.md. NFL did not improve MAE. No models are validated. Current prop prices captured for four sports, NHL returned no props. Next: current identities/roles, prospective prop freeze and settlement/CLV. Git push attempted below; development continues independently.

## Executed all five sports â€” 2026-10-16T05:42:35.450239+00:00

295 tests pass. Published 353 previously frozen real-data forecasts, 353 marginal simulation runs and 14,120,000 draws. No new frozen observations or settled prospective evidence. CFB refresh succeeded; other refreshes hit daily quota. CORE remains disabled. See reports/EXECUTION_RESULTS.md and outputs/execution_status.json. Joint game-state simulation and empirical betting calibration remain incomplete. Source/test work is preserved, not staged in this output-only checkpoint.

Git checkpoint: results commit `921e1f0586c860eb403d8936b294aa28b916d3fa` is local. Shell push authentication unavailable; connector write HTTP 403. Verified remote remains `6db215e00b5d42b8d7f94b556985a97f44104d75`. Final non-force retry follows the delivery-receipt commit.

## Prospective market research â€” 2026-10-16T15:04:43.655221+00:00

244 exact-side/line/book research records; 8 positive conditional-EV NBA watchlist entries, all with stale prices and PASS decisions. NHL shots access now yields 45 pairs (19 DK / 10 FD), using the final permitted credit: daily usage 24/24. NFL opportunity models fail the recent-average benchmark and are removed from ranking; 120 separate benchmark-reference forecasts frozen. MLB expanded by 18 currently quoted hitters through 54 real source requests, producing 36 additional forecasts (38 total); hits/TB each train on 7,816 appearances and evaluate on 5,410. Current-roster survivor selection is disclosed. All availability, quote and forecast clocks are preserved; NHL/MLB start conflicts block associated probability/EV. CFB source hashes and all 18 Phase 1 protected files unchanged. 316 regression tests pass. No prospective settlements or validated betting edges.


Checkpoint delivery 2026-10-16T15:09:08.948370+00:00: 316 tests passed, 0 failed. Safe source, tests and results saved in commit `bb0f5d98dc44bd0c1b5c721985ad188de7d8595e`. Push failed: `GITHUB_AUTHENTICATION_UNAVAILABLE`. Remote branch verified at `6db215e00b5d42b8d7f94b556985a97f44104d75`; new results are local only. No force push or reset was used.


P0 executed 2026-10-17T02:13:21.407745+00:00: expanded all five sport histories; 16 prop challengers evaluated, 333 new-version forecasts frozen, 15720000 marginal simulation draws. Detailed before/after: reports/P0_MEASURED_RESULTS.md. No CORE approval.


P0 checkpoint 2026-10-17T02:26:33.770670+00:00: see reports/P0_MEASURED_RESULTS.md and outputs/p0_market_refresh.json. Existing forecasts and simulation records retained. No CORE approval.


P0 checkpoint 2026-10-17T02:29:15.159230+00:00: see reports/P0_MEASURED_RESULTS.md and outputs/p0_market_refresh.json. Existing forecasts and simulation records retained. No CORE approval.


P0 freshness checkpoint 2026-10-17T02:30:04.867982+00:00: 351 tests passed, zero failed; all 389 original forecasts and 18 Phase 1 files verified. NHL crosswalk resolved for research; MLB postponement remains blocked. Zero new draws/forecasts in refresh; zero settled priced evidence, zero validated edges. See reports/P0_FRESHNESS_DELIVERY.md.


P0 checkpoint 2026-10-17T02:32:09.172684+00:00: see reports/P0_MEASURED_RESULTS.md and outputs/p0_market_refresh.json. Existing forecasts and simulation records retained. No CORE approval.


P0 freshness checkpoint 2026-10-17T02:32:11.360605+00:00: 351 tests passed, zero failed; all 389 original forecasts and 18 Phase 1 files verified. NHL crosswalk resolved for research; MLB postponement remains blocked. Zero new draws/forecasts in refresh; zero settled priced evidence, zero validated edges. See reports/P0_FRESHNESS_DELIVERY.md.

Git delivery 2026-10-17T02:32:37.057376+00:00: local source 5d357c6dfabba8392b3ec2954049bebdd014ecb5; remote bd4a8e5862e038c7ae77c71e50873f08dc234547; local push authentication unavailable and connector write HTTP 403. Delivery receipt committed locally.


### P0 reliable engine — 2026-10-18T03:24:07.788450+00:00

378 tests passed, 0 failed. All 389 original forecasts and 18 Phase 1 files verified. Real prospective scoring: 161 forecast records across 45 games. Eight fixed-Over FanDuel comparisons scored in one game; independent consensus, qualified CLV and ROI remain unavailable. Current NHL SOG loses its simple MAE/RMSE baseline. No model promoted, no new training or Monte Carlo draws. Native scheduler install failed at CIM; two standalone Codex fallback executions verified with exit 0, but their provider network access was blocked. See reports/P0_RELIABLE_DELIVERY.md and outputs/reliable_delivery.json.

Code/results commit 23be499b9adeb83b80f63badd958b4aa494bd23d saved. Git push blocked (credentials unavailable); GitHub connector blob write returned 403. Verified remote remains 2b448643c128b14e49c0ae7acaf6cacb990e598b. No force-push or reset.

## NFL full-slate repair — 2026-10-18

Completed the 12-game schedule-first sweep. Coverage increased from one NFL game to 12; 12 independent game forecasts, 1,494 prop forecasts, 1,600 price comparisons. Initial collection spent 63 credits; 280 remain. All quotes expire after 180 seconds. Latest archived recalculation has 0 fresh comparisons. All candidates PASS.

404 tests passed; both supplied 12-game acceptance modes passed. Original 389 forecasts and 18 Phase 1 files verified unchanged. Current game model trains on 803 prior outcomes; chronological evaluation has 1,951 games. Ridge MAE 10.4191 beats home-field 11.0790 but does not beat Elo MAE 10.4112. No betting validation.

See reports/NFL_FULL_SLATE_SWEEP.md and outputs/nfl_sweep_delivery.json for all games, role evidence, rejections, quota, and remaining blockers. Default NFL delivery now uses all canonical events; explicit complete NFL sweep: `python -m ap_evsims.p0_refresh --nfl-date 2026-10-18 --collect --daily-cap 96`.
