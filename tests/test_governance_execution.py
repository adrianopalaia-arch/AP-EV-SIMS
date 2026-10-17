import tempfile,unittest
from pathlib import Path
from dataclasses import replace
from ap_evsims.governance import ExperimentLedger,assess_challenger
from ap_evsims.execution import MarketIdentity,execution_reasons,refresh_reasons,pessimistic_decimal_price,simple_edge_flags
from ap_evsims.integrity import utc

class GovernanceExecutionTests(unittest.TestCase):
    def test_holdout_once_and_variants_retained(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=ExperimentLedger(Path(t)/'g.sqlite');h=ledger.lock_holdout('a'*64,'2025-09-01T00:00:00Z','2026-01-01T00:00:00Z')
            args=dict(hypothesis='registered fixture hypothesis',registered_at='2025-01-01T00:00:00Z',training_end='2024-01-01T00:00:00Z',validation_end='2024-09-01T00:00:00Z',calibration_end='2025-01-01T00:00:00Z',holdout_id=h,dataset_hash='a'*64,features=['prior_feature'],model='simple',threshold=.04,feature_version='v1')
            first=ledger.register(**args);args['model']='complex';second=ledger.register(**args)
            self.assertEqual(ledger.variant_count(),2);ledger.seal_final_result(first,{'fixture_result':True})
            with self.assertRaisesRegex(ValueError,'FINAL_HOLDOUT_ALREADY_CONSUMED'):ledger.seal_final_result(second,{})
            with self.assertRaisesRegex(ValueError,'FINAL_HOLDOUT_ALREADY_CONSUMED'):ledger.register(**args)
    def test_holdout_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=ExperimentLedger(Path(t)/'g.sqlite');ledger.lock_holdout('a'*64,'2025-01-01T00:00:00Z','2026-01-01T00:00:00Z')
            with self.assertRaisesRegex(ValueError,'OVERLAPPING_FINAL_HOLDOUT'):ledger.lock_holdout('a'*64,'2025-06-01T00:00:00Z','2027-01-01T00:00:00Z')
    def test_good_fixture_roi_cannot_promote_model(self):
        a=[dict(event_id='e',market='spread',selection='home',probability=.5,outcome=1,dataset_kind='synthetic_test',season=2025,regime='normal',clv=None,roi=100)]
        b=[dict(a[0],probability=.9)]
        r=assess_challenger(a,b);self.assertEqual(r['action'],'KEEP_CHAMPION');self.assertIn('NON_EMPIRICAL_EVIDENCE',r['reasons'])
    def identity(self):return MarketIdentity('e','2026-10-14T18:00:00Z','draftkings','spread','full_game','team-home',3.5,'fixture-rule')
    def test_stale_suspended_async_pair_and_unknown_execution_fail(self):
        reasons=execution_reasons(self.identity(),at='2026-10-14T17:00:00Z',quote_at='2026-10-14T16:00:00Z',available_at='2026-10-14T16:01:00Z',opposite_quote_at='2026-10-14T15:00:00Z',market_open=False)
        for r in ('STALE_PRICE','NO_VIG_UNRELIABLE','MARKET_SUSPENDED_OR_UNVERIFIED','QUOTE_EXECUTION_UNVERIFIED','UNVERIFIED_LINEUP'):self.assertIn(r,reasons)
    def test_line_or_schedule_change_requires_new_probability(self):
        a=self.identity()
        for b in (replace(a,line=2.5),replace(a,event_start='2026-10-15T18:00:00Z'),replace(a,settlement_rule_id='other-rule')):
            self.assertIn('PROBABILITY_RECALCULATION_REQUIRED',refresh_reasons(a,b,-110,-115))
        self.assertEqual(refresh_reasons(a,a,-120,-115),['PRICE_MOVED'])
    def test_names_cannot_replace_player_ids(self):
        with self.assertRaisesRegex(ValueError,'UNVERIFIED_PLAYER_IDENTITY'):self.identity().validate(player_market=True)
    def test_slippage_is_monotonic(self):
        prices=[pessimistic_decimal_price(-110,c) for c in (0,5,10,15)]
        self.assertEqual(prices,sorted(prices,reverse=True))
    def test_simple_edge_flag_never_overrides_phase1_pass(self):
        self.assertFalse(simple_edge_flags('PASS','HIGH','HIGH',.6,.6,.6,.5,True)['CLEAN_EDGE'])
        self.assertFalse(simple_edge_flags('RESEARCH_CANDIDATE','HIGH','FAIL',.6,.6,.6,.5,True)['CLEAN_EDGE'])
    def test_dst_midnight_and_naive_dates(self):
        self.assertLess(utc('2026-11-01T01:30:00-05:00'),utc('2026-11-01T01:30:00-06:00'))
        self.assertEqual(utc('2026-10-13T23:00:00-10:00'),utc('2026-10-14T09:00:00Z'))
        with self.assertRaises(ValueError):utc('2026-10-14T09:00:00')
