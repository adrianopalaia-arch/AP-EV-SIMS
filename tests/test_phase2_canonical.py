"""Constructed payloads verify joins and tamper rejection, not provider performance."""
import unittest,tempfile,json
from pathlib import Path
from dataclasses import replace
from ap_evsims.research_store import ResearchStore
from ap_evsims.models.base import FeatureSnapshot,FeatureValue
from ap_evsims.canonical import join_canonical,verify_provider_dataset,verify_feature_sources
from test_phase2_history import odds_payload

class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=ResearchStore(Path(self.tmp.name)/'data')
        self.mapping={'provider-g1':dict(event_id='g1',home_team='Home',away_team='Away')}
        self.odds=self.store.archive(provider='odds',endpoint='historical/sports/americanfootball_ncaaf/odds',parameters={'date':'2024-08-03T01:00:00Z'},body=json.dumps(odds_payload()).encode(),
            fetched_at='2026-10-14T05:00:00Z',observed_at='2024-08-03T01:00:00Z',available_at='2024-08-03T01:00:00Z',availability_basis='historical_odds_snapshot')
        self.results=self.store.archive(provider='cfbd',endpoint='games',parameters={'year':2024},body=json.dumps([dict(id='g1',homeTeam='Home',awayTeam='Away',completed=True,homePoints=20,awayPoints=23,startDate='2024-08-03T04:00:00Z')]).encode(),
            fetched_at='2024-08-04T00:00:00Z',observed_at='2024-08-04T00:00:00Z',available_at='2024-08-04T00:00:00Z',availability_basis='recorded_response')
        self.source=self.store.archive(provider='cfbd',endpoint='venues',parameters={},body=b'{"home_field":1}',fetched_at='2024-08-02T00:00:00Z',observed_at='2024-08-02T00:00:00Z',available_at='2024-08-02T00:00:00Z',availability_basis='recorded_response')
        self.features=FeatureSnapshot('g1','CFB','2024-08-03T00:00:00Z',{'home_field':FeatureValue(1,'constructed_contract_fixture',self.source['observed_at'],self.source['available_at'],self.source['snapshot_id'],self.source['payload_hash'],'/home_field')})
    def tearDown(self): self.tmp.cleanup()
    def join(self,features=None):
        return join_canonical(self.store,odds_snapshot_id=self.odds['snapshot_id'],results_snapshot_id=self.results['snapshot_id'],
            event_mapping=self.mapping,feature_snapshots={'g1':features or self.features},prediction_at='2024-08-03T01:00:00Z')
    def test_join_and_source_bound_prices_results(self):
        output=self.join(); self.assertEqual(len(output['rows']),1); self.assertEqual(output['rejections'],[])
        verify_provider_dataset(self.store,output['rows'])
        row=output['rows'][0]
        with self.assertRaisesRegex(ValueError,'RESULT_PROVENANCE_MISMATCH'): verify_provider_dataset(self.store,[replace(row,home_score=99)])
        with self.assertRaisesRegex(ValueError,'MARKET_PROVENANCE_MISMATCH'): verify_provider_dataset(self.store,[replace(row,context=replace(row.context,odds=120))])
    def test_fake_feature_and_unknown_source_rejected(self):
        v=self.features.values['home_field']
        for fake in (replace(v,value=999),replace(v,snapshot_id='c'*64),replace(v,source_path=None)):
            with self.assertRaises(ValueError): verify_feature_sources(self.store,replace(self.features,values={'home_field':fake}))
            self.assertEqual(self.join(replace(self.features,values={'home_field':fake}))['rows'],[])
    def test_manifest_tampering(self):
        path=self.store.root/'manifests'/(self.source['snapshot_id']+'.json'); m=json.loads(path.read_text()); m['available_at']='2020-01-01T00:00:00Z'; path.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'MANIFEST_HASH_MISMATCH'): self.store.manifest(self.source['snapshot_id'])
    def test_provider_snapshot_later_than_requested_forecast(self):
        features=replace(self.features,timestamp='2024-08-01T00:00:00Z')
        self.assertEqual(self.join(features)['rows'],[])
