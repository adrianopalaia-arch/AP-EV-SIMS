"""Constructed source tests; never reported as empirical model observations."""
import json, tempfile, unittest
from dataclasses import replace
from pathlib import Path
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.cfb_universe import build_cfb_universe
from ap_evsims.canonical import materialize_rolling_features,verify_feature_sources
from ap_evsims.cfb_features import normalize_cfbd_plays
from ap_evsims.integrity import digest,utc


def source(store, warehouse, endpoint, payload, at='2026-10-14T10:00:00Z'):
    m=store.archive(provider='cfbd',endpoint=endpoint,parameters={},body=json.dumps(payload).encode(),
        fetched_at=at,observed_at=at,available_at=at,availability_basis='recorded_response')
    warehouse.ingest_manifest(store,m)
    return m


def game(identity=1, **kwargs):
    return dict(id=identity,homeTeam='Home',awayTeam='Away',homeId=1,awayId=2,season=2026,week=7,
        homeClassification='fbs',awayClassification='fbs',**(dict(startDate='2026-10-17T18:00:00Z',startTimeTBD=False,completed=False)|kwargs))


class UniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=ResearchStore(Path(self.tmp.name)/'data'); self.w=Warehouse(self.s.root)
    def tearDown(self):self.tmp.cleanup()
    def build(self,at='2026-10-14T11:00:00Z'):
        return build_cfb_universe(self.s,self.w,at,[])
    def test_unquoted_game_retained_and_not_complete_season(self):
        source(self.s,self.w,'games',[game()])
        r=self.build();self.assertEqual(r['games_scanned'],1)
        self.assertIn('NO_MATCHED_MARKET',r['games'][0]['pass_reason'])
        self.assertIn('NOT_A_COMPLETE_SEASON',r['coverage']);self.assertEqual(r['qualifying_real_sample'],0)
    def test_future_revision_excluded_then_latest_revision_retained(self):
        source(self.s,self.w,'games',[game()])
        source(self.s,self.w,'games',[game(startTimeTBD=True)],'2026-10-14T12:00:00Z')
        self.assertNotIn('EVENT_START_UNCONFIRMED',self.build()['games'][0]['pass_reason'])
        self.assertIn('EVENT_START_UNCONFIRMED',self.build('2026-10-14T13:00:00Z')['games'][0]['pass_reason'])
    def test_duplicate_and_impossible_completion_fail_closed(self):
        source(self.s,self.w,'games',[game(completed=True,homePoints=20,awayPoints=10)]*2)
        reasons=self.build()['games'][0]['pass_reason']
        self.assertIn('LOOKAHEAD_RISK',reasons);self.assertIn('CONFLICTING_GAME_REVISION',reasons)
    def test_mutated_raw_is_rejected(self):
        m=source(self.s,self.w,'games',[game()]);(self.s.root/m['raw_path']).write_text('[]')
        with self.assertRaisesRegex(ValueError,'HASH'):self.build()
    def feature_sources(self):
        prior=game(startDate='2026-10-10T18:00:00Z',completed=True,homePoints=20,awayPoints=10)
        results=source(self.s,self.w,'games',[prior],'2026-10-11T10:00:00Z')
        plays=[dict(id=i,gameId=1,offense=t,defense='Away' if t=='Home' else 'Home',down=1,distance=10,yardsGained=6,
            playType='Rush',ppa=.1) for i,t in enumerate(('Home','Away'))]
        pm=source(self.s,self.w,'plays',plays,'2026-10-11T09:00:00Z')
        return pm,results
    def test_completion_proof_availability_is_max_not_backdated(self):
        pm,r=self.feature_sources()
        rows,_=normalize_cfbd_plays(self.s.payload(pm),pm,game_observed_times={'1':r['available_at']})
        self.assertTrue(all(utc(p.available_at)==utc(r['available_at']) for p in rows))
    def test_materialization_recomputes_and_detects_rehashed_forgery(self):
        pm,r=self.feature_sources()
        f,_=materialize_rolling_features(self.s,plays_snapshot_id=pm['snapshot_id'],results_snapshot_id=r['snapshot_id'],
            event_id='future',home_team='Home',away_team='Away',as_of='2026-10-14T10:00:00Z',minimum_plays=1,minimum_games=1)
        verify_feature_sources(self.s,f)
        self.assertNotIn('offensive_epa_diff',f.values)
        v=f.values['success_rate_diff'];body=json.loads((self.s.root/'features'/(v.payload_hash+'.json')).read_text())
        body['values']['success_rate_diff']=.8;h=digest(body)
        (self.s.root/'features'/(h+'.json')).write_text(json.dumps(body))
        forged=replace(f,values={'success_rate_diff':replace(v,value=.8,payload_hash=h,snapshot_id='derived-'+h)})
        with self.assertRaisesRegex(ValueError,'DERIVATION'):verify_feature_sources(self.s,forged)
