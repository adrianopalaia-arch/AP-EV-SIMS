# Daily betting decisions

Generated UTC: 2026-10-18T04:00:40.459660+00:00. **PASS — CORE disabled.** Reference unit $22; no stakes authorized.

| Sport | Future forecasts | Exact side comparisons | Fresh | Priced settled | Distinct prospective games | Approved |
|---|---:|---:|---:|---:|---:|---:|
| CFB | 45 | 16 | 0 | 0 | 43 | 0 |
| NHL | 49 | 22 | 0 | 8 | 2 | 0 |
| NBA | 124 | 64 | 0 | 0 | 0 | 0 |
| NFL | 124 | 96 | 0 | 0 | 0 | 0 |
| MLB | 38 | 0 | 0 | 0 | 0 | 0 |

## Failures and missing evidence

- CFB: {"availability": [], "candidate_rejections": {"BOOK_SETTLEMENT_RULE_UNVERIFIED": 16, "MODEL_NOT_CALIBRATED": 16, "PROSPECTIVE_EVIDENCE_INSUFFICIENT": 16, "STALE_PRICE": 16, "UNVERIFIED_LINEUP": 16}, "collection": null, "identity_warnings": [], "missing_history": {}}
- NHL: {"availability": ["PARTICIPATION_NOT_CONFIRMED", "ROLE_NOT_CONFIRMED", "STARTING_GOALIE_NOT_CONFIRMED"], "candidate_rejections": {"BOOK_SETTLEMENT_RULE_UNVERIFIED": 22, "PARTICIPATION_NOT_CONFIRMED": 22, "PROSPECTIVE_CALIBRATION_PENDING": 22, "ROLE_NOT_CONFIRMED": 22, "STALE_PRICE": 22}, "collection": "REFRESH_COOLDOWN", "identity_warnings": ["BOOK_CANONICAL_START_MISMATCH"], "missing_history": {"INSUFFICIENT_PRIOR_PLAYER_HISTORY": 1}}
- NBA: {"availability": ["INJURY_OR_RESTRICTION_REPORTED", "PARTICIPATION_NOT_CONFIRMED", "ROLE_NOT_CONFIRMED"], "candidate_rejections": {"BOOK_SETTLEMENT_RULE_UNVERIFIED": 64, "LONG_LAYOFF_ROLE_UNVERIFIED": 64, "MODEL_MARKET_DISAGREEMENT": 2, "PARTICIPATION_NOT_CONFIRMED": 64, "PROSPECTIVE_CALIBRATION_PENDING": 64, "ROLE_NOT_CONFIRMED": 64, "STALE_PRICE": 64, "TEAM_CHANGE_ROLE_UNVERIFIED": 10}, "collection": "REFRESH_COOLDOWN", "identity_warnings": [], "missing_history": {"INSUFFICIENT_PRIOR_PLAYER_HISTORY": 16}}
- NFL: {"availability": ["INJURY_OR_RESTRICTION_REPORTED", "PARTICIPATION_NOT_CONFIRMED", "PLAYER_REPORTED_OUT", "ROLE_NOT_CONFIRMED"], "candidate_rejections": {"BOOK_SETTLEMENT_RULE_UNVERIFIED": 96, "MODEL_MARKET_DISAGREEMENT": 26, "PARTICIPATION_NOT_CONFIRMED": 96, "PROSPECTIVE_CALIBRATION_PENDING": 96, "ROLE_NOT_CONFIRMED": 96, "STALE_PRICE": 96, "TEAM_CHANGE_ROLE_UNVERIFIED": 8}, "collection": "REFRESH_COOLDOWN", "identity_warnings": [], "missing_history": {"INSUFFICIENT_PRIOR_PLAYER_HISTORY": 481}}
- MLB: {"availability": ["MODEL_COMPETITION_DOMAIN_MISMATCH", "PARTICIPATION_NOT_CONFIRMED", "ROLE_NOT_CONFIRMED"], "candidate_rejections": {}, "collection": "REFRESH_COOLDOWN", "identity_warnings": ["BOOK_CANONICAL_START_MISMATCH", "POSTPONED_SCHEDULE_REVISION"], "missing_history": {"INSUFFICIENT_PRIOR_PLAYER_HISTORY": 91}}
- Missing confirmed participation, current opportunities and complete injury coverage continue to block wagering.
- MLB postponement and postseason-domain conflicts remain blocked when sources disagree.
- No verified pre-entry bookmaker terms or independent multi-book NHL consensus for the settled cohort.
- Missing historical sportsbook entitlement is not replaced with closing prices or fabricated history.
- Prices expire after 180 seconds. A cached schedule run does not refresh quote timestamps.

See reliability_status.json for actual source/cadence failures and quota metadata, and MODEL_PERFORMANCE_SCOREBOARD.md for measured results.
