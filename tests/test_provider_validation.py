import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from ap_evsims.providers.security import load_credentials, redact, safe_quota
from ap_evsims.providers.validation import ProviderValidator
from ap_evsims.providers.live import HTTPResponse
from ap_evsims.research_store import ResearchStore

class ProviderValidationTests(unittest.TestCase):
    def test_dotenv_is_data_and_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{},clear=True):
            p=Path(t)/'.env';p.write_text('CFBD_API_KEY="contract-one"\nTHE_ODDS_API_KEY=contract-two\nUNRELATED=do-not-load\n')
            self.assertTrue(all(load_credentials(p).values()));self.assertNotIn('UNRELATED',os.environ)
            os.environ['CFBD_API_KEY']='';load_credentials(p);self.assertEqual(os.environ['CFBD_API_KEY'],'')
    def test_error_url_and_bearer_secrets_are_redacted(self):
        with patch.dict(os.environ,{'CFBD_API_KEY':'contract+one','THE_ODDS_API_KEY':'contract/two'}):
            text=redact('https://example.test?apiKey=contract%2Ftwo&x=1 Authorization: Bearer contract+one')
            self.assertNotIn('contract',text);self.assertIn('&x=1',text)
    def test_quotas_are_allowlisted_numeric_only(self):
        self.assertEqual(safe_quota({'Authorization':'secret','x-requests-remaining':'7','retry-after':'private'}),{'x-requests-remaining':7})
    def test_failure_archive_has_no_secret_or_credential_url(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'THE_ODDS_API_KEY':'contract-secret'}):
            response=HTTPResponse(401,b'{"message":"https://example.test?apiKey=contract-secret&x=1"}','2026-10-14T06:00:00Z')
            v=ProviderValidator(ResearchStore(t),lambda u,h:response)
            record,payload=v.request('odds','historical/sports/americanfootball_ncaaf/odds',{'date':'2025-10-04T16:00:00Z'},historical=True)
            self.assertIsNone(payload);self.assertEqual(record['status'],401)
            for f in Path(t).rglob('*.json'):self.assertNotIn('contract-secret',f.read_text())
    def test_historical_snapshot_after_requested_time_rejected(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'THE_ODDS_API_KEY':'contract-secret'}):
            response=HTTPResponse(200,b'{"timestamp":"2025-10-04T16:05:00Z","data":[]}','2026-10-14T06:00:00Z')
            v=ProviderValidator(ResearchStore(t),lambda u,h:response)
            record,payload=v.request('odds','historical/sports/americanfootball_ncaaf/odds',{'date':'2025-10-04T16:00:00Z'},historical=True)
            self.assertIsNone(payload);self.assertEqual(record['status'],'LOOKAHEAD_RISK')
    def test_credit_budget_does_not_make_a_network_call(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'THE_ODDS_API_KEY':'contract-secret'}):
            v=ProviderValidator(ResearchStore(t),lambda u,h:self.fail('called network'),max_odds_credits=0)
            record,payload=v.request('odds','sports/americanfootball_ncaaf/odds',credit_cost=3)
            self.assertEqual(record['status'],'QUOTA_BUDGET_LIMIT')
    def test_success_payload_bytes_and_historical_availability_preserved(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'THE_ODDS_API_KEY':'contract-secret'}):
            body=b'{"timestamp": "2025-10-04T15:55:00Z", "data": []}'
            v=ProviderValidator(ResearchStore(t),lambda u,h:HTTPResponse(200,body,'2026-10-14T06:00:00Z'))
            record,_=v.request('odds','historical/sports/americanfootball_ncaaf/odds',{'date':'2025-10-04T16:00:00Z'},historical=True)
            m=v.store.manifest(record['snapshot_id']);self.assertEqual(m['available_at'],'2025-10-04T15:55:00Z')
            self.assertEqual((Path(t)/m['raw_path']).read_bytes(),body)
    def test_200_error_payload_is_not_access_success(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'THE_ODDS_API_KEY':'contract-secret'}):
            v=ProviderValidator(ResearchStore(t),lambda u,h:HTTPResponse(200,b'{"error_code":"NO_ACCESS"}','2026-10-14T06:00:00Z'))
            record,payload=v.request('odds','sports');self.assertIsNone(payload)
            self.assertEqual(record['status'],'PROVIDER_ERROR_PAYLOAD')
