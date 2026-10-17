# Integration plan

## 1. Preserve existing local Codex project first

The GitHub repository was empty when this rebuild was created. Do not overwrite your local sports-betting project. Copy this package into a branch of that project, then adapt its existing provider/model interfaces.

## 2. Connect existing models behind a strict contract

Each sport/market model must emit: `model_version`, `model_mode` (`pregame` or `live`), `p_model`, `p_low`, `feature_cutoff_utc`, and a validation report generated only from earlier out-of-sample predictions.

## 3. Odds ingestion

Store full two-sided book snapshots with timestamps. For DK execution candidates, also capture FanDuel/market comparisons when available. Historical backtests must load contemporaneous historical snapshots, not current odds.

## 4. Data ingestion

Timestamp every lineup/injury/goalie/weather/role update. A candidate fails closed when required state is unknown.

## 5. Sport modules

Build separately by sport and market. Do not share a generic confidence score across CFB spreads and NHL shots props. Recommended first production targets: CFB sides/totals, NHL SOG/saves, MLB pitcher Ks/outs, NFL receptions/rush attempts.

## 6. Validation

Use walk-forward or rolling-origin splits. Compare Brier and log loss against a de-vigged market baseline on the same observations. Save calibration bins, CLV distribution, ROI, drawdown, and sample size by model version.

## 7. Selection

Run `screen_candidate`, then `allocate_card`. A bet is CORE only when it survives uncertainty stress, stale-data checks, model validation, market de-vig comparison, settlement verification, and exposure caps.

## 8. Parlays

No parlay is CORE simply because its legs are CORE. Use shared game simulations to estimate joint probability, and compare that to the actual offered parlay price.

## 9. Live betting

Live models must be independently trained/calibrated with live state features (score, time, possession/strength, current usage/TOI, etc.). Pregame models cannot be reused after event start.

## 10. Deployment gate

Paper-track at least hundreds of selected singles per market/model version as an early diagnostic; continue until confidence intervals on calibration/ROI are useful. Never scale stakes merely because a short recent streak won.
