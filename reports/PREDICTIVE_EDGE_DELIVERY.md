# Predictive edge rebuild: first delivery

This delivery repairs reporting and starts a prospective CFB market benchmark. It does not establish a betting edge. Existing models, validation gates, source archives and Git history are preserved. No cash bets are authorized.

## Working changes

- `paper_track --start-paper` starts an idempotent, persistent 100-candidate diagnostic. Repeated cards retain original predictions and record changed observations and PASS reasons. SQLite and detailed evidence stay under ignored `data/`.
- The cohort freezes one home/over direction per CFB event and full-game market at the first qualifying observation within 24 hours of kickoff. It requires a fresh paired DK price, a unique canonical CFBD game match, and at least two other contemporaneous books at the exact same line and period. Both sides and all rejected DK CFB observations remain in the audit. Different markets on one game are correlated, not independent trials.
- The benchmark is the median of each other book's two-way no-vig probability, excluding DK. It is never an AP model forecast or proof of an edge.
- True opening, first-observed, candidate, recommended and near-start prices have separate fields. An unknown true opener or unapproved recommendation remains null. Closing evidence requires an actual capture within five minutes before kickoff and an opposite-side pair. Older last observations and suspended markets cannot manufacture CLV. Price CLV is withheld across different lines; point CLV is separate.
- Official final CFBD scores use the existing settlement machinery with an explicit paper convention. Corrections and retractions append revisions. Integer-line pushes refund the hypothetical stake and do not enter binary probability scores. Cash settlement, costs and cancellation rules are not inferred.
- Brier, log loss and calibration compare models and the market on identical settled rows. Predefined sport/market/odds/probability bands remain descriptive. Missing models, calibrated probabilities and p_low remain null. Counterfactual home/over ROI and cost scenarios are labeled separately from unavailable actual cash and model-selected ROI.
- `latest_predictions.json` now publishes genuine verified research forecasts when available. It previously always published an empty array. Current zero forecasts still correctly produces an empty array. `latest_edges.json` remains empty until approval gates pass.
- Morning/lunch/evening reports and JSON feeds share an explicit hashed publication generation. Their names do not imply separate refreshes. The dashboard research tab exposes the paper diagnostic; fresh quota evidence overrides older collection summaries.

## Four evidence milestones

| Milestone | Current state | Required evidence |
|---|---|---|
| Reliable data | Partial; current prices and prior-game play archive work | Qualifying historical or prospective joins of prices, pregame features and final outcomes |
| Working predictions | Blocked; zero qualifying historical training rows and zero actual model forecasts | Chronological model training, evaluation and untouched holdout |
| Demonstrated value | Not established | Paired baseline comparisons, calibration, uncertainty coverage, executable-price/cost evidence |
| Prospective verification | Collecting real price observations; zero settlements so far | Completed paper cohort, frozen model forecasts when available, verified results and near-start quotes |

The 100-candidate phase is an initial diagnostic, not approval. A benchmark-only cohort cannot validate a model that made no forecasts. Do not change the cohort after seeing results; introduce a separately versioned prospective model cohort once genuine forecasts exist.

## Historical coverage investigation

Fresh checks: CFBD games and current NCAAF odds returned HTTP 200; DraftKings and FanDuel were returned. The historical NCAAF endpoint at `2025-10-04T16:00:00Z` returned HTTP 401 again. Current odds and historical access are separate entitlements. Earliest accessible historical date remains unestablished.

[The Odds API documentation](https://the-odds-api.com/historical-odds-data/) describes paid historical access, nearest-at-or-before snapshots and NCAAF coverage beginning in 2020. This documents provider capability, not our account's entitlement.

The local CFBD supplemental lines archive contains 95 games from a 2025 query, captured twice in October 2026. Returned line fields contain opening/final line values and moneylines, but no per-price historical availability timestamps or spread/total juice. Those responses cannot substitute for contemporaneous paired sportsbook snapshots. They remain supplemental, not qualifying prices.

[SportsDataIO's historical integration guide](https://sportsdata.io/help/historical-data-integration-guide) describes historical line movement and account-enabled access. Its [CFB endpoint documentation](https://sportsdata.io/developers/api-documentation/ncaa-football) marks odds access as subscription-required. No alternative credentials, entitlement, downloaded dataset or timestamp coverage has been verified here. No purchase was made. Free closing-only tables would not establish the prices available at an earlier decision time.

Owned prospective captures are usable from their actual capture times forward. They do not repair historical feature availability. Previously captured completed-game audit: 383 FBS matchups, 381 without a qualifying DK archive price, and two priced games without sufficient prequote play history. No model fit is fabricated to fill that gap.

## Remaining dependencies and operations

1. Continue bounded prospective captures and obtain final results and near-start prices for the frozen cohort. Already-started games and stale quotes remain excluded from executable cards.
2. Resolve timestamp-authentic historical features and price access, then fit the existing CFB spread/total baselines and run chronological evaluation. Advanced CFB injuries/depth/weather feature contracts remain incomplete.
3. Verify NHL goalie/news/team feature coverage before NHL moneyline fitting. Player props, NFL, MLB, NBA, live and parlay activation remain dependent on their own verified inputs and models. No new algorithm family is justified by this delivery.
4. GitHub Actions data collection is **not deployed**. The durable raw archive, quota state and paper ledger currently live only on this Windows machine; GitHub-hosted ephemeral runners do not have that store or its credentials. Publishing raw data/databases to this public repository or public workflow artifacts is prohibited. A private durable execution/storage connection must be established before scheduling the collector. A missing scheduler must never be presented as an active background service.
5. Scheduled GitHub workflows must be present on the default branch and may run late, per [GitHub's event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Three scheduled cards alone also cannot guarantee a quote within five minutes of each kickoff. Missing close coverage must stay visible.

No automatic retraining or model promotion is introduced. The existing chronological holdout, calibration, uncertainty, freshness, news and exposure requirements remain in force. Public compact progress is in `outputs/paper_tracking_status.json`; local full audit evidence is in `data/evaluations/paper-tracking-observations.json` and `paper-tracking-settlements.json`.

## Windows verification and use

Run in PowerShell:

```powershell
Set-Location 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests
& '.\.venv\Scripts\python.exe' -m ap_evsims paper_track --offline
```

Explicit bounded quote collection (maximum 24 daily credits, preserving the 50-credit reserve and existing cooldown):

```powershell
& '.\.venv\Scripts\python.exe' -m ap_evsims paper_track --refresh-quotes
```

Use `--start-paper` only to initialize a new local store; it does not reset an existing cohort. Paper tracking starts before capture, never by backdating old observations. Provider results refresh remains the existing explicit `sync_data --cfbd-year YEAR --cfbd-week WEEK --refresh-cfbd-games` command. Re-run `paper_track --offline` to reconcile newly archived results.

Dashboard:

```powershell
& '.\.venv\Scripts\python.exe' -m streamlit run '.\src\ap_evsims\dashboard.py' --server.address 127.0.0.1 --server.port 8501
```

Keep that PowerShell process running and open http://127.0.0.1:8501/.
