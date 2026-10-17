"""Constructed contract fixtures only; never empirical betting evidence."""
import unittest, tempfile, json
from pathlib import Path
from dataclasses import replace, asdict
from unittest.mock import patch
from ap_evsims.research_store import ResearchStore
from ap_evsims.providers.live import CFBDClient, OddsAPIClient, WeatherClient, HTTPResponse, ProviderAccessError
from ap_evsims.providers.normalize import odds_contexts, require_historical_availability
from ap_evsims.historical import HistoricalObservation, validate_dataset, settle, unit_profit, partition, FoldWindow
from test_phase2_base import feature, snapshot, market

def historical(**kw):
    d=dict(observation_id='r1',features=snapshot(),context=market(),home_score=20,away_score=23,
           result_available_at='2024-08-04T00:00:00Z',result_snapshot_id='result-fixture',result_payload_hash='b'*64,game_status='final')
    d.update(kw); return HistoricalObservation(**d)

def odds_payload():
    return dict(timestamp='2024-08-03T01:00:00Z',data=[dict(id='provider-g1',home_team='Home',away_team='Away',commence_time='2024-08-03T04:00:00Z',bookmakers=[dict(key='draftkings',last_update='2024-08-03T01:00:00Z',markets=[dict(key='spreads',outcomes=[dict(name='Home',point=3.5,price=-110),dict(name='Away',point=-3.5,price=-110)])])])])

