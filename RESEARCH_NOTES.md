# AP EV/SIMS 3.0 research notes

## What the Iowa +3 type of win teaches us

The useful lesson is not "bet underdogs." It is **price movement plus model disagreement**. Iowa was available around +3 after Washington had moved from roughly -1.5 toward -3. A public model/handicap source still made Iowa the better team, so the market move improved the price on the side the model preferred. AP EV/SIMS 3.0 therefore stores the full price history, checks the current quote against a no-vig baseline, and rejects a play once the price moves beyond the model's value threshold.

## Why recent NHL failures are different

NHL outcomes and player props require role and state verification. Goalie confirmation, projected TOI, line/PP role, rest, shot attempts, expected goals and high-danger chances belong in sport-specific models. A generic public win probability or a recent-game hit rate is not sufficient evidence.

## Production data sources to wire in

- CollegeFootballData for timestamped CFB game/play/advanced metrics such as EPA, success rate, explosiveness and line yards.
- MoneyPuck for NHL shot/xG and goalie research inputs; official/team sources should verify actual starting goalie and line availability.
- Baseball Savant / Statcast for MLB contact and pitch-level features.
- nflverse for NFL play-by-play and player usage research.
- A timestamped sportsbook/odds feed for DraftKings/FanDuel prices and historical snapshots. Backtests must use the quote that existed at the time.

## Non-negotiable model rules

1. Each sport + market has its own model version and calibration report.
2. Pregame and live models are separate.
3. No postgame or future feature may leak into training/evaluation.
4. A public model is an input/benchmark, not a probability oracle.
5. Model confidence is reduced to a conservative lower probability before EV.
6. CORE requires both model edge and price edge.
7. Parlays require a shared scenario engine and the actual offered combined odds.
8. All candidates, including passes and losses, remain in the ledger.
