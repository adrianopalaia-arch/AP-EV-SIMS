"""Fixture assertions test mechanics only, never empirical model performance."""
import json
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile
import unittest
from ap_evsims.prop_research import PlayerOutcome,OpportunityModel,evaluate,summarize
from ap_evsims.providers.public_stats import PublicStatsArchive
from ap_evsims.providers.live import HTTPResponse
from ap_evsims.prop_prices import normalize_props
from ap_evsims.research_store import ResearchStore


def row(i,**kw):
    d=dict(sport='NBA',market='points',event_id=str(i),player_id=str(i%10),player_name='Player',team_id='A',opponent_id='B',
        played_on=(datetime(2024,1,1,tzinfo=timezone.utc)+timedelta(days=i//10)).date().isoformat(),season=2025,
        opportunity=25.,outcome=10,source_id='a'*64,source_hash='b'*64,captured_at='2026-10-16T00:00:00Z')
    d.update(kw);return PlayerOutcome(**d)


class PropResearchTests(unittest.TestCase):
    def test_real_format_train_without_odds(self):
        m,records,_=evaluate([row(i) for i in range(400)],'NBA','points')
        self.assertEqual(m.n,400);self.assertGreater(len(records),0);self.assertEqual(summarize(records)['mae'],0)
    def test_future_target_outcome_never_changes_forecast(self):
        rows=[row(i) for i in range(400)];_,a,_=evaluate(rows,'NBA','points')
        _,b,_=evaluate(rows[:-1]+[replace(rows[-1],outcome=100)],'NBA','points')
        self.assertEqual(a[-1]['projection'],b[-1]['projection']);self.assertEqual(a[:-1],b[:-1])
    def test_target_workload_never_used(self):
        rows=[row(i) for i in range(400)];_,a,_=evaluate(rows,'NBA','points')
        _,b,_=evaluate(rows[:-1]+[replace(rows[-1],opportunity=1)],'NBA','points')
        self.assertEqual(a[-1]['projected_opportunity'],b[-1]['projected_opportunity'])
    def test_duplicates_reject(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):evaluate([row(1),row(1)],'NBA','points')
    def test_sport_market_alias_reject(self):
        with self.assertRaisesRegex(ValueError,'CROSS_SPORT'):OpportunityModel('NFL','points')
    def test_wrong_player_team_reject(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY'):replace(row(1),team_id='B').validate()
    def test_missing_outcome_not_zero(self):
        with self.assertRaisesRegex(ValueError,'OUTCOME'):replace(row(1),outcome=None).validate()
    def test_timestamp_cannot_backdate_capture(self):
        with self.assertRaises(ValueError):replace(row(1),captured_at='2023-01-01T00:00:00Z').validate()
    def test_distributions_and_uncalibrated_null(self):
        m,_,_=evaluate([row(i) for i in range(400)],'NBA','points');p=m.predict('1','2025-01-01')
        self.assertAlmostEqual(sum(p['distribution'].values()),1);self.assertFalse(p['recommendations_enabled'])
        self.assertIsNone(p['p_low']);self.assertIsNone(p['calibrated_probability'])
    def test_own_result_in_history_rejects(self):
        m,_,_=evaluate([row(i) for i in range(400)],'NBA','points')
        with self.assertRaisesRegex(ValueError,'LEAKAGE'):m.predict('1','2024-02-01')
    def test_unknown_player_rejects(self):
        m,_,_=evaluate([row(i) for i in range(400)],'NBA','points')
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):m.predict('unknown','2025-01-01')
    def test_public_raw_hash_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def transport(url,headers):calls.append(url);return HTTPResponse(200,b'[{"id":1}]','2026-10-16T00:00:00Z')
            s=PublicStatsArchive(d,transport);m=s.capture('NHL','https://api-web.nhle.com/v1/test')
            self.assertEqual(s.read(m),[{'id':1}]);s.capture('NHL','https://api-web.nhle.com/v1/test');self.assertEqual(len(calls),1)
            (Path(d)/m['path']).write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError,'HASH'):s.read(m)
    def test_secret_and_unapproved_url_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            s=PublicStatsArchive(d)
            for url in ('https://api-web.nhle.com/v1/test?apiKey=not-a-secret','https://unapproved.test/stats'):
                with self.assertRaises(ValueError):s.capture('NHL',url)


class PropPriceTests(unittest.TestCase):
    def capture(self,s,p):
        at='2026-10-16T00:00:00Z';return s.archive(provider='odds',endpoint='sports/basketball_nba/events/1/odds',parameters={},body=json.dumps(p).encode(),
            fetched_at=at,observed_at=at,available_at=at,availability_basis='recorded_response')
    def payload(self):
        return dict(id='1',sport_key='basketball_nba',home_team='Home',away_team='Away',commence_time='2026-10-17T00:00:00Z',
            bookmakers=[dict(key='draftkings',markets=[dict(key='player_points',last_update='2026-10-16T00:00:00Z',outcomes=[
                dict(name='Over',description='Player A',point=20,price=-110),dict(name='Under',description='Player A',point=20,price=-110)])])])
    def test_pair_integer_push_unknown_stale_and_no_identity(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);m=self.capture(s,self.payload());qs,_=normalize_props(s,m,'NBA','2026-10-16T00:05:00Z')
            self.assertEqual(qs[0]['over_no_vig'],.5);self.assertIsNone(qs[0]['market_push_probability']);self.assertIsNone(qs[0]['player_id'])
            self.assertIn('STALE_PRICE',qs[0]['reasons'])
    def test_wrong_player_or_alternate_line_not_paired(self):
        for field,value in (('description','Player B'),('point',21)):
            with tempfile.TemporaryDirectory() as d:
                s=ResearchStore(d);p=self.payload();p['bookmakers'][0]['markets'][0]['outcomes'][1][field]=value
                qs,rejected=normalize_props(s,self.capture(s,p),'NBA','2026-10-16T00:00:00Z');self.assertFalse(qs);self.assertIn('MISSING_PROP_COUNTERPART',rejected)
    def test_suspended_missing_side_is_not_reused(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);p=self.payload();p['bookmakers'][0]['markets'][0]['outcomes'].pop()
            self.assertFalse(normalize_props(s,self.capture(s,p),'NBA','2026-10-16T00:00:00Z')[0])
    def test_cross_sport_payload_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d)
            with self.assertRaisesRegex(ValueError,'SOURCE'):normalize_props(s,self.capture(s,self.payload()),'NFL','2026-10-16T00:00:00Z')
