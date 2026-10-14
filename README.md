# AP EV/SIMS 3.0

AP EV/SIMS 3.0 is a **research, calibration, and price-screening engine**. It is intentionally built to fail closed: missing prices, stale data, unknown lineup state, unvalidated model versions, live/pregame model mismatches, and unpriced correlations all cause `PASS`.

It does **not** promise profitable betting and it does not auto-place wagers.

## Local application

From this repository directory, using Python 3.11 or newer:

```powershell
python -m pip install -e .
```

Launch with:

```powershell
python -m ap_evsims dashboard
```

Open **http://127.0.0.1:8501**. In the existing Windows checkout, replace `python`
with `.\.venv\Scripts\python.exe`. The server binds only to localhost and disables
usage telemetry. Run the launch command in normal PowerShell if the Codex sandbox
cannot reach loopback. No terminal activation or credentials in command arguments
are required. Keep the server terminal running; Ctrl+C stops it.

The dashboard shows exact archived prices, DK/FD priority, no-vig market baselines,
all 26 requested market categories, CFB schedule coverage, provider status and
explicit PASS reasons. All models remain **UNVALIDATED**. The $22 reference unit
is configurable in the browser session; it never sets a bankroll or stake.
Unavailable player markets stay visible as **Await data**. Live mode and all
card builders are disabled until their independent eligibility requirements pass.

Put keys only in the ignored `.env`, using the names from `.env.example`.
The app reads them without displaying them. Missing credentials leave a usable
offline dashboard. Click Refresh to request current markets; the application
does not poll or place wagers in the background.

```powershell
python -m ap_evsims verify_providers
python -m ap_evsims daily_card --sports CFB,NHL,NFL,MLB,NBA --daily-credit-cap 48 --force-refresh
python -m ap_evsims daily_card --offline
python -m ap_evsims research_cycle --offline
```

`verify_providers` separately tests current and historical access (at most 13
estimated Odds API credits). Daily card defaults to a 24-credit daily ceiling and
50-credit reserve; the example explicitly raises the ceiling to 48. Manual forced
refreshes retain a 60-second cooldown. Provider response quota is recorded locally.
Historical HTTP 401/403 never triggers fabricated prices or automatic purchasing.

`daily_card` writes `outputs/latest_predictions.json`, `latest_edges.json`,
`latest_passes.json`, `model_status.json`, `provider_status.json`,
`cfb_universe.json`, `last_update.json`, and `reports/MORNING_CARD.md`. Zero qualified
models produces **NO QUALIFYING BETS**, empty predictions/edges, and explicit
market PASS records. Other-book comparisons remain in ignored local snapshots to
keep GitHub feeds small. Raw data, account balances and databases stay local.
The reader validates generation hashes before showing files together.

Current product limits: no approved empirical model artifact; historical odds
entitlement denied; insufficient verified rolling feature coverage. Research
algorithms and synthetic tests do not establish betting performance. See
`reports/PRODUCT_DELIVERY.md` for the tested build and exact remaining milestones.

Phase 2 checkpoint: local research infrastructure and 24 market contracts are
implemented. CFB spread/total/win research predictors exist, but **no real model
is calibrated or approved**. Other sport predictors are not fitted or implemented
beyond their contracts. Historical Odds API access returned HTTP 401 while current
access succeeded. Read `TASK_STATE.json`, `PHASE2_PROGRESS.md`, and
`OVERNIGHT_BUILD_REPORT.md` for the exact evidence and remaining dependencies.
See `PHASE2.md` for local/offline commands and publication behavior.

## Design principles

1. Separate sports forecasting from sportsbook price evaluation.
2. Require time-respecting validation before a model can qualify a candidate.
3. Use market de-vigging as a baseline, never as proof of truth.
4. Stress model probabilities downward before computing EV.
5. Treat live models as separate models from pregame models.
6. Track every candidate, rejection, accepted price, closing price, and result.
7. Use actual same-game parlay payouts; never multiply leg odds as if independent.
8. Cap correlated exposure at the event/player-risk level.
9. No-lookahead: features must be timestamped before the quote being evaluated.
10. Zero qualifying plays is a valid output.

## Quick start

Phase 1 adds `decision.decide`, `ValidationRegistry`, `SnapshotStore`,
`ExposureLedger`, CFB/NHL feature contracts, and six fixture provider interfaces.
Legacy `screen` CSV input always returns PASS because caller-provided validation
flags and incomplete timestamps are not evidence. Use `python -m ap_evsims.cli
evaluate evaluation.json --registry validation.db` to compute registered evidence;
use `python -m ap_evsims.cli decide candidate.json --registry validation.db
--exposure exposure.db --ledger decisions.jsonl --bankroll 1000 --now <UTC timestamp>`
for an audited research decision. See PHASE1.md for formats and limitations.

On a source checkout, set PYTHONPATH to src or install the package first.

```bash
python -m unittest discover -s tests -v
python -m ap_evsims.cli screen examples/candidates.csv --now 2026-10-14T01:00:00Z
```

## Modules

- `odds.py` — American/decimal conversion, implied probability, two-way de-vigging.
- `calibration.py` — Brier score, log loss, calibration buckets, validation reports.
- `schemas.py` — typed candidate and validation records.
- `screening.py` — fail-closed CORE candidate gate.
- `portfolio.py` — correlation-aware card allocation and stake caps.
- `parlay.py` — rejects unverified parlays; supports scenario-based joint probability only.
- `ledger.py` — append-only JSONL candidate/result/CLV ledger.
- `providers/` — provider interfaces for odds and sport data; no secrets in code.

## Sport-specific modeling targets

- CFB sides/totals: opponent-adjusted EPA, success rate, explosiveness, line yards, pace/possessions, QB/OL/secondary availability, field position, finishing drives, weather.
- NHL: 5v5 xG/shot attempts, high-danger chances, confirmed goalie, goalie GSAx, rest/travel, line/PP role, individual shot attempts and projected TOI.
- MLB: Statcast contact quality, pitch mix, platoon, park/weather, starter pitch count/removal risk, bullpen, confirmed lineup.
- NFL: EPA/play, success rate, pressure, route/target/attempt share, red-zone role, injuries, weather.

## Important

Historical backtests must use historical market snapshots and only information available at the time. Reconstructed postgame features are prohibited.
