"""Application tests use explicitly constructed inputs, never performance samples."""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from ap_evsims.product import daily_card, read_card, current_quotes, card_lock, model_catalog, preflight
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.providers.live import HTTPResponse
from test_warehouse import archive


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name)
        self.s=ResearchStore(self.repo/'data');self.w=Warehouse(self.s.root)
        self.env=patch.dict('os.environ',{'CFBD_API_KEY':'','THE_ODDS_API_KEY':''});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def run_card(self,**kwargs):return daily_card(self.repo,now=kwargs.pop('now','2026-10-14T10:01:00Z'),**kwargs)
    def test_cold_start_and_missing_credentials_no_network_or_fake_models(self):
        transport=lambda *args: self.fail('missing credentials must not reach network')
        r=self.run_card(transport=transport)
        self.assertEqual(r['status'],'NO QUALIFYING BETS');self.assertEqual(r['games_scanned'],0)
        self.assertEqual(r['real_model_evaluation_sample'],0)
        self.assertEqual(r['refresh_failures'][0]['endpoint_status'],'MISSING_CREDENTIAL')
        _,feeds=read_card(self.repo);self.assertEqual(feeds['latest_predictions.json'],[])
        self.assertTrue((self.repo/'reports/MORNING_CARD.md').is_file())
    def test_offline_real_shape_quotes_are_pass_with_complete_audit_fields(self):
        archive(self.s)
        r=self.run_card(offline=True);_,f=read_card(self.repo);row=f['latest_passes.json'][0]
        self.assertEqual(r['games_scanned'],1);self.assertEqual(len(f['latest_passes.json']),2)
        self.assertIsNone(row['p_low']);self.assertIsNone(row['expected_value'])
        self.assertIn('MODEL_NOT_CALIBRATED',row['pass_reason'])
        self.assertTrue({'event_start','sportsbook_quote','lineup_injury','feature_snapshot','model_prediction','decision'}<=row['data_timestamps'].keys())
        self.assertAlmostEqual(sum(v['market_no_vig_probability'] for v in f['latest_passes.json']),1)
    def test_price_move_is_recomputed_and_flagged(self):
        archive(self.s);self.run_card(offline=True)
        archive(self.s,'2026-10-14T10:02:00Z',line=2.5,price=-120)
        self.run_card(offline=True,now='2026-10-14T10:03:00Z');_,f=read_card(self.repo)
        home=next(r for r in f['latest_passes.json'] if r['selection']=='Home')
        self.assertEqual(home['line'],2.5);self.assertEqual(home['odds'],-120)
        self.assertIn('PRICE_MOVED',home['pass_reason']);self.assertIsNone(home['expected_value'])
    def test_empty_latest_slate_removes_suspended_market(self):
        archive(self.s);self.run_card(offline=True)
        t='2026-10-14T10:02:00Z'
        self.s.archive(provider='odds',endpoint='sports/americanfootball_ncaaf/odds',parameters={},body=b'[]',
            fetched_at=t,observed_at=t,available_at=t,availability_basis='recorded_response')
        r=self.run_card(offline=True,now='2026-10-14T10:03:00Z')
        self.assertEqual(r['market_sides_scanned'],0);self.assertEqual(r['suspended_or_superseded_quotes'],2)
    def test_stale_and_started_games_never_recommend(self):
        archive(self.s)
        self.run_card(offline=True,now='2026-10-14T10:10:00Z');_,f=read_card(self.repo)
        self.assertIn('STALE_PRICE',f['latest_passes.json'][0]['pass_reason'])
        self.assertEqual(self.run_card(offline=True,now='2026-10-14T18:01:00Z')['games_scanned'],0)
    def test_restart_is_idempotent_and_lock_released_after_error(self):
        archive(self.s);self.run_card(offline=True);count=self.w.health()['odds_quotes']
        self.run_card(offline=True);self.assertEqual(self.w.health()['odds_quotes'],count)
        with self.assertRaises(RuntimeError):
            with card_lock(self.s.root):raise RuntimeError('test-only')
        with card_lock(self.s.root):pass
    def test_concurrent_refresh_rejected(self):
        with card_lock(self.s.root):
            with self.assertRaisesRegex(ValueError,'ALREADY_RUNNING'):
                with card_lock(self.s.root):pass
    def test_partial_publication_rejected(self):
        self.run_card(offline=True)
        (self.repo/'outputs/latest_edges.json').write_text('[{"fake":true}]')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):read_card(self.repo)
    def test_public_card_contains_no_private_balance(self):
        from ap_evsims.accounting import AccountLedger
        # A private sentinel in an unrelated local file must not enter publication.
        (self.s.root/'settlements/private.json').write_text('{"balance":123456789}')
        self.run_card(offline=True)
        for p in (self.repo/'outputs').glob('*.json'):self.assertNotIn('123456789',p.read_text())
    def test_provider_outage_redacts_authenticated_response(self):
        with patch.dict('os.environ',{'THE_ODDS_API_KEY':'fixture-secret-not-real'}):
            r=self.run_card(transport=lambda *a:HTTPResponse(503,b'{"error":"https://example.invalid/?apiKey=fixture-secret-not-real"}','2026-10-14T10:00:00Z',{}))
            self.assertEqual(r['refresh_failures'][0]['endpoint_status'],503)
            for p in self.repo.rglob('*.json'):self.assertNotIn('fixture-secret-not-real',p.read_text())
    def test_all_requested_markets_visible_without_fake_prop_prices(self):
        catalog=model_catalog([])
        self.assertEqual(len(catalog),26)
        self.assertIn('Rushing attempts',{r['market'] for r in catalog})
        self.assertIn('Game total',{r['market'] for r in catalog})
        self.assertTrue(all(r['status']=='UNVALIDATED' and r['probability'] is None for r in catalog))
    def test_unknown_nhl_availability_never_qualifies(self):
        m=archive(self.s);self.w.ingest_manifest(self.s,m);self.w.record_odds(self.s,m)
        quotes=self.w.as_of_quotes('2026-10-14T10:01:00Z')
        for q in quotes:q['sport']='NHL'
        rows=preflight(quotes,'2026-10-14T10:01:00Z')
        self.assertTrue(all(r['decision']=='PASS' and 'UNCONFIRMED_GOALIE' in r['pass_reason'] and 'UNVERIFIED_LINEUP' in r['pass_reason'] for r in rows))
    def test_forced_refresh_respects_minimum_cooldown_and_budget(self):
        from ap_evsims.operations import collect_odds
        m=archive(self.s);self.w.ingest_manifest(self.s,m);self.w.record_odds(self.s,m)
        forbidden=lambda *a:self.fail('network during cooldown or budget limit')
        r=collect_odds(self.s,self.w,now='2026-10-14T10:00:30Z',force_refresh=True,transport=forbidden)
        self.assertEqual(r['results'][0]['status'],'CACHED_CADENCE')
        r=collect_odds(self.s,self.w,now='2026-10-14T11:00:00Z',force_refresh=True,daily_credit_cap=0,transport=forbidden)
        self.assertEqual(r['results'][0]['status'],'QUOTA_BUDGET_LIMIT')
    def test_ui_cold_start_and_live_separation(self):
        from streamlit.testing.v1 import AppTest
        code='from pathlib import Path\nfrom ap_evsims.dashboard import main\nmain(Path('+repr(str(self.repo))+'))'
        app=AppTest.from_string(code,default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.title[0].value,'AP EV/SIMS')
        self.assertEqual([m.value for m in app.metric],['0','0','0'])
        app.radio[0].set_value('Live').run()
        self.assertIn('LIVE MODE UNAVAILABLE',app.warning[0].value)
        self.assertEqual(len(app.dataframe),0)
