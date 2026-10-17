# Phase 1 delivery

Local implementation based on the supplied ZIP. The named GitHub repository was empty at clone time. Nothing has been pushed and no wager placement exists.

## Behavior

- ValidationRegistry computes Brier/log loss from timestamped binary OOS observations, fingerprints the canonical dataset and report, and stores an immutable-by-API report. Eligibility binds sport, market, model version, mode, training cutoff, dataset fingerprint, evaluation window and expiry. Unregistered/tampered reports, reuse across a mismatched identity, insufficient samples, evaluation unavailable at feature time, and expired evidence fail closed. The same valid report can support multiple forecasts of its own model; candidate/position IDs prevent duplicate reservation.
- Each decision retains event start, both quotes, availability, feature snapshot, prediction and decision timestamps. Timezone-aware values are mandatory. No future tolerance exists. Availability <= features <= prediction <= quote <= decision is required. Opposite prices must be contemporaneous and match the market line. Live mode has a separate identity and tighter age limits.
- ExposureLedger uses SQLite BEGIN IMMEDIATE transactions. Reservations and open bets count across process restarts/cards. GAME, TEAM, PLAYER and SLIP groups use a shared risk cap. Cash and bonus budgets are separate; correlated exposure spans both. Existing external bets can be imported even above current caps so real exposure cannot be hidden. Transitions are manual: reserved -> open/cancelled; open -> settled/void. A reservation is never a placed bet. Reservations do not expire automatically.
- SnapshotStore preserves observed and available timestamps; as-of lookup excludes late arrivals and future updates. Six provider protocols and FixtureProvider cover odds, official availability, weather, CFB, NHL, and results. Each CFB/NHL feature requires a value, source and availability timestamp.
- decision.decide is the Phase 1 gate and always logs PASS or RESEARCH_CANDIDATE. It uses conservative probability EV and quarter Kelly against explicit cash bankroll, capped at 1% per shared group and 2% total open cash exposure by default. Those caps are policy defaults, not empirically justified optimal stakes. A successful research candidate is reserved atomically. Bonus EV and push-capable CFB integer lines fail closed.
- Legacy source remains. Legacy CSV screen cannot qualify a pick through its caller-authenticated ValidationReport. Legacy portfolio/parlay utilities are not the Phase 1 decision boundary.

## CLI formats

`evaluate` takes JSON with sport, market, model_version, mode, training_cutoff, expires, observations. Each observation includes id, those four identity fields, feature_time, prediction_time, quote_time, event_start, outcome_time, p, market_p, outcome (0/1). It accepts observations, never supplied performance metrics or validated=true.

`decide` takes JSON with candidate (ResearchCandidate fields) and report_id. The registry must already contain the exact matching evidence. Use one persistent exposure database per bankroll across cards, and import all externally placed bets before screening. Teams, players and correlated-slip groups must be canonical and complete. Cash bankroll is supplied explicitly; settlement does not yet update a cash account balance.

Synthetic examples exercise the API only. They are not sporting predictions or empirical validation. Tests use a local writable temporary directory on this Windows sandbox.

## Files changed relative to the ZIP

Modified: .gitignore, README.md, src/ap_evsims/{calibration,cli,ledger,odds,schemas,screening}.py, tests/test_engine.py.

Added: AUDIT.md, PHASE1.md, REPOSITORY_MAP.txt, TEST_RESULTS.txt, src/ap_evsims/{decision,exposure,features,integrity}.py, src/ap_evsims/providers/contracts.py, tests/test_phase1.py, examples/phase1-evaluation.json, examples/phase1-candidate.json.

All other baseline source, documents and examples were imported unchanged into the previously empty checkout. Bundled bytecode is ignored by Git. No working source was deleted.

## Remaining limitations

Local registry membership and hashes prevent accidental substitution and caller flags; they do not authenticate a dishonest dataset producer or a user directly modifying SQLite. A trusted evaluator, source manifest, signed approvals and access separation are still required. Timestamp assertions need real ingestion provenance. p_low is supplied, not yet estimated or coverage-validated. Strictly better aggregate scores and 300 observations are an early gate, not statistical evidence of an edge. Event dependence, duplicate economic observations and model-selection bias need a full evaluation pipeline.

Feature contracts currently enforce completeness/provenance and basic ranges, not every sport-specific semantic/range/unit rule. Weather/injury freshness is represented at candidate level; adapters still need source-specific retention policies. Price movement compares the feature quote/line to execution; no full movement analysis exists. Store access is as-of safe, but a complete backtester and mandatory snapshot-ID joins are not yet implemented. Persistent exposure requires accurate manual import and complete risk groups; correlations are categorical caps, not fitted joint distributions. Candidate JSONL and reservation SQLite are separate writes; a failed log write leaves a conservative reservation requiring reconciliation. No complete profit/loss/CLV settlement accounting exists. Live forecasting, actual sport models and API clients do not exist.

## Exact Phase 2 plan

1. Build a canonical ingestion manifest: event/market/selection/line/settlement identities, snapshot IDs, observed/available/ingested times, hashes, source-specific freshness, revision history and credential injection. Implement odds + official availability + weather adapters and recorded contract fixtures. Acceptance: missing opposite markets, late corrections, unconfirmed goalies and expired availability fail closed.
2. Build a reproducible rolling-origin evaluator with frozen training/evaluation boundaries and no event overlap. Persist actual predictions, outcomes and contemporaneous two-sided prices; reject duplicates and feature revisions unavailable then. Compute paired market Brier/log loss, calibration bins/intervals, uncertainty coverage, CLV, ROI confidence intervals and drawdown by market/version. Bind signed approval and immutable manifests to evidence. Acceptance: deliberately leaked and substituted datasets cannot qualify.
3. Implement CFB spread/total forecasts first using the complete contract, opponent adjustment fitted only on prior games, possession/pace and injury/weather effects. Model win/push/loss distributions at the exact line and stress parameter/model disagreement. Derive p_low from measured OOS uncertainty. Acceptance: integer lines settle correctly and odds changes alter EV/PASS deterministically.
4. Implement NHL shots/goalie/team forecasts next with confirmed goalie, shot/TOI/role and shared game state. Validate count distributions and tail probabilities separately per market and pregame/live mode. Acceptance: role/goalie uncertainty lowers probability or forces PASS; no recent hit-rate shortcuts.
5. Unify reservation and decision audit transactionally; add external-bet reconciliation, cash/bonus settlement balances, withdrawals/deposits, canonical team/player/slip groups, free-bet payout rules and restart recovery. Acceptance: concurrent/replayed cards cannot exceed budgets or hide open bets.
6. Run prospective paper decisions with frozen policy/model versions and record every PASS. Compare calibration and market edge with uncertainty; scale only after historical and prospective evidence supports it. NFL sides/totals/usage and MLB pitcher/hitter work follows CFB/NHL. Joint simulations/parlays remain research-only until independently validated.

There is no evidence here that the algorithm is profitable.
