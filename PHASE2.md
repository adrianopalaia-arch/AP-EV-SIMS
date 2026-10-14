# Phase 2 operation and evidence rules

Run commands from this repository root. Install the project into a Python 3.11+
environment (`python -m pip install -e .`) or use the existing `.venv` with
`PYTHONPATH=src`. DuckDB and pytz are required. The current environment has DuckDB
1.5.6 and pytz 2026.5. Tests use unittest and no authenticated network calls.

```powershell
$env:PYTHONPATH = 'src'
& .\.venv\Scripts\python.exe -m unittest discover -s tests -q
& .\.venv\Scripts\python.exe -m ap_evsims data_health
& .\.venv\Scripts\python.exe -m ap_evsims sync_data --offline
& .\.venv\Scripts\python.exe -m ap_evsims collect_odds --sports CFB --daily-credit-cap 24 --reserve-credits 50
& .\.venv\Scripts\python.exe -m ap_evsims research_cycle --offline
& .\.venv\Scripts\python.exe -m ap_evsims publish_handoff
```

`sync_data --offline` imports already archived sources. `sync_data --cfbd-year
2026 --cfbd-week 7` downloads that explicit query only if absent. It does not yet
refresh changed game status; future result revisions need explicit capture.
`collect_odds` preserves each observed two-sided line/price and records quota
metadata. Cadence accelerates near starts, subject to the daily cap and reserve.
The cap is based on locally recorded costs; the provider quota header remains the
authoritative remaining allowance. Initial validation used credits before the
local ledger existed, so provider-used and ledger-recorded totals differ.

`research_cycle --offline --dataset <local.jsonl> --folds <folds.json> --market
spread` requires a locally joined, provider-provenance dataset. Missing data
produces `MISSING_LOCAL_DATA`, not synthetic results. Training, calibration,
historical replay and reporting run under a socket/DNS prohibition. No script
retrieves missing historical information from the network during fitting.
The cycle imports local snapshots, verifies hashes, records observed closes only
after event start, checks data health and publishes the local feed. The optional
online cycle refreshes current CFB quotes after historical work finishes.

`publish_handoff` runs all tests, applies bounded current collection, writes the
safe feed, scans an explicit file allowlist, commits and attempts a normal push
to `ap-evisims-live`. It never force pushes or replaces remote work. Git failures
return a status and preserve local research. `--offline` suppresses all network
refresh/push and still permits a local commit. Git identity may be supplied with
`--author-name` and `--author-email`; normal configured Git identity otherwise
applies. Use `--git` if Git is not on PATH. All subprocess output is captured;
authenticated URLs and credential helper errors are not saved in reports.

The publisher includes no raw data, databases, `.env`, runtime binaries or files
over 5 MB. `.env.example` contains only blank provider entries. Keys are loaded
from the local `.env` or process environment, never from code or fixtures.
The collector has no distributed scheduler lock yet: run only one writer at a
time. Do not run a collector concurrently with a publishing job.

Each published JSON file is replaced atomically. `outputs/last_update.json` is
the generation manifest and is written last. Readers must verify its canonical
JSON SHA256 hashes for all four feed files and retry if they observe mixed
generations. The Git commit field is the source HEAD before publication; a commit
cannot contain its own hash. GitHub's branch HEAD is the publication commit.
An old quote is retained for audit and marked stale; publication never makes it
fresh. A seen quote is not proof that a sportsbook would execute a wager.

## Models and uncertainty

The CFB ridge/discrete-score models standardize using training data only and
preserve score mass at integer lines. Their algorithm version hashes source and
configuration; fitted artifacts also hash training observations and fitted state.
Chronological windows are train, calibration fit, later calibrator selection,
then untouched evaluation. Original Phase 1 guards remain unchanged. The
universal freeze/result ledger is used by CFB replay; other sport predictors are
not implemented. Each of their 21 markets has a separate required-feature,
opportunity, unit, role and player identity contract.

Calibration candidates are identity, Platt, beta and isotonic. Selection uses
Brier/log loss on the later selection window, never final test ROI or hit rate.
The current p_low diagnostic is:

`max(0, p_calibrated - bootstrap_lower_penalty - calibration_bin_penalty)`

The bootstrap penalty uses the fifth percentile of transformed week-bootstrap
predictions. The calibration penalty compares mean predicted probability to a
Wilson lower rate with effective n capped by independent week count. It is a
conservative diagnostic recipe, **not proven individual probability coverage**;
`coverage_validated` remains false. Scenario/role uncertainty is not empirically
estimated. Real approval remains blocked until unseen and prospective evidence
supports calibration, uncertainty, market advantage and execution.

The existing Phase 1 feature names, integer-line settlement restriction and
supported-market list are deliberately unchanged. Phase 2's derived matchup
features are not yet a complete verified mapping into those contracts. CFB
moneyline and additional sport markets must not bypass unsupported-market PASS.
Legacy parlay arithmetic has no deployment authority.

## Next Phase 2 dependency sequence

1. Obtain qualifying historical two-sided odds through existing entitlement or
   an authorized timestamped export; otherwise continue bounded prospective
   collection. No purchase is required or recommended by this checkpoint.
2. Audit historical feature availability and event/result identities. Preserve
   all excluded games and reasons. Use only prior completed-game information;
   no retrospective CORE, season-end ratings or observed postgame weather.
3. Register the CFB spread experiment, freeze feature schema and cutoff windows,
   lock an untouched holdout, and complete the verified feature/Phase 1 mapping.
   Establish actual book rules and executable quote evidence.
4. Run rolling-origin spread evaluation against the matched no-vig market, with
   separate calibration, p_low diagnostics, slippage, clustered uncertainty,
   negative controls, source ablation, tail cases and full exclusion accounting.
   Keep PASS if the evidence is insufficient or there is no edge.
5. Collect immutable prospective shadow predictions. Consider manual promotion
   only after all critical readiness requirements are resolved. Then repeat for
   CFB total and moneyline; proceed in order through NHL, NFL, MLB and NBA.
6. Live and parlay models remain blocked by their separate calibrated components,
   synchronized state/joint outcome data and actual payout/settlement rules.
