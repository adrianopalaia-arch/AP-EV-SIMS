# Red-team report

Generated: 2026-10-14T07:26:48.660265+00:00
Full suite: 154 passed; 0 failed. Critical unresolved audit categories: 13.
FAIL below includes missing evidence and incomplete implementation, not just failing unit tests. Mechanics PASS does not approve a market.
All markets remain RESEARCH_ONLY. No real model evaluation or prospective performance sample exists.

| ID | Failure mode | Tested | Result | Severity | Fix/control | Remaining risk | Tests |
|---:|---|---|---|---|---|---|---|
| 1 | EXECUTION REALITY | True | FAIL | CRITICAL | Stale/suspended/unverified execution rejects; slippage arithmetic | No historical execution proof or realistic empirical backtest. | tests/test_governance_execution.py |
| 2 | DRAFTKINGS / FANDUEL MARKET IDENTITY | True | FAIL | CRITICAL | Exact alias/start matching and market/rule identity | Player mappings and actual book rule versions absent. | tests/test_identity.py |
| 3 | MARKET AVAILABILITY BIAS | True | FAIL | HIGH | Eligible/included strata and selection-bias diagnostic | Complete historical eligible universe not ingested. | tests/test_diagnostics_redteam.py |
| 4 | MULTIPLE TESTING / DATA SNOOPING | True | FAIL | HIGH | Immutable experiment specifications and variant count | Retrospective registration cannot prove an analyst never saw a holdout. | tests/test_governance_execution.py |
| 5 | FINAL HOLDOUT LOCK | True | FAIL | CRITICAL | One-use holdout consumption and overlap rejection | No genuine prospective holdout has elapsed. | tests/test_governance_execution.py |
| 6 | SURVIVORSHIP BIAS | False | FAIL | HIGH | Missing rows are retained as PASS where evaluable | Retired/traded/minor-league population coverage not audited. |  |
| 7 | ROSTER IDENTITY / NAME COLLISIONS | True | FAIL | CRITICAL | Player markets require player and team IDs | Real cross-provider player roster mappings absent. | tests/test_governance_execution.py |
| 8 | STAT CORRECTIONS | True | FAIL | CRITICAL | Append-only corrected results and account corrections | Book-specific correction timing not integrated. | tests/test_replay_settlement.py |
| 9 | TIMEZONE / DST / DATE BOUNDARY | True | PASS | HIGH | UTC normalization, DST offset, naive-time rejection | Host/provider clock offsets are not measured. | tests/test_governance_execution.py |
| 10 | GAME POSTPONEMENTS / CANCELLATIONS | True | FAIL | CRITICAL | Exact start changes force remapping; cancellations void | Schedule revision histories need live observation. | tests/test_identity.py |
| 11 | SETTLEMENT RULES | True | FAIL | CRITICAL | Unknown, regulation-only, pitcher and participation rules reject | Actual book rule documents and identities unavailable. | tests/test_replay_settlement.py |
| 12 | ALT LINES | True | FAIL | HIGH | CFB line monotonicity and discrete push mass | Prop alternate-line distributions not fitted. | tests/test_phase2_cfb.py |
| 13 | PRICE / LINE JOINT CONSISTENCY | True | PASS | HIGH | Line/rule/start changes require new probability | No empirical execution observations. | tests/test_governance_execution.py |
| 14 | LATENCY | True | FAIL | HIGH | Latency ordering and P50/P90/P99 diagnostic | No real candidate latency or edge half-life sample. | tests/test_diagnostics_redteam.py |
| 15 | STALE LINEUP / ROLE INFORMATION | True | FAIL | CRITICAL | Event-specific confirmation age and restrictions | No historical availability/role archive. | tests/test_sport_contracts.py |
| 16 | WEATHER REVISION RISK | True | FAIL | CRITICAL | Current weather cannot be backdated | Historical forecast revision proof and sensitivity analysis absent. | tests/test_phase2_history.py |
| 17 | MARKET-MAKER INFORMATION | False | FAIL | HIGH | No automatic contrarian movement signal enabled | Market-disagreement penalty must be estimated from untouched data. |  |
| 18 | CLOSING LINE VALUE CAVEAT | True | FAIL | HIGH | Point CLV and same-line price CLV remain separate | No qualifying outcome/close evaluation sample. | tests/test_phase2_backtest.py |
| 19 | BOOKMAKER HOLD / VIG CHANGES | True | PASS | HIGH | Paired-price timing tolerance and exact same line | Snapshot presence is not execution proof. | tests/test_governance_execution.py |
| 20 | CORRELATED FEATURE DUPLICATION | False | FAIL | HIGH | Feature/source ablation comparison requires matched rows | Real feature correlation and incremental contribution unmeasured. |  |
| 21 | ENSEMBLE FALSE CONFIDENCE | True | FAIL | HIGH | Correlated prediction errors reject ensemble weight | No real ensemble independence evidence. | tests/test_phase2_backtest.py |
| 22 | REGIME SHIFT | False | FAIL | HIGH | Group diagnostics preserve season/regime distinctions | Regime drift thresholds and empirical regime samples absent. |  |
| 23 | SMALL SAMPLE STARS | True | FAIL | HIGH | Model minimum training sample; props remain disabled | Sport-specific prior estimates and role shrinkage not fitted. | tests/test_phase2_cfb.py |
| 24 | ROLE CHANGE DETECTION | False | FAIL | HIGH | Unknown or limited roles fail contract validation | Structural-break detection not fitted. |  |
| 25 | INJURY RETURN / LIMITATION | True | FAIL | HIGH | Unverified limitations cannot use normal opportunity | Actual restriction/injury return data absent. | tests/test_sport_contracts.py |
| 26 | BLOWOUT / GAME-STATE RISK | True | FAIL | HIGH | Scenario probabilities cannot bypass calibration | Empirical blowout/script mixtures unmeasured. | tests/test_phase2_calibration.py |
| 27 | COACHING / SYSTEM CHANGES | False | FAIL | HIGH | No coach/system effect enabled | Timestamp-safe coaching/system regimes absent. |  |
| 28 | PROVIDER SCHEMA DRIFT | True | FAIL | CRITICAL | Odds schema and pair validation; feature units explicit | CFBD generic records need per-endpoint semantic schema versions. | tests/test_warehouse.py |
| 29 | PROVIDER OUTAGE / PARTIAL RESPONSE | True | PASS | CRITICAL | 401/403, invalid/error payloads, quota limits fail closed | Long-run outage recovery remains unobserved. | tests/test_provider_validation.py |
| 30 | UNIT / SCALE ERRORS | True | FAIL | CRITICAL | Explicit units, fractions, ranges and discrete roles | Provider-to-feature mappings still require verified conversions. | tests/test_sport_contracts.py |
| 31 | NUMERIC INSTABILITY | True | PASS | CRITICAL | Finite bounded probabilities; finite JSON; stable sigmoid | Extreme empirical tails unvalidated. | tests/test_phase1.py |
| 32 | CLASS IMBALANCE | True | FAIL | HIGH | Proper scores and single-class calibration rejection | Rare-event calibration requires real tails. | tests/test_phase2_calibration.py |
| 33 | PUSH / VOID IMPACT ON ROI | True | PASS | HIGH | Cash/bonus journals and push/void denominators | External account/exposure reconciliation not connected. | tests/test_accounting_promotions.py |
| 34 | PROMOTIONS | True | PASS | HIGH | Boost/free-bet/no-sweat payoff separate from probability | Real terms and conversion assumptions unverified; research only. | tests/test_accounting_promotions.py |
| 35 | LIVE BETTING DANGER | True | PASS | CRITICAL | Pregame cannot qualify as live | No synchronized live model/state/quote feed; live disabled. | tests/test_engine.py |
| 36 | DATA-SNOOPING FROM MISSES | True | FAIL | HIGH | Postmortem hypotheses never auto-modify models | Independent hypothesis evaluation awaits data. | tests/test_governance_execution.py |
| 37 | BACKTEST REALISM | True | FAIL | CRITICAL | Slippage and execution gates available | Ideal versus realistic end-to-end empirical comparison absent. | tests/test_governance_execution.py |
| 38 | BOOTSTRAP UNCERTAINTY | True | FAIL | HIGH | Proper-score intervals resample weeks | ROI cluster intervals require actual qualified selections. | tests/test_phase2_backtest.py |
| 39 | MONTE CARLO BANKROLL STRESS | True | FAIL | HIGH | Hypothetical bankroll path, drawdown and ruin stress | No empirical joint-outcome distribution; scenario assumptions explicit. | tests/test_diagnostics_redteam.py |
| 40 | KELLY ESTIMATION RISK | True | PASS | HIGH | Quarter-Kelly ceiling and extra-error sensitivity | No empirically approved probabilities or stakes. | tests/test_diagnostics_redteam.py |
| 41 | SAME-DAY EXPOSURE | True | PASS | CRITICAL | Atomic persistent team/player/game/correlation exposure | All external open slips must be imported; no actual account provided. | tests/test_phase1.py |
| 42 | BETTER-THAN-MARKET REQUIREMENT | True | FAIL | CRITICAL | Registry requires proper-score advantage versus market | No empirically qualifying model. | tests/test_phase1.py |
| 43 | NEGATIVE CONTROL TESTS | True | FAIL | HIGH | Noise features fail unseen advantage on mechanics fixture | Full provider-history negative-control reruns blocked. | tests/test_diagnostics_redteam.py |
| 44 | LABEL SHUFFLE TEST | True | FAIL | HIGH | Shuffled-label training loses unseen fixture signal | Full sport-specific shuffled-label backtests blocked. | tests/test_diagnostics_redteam.py |
| 45 | TIME-SHIFT LEAKAGE TEST | True | PASS | CRITICAL | Future features, revisions and forbidden postgame fields reject | Provider availability proof still required; caller labels alone insufficient. | tests/test_diagnostics_redteam.py |
| 46 | ADVERSARIAL MARKET TEST | True | PASS | HIGH | Adverse exact-line changes demand recalculation | No current eligible model can issue a recommendation. | tests/test_governance_execution.py |
| 47 | MIRACLE GAME TEST | True | FAIL | HIGH | Finite nonzero CFB tails; no outcome-triggered retraining | Requested real extreme-game reconstructions lack historical snapshots. | tests/test_phase2_cfb.py |
| 48 | FALSE CONFIDENCE AUDIT | True | PASS | HIGH | PASS-only unvalidated feed; no guaranteed outcome classifications | Legacy documentation may quote prohibited terms as warnings, not classifications. | tests/test_handoff_cycle.py |
| 49 | RED TEAM REPORT | True | PASS | HIGH | All 50 requested categories enumerated | A complete inventory is not a successful readiness audit. | tests/test_diagnostics_redteam.py |
| 50 | READINESS GATE | True | PASS | CRITICAL | Untested critical failures prohibit readiness | No real/prospective evidence; all markets RESEARCH_ONLY. | tests/test_diagnostics_redteam.py |
