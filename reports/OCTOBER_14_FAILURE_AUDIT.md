# October 14 research failure audit — research preview

Updated October 14, 2026, 10:35 PM CT. This is a dated, read-only audit of four selections. It is not a live recommendation card or a trained forecast. Descriptive facts below do not confer model approval.

## Findings

The local prediction ledger contains zero frozen predictions; the accounting journal contains zero entries. There is no recorded model forecast to score for these calls. Original recommendation messages, timestamps, executable prices and pre-bet reasoning were not supplied. Whether a specific researcher actually missed a particular fact remains unverified. The supported classification is incomplete recommendation provenance and incomplete verified research coverage, not demonstrated failure of a trained model.

The user distinguished actual wagers from recommendations. Those personal records are retained only in ignored local storage; they have not been added to a bankroll or settlement journal. Receipt, placement-time and bookmaker-settlement verification remain outstanding. This shareable report omits stakes and the user's wager identities.

## Verified event outcomes

| Selection under review | Opponent | Result at verification | Evidence |
|---|---|---|---|
| Dodgers ML | Milwaukee Brewers | Lost 2–6; MLB status Final | [MLB game data](https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-10-14&teamId=119) |
| Colorado Avalanche ML | Dallas Stars | Lost 2–3 after shootout; NHL status FINAL | [NHL game data](https://api-web.nhle.com/v1/gamecenter/2026020107/landing) |
| Kennesaw State ML | Missouri State | Lost 21–24; CFBD completed=true | CFBD /games, event 401871054; hashed local response |
| Sam Houston ML | Western Kentucky | UNGRADED: canonical CFBD completed=false, scores absent | CFBD /games, event 401871068; hashed local response |

Result responses were captured Oct 14 10:28:17 PM CT through Oct 14 10:28:17 PM CT. These are verification times, not claimed final-whistle times. A provider delay is possible. An NHL full-game moneyline includes the shootout; the actual wager's market rules must still be verified. Event results do not prove that a wager was placed, paid, voided or cashed out.

## Actual archived prices

Latest locally captured DraftKings moneyline pair strictly before the official scheduled start, selected from immutable provider payloads. These are neither the original recommendation price nor a verified closing or execution price. Both quote and capture timestamps are retained in the local evidence JSON. All quote pairs refer to the same event, book and market.

| Team | Team / opposite American odds | Implied / proportional no-vig probability | Quote time |
|---|---|---|---|
| Los Angeles Dodgers | -174 / +155 | 63.50% / 61.82% | Oct 14 06:25:36 PM CT |
| Colorado Avalanche | -162 / +136 | 61.83% / 59.34% | Oct 14 06:26:05 PM CT |
| Kennesaw State Owls | -142 / +120 | 58.68% / 56.35% | Oct 14 06:26:06 PM CT |
| Sam Houston State Bearkats | -108 / -112 | 51.92% / 49.57% | Oct 14 06:26:06 PM CT |

The archive also contains later in-play quotes. They were excluded from this pregame comparison. Provider start-time revisions exist; the earlier official scheduled time was used conservatively. Recommendation time is unknown, so availability before a specific recommendation cannot be certified. Market-implied and no-vig figures are price-derived quantities, not model probabilities. Model probability, p_low, fair model odds, EV and maximum acceptable price all remain unavailable.

## Research evidence and missing stats

### Dodgers

Pregame coverage flagged Snell’s five walks in 3⅔ innings and seven Dodgers relievers used in Game 2. [MLB matchup preview](https://www.mlb.com/brewers/news/brewers-dodgers-nl-championship-series-game-3-starting-lineups-and-pitching-matchup)

Missing from the recommendation record: confirmed pitcher/lineup timestamps, an opponent-adjusted offense estimate, bullpen availability/workload calculation, exact offered price and a validated win probability. Starting-pitcher identification in the subsequently fetched game feed is outcome-era evidence; it does not prove when the recommendation verified the starter. The eventual score does not establish which pregame variable would have improved the forecast.

### Avalanche

Projected goalies: Wedgewood/DeSmith; Makar and O’Connor unavailable; both teams on a back-to-back. Confirmation before recommendation unverified. [NHL lineup preview](https://www.nhl.com/news/dallas-stars-colorado-avalanche-game-preview-october-14-2026)

Missing: a recorded confirmation, pregame 5v5 xG/high-danger metrics, goalie GSAx with model/version provenance, lineup-adjusted probability and price threshold. Expected starters and officially confirmed starters are different evidence states. Do not attribute the shootout loss to these omissions without broader testing.

### Kennesaw State

The October 13 pregame article's Game Notes link resolves to a September 8 Georgia State document. That opponent/date mismatch makes the linked file unsuitable for this matchup without further verification. [Pregame article](https://ksuowls.com/news/2026/10/13/football-the-night-before-game-six-at-missouri-state.aspx), [linked document](https://ksuowls.com/documents/2026/9/8/2026_KSU_FB_Game_Notes__Georgia_State_.pdf).

Missing: verified QB efficiency, opponent-adjusted defense, pressure/line-play matchup, availability and original ML versus spread selection. The stale link is a confirmed source-selection problem discovered during this audit, not proof it caused the original recommendation. Published schedules and a three-point loss do not substitute for those pregame measures.

### Sam Houston

The team's October 12 preview reported 350.6 total yards allowed per game, 5.56 opponent yards per pass attempt and a 25.8% three-and-out rate through five games. It also noted two true freshmen had started on the offensive line at Liberty and three 300-yard passing games for Landyn Locke. These are descriptive, small-sample team-reported figures, not opponent-adjusted EPA or a win forecast. [Sam Houston preview](https://gobearkats.com/news/2026/10/12/football-game-6-preview-vs-wku).

Missing: verified efficiency against comparable opponents, pressure sensitivity, current availability, the recommendation timestamp and an executable price pair. Raw yardage alone cannot establish value. Result remains ungraded until the canonical feed reports a completed result with both scores.

All preview articles were retrieved during this audit. Their displayed publication dates suggest pregame material, but exact historical revisions and availability before an unknown recommendation time are unproven. They are not inserted into qualifying backtest features. Missing statistics remain unavailable rather than zero.

## Focused corrections and how to test them

1. Freeze a recommendation record before an event: event ID, market and line, both prices, book, quote/capture/decision times, source snapshots, rationale, model artifact and validation evidence. Without qualifying evidence, retain PASS. Preserve recommendations separately from user-reported placements and bookmaker receipts.
2. Require opponent/date checks for source documents, confirmed versus projected starter labels, and complete freshness/context checks. A current article can contain an old attachment.
3. Keep pregame and live evidence separate. Audit later quotes without treating them as historical pregame prices or claiming closing-line value without a genuine close.
4. Use canonical final status and explicit settlement rules. Never infer finality from a score, a social post, or the user's loss description. Do not write inferred money movements into the exposure/accounting ledger.
5. Pre-register one repeatable feature comparison at a time on unseen games: bullpen workload/lineup; confirmed goalie/availability; opponent-adjusted CFB QB-pressure matchup. Keep all quotes for a game in one evaluation group. Use calibration, proper scores, uncertainty and price-based outcomes. These four selected examples provide no demonstrated incremental predictive value.

No model weights, bankroll rules, validation authority or betting eligibility have been changed. All four calls would require independent qualifying evidence before being recommendations from this application. Existing protections were retained; no final result was used to tune a prediction.

## Verification and boundaries

Full existing suite: **197 passed, 0 failed, 0 skipped**. Raw result payloads and quote manifests are hashed locally. Source-code changes display this research preview and add optional quota-bounded pregame price refresh with timestamp/started-game checks. Advanced-stat and availability feeds remain incomplete. Two added tests cover refresh backoff/cadence and saved-card timestamp safety; all original 195 tests remain passing. No historical prices were fabricated, no wager was placed, and no fixture was included in empirical performance. Audit sample is not a trained-model evaluation sample.

Still needed: original recommendation texts/times, original book and market receipt, verifiable pre-bet lineup/pitcher/goalie status, missing research statistics, final canonical Sam Houston result, and an independently evaluated predictive model. Iowa +3 and Oklahoma +2.5 were not graded or added to training: dates, opponents and receipts were not provided.
