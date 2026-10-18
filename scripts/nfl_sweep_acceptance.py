#!/usr/bin/env python3
"""Read-only AP EV/SIMS NFL sweep contract verifier.

Checks coverage and safety, not whether any selection will win.
Usage:
 python nfl_sweep_acceptance.py outputs/nfl_sweep_status.json --expected 12 --require-probabilities
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys


ALLOWED = {
    "FORECASTED", "NO_TRAINED_GAME_MODEL", "INSUFFICIENT_HISTORY",
    "MISSING_FEATURES", "BLOCKED_IDENTITY", "NOT_AVAILABLE",
    "MODEL_FAILED_VALIDATION", "IN_PROGRESS"
}
PRICE_STATES = {"FETCHED", "NO_MARKET", "RATE_LIMIT", "BUDGET_DEFERRED", "FAILED", "NOT_REQUESTED"}
PROP_STATES = {"SCANNED", "NO_MARKET", "BUDGET_DEFERRED", "FAILED", "NOT_REQUESTED"}


def dt(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include UTC offset")
    return result.astimezone(timezone.utc)


def check(report, expected=None, require_probabilities=False):
    problems = []
    def fail(msg):
        problems.append(msg)

    source = report.get("schedule") or {}
    if not source.get("source") or not source.get("captured_at"):
        fail("schedule source and capture timestamp are required")
    elif not isinstance(source.get("games"), list):
        fail("schedule.games must be an array")
        return {"ok": False, "problems": problems}

    expected_games = source.get("games") or []
    games = report.get("games") or []
    if expected is not None and len(expected_games) != expected:
        fail(f"schedule count {len(expected_games)} != expected {expected}")
    if len(expected_games) < 1:
        fail("no scheduled games")
    ids = [g.get("event_id") for g in expected_games]
    actual_ids = [g.get("event_id") for g in games]
    if any(not x for x in ids):
        fail("every schedule event needs a canonical event_id")
    if len(set(ids)) != len(ids):
        fail("schedule contains duplicate event IDs")
    if len(set(actual_ids)) != len(actual_ids):
        fail("sweep contains duplicate event IDs")
    missing = sorted(set(ids)-set(actual_ids))
    extras = sorted(set(actual_ids)-set(ids))
    if missing:
        fail(f"missing games: {missing}")
    if extras:
        fail(f"games not in schedule: {extras}")
    by_id = {g.get("event_id"): g for g in expected_games}
    counts = Counter()
    models = 0
    scanned = 0
    for game in games:
        eid = game.get("event_id")
        if eid not in by_id:
            continue
        sched = by_id[eid]
        if not all(sched.get(k) for k in ("home_team", "away_team", "kickoff")):
            fail(f"{eid}: canonical home/away/kickoff missing")
        try:
            kick = dt(sched["kickoff"])
            if source.get("captured_at") and dt(source["captured_at"]) >= kick:
                fail(f"{eid}: schedule not recorded before kickoff")
        except (KeyError, ValueError):
            fail(f"{eid}: invalid schedule kickoff")
        status = game.get("forecast_status")
        if status not in ALLOWED:
            fail(f"{eid}: missing or unknown forecast status")
        counts[status] += 1
        p_home = game.get("p_home_win")
        p_away = game.get("p_away_win")
        if status == "FORECASTED":
            if any(not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p < 0 or p > 1 for p in [p_home, p_away]):
                fail(f"{eid}: missing or invalid win probabilities")
            elif abs(p_home+p_away-1) > 1e-6:
                fail(f"{eid}: NFL full-game probabilities do not sum to one")
            if not game.get("model_version") or not game.get("model_data_cutoff"):
                fail(f"{eid}: source/model provenance missing")
            elif dt(game["model_data_cutoff"]) >= dt(sched["kickoff"]):
                fail(f"{eid}: model data cutoff is not pregame")
            models += 1
        elif p_home is not None or p_away is not None:
            fail(f"{eid}: must use null probabilities when no actual game forecast exists")
        if game.get("main_market_status") not in PRICE_STATES:
            fail(f"{eid}: main-market attempt status missing")
        if game.get("prop_market_status") not in PROP_STATES:
            fail(f"{eid}: player-prop attempt status missing")
        if game.get("prop_market_status") == "SCANNED":
            scanned += 1
        for quote in game.get("quotes", []):
            if quote.get("event_id") != eid:
                fail(f"{eid}: cross-event quote association")
            if not all(quote.get(k) is not None for k in ("book", "market", "line", "selection", "american_odds", "observed_at", "captured_at")):
                fail(f"{eid}: incomplete price evidence")
            else:
                try:
                    if dt(quote["observed_at"]) > dt(quote["captured_at"]):
                        fail(f"{eid}: quote future of capture")
                    if dt(quote["captured_at"]) >= dt(sched["kickoff"]):
                        fail(f"{eid}: quote captured after kickoff")
                except ValueError:
                    fail(f"{eid}: invalid quote timestamp")
    quota = report.get("quota") or {}
    if not isinstance(quota.get("credits_used"), (int, float)) or not isinstance(quota.get("daily_cap"), (int, float)):
        fail("provider quota usage and cap required")
    elif quota["credits_used"] > quota["daily_cap"]:
        fail("provider daily quota exceeded")
    if require_probabilities and models < len(expected_games):
        fail(f"only {models}/{len(expected_games)} game win probabilities forecasted")
    if report.get("validated_edges", 0) > 0 and not report.get("prospective_validation_evidence"):
        fail("validated edge claimed without prospective validation evidence")
    if report.get("auto_bets_placed", 0):
        fail("sweep must not place real-money bets")

    return {"ok": not problems, "target_date": report.get("target_date"),
            "scheduled_games": len(expected_games), "covered_games": len(set(actual_ids)&set(ids)),
            "game_probabilities": models, "prop_scanned_games": scanned,
            "model_status_counts": dict(counts), "problems": problems}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path)
    p.add_argument("--expected", type=int, default=None, help="expected Sunday schedule count")
    p.add_argument("--require-probabilities", action="store_true", help="fail until every game has a real model forecast")
    args = p.parse_args()
    try:
        data=json.loads(args.report.read_text(encoding="utf-8"))
        status=check(data, expected=args.expected, require_probabilities=args.require_probabilities)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        status={"ok": False, "problems": [str(e)]}
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
