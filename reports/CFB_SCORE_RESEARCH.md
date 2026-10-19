# CFB score research

Generated UTC: 2026-10-16T05:23:02.576787+00:00

Independent regularized team-strength margin model; no sportsbook price is required to train.

| Item | Before | After |
|---|---:|---:|
| Score training rows | 0 | 1442 current fit / 2600 collected |
| Evaluated forecasts | 0 | 1086 |
| MAE, model / baseline | unavailable | 14.5269 / 16.2073 |
| RMSE, model / baseline | unavailable | 18.4755 / 20.5783 |
| Future forecasts frozen | 0 | 59 |
| Qualified betting models | 0 | 0 |

Forecast generation: 2026-10-16T05:08:15.067026+00:00. 56 future events have an exact odds-provider identity match; the initial frozen forecast records contain no qualifying attached price pairs. Price attachment remains unfinished.

All retrospective results are RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF. Provider capture times were retained; this is not a historical executable-bet backtest. 2024 is warm-up; 2025/2026 are predeclared chronological evaluation. No tuning after results. Weekly seven-day completion embargo, fixed ridge/home priors and half weight per prior season. Full policy and by-season numbers are in outputs/cfb_score_research_status.json.

59 initial trial files with invalid serialization hashes were quarantined locally, never accepted as valid forecasts. The corrected 59 forecast files are hash checked. Cash/CORE, calibration and p_low remain disabled/null.

Run: `.\.venv\Scripts\python.exe -m ap_evsims.cfb_score_research --root .`

Historical Odds API access remains HTTP 401 (free-plan historical restriction). Current CFB odds HTTP 200 with DK/FD; 73 events returned at 2026-10-16T05:07:27.795643+00:00. No prices invented.
