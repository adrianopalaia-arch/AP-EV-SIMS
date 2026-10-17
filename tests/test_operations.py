import json,tempfile,unittest
from unittest.mock import patch
from ap_evsims.operations import collect_odds,sync_data,cadence_seconds
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.offline import offline_mode
from test_warehouse import archive

class OperationsTests(unittest.TestCase):
    def test_cadence_increases_near_start(self):
        self.assertEqual([cadence_seconds(x) for x in (100000,80000,10000,3000,600)],[21600,3600,900,300,60])
    def test_recorder_reuses_recent_capture(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t);w.record_odds(s,archive(s))
            r=collect_odds(s,w,now='2026-10-14T10:01:00Z',transport=lambda u,h:self.fail('unneeded request'))
            self.assertEqual(r['results'][0]['status'],'CACHED_CADENCE')
    def test_daily_quota_gate_prevents_network(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t)
            r=collect_odds(s,w,daily_credit_cap=0,transport=lambda u,h:self.fail('quota overrun'))
            self.assertEqual(r['results'][0]['status'],'QUOTA_BUDGET_LIMIT')
    def test_local_sync_runs_offline(self):
        with tempfile.TemporaryDirectory() as t,offline_mode():
            s=ResearchStore(t);w=Warehouse(t);archive(s)
            result=sync_data(s,w,transport=lambda u,h:self.fail('offline network'))
            self.assertEqual(result['health']['odds_quotes'],2)
    def test_week_subset_does_not_claim_whole_season_cached(self):
        from ap_evsims.providers.live import HTTPResponse
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'CFBD_API_KEY':'test-only'}):
            s=ResearchStore(t);w=Warehouse(t)
            m=s.archive(provider='cfbd',endpoint='games',parameters={'year':2025,'week':6,'seasonType':'regular'},body=b'[]',fetched_at='2026-10-14T10:00:00Z')
            w.ingest_manifest(s,m);calls=[]
            def fetch(u,h):calls.append(u);return HTTPResponse(200,b'[]','2026-10-14T11:00:00Z')
            result=sync_data(s,w,cfbd_year=2025,transport=fetch)
            self.assertEqual(len(calls),1);self.assertEqual(len(result['downloaded']),1)
