# CFB training data and verified feature checkpoint

The existing project now assembles real CFB play history across multiple provider queries and produces verified prospective baseline features. The first real model is **not fitted or validated**: no historical row currently has the required combination of pregame features, a qualifying archived price and a settled result. The existing walk-forward runner rejected the empty training sample rather than inventing a forecast.

Machine-readable evidence: `outputs/cfb_training_status.json`. Raw responses, normalized tables, feature recipes and detailed evaluation exclusions remain under ignored `data/`.

## Verified work

- All **228 tests pass**, including the original 208. All 18 frozen Phase 1 files retain their original SHA-256 hashes.
- CFBD returned HTTP 200 for the 2026 FBS schedule and six weekly play queries. The final reported quota was 970 calls remaining. Both credentials remain local; no credentials were printed or committed.
- Captured **142,879 real 2026 play rows**, covering regular-season weeks 1â€“6. Each response has an immutable payload, manifest, capture time and hash. There were no Odds API calls in this checkpoint.
- Assembled **57,978 eligible plays from 448 prior games**, involving 235 teams. These include games involving FCS opponents; the target training scope remains FBS versus FBS.
- Saved typed prior-play facts and prospective matchup features as JSONL and Parquet. Every derived feature recipe retains its source identities and is independently recomputed during provenance validation.
- Produced **211 upcoming matchups with all four research baseline features**. Another 214 upcoming FBS matchups have an unconfirmed start time and remain blocked. Coverage is limited to captured queries, not a claim of complete provider coverage.
- Recalculated the existing dashboard from local archives. The display distinguishes research baseline feature sets from complete Phase 1 feature sets. AP probabilities and p_low remain null when no model exists.

## Feature definitions and safeguards

The deliberately small baseline uses opponent-adjusted offensive PPA difference, offensive success-rate difference and sum, and combined offensive plays per game. Success uses the existing 50%/70%/100% down-based thresholds. Both teams require at least 100 eligible offensive plays across three completed prior games. PPA additionally requires that minimum amount of nonmissing PPA data.

PPA is not renamed EPA. Plays per game measures volume, not clock-based pace. No weather, injury, QB, pressure, depth-chart or other missing input is filled with zero or invented. These four features do **not** satisfy the complete Phase 1 feature contract, so 211 research previews do not mean 211 qualified wagers.

The new assembly replaces older revisions of the same query, deduplicates overlapping plays, scopes play IDs to games, excludes conflicting games, verifies team and season/week identities, and rejects future or impossible completion evidence. A target game's own plays cannot enter its pregame features. Hash or recipe forgery fails verification.

Data-quality accounting across the latest play-query revisions:

| Category | Play rows |
| --- | ---: |
| Eligible prior plays | 57,978 |
| No matching verified game identity | 63,644 |
| Unsupported or incomplete play type/fields | 20,562 |
| Invalid/zero distance | 695 |
| Outside the lookback window | 161 |

The final 161 rows are the previously archived 2025 query, not new 2026 ingestion. The unmatched rows remain excluded; this checkpoint did not assume their game identities or completion status. Of the eligible plays, 278 have missing PPA. Their missing value is preserved. No source conflicts were observed in the actual assembled data.

