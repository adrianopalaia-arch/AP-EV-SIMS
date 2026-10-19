"""Constructed provenance checks, never empirical observations."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest

from ap_evsims.cfb_history import RollingCFBHistory, BASELINE_FEATURES
from ap_evsims.cfb_features import rolling_matchup_features
from ap_evsims.canonical import verify_feature_sources
from ap_evsims.integrity import digest
from ap_evsims.research_store import ResearchStore


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.store = ResearchStore(Path(self.tmp.name))
        self.at = '2026-10-15T10:00:00+00:00'; self.play_ids = []; self.result_ids = []
        games = [dict(id=i, homeTeam='Home', awayTeam='Away', completed=True, homePoints=20, awayPoints=10,
                      startDate=f'2026-09-{i:02d}T10:00:00Z', season=2026, week=i, seasonType='regular') for i in range(1, 4)]
        games.append(dict(id=4, homeTeam='Home', awayTeam='Away', completed=False, startDate='2026-10-17T10:00:00Z', startTimeTBD=False))
        self.result_ids.append(self.capture('games', games))
        for i in range(1, 4):
            rows = [dict(id=n, gameId=i, offense=t, defense='Away' if t=='Home' else 'Home', down=1, distance=10,
                         yardsGained=6 if t=='Home' else 3, playType='Rush', ppa=.2 if t=='Home' else -.1)
                    for n, t in enumerate(['Home']*40 + ['Away']*40)]
            self.play_ids.append(self.capture('plays', rows, params=dict(year=2026, week=i, seasonType='regular')))
    def tearDown(self): self.tmp.cleanup()
    def capture(self, endpoint, rows, at='2026-10-14T10:00:00Z', params=None):
        return self.store.archive(provider='cfbd', endpoint=endpoint, parameters=params or {}, body=json.dumps(rows).encode(),
            fetched_at=at, observed_at=at, available_at=at, availability_basis='recorded_response')['snapshot_id']
    def history(self, **kwargs):
        return RollingCFBHistory(self.store, **(dict(plays_snapshot_ids=self.play_ids, results_snapshot_ids=self.result_ids, as_of=self.at)|kwargs))
    def features(self, history=None, **kwargs):
        return (history or self.history()).materialize(**(dict(event_id='4', home_team='Home', away_team='Away')|kwargs))
    def test_multiple_weeks_are_combined_and_match_existing_formula(self):
        h=self.history(); f=self.features(h)
        self.assertEqual(h.counts['eligible_play_rows'], 240); self.assertEqual(set(f.values), set(BASELINE_FEATURES))
        old=rolling_matchup_features(h.plays,event_id='4',home_team='Home',away_team='Away',as_of=self.at)
        self.assertEqual({k:v.value for k,v in f.values.items()}, {k:v.value for k,v in old.values.items()})
        verify_feature_sources(self.store,f)
        self.assertNotIn('offensive_epa_diff',f.values)
    def test_future_capture_cannot_be_backdated_from_game_or_play_time(self):
        with self.assertRaisesRegex(ValueError,'AVAILABILITY'): self.history(as_of='2026-10-13T10:00:00Z')
    def test_overlap_deduplicates_and_later_revision_wins(self):
        m=self.store.manifest(self.play_ids[0]); p=self.store.payload(m)
        self.play_ids.append(self.capture('plays',p,params={'team':'Home'}))
        self.assertEqual(self.history().counts['eligible_play_rows'],240)
        p[0]['yardsGained']=0
        self.play_ids.append(self.capture('plays',p,at='2026-10-14T11:00:00Z',params={'team':'Home'}))
        h=self.history(); self.assertEqual(next(p for p in h.plays if p.play_id=='1:0').yards,0)
        self.assertEqual(self.features(h).values['ppa_diff'].available_at,'2026-10-14T11:00:00+00:00')
    def test_replaced_query_does_not_resurrect_deleted_plays(self):
        m=self.store.manifest(self.play_ids[0])
        self.play_ids.append(self.capture('plays',[],at='2026-10-14T11:00:00Z',params=m['parameters']))
        self.assertEqual(self.history().counts['prior_games'],2)
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'): self.features()
    def test_conflicting_overlap_excludes_entire_game(self):
        m=self.store.manifest(self.play_ids[0]); p=self.store.payload(m); p[0]['yardsGained']=0
        self.play_ids.append(self.capture('plays',p,params={'team':'Home'}))
        h=self.history(); self.assertEqual(h.counts['conflicting_games'],1)
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'): self.features(h)
    def test_duplicate_within_query_excludes_game(self):
        m=self.store.manifest(self.play_ids[0]); p=self.store.payload(m)
        self.play_ids[0]=self.capture('plays',p+[p[0]],params=m['parameters'])
        self.assertEqual(self.history().counts['conflicting_games'],1)
    def test_wrong_week_query_and_team_identity_are_excluded(self):
        m=self.store.manifest(self.play_ids[0]); p=self.store.payload(m)
        self.play_ids[0]=self.capture('plays',p,params={'week':2})
        self.assertEqual(self.history().counts['PLAY_QUERY_SCOPE_MISMATCH'],80)
        p[0]['offense']='Unknown';self.play_ids[0]=self.capture('plays',p)
        self.assertEqual(self.history().counts['PLAY_TEAM_IDENTITY_MISMATCH'],1)
    def test_unsettled_and_impossible_completed_games_are_excluded(self):
        m=self.store.manifest(self.result_ids[0]); games=self.store.payload(m)
        games[0]['completed']=False;games[1]['startDate']='2026-10-17T10:00:00Z'
        self.result_ids.append(self.capture('games',games,at='2026-10-14T11:00:00Z'))
        h=self.history();self.assertEqual(h.counts['GAME_NOT_COMPLETED'],80);self.assertEqual(h.counts['LOOKAHEAD_RISK'],80)
    def test_current_game_wrong_identity_and_unknown_start_cannot_predict(self):
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):self.features(event_id='1')
        with self.assertRaisesRegex(ValueError,'MAPPING'):self.features(home_team='Unknown')
        m=self.store.manifest(self.result_ids[0]);p=self.store.payload(m);p[-1]['startTimeTBD']=True
        self.result_ids.append(self.capture('games',p,at='2026-10-14T11:00:00Z'))
        with self.assertRaisesRegex(ValueError,'START_UNCONFIRMED'):self.features()
    def test_missing_ppa_does_not_become_zero_or_epa(self):
        for i,sid in enumerate(self.play_ids):
            m=self.store.manifest(sid);p=self.store.payload(m)
            for row in p:row['ppa']=None
            self.play_ids[i]=self.capture('plays',p,params=m['parameters'])
        f=self.features();self.assertNotIn('ppa_diff',f.values);self.assertEqual(len(f.values),3)
    def test_forged_recipe_and_raw_mutation_rejected(self):
        f=self.features();v=f.values['ppa_diff'];path=self.store.root/'features'/(v.payload_hash+'.json')
        body=json.loads(path.read_text());body['values']['ppa_diff']=.99;fingerprint=digest(body)
        (self.store.root/'features'/(fingerprint+'.json')).write_text(json.dumps(body))
        forged=replace(f,values={'ppa_diff':replace(v,value=.99,snapshot_id='derived-'+fingerprint,payload_hash=fingerprint)})
        with self.assertRaisesRegex(ValueError,'DERIVATION'):verify_feature_sources(self.store,forged)
        m=self.store.manifest(self.play_ids[0]);(self.store.root/m['raw_path']).write_text('[]')
        with self.assertRaisesRegex(ValueError,'HASH'):self.history()
    def test_lookback_and_minimum_samples_remain_enforced(self):
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):self.features(self.history(lookback_days=7))
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):self.features(minimum_plays=121)
        with self.assertRaisesRegex(ValueError,'INVALID_FEATURE_POLICY'):self.features(minimum_games=True)
