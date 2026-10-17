# AP EV/SIMS execution results

Executed: 2026-10-16T05:42:35.450239+00:00. Source commit: `6db215e00b5d42b8d7f94b556985a97f44104d75`.
All five existing research pipelines ran against local immutable real-data archives. No new market model or dashboard was added.
Source/test work in progress is preserved. This checkpoint publishes shareable outputs and reports only. Source-file hashes are in execution_status.json.

**353 frozen forecast records republished; 0 newly frozen this run. 353 marginal simulation runs, 706 replicates, 14,120,000 Monte Carlo draws.**
Monte Carlo draws are generated outcomes, not additional real observations. These are samples from existing residual PMFs, not jointly simulated games.
**0 validated edges. All CORE/cash approvals remain disabled. 0 prospective results settled.**

| Sport / market | Training rows | Chronological evaluation | Model MAE | Baseline MAE | Model RMSE | Baseline RMSE | CRPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| NFL receptions | 12332 | 6152 | 1.2836 | 1.2719 | 1.7163 | 1.7400 | 0.8785 |
| NFL receiving_yards | 12332 | 6152 | 16.7496 | 16.5414 | 23.5942 | 23.8903 | 12.0533 |
| NFL rushing_attempts | 12332 | 6152 | 1.3720 | 1.1432 | 2.6620 | 2.6111 | 0.9768 |
| NFL rushing_yards | 12332 | 6152 | 7.4874 | 6.5989 | 16.0560 | 16.0200 | 5.7681 |
| NFL passing_yards | 1510 | 733 | 68.2564 | 68.0111 | 86.5141 | 87.5476 | 48.7768 |
| NBA points | 79632 | 51938 | 4.7637 | 4.7590 | 6.1961 | 6.2607 | 3.3677 |
| NBA rebounds | 79632 | 51938 | 1.9531 | 1.9662 | 2.5585 | 2.5976 | 1.3747 |
| NBA assists | 79632 | 51938 | 1.3797 | 1.3861 | 1.8637 | 1.8918 | 0.9637 |
| NBA threes | 79632 | 51938 | 0.9159 | 0.9102 | 1.2609 | 1.2832 | 0.6254 |
| NHL shots_on_goal | 145238 | 96525 | 1.0375 | 1.0591 | 1.3398 | 1.3722 | 0.7054 |
| NHL goalie_saves | 8540 | 5597 | 5.9885 | 6.0866 | 7.7202 | 7.8341 | 4.2976 |
| MLB pitcher_strikeouts | 950 | 540 | 1.2913 | 1.2939 | 1.7631 | 1.7414 | 0.9228 |
| MLB pitcher_outs | 950 | 540 | 2.1340 | 1.8741 | 2.9093 | 2.7544 | 1.5436 |
| MLB hits_allowed | 950 | 540 | 1.1717 | 1.1856 | 1.5753 | 1.5920 | 0.8278 |
| MLB hitter_hits | 2451 | 1410 | 0.6635 | 0.6712 | 0.8086 | 0.8293 | 0.4028 |
| MLB total_bases | 2451 | 1410 | 1.1187 | 1.1373 | 1.5108 | 1.5441 | 0.7211 |
| CFB game_margin | 1442 | 1086 | 14.5269 | 16.2073 | 18.4755 | 20.5783 | 10.4068 |

Evaluation is chronological and uses only prior outcomes at each simulated forecast date. Historical records were downloaded later and may contain revisions: no claim of historical timestamp-authentic execution. Prop evaluation conditions on observed appearances and does not assess DNP probability. CFB uses a home-advantage baseline; props use the player recent-average baseline. Prop baseline CRPS has not been computed. All raw probabilities are uncalibrated.
NFL models did not beat their recent-average MAE benchmark. NBA rebounds/assists and both NHL models have lower MAE. MLB gains are small and its training universe is a predeclared 24-player cohort; pitcher outs worsened. CFB margin MAE improved, with 25-week block-bootstrap difference interval [-1.962, -1.419]. None establishes a price edge.

Monte Carlo convergence: DKW family-wise tolerance 0.017218; largest observed CDF error 0.012408; all passed = True. This verifies sampling precision only.

| Sport | Frozen forecasts / simulation runs | Event coverage | Missing requested results |
|---|---:|---|---|
| NFL | 120 | 1 upcoming events | TD props: no trained touchdown model |
| NBA | 124 | 1 upcoming events | PRA: no fitted joint points/rebounds/assists distribution |
| NHL | 48 | 1 upcoming events | player points: no trained points model |
| MLB | 2 | 1 upcoming events | HR props: no trained home-run model |
| CFB | 59 | 59 upcoming events | No additional requested model absent |

CFB: 59 forecasts; NFL: 120 player-market forecasts for HOU/JAX; NBA: 124 for BOS/DET; NHL: 48 for PIT/COL; MLB: 2 for one covered hitter in TB/CLE. Forecasts preserve their original freeze timestamps; rerunning does not create new evidence.
NHL official start 01:00 UTC versus book 01:10 UTC; MLB official start 00:00 UTC versus book 22:00 UTC the prior date. Those price identities are rejected. NHL returned no props. MLB pitcher examples for the selected future game are missing because the bounded training cohort does not cover its current pitchers.
All player participation, lineup/role and goalie confirmations remain insufficient for betting. NFL source-context lineage still needs the schedule manifest added to each model artifact. NHL/MLB event-time discrepancies require source reconciliation. MLB postseason settlement coverage is incomplete. Shared game-state effects, joint-market consistency, and joint/tail held-out validation remain unimplemented.

Price refresh: CFB captured 2,980 new quote sides through the bounded API call. NFL/NBA/NHL/MLB refreshes returned DAILY_QUOTA_BUDGET_LIMIT; remaining provider credits 399. The daily ceiling was preserved. Earlier prop prices remain explicitly timestamped and stale; no executable-price claim.
Historical Odds API access remains blocked by HTTP 401/free-plan entitlement from the last recorded probe. The public historical archive lacks provable quote availability timestamps; none of those prices qualify as historical execution evidence.

Tests: 295 passed, 0 failed. Software tests do not validate predictive accuracy.
Files: execution_status.json; simulation_execution.json; latest_predictions.json; model_status.json; research_rejections.json; prop_pricing_comparisons.json; per-sport research/prospective/settlement JSONs. Git push verification is reported separately after the commit attempt.

The current reports supersede earlier zero-model and unfinished-prop-freeze statements. Original reports are retained as historical checkpoints.

## Git publication result

Execution results committed locally as `921e1f0586c860eb403d8936b294aa28b916d3fa`. Git push failed: this session cannot obtain GitHub credentials. The connector write attempt independently returned HTTP 403, Resource not accessible by integration. Remote branch verified at `6db215e00b5d42b8d7f94b556985a97f44104d75`; it does not contain this execution. All shareable output files were secret-scanned. Source/test edits remain unstaged and intact. No reset or force push was used.
