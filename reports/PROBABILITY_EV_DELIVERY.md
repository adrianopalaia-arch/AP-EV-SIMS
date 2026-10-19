# Probability and EV display delivery

Verified 2026-10-15T05:04:30.209901+00:00. The dashboard now separates market-derived calculations from AP model forecasts. No layout redesign, automatic wager placement, model approval, or bankroll-rule changes.

## Working local demonstration

Recalculated 5852 real archived quote sides across 159 events without API calls. All 5852 sides had exact same-snapshot opposite pairs. 4388 sides have unconditional market-baseline EV under standard settled-game/no-push conventions; 1464 have unknown push mass and retain null unconditional EV. Those counts describe archived market observations, not training, validation or profitable picks.

Example quotes captured 2026-10-15T03:42:44Z (October 14, 10:42:44 PM America/Chicago). They are historical observations and were STALE_PRICE at this demonstration. The model fields remain null.

| Game / selection | DK odds | Break-even | No-vig | Market EV | Conditional non-push EV | p_push |
|---|---:|---:|---:|---:|---:|---:|
| East Carolina Pirates @ UAB Blazers / East Carolina Pirates h2h | -205 | 67.213% | 64.473% | -4.077% | -4.077% | 0.000% |
| East Carolina Pirates @ UAB Blazers / East Carolina Pirates spreads -5.5 | -108 | 51.923% | 49.567% | -4.538% | -4.538% | 0.000% |
| Memphis Tigers @ Tulane Green Wave / Memphis Tigers spreads -7.0 | -112 | 52.830% | 50.433% | Unavailable | -4.538% | Unavailable |
| East Carolina Pirates @ UAB Blazers / Over totals 47.5 | -110 | 52.381% | 50.000% | -4.545% | -4.545% | 0.000% |

The current DK demonstration has no integer-total example; integer totals and spreads are both covered by constructed mechanics tests. Full exact quote/capture/event times, opposite prices, source snapshot IDs and hashes are retained in outputs/probability_ev_demo.json. All underlying provider payloads stay in ignored local storage.

## How to use

Reload the existing dashboard at http://127.0.0.1:8501/. **Recalculate** uses the current immutable local archive without provider requests. **Refresh Quotes** requests selected sports subject to the existing credit ceiling, reserve, cooldown and refresh lock. Automatic price refresh remains optional. Refreshing screen/calculation timestamps does not make source data fresh.

Columns: Sport, Game, Market, Selection, Book, Line, Odds, Break-even %, Market no-vig %, Market-baseline EV %, AP raw probability %, AP calibrated probability %, AP p_low %, AP model EV %, Data quality, Quote age and Status/PASS reason. Additional columns retain probability basis, conditional market EV, both push probabilities, period and source/event timestamps.

Market probabilities are never copied into AP columns. A row without a model says MARKET BASELINE ONLY. Stale prices preserve their historical calculations but show PASS: STALE_PRICE. Started or impossible-timestamp observations remain withheld from the pregame display.

## Calculation semantics

- American odds use the specified exact implied-probability and decimal-payout formulas.
- Pairing requires the same provider, sport, event/start, book, market, period, source snapshot/hash, quote and availability time, and settlement-rule identity. Spreads require equal and opposite lines; totals require equal lines. Duplicate/ambiguous sides, invalid prices or a missing opposite side prevent no-vig/EV calculation. A valid single side still retains break-even probability.
- No-vig is proportional two-side normalization. For push-capable lines, it is conditional on non-push; quotes alone do not identify push probability. Integer spreads/totals, NFL two-way ML and partial-game ML never receive an invented zero push.
- Unconditional EV is p_win × (decimal − 1) − p_loss, with p_push preserved separately. With unknown push mass, unconditional EV is null. Conditional non-push EV is separately labelled and is not a claim about return per original stake.
- Quarter-line/unknown payout rules do not receive binary-market EV. Standard full-game no-push calculations exclude voids and do not certify bookmaker settlement or execution. UNKNOWN_SETTLEMENT_RULE remains a PASS reason.
- Same-book no-vig baseline EV generally reflects the bookmaker margin. It is not an independent sports edge.

