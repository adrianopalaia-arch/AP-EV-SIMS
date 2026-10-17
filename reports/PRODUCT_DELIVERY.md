# AP EV/SIMS product delivery

Generated: 2026-10-15T00:37:33.605528+00:00

## Start the existing Windows checkout

Repository: `C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS`

Installation command (in that directory):
```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```
Launch command:
```powershell
.\.venv\Scripts\python.exe -m ap_evsims dashboard
```
Dashboard: http://127.0.0.1:8501

On a fresh checkout with Python 3.11+, `python -m pip install -e .` is the installation command and `python -m ap_evsims dashboard` launches it.

## Verified delivery

- Full suite: 195 passed, 0 failed, 0 skipped. Original 171 preserved. All 18 frozen Phase 1 file hashes unchanged.
- Independently installed wheel in a fresh virtual environment: all 195 tests pass, 0 failures.
- Clean virtual-environment wheel installation passed; installed-package cold start tested separately from source checkout.
- Real-data Streamlit AppTest: zero exceptions, three tables, all 26 market categories visible; pregame/live separation tested.
- Server startup passed. Loopback HTTP and in-app browser timed out in the Codex session. Browser visual acceptance is NOT complete; no security settings were changed.
- CFBD/current CFB odds/sports endpoints: HTTP 200. DK and FD returned. Both credentials present; no secret values displayed.
- Historical odds: HTTP 401, BLOCKED_BY_HISTORICAL_ODDS_ACCESS. Earliest usable historical date remains unknown.
- Current featured-market observations available for CFB, NHL, NFL, MLB, NBA. Props remain Await data. These are prices, not validated forecasts.
- Current card: 160 events, 5840 quote sides, 1634 DK/FD sides.
- CFB captured schedule universe: 1666 games across captured 2025/2026 queries; 428 upcoming FBS-vs-FBS matchups; 66 mapped market events; 7 unmatched Odds events. A captured full-year FBS query is not an independently proven complete historical universe.
- Full-year all-division response: 3 of 3,679 games marked completed with missing scores. Entire snapshot excluded, raw bytes retained. Separate FBS response: 888 rows accepted.
- Zero complete real rolling feature sets. Zero qualifying model training/evaluation observations; synthetic performance sample zero. Test fixtures never become performance metrics.
- Model probabilities, p_low, fair odds, EV, maximum acceptable prices, Brier, log loss, ROI, CLV and drawdown remain unavailable. NO QUALIFYING BETS.
- Reference unit: $22, configurable per browser session. Private bankroll and exposure balances never published or inferred.
- Source recipes recomputed; completion proof timestamps cannot be backdated; omitted sportsbook markets withheld; line/price changes flagged; real quote ingestion uses transactional batches.

## Outputs

`outputs/latest_predictions.json`, `latest_edges.json`, `latest_passes.json`, `model_status.json`, `provider_status.json`, `cfb_universe.json`, `last_update.json`; `reports/MORNING_CARD.md`.
Generation hashes protect against mixed publications. Other-book comparisons remain local in ignored snapshots. Refresh is explicit, quota-bounded, with a 60-second forced-refresh cooldown.

## Exact remaining dependency order

1. Complete browser visual acceptance from normal PowerShell. The runnable app and real-data AppTest are delivered; HTTP loopback acceptance remains blocked here.
2. Extend CFB rolling input assembly across multiple verified prior-game queries; collect enough plays for both teams, verify identity and complete EPA/line-play/QB/availability/weather contracts without relabeling PPA or leaking revisions.
3. Obtain entitled historical prices with verifiable historical feature availability, or accumulate owned prospective snapshots. Join complete eligible-game denominators; retain missingness and exclusions. No new purchase is assumed.
4. Fit the first real CFB spread model; chronological train/calibrate/select/evaluate with untouched holdout and market baseline. Independently approve p_low coverage, execution/settlement and exposure gates before any wager eligibility. Then CFB total and moneyline.
5. Implement and empirically evaluate NHL SOG/saves first, then NFL, MLB and NBA predictors/props as source data permits. Current-featured-price ingestion does not implement these models.
6. Finish real drift/error diagnostics, justified challenger training and prospective promotion evidence. The cycle already reconciles verified result revisions and keeps the champion; it cannot manufacture a sample.
7. Enable live, parlays, prop builders, moneyline hammer, lotto and promotions only after their component models and independent correlation/exposure/execution gates qualify. They remain unavailable.
8. Finish remote Git delivery if session credentials cannot push. Do not block independent local development on GitHub.

## Git delivery

Branch: `ap-evisims-live`. Local checkpoint saved; remote read works. Local push failed authentication/permission; GitHub connector returned HTTP 403. Remote branch remains `3e7e5768f3e403ccfac137477e61d591c49db6f6`. No reset, force-push, history overwrite, raw-data commit or credential commit occurred. Known-secret Git history scan passed.

Run this single command in normal authenticated PowerShell:
```powershell
& 'C:\Users\adria\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```

Provider query parameter reference: [CFBD games documentation](https://api.collegefootballdata.com/api/games). App test reference: [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

## Files changed in this delivery

- `.gitignore`
- `PHASE2_PROGRESS.md`
- `README.md`
- `TASK_STATE.json`
- `outputs/cfb_universe.json`
- `outputs/last_update.json`
- `outputs/latest_passes.json`
- `outputs/model_status.json`
- `outputs/provider_status.json`
- `pyproject.toml`
- `reports/MORNING_CARD.md`
- `reports/PRODUCT_DELIVERY.md`
- `src/ap_evsims/__main__.py`
- `src/ap_evsims/canonical.py`
- `src/ap_evsims/cfb_features.py`
- `src/ap_evsims/cfb_universe.py`
- `src/ap_evsims/checkpoint.py`
- `src/ap_evsims/cycle.py`
- `src/ap_evsims/dashboard.py`
- `src/ap_evsims/handoff.py`
- `src/ap_evsims/operations.py`
- `src/ap_evsims/product.py`
- `src/ap_evsims/providers/access.py`
- `src/ap_evsims/warehouse.py`
- `tests/test_application_access.py`
- `tests/test_cfb_universe.py`
- `tests/test_checkpoint.py`
- `tests/test_product.py`