class HistoricalTests(unittest.TestCase):
    def test_duplicate_economic_observations(self):
        r=historical()
        with self.assertRaisesRegex(ValueError,'DUPLICATE'): validate_dataset([r,replace(r,observation_id='new',context=replace(r.context,book='fanduel'))])
    def test_push_loss_win_and_refund(self):
        r=historical(context=market(line=3,opposite_line=3)); self.assertEqual(settle(r),'PUSH')
        self.assertEqual(settle(historical()),'WIN')
        self.assertEqual(settle(historical(context=market(line=2.5,opposite_line=2.5))),'LOSS')
        self.assertEqual(unit_profit('PUSH',-110),0); self.assertAlmostEqual(unit_profit('WIN',-110),100/110)
    def test_totals_and_moneyline(self):
        r=historical(context=market(market_type='total',selection='over',line=43,opposite_line=43))
        self.assertEqual(settle(r),'PUSH')
        self.assertEqual(settle(replace(r,context=replace(r.context,line=42.5,opposite_line=42.5))),'WIN')
        self.assertEqual(settle(historical(context=market(market_type='win',line=None,opposite_line=None))),'LOSS')
    def test_no_unsettled_or_future_result(self):
        with self.assertRaisesRegex(ValueError,'UNSETTLED'): historical(game_status='scheduled').validate()
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): historical(result_available_at='2024-08-03T03:00:00Z').validate()
    def test_chronological_folds_and_late_result(self):
        window=FoldWindow('2024-08-05T00:00:00Z','2024-08-10T00:00:00Z','2024-08-15T00:00:00Z','2024-08-20T00:00:00Z')
        a,b,c,d=partition([historical()],window); self.assertEqual(len(a),1); self.assertFalse(b or c or d)
        a,_,_,_=partition([historical(result_available_at='2024-08-06T00:00:00Z')],window); self.assertEqual(a,[])
        with self.assertRaisesRegex(ValueError,'INVALID_TIME_FOLD'): partition([],replace(window,training_end=window.selection_end))
    def test_event_overlap_across_markets(self):
        r=historical(); s=replace(r,observation_id='total',features=replace(r.features,timestamp='2024-08-07T00:00:00Z'),context=market(market_type='total',selection='over',prediction_timestamp='2024-08-07T01:00:00Z',quote_timestamp='2024-08-07T01:00:00Z',event_timestamp='2024-08-07T04:00:00Z'),result_available_at='2024-08-08T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'FOLD_LEAKAGE'): partition([r,s],FoldWindow('2024-08-05T00:00:00Z','2024-08-10T00:00:00Z','2024-08-15T00:00:00Z','2024-08-20T00:00:00Z'))

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=ResearchStore(Path(self.tmp.name)/'data')
    def tearDown(self): self.tmp.cleanup()
    def response(self,payload): return HTTPResponse(200,json.dumps(payload).encode(),'2026-10-14T05:00:00Z')
    def test_historical_odds_and_raw_hash(self):
        with patch.dict('os.environ',{'THE_ODDS_API_KEY':'contract-test-secret'}):
            client=OddsAPIClient(self.store,lambda url,headers:self.response(odds_payload()))
            m=client.fetch(historical_at='2024-08-03T01:03:00Z')
        self.assertEqual(m['available_at'],'2024-08-03T01:00:00Z'); self.assertEqual(self.store.payload(m),odds_payload())
        self.assertNotIn('apiKey',m['parameters'])
        contexts,rejections=odds_contexts(self.store.payload(m),m,prediction_at='2024-08-03T01:00:00Z',event_mapping={'provider-g1':dict(event_id='g1',home_team='Home',away_team='Away')})
        self.assertEqual(len(contexts),1); self.assertEqual(rejections,[])
        self.assertEqual(contexts[0].opposite_line,3.5)
    def test_missing_pair_and_unverified_mapping(self):
        p=odds_payload(); m=dict(available_at=p['timestamp'],observed_at=p['timestamp'],availability_basis='historical_odds_snapshot',snapshot_id='x')
        _,r=odds_contexts(p,m,prediction_at=p['timestamp'],event_mapping={}); self.assertEqual(r[0]['reason'],'EVENT_MAPPING_UNVERIFIED')
        p['data'][0]['bookmakers'][0]['markets'][0]['outcomes'].pop()
        _,r=odds_contexts(p,m,prediction_at=p['timestamp'],event_mapping={'provider-g1':dict(event_id='g1',home_team='Home',away_team='Away')}); self.assertEqual(r[0]['reason'],'MISSING_MARKET_PAIR')
    def test_historical_403_never_fabricates(self):
        with patch.dict('os.environ',{'THE_ODDS_API_KEY':'contract-test-secret'}):
            c=OddsAPIClient(self.store,lambda u,h:HTTPResponse(403,b'{}','2026-10-14T05:00:00Z'))
            with self.assertRaisesRegex(ProviderAccessError,'BLOCKED_BY_HISTORICAL_ODDS_ACCESS'): c.fetch(historical_at='2024-08-03T01:03:00Z')
        self.assertEqual(list((self.store.root/'raw/odds').iterdir()),[])
    def test_historical_future_snapshot(self):
        with patch.dict('os.environ',{'THE_ODDS_API_KEY':'contract-test-secret'}):
            c=OddsAPIClient(self.store,lambda u,h:self.response(odds_payload()))
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): c.fetch(historical_at='2024-08-03T00:00:00Z')
    def test_cfbd_and_weather_not_backdated(self):
        with patch.dict('os.environ',{'CFBD_API_KEY':'contract-test-secret'}):
            m=CFBDClient(self.store,lambda u,h:self.response([])).fetch('ratings/core',year=2024)
        with self.assertRaisesRegex(ValueError,'UNVERIFIED'): require_historical_availability(m,'2024-08-03T00:00:00Z')
        w=WeatherClient(self.store,lambda u,h:self.response({})).points(41,-93)
        with self.assertRaisesRegex(ValueError,'UNVERIFIED'): require_historical_availability(w,'2024-08-03T00:00:00Z')
    def test_missing_credentials_no_network(self):
        with patch.dict('os.environ',{'CFBD_API_KEY':'','THE_ODDS_API_KEY':''}):
            with self.assertRaisesRegex(ProviderAccessError,'MISSING_CFBD'): CFBDClient(self.store).games(2024)
            with self.assertRaisesRegex(ProviderAccessError,'BLOCKED_BY_HISTORICAL'): OddsAPIClient(self.store).fetch(historical_at='2024-08-03T00:00:00Z')
    def test_payload_tampering_and_secret_metadata(self):
        m=self.store.archive(provider='cfbd',endpoint='games',parameters={},body=b'[]',fetched_at='2026-10-14T05:00:00Z')
        (self.store.root/m['raw_path']).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): self.store.payload(m)
        with self.assertRaisesRegex(ValueError,'SECRET'): self.store.archive(provider='odds',endpoint='x',parameters={'apiKey':'never-store'},body=b'[]',fetched_at='2026-10-14T05:00:00Z')
    def test_no_arbitrary_availability_assertion(self):
        with self.assertRaisesRegex(ValueError,'unproven'): self.store.archive(provider='cfbd',endpoint='games',parameters={},body=b'[]',fetched_at='2026-10-14T05:00:00Z',observed_at='2024-08-03T00:00:00Z',available_at='2024-08-03T00:00:00Z',availability_basis='recorded_response')
