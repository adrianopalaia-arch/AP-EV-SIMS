import unittest,tempfile,io,json,sys
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from ap_evsims.research_cli import main
from ap_evsims.providers.live import HTTPResponse,CFBDClient,OddsAPIClient,ProviderAccessError
from ap_evsims.research_store import ResearchStore

class ResearchCLITests(unittest.TestCase):
    def test_ingestion_without_credentials_keeps_canonical_data_empty(self):
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'CFBD_API_KEY':'','THE_ODDS_API_KEY':''}),patch.object(sys,'argv',['ap','ingest','--store',t,'--year','2025','--week','6','--historical-at','2025-10-04T16:00:00Z']),redirect_stdout(io.StringIO()) as output:
            main(); payload=json.loads(output.getvalue())
            self.assertEqual(payload['status'],'BLOCKED_BY_HISTORICAL_ODDS_ACCESS')
            self.assertEqual(payload['canonical_rows_created'],0); self.assertEqual(payload['manifests'],[])
    def test_recorded_401_fixtures_reject_access(self):
        root=Path(__file__).parent/'fixtures/provider_access'
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'CFBD_API_KEY':'test-credential-not-recorded','THE_ODDS_API_KEY':'test-credential-not-recorded'}):
            store=ResearchStore(t)
            cfbd=CFBDClient(store,lambda u,h:HTTPResponse(401,(root/'cfbd_401.json').read_bytes(),'2026-10-14T05:00:00Z'))
            with self.assertRaisesRegex(ProviderAccessError,'CFBD_ACCESS_ERROR'): cfbd.games(2025)
            odds=OddsAPIClient(store,lambda u,h:HTTPResponse(401,(root/'odds_historical_401.json').read_bytes(),'2026-10-14T05:00:00Z'))
            with self.assertRaisesRegex(ProviderAccessError,'BLOCKED_BY_HISTORICAL_ODDS_ACCESS'): odds.fetch(historical_at='2025-10-04T16:00:00Z')
    def test_access_probe_never_exposes_credentials(self):
        from ap_evsims.providers.live import probe_access
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'CFBD_API_KEY':'do-not-print-one','THE_ODDS_API_KEY':'do-not-print-two'}):
            output=probe_access(ResearchStore(t),transport=lambda u,h:HTTPResponse(403,b'{"error":"not entitled"}','2026-10-14T05:00:00Z'))
            serialized=json.dumps(output)
            self.assertNotIn('do-not-print',serialized); self.assertFalse(output[1]['historical_entitlement'])
            for path in Path(t).rglob('*'):
                if path.is_file(): self.assertNotIn('do-not-print',path.read_text())
