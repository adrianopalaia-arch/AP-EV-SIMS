import unittest, tempfile
from datetime import datetime, timezone
from pathlib import Path
from ap_evsims.odds import *
from ap_evsims.calibration import *
from ap_evsims.schemas import Candidate
from ap_evsims.screening import screen_candidate
from ap_evsims.portfolio import allocate_card
from ap_evsims.parlay import evaluate_parlay
from ap_evsims.ledger import Ledger

NOW=datetime(2026,10,14,1,0,tzinfo=timezone.utc)

def report(**kw):
    d=dict(sport="NHL",market="SOG",model_version="nhl-sog-v1",mode="pregame",n=800,brier=.20,market_brier=.23,logloss=.58,market_logloss=.62,training_cutoff_utc="2026-09-30T00:00:00Z",validation_end_utc="2026-10-10T00:00:00Z",authenticated=True);d.update(kw);return ValidationReport(**d)
def cand(**kw):
    d=dict(event_id="G1",sport="NHL",market="SOG",selection="Player O2.5",book="DraftKings",american_odds=110,opposite_odds=-140,quote_time_utc="2026-10-14T00:59:00Z",event_time_utc="2026-10-14T01:30:00Z",data_time_utc="2026-10-14T00:58:00Z",model_version="nhl-sog-v1",model_mode="pregame",p_model=.63,p_low=.58,lineup_verified=True,role_verified=True,live_state_verified=False,settlement_verified=True,event_group="G1",risk_groups=("PLAYER:A",),feature_cutoff_utc="2026-10-14T00:58:00Z");d.update(kw);return Candidate(**d)

class Tests(unittest.TestCase):
    def test_odds(self):
        self.assertAlmostEqual(american_to_implied(-110),110/210); self.assertAlmostEqual(american_to_decimal(150),2.5)
        a,b,v=devig_two_way(-110,-110); self.assertAlmostEqual(a,.5); self.assertGreater(v,0)
    def test_max_price(self): self.assertEqual(max_american_for_min_ev(.60,.05),-133)
    def test_legacy_candidate_is_untrusted(self): self.assertEqual(screen_candidate(cand(),report(),NOW,22)["status"],"PASS")
    def test_no_lookahead(self): self.assertIn("LOOKAHEAD_FEATURE_TIMESTAMP",screen_candidate(cand(feature_cutoff_utc="2026-10-14T01:00:30Z"),report(),NOW,22)["reasons"])
    def test_stale(self): self.assertIn("STALE_OR_FUTURE_QUOTE",screen_candidate(cand(quote_time_utc="2026-10-14T00:50:00Z"),report(),NOW,22)["reasons"])
    def test_live_separate(self):
        x=screen_candidate(cand(model_mode="live",event_time_utc="2026-10-14T00:30:00Z",live_state_verified=True),report(),NOW,22)
        self.assertIn("VALIDATION_REPORT_MISMATCH",x["reasons"])
    def test_missing_devig(self): self.assertIn("MISSING_OPPOSITE_PRICE_FOR_DEVIG",screen_candidate(cand(opposite_odds=None),report(),NOW,22)["reasons"])
    def test_unauthenticated_validation(self): self.assertIn("VALIDATION_REPORT_NOT_ELIGIBLE",screen_candidate(cand(),report(authenticated=False),NOW,22)["reasons"])
    def test_portfolio_correlation(self):
        a=screen_candidate(cand(),report(),NOW,22); b=dict(a); b["selection"]="B"; b["risk_groups"]=["PLAYER:A"]
        a.update(status="CORE_CANDIDATE",stake_usd=2); b.update(status="CORE_CANDIDATE",stake_usd=2)
        out=allocate_card([a,b],22); self.assertEqual(sum(x["status"]=="CORE_CANDIDATE" for x in out),1)
    def test_parlay_fails_closed(self): self.assertEqual(evaluate_parlay(offered_american_odds=400,scenario_joint_probability=None,legs=4)["status"],"PASS")
    def test_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            l=Ledger(Path(d)/"x.jsonl"); l.append({"a":1}); self.assertEqual(l.read()[0]["a"],1)

if __name__=="__main__":unittest.main()
