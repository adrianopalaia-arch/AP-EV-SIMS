# Multi-sport prop evidence

Generated UTC: 2026-10-16T05:23:02.576787+00:00

**IN PROGRESS. All models remain UNVALIDATED; no cash or CORE authorization.**

| Sport / market | Training appearances | Chronological evaluation | Model MAE | Recent-average MAE | Model RMSE | Baseline RMSE |
|---|---:|---:|---:|---:|---:|---:|
| NFL receptions | 12332 | 6152 | 1.2836 | 1.2719 | 1.7163 | 1.7400 |
| NFL receiving_yards | 12332 | 6152 | 16.7496 | 16.5414 | 23.5942 | 23.8903 |
| NFL rushing_attempts | 12332 | 6152 | 1.3720 | 1.1432 | 2.6620 | 2.6111 |
| NFL rushing_yards | 12332 | 6152 | 7.4874 | 6.5989 | 16.0560 | 16.0200 |
| NFL passing_yards | 1510 | 733 | 68.2564 | 68.0111 | 86.5141 | 87.5476 |
| NBA points | 79632 | 51938 | 4.7637 | 4.7590 | 6.1961 | 6.2607 |
| NBA rebounds | 79632 | 51938 | 1.9531 | 1.9662 | 2.5585 | 2.5976 |
| NBA assists | 79632 | 51938 | 1.3797 | 1.3861 | 1.8637 | 1.8918 |
| NBA threes | 79632 | 51938 | 0.9159 | 0.9102 | 1.2609 | 1.2832 |
| NHL shots_on_goal | 145238 | 96525 | 1.0375 | 1.0591 | 1.3398 | 1.3722 |
| NHL goalie_saves | 8540 | 5597 | 5.9885 | 6.0866 | 7.7202 | 7.8341 |
| MLB pitcher_strikeouts | 950 | 540 | 1.2913 | 1.2939 | 1.7631 | 1.7414 |
| MLB pitcher_outs | 950 | 540 | 2.1340 | 1.8741 | 2.9093 | 2.7544 |
| MLB hits_allowed | 950 | 540 | 1.1717 | 1.1856 | 1.5753 | 1.5920 |
| MLB hitter_hits | 2451 | 1410 | 0.6635 | 0.6712 | 0.8086 | 0.8293 |
| MLB total_bases | 2451 | 1410 | 1.1187 | 1.1373 | 1.5108 | 1.5441 |

Models predict opportunity from prior appearances, then partially pooled production per opportunity. Target-game minutes, targets, carries, shots faced or batters faced never enter their own prediction. Empirical prior out-of-fold residual distributions retain push mass at integer lines. No Poisson assumption, synthetic empirical records, p_low, or calibration claims.

Results are reconstructed observed-appearance diagnostics, not timestamp-authentic pregame evaluations. DNP/absences are not zero-filled; appearance selection bias remains. MLB is only a predeclared 24-player cohort from the Detroit 2024 full-season roster, not league-wide coverage. NBA uses the public hoopR ESPN archive because the official stats endpoint timed out and the CDN returned 403. NHL monthly API truncation was detected; corrected unlimited-size monthly requests returned complete partition counts.

NFL: none of the five models improved MAE; keep the recent-average benchmark and reject promotion. NBA: small MAE improvements for rebounds/assists only. NHL: both evaluated markets improved MAE. MLB: pitcher outs worsened, and several small improvements have uncertainty spanning zero. These comparisons are not evidence of beating sportsbook prices. Full CRPS, opportunity MAE, by-season counts and week-block bootstrap intervals are in the per-sport JSON outputs.

Current prop access: earliest upcoming event per sport. NFL 116 pairs (37 DK/33 FD), NBA 53 (23 DK/8 FD), MLB 27 (25 DK/1 FD), NHL zero returned. All responses were HTTP 200; empty NHL markets are an explicit coverage gap. Captured 2026-10-16T05:19:34 UTC; 402 provider credits remained. All prices retain actual timestamps and are subject to 180-second freshness rejection. No historical prices were synthesized.

Unfinished: source-backed current player/event mapping; confirmed role/injury/goalie/lineup evidence; frozen future prop forecasts; prospective calibration; exact-line same-rule consensus; settlement and near-start CLV linkage; independent scheduled collection. No retrospective forecasts count as frozen prospective predictions. Existing CFB 59 future forecasts are separate.

Commands:
```powershell
Set-Location 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_ingestion --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_research --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_prices --root .
```

Public raw sources remain ignored/local. Public reachability does not establish redistribution permission. Source attribution: nflverse/nflverse-data; sportsdataverse/hoopR-nba-data (ESPN-derived); NHL public statistics API; MLB Stats API. See immutable public source manifests for exact URLs/hashes/capture times.

Tests at this checkpoint: 283 passed, 0 failed; all 18 frozen Phase 1 files unchanged. Development continues after the checkpoint.