Provider market keys and separate period markets follow [The Odds API market definitions](https://the-odds-api.com/sports-odds-data/betting-markets.html). The displayed formulas and strict pairing are implemented locally in src/ap_evsims/display_pricing.py.

## Existing AP model pipeline

The CFB ridge/discrete-score model, calibration machinery, model bridge and Phase 1 decision gates are unchanged. An optional ignored local file data/models/dashboard-models.json can bind existing fitted artifacts to their original provider-backed JSONL training datasets:

```json
{"models":[{"artifact":"models/existing-artifact.json","training_dataset":"normalized/existing-training.jsonl"}]}
```

These are documentation placeholders, not supplied data. Dataset availability/result/price/feature provenance, training cutoff, event uniqueness and training fingerprint are checked. The original training recipe is reproduced and its fitted artifact identity must match; a self-consistent altered coefficient/hash is insufficient. Calibration additionally requires calibration_fit_dataset and calibration_selection_dataset paths, verified source data, disjoint events and regeneration through the existing OOS calibration selection with the normal minimum sample policy. Missing/unverifiable calibration remains null. No real-data/validated flag bypasses these checks.

At inference, the current canonical CFB matchup and complete required features must verify against raw sources. The display records actual computation time after quote availability and before start through a research-only context; historical pipeline timestamp semantics remain unchanged. Raw/calibrated research EV uses the current exact price and the model's outcome mass. A calibrated conditional probability retains the raw model's push estimate; that push estimate is not independently certified. Any produced p_low remains an unvalidated diagnostic with coverage explicitly unverified. Model fields can never set phase1_eligible, emit CORE/edges, create a stake or authorize a wager.

## What remains unfinished

There are zero trained real artifacts, zero joined training tables and zero complete verified current CFB feature sets in this checkout. Consequently no new model was fitted and no empirical AP probabilities or performance metrics were manufactured. The requested interpretable research fit is blocked on sufficient timestamp-safe real prior-game observations; the existing simple baseline is ready to reuse when those inputs exist. Historical Odds API entitlement and historical feature availability remain separate blockers. Other sport predictors/advanced-stat/availability feeds remain unfinished as previously documented.

## Verification

**208 passed, 0 failed, 0 skipped.** All prior 197 tests (including the original 195) remain passing. Eleven new tests cover moneyline arithmetic, normalization, integer/half/quarter lines, exact pairing, missing/invalid odds, stale quotes, price movement, offline recalculation, UI columns, preliminary-model authority, absent calibration/p_low, synthetic-artifact rejection and coefficient reproduction. No fixture contributes any real demonstration or performance metric.

Real-data Streamlit AppTest rendered 1,622 DK/FD sides, all requested columns, null AP fields and zero qualified edges/models. Browser visual acceptance remains user-operated. All 18 frozen Phase 1 files match baseline hashes; commit 6b20b15 remains an ancestor. Existing provider credentials and private wager records remain ignored and excluded from Git.

Files in this checkpoint:

- src/ap_evsims/display_pricing.py
- src/ap_evsims/research_display.py
- src/ap_evsims/product.py
- src/ap_evsims/warehouse.py
- src/ap_evsims/dashboard.py
- tests/test_display_pricing.py
- reports/PROBABILITY_EV_DELIVERY.md
- reports/MORNING_CARD.md
- TASK_STATE.json
- PHASE2_PROGRESS.md
- outputs/last_update.json
- outputs/cfb_universe.json
- outputs/latest_passes.json
- outputs/provider_status.json
- outputs/probability_ev_demo.json

## Git delivery

Commit and push are attempted after staged-content secret scanning. Previous session writes were blocked by authentication/permission; the actual result is reported in the final response and ignored local data/evaluations/probability-ev-push.json. No force-push or reset.

Exact manual PowerShell retry if needed:

```powershell
& 'C:\Program Files\Git\cmd\git.EXE' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```