The official CFBD documentation describes [weekly play query parameters](https://github.com/CFBD/cfbd-python/blob/main/docs/PlaysApi.md) and notes that [historical data can be corrected after publication](https://api.collegefootballdata.com/data-availability). Accordingly, a past game date or play wallclock does not prove when this retrieved revision became available. Newly fetched plays retain their October 16 UTC capture time.

## Actual walk-forward attempt

The eligibility audit retains all **383 completed FBS-versus-FBS games** in the captured queries, including games with no sportsbook snapshot. It selects at most one home spread per game: the earliest qualifying DraftKings full-game quote within 24 hours before kickoff, with a contemporaneous opposite side, no more than 180 seconds of capture latency, and independently verified prequote features and identities. Selection never depends on the outcome.

| Audit result | Games |
| --- | ---: |
| Completed FBS games in captured queries | 383 |
| No qualifying archived DraftKings price | 381 |
| Qualifying price, insufficient prequote play history | 2 |
| Eligible joined training observations | 0 |
| Real model forecasts / validated models | 0 / 0 |

The unchanged score-model/walk-forward pipeline returned `INSUFFICIENT_TRAINING_SAMPLE`. The diagnostic development fold used training cutoff August 1, 2025; calibration cutoff February 1, 2026; selection cutoff August 1, 2026; evaluation cutoff at the recorded run time. These are readiness diagnostics, not an empirically evaluated model. No coefficient artifact was fitted, and Brier score, log loss, ROI, CLV and uncertainty coverage remain unavailable.

Minimums remain 80 training games, 300 calibration-fit observations and 100 calibration-selection observations. The separate validation, exposure, price, lineup and uncertainty controls remain in place. Neither the default fold nor smaller research feature requirements bypasses them.

## What remains unfinished

1. **Historical pregame feature availability.** Plays fetched today cannot be backdated to September. Qualifying retrospective evaluation requires independently provable earlier versions, or prospective feature captures followed by later outcomes. This is now a demonstrated blocker.
2. **Historical odds access.** The last entitlement check returned HTTP 401. It was not retried or upgraded here. Restoring historical odds alone will not solve feature publication-time provenance.
3. **Sufficient chronological training, calibration and evaluation cohorts.** The first real fit remains blocked; no synthetic observations or fixture results enter the empirical reports.
4. **Complete CFB feature/availability coverage.** Verified EPA, defense/line/QB/pressure inputs, injuries/depth, appropriate weather and other Phase 1 requirements remain incomplete. Their incremental predictive value must later be tested on unseen games.
5. **Prospective validation and p_low coverage.** No betting model has earned validation or wagering authority. Live models also remain unvalidated.

The next independent step is to keep capturing current pregame feature and exact two-sided price snapshots, then join verified final results as they arrive. A chronological fold plan must be fixed before scoring those outcomes. Avoid choosing dates or feature definitions to improve already observed results.

## Exact local commands

Repository: `C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS`

Offline feature assembly, eligibility audit and existing walk-forward runner:

```powershell
Set-Location 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
& '.\.venv\Scripts\python.exe' -m ap_evsims.cfb_training --root .
```

Bounded collection of the same six weeks, reusing all matching archived queries:

```powershell
& '.\.venv\Scripts\python.exe' -m ap_evsims.cfb_training --root . --collect --year 2026 --through-week 6 --max-requests 7
```

The collector does not refresh cached queries. Fresh results use the existing bounded CFBD result-refresh workflow. For a new predeclared chronological experiment, supply `--folds` with a JSON array of the existing `FoldWindow` fields. Future evaluation endpoints are rejected.

If the session's GitHub authentication remains blocked, the exact non-force push is:

```powershell
& 'C:\Users\adria\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' -C 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS' push -u origin ap-evisims-live
```

Git delivery outcome is recorded in `TASK_STATE.json`. No reset, force-push, automatic wager, purchase, or entitlement change is part of this checkpoint.


## Files changed and delivery verification

- Source: `src/ap_evsims/cfb_history.py`, `src/ap_evsims/cfb_training.py`, `src/ap_evsims/canonical.py`, `src/ap_evsims/cfb_universe.py`, `src/ap_evsims/dashboard.py`.
- Tests: `tests/test_cfb_history.py`, `tests/test_cfb_training.py` (20 new regression tests).
- Reports/status: `TASK_STATE.json`, `PHASE2_PROGRESS.md`, `reports/CFB_TRAINING_VALIDATION.md`, `reports/MORNING_CARD.md`, `outputs/cfb_training_status.json`, `outputs/cfb_universe.json`, `outputs/last_update.json`, `outputs/latest_passes.json`, `outputs/model_status.json`, `outputs/provider_status.json`.

Real archived-data Streamlit AppTest completed with zero exceptions, and feed hashes verified. Baseline commit `6b20b15` remains an ancestor. Implementation commit `7d991e6523bfaf429bd3eb0f968fe0c29ea5417f` is saved locally. The first push was blocked; the delivery-status checkpoint receives a final non-force push attempt. The exact manual command is above.
