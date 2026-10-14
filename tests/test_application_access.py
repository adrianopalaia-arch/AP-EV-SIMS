"""Bounded access fixtures prove status separation, not real provider entitlement."""
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from ap_evsims.providers.access import verify_access
from ap_evsims.providers.live import HTTPResponse

class ApplicationAccessTests(unittest.TestCase):
    def test_current_success_historical_denial_are_separate(self):
        urls=[]
        def transport(url,headers):
            urls.append(url.split('?')[0])
            status=403 if '/historical/' in url else 200
            return HTTPResponse(status,b'[]' if status==200 else b'{"message":"plan required"}','2026-10-14T10:00:00Z',{})
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'CFBD_API_KEY':'fixture-cfbd','THE_ODDS_API_KEY':'fixture-odds'}):
            result=verify_access(root,transport=transport)
            self.assertEqual(result['CURRENT_ODDS_ACCESS'],'YES')
            self.assertEqual(result['HISTORICAL_ODDS_ACCESS'],'NO')
            self.assertEqual(result['blocker'],'BLOCKED_BY_HISTORICAL_ODDS_ACCESS')
            self.assertEqual(len(urls),4)
            self.assertFalse((Path(root)/'outputs/provider_status.json').exists())
    def test_no_credentials_causes_no_request(self):
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'CFBD_API_KEY':'','THE_ODDS_API_KEY':''}):
            result=verify_access(root,transport=lambda *a:self.fail('network'))
            self.assertEqual(result['CURRENT_ODDS_ACCESS'],'NO')
            self.assertFalse(result['providers']['cfbd']['credential_present'])
