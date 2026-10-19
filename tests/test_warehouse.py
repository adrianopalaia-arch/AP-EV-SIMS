import json,tempfile,unittest,socket
from pathlib import Path
from unittest.mock import patch
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.offline import offline_mode
from ap_evsims.providers.validation import ProviderValidator
from ap_evsims.providers.live import HTTPResponse

def archive(store,time='2026-10-14T10:00:00Z',line=3.5,price=-110):
    event=dict(id='fixture-event',sport_key='americanfootball_ncaaf',commence_time='2026-10-14T18:00:00Z',home_team='Home',away_team='Away',
        bookmakers=[dict(key='draftkings',last_update=time,markets=[dict(key='spreads',outcomes=[dict(name='Home',point=line,price=price),dict(name='Away',point=-line,price=-110)])])])
    return store.archive(provider='odds',endpoint='sports/americanfootball_ncaaf/odds',parameters={},body=json.dumps([event]).encode(),fetched_at=time,observed_at=time,available_at=time,availability_basis='recorded_response')

class WarehouseTests(unittest.TestCase):
    def test_roundtrip_parquet_idempotence_and_missing_history(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t);m=archive(s)
            self.assertEqual(w.ingest_manifest(s,m)['rows'],1)
            self.assertEqual(w.ingest_manifest(s,m)['status'],'CACHED')
            self.assertTrue(list((Path(t)/'parquet/odds').glob('*.parquet')))
            with self.assertRaisesRegex(ValueError,'MISSING_LOCAL_DATA'):w.local_records('odds',m['endpoint'],'2025-01-01T00:00:00Z')
            self.assertEqual(len(w.local_records('odds',m['endpoint'],'2026-10-14T10:01:00Z')),1)
    def test_quote_asof_no_future_and_movement(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t);a=archive(s);b=archive(s,'2026-10-14T11:00:00Z',2.5,-115)
            w.record_odds(s,a);w.record_odds(s,b)
            before=w.as_of_quotes('2026-10-14T10:30:00Z')
            self.assertEqual({r['line'] for r in before},{3.5,-3.5})
            self.assertEqual(w.health()['odds_movements'],2)
            self.assertEqual(w.record_odds(s,a)['quotes_inserted'],0)
    def test_close_only_revealed_after_start(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t);w.record_odds(s,archive(s))
            w.close_events('2026-10-14T17:59:59Z');self.assertEqual(w.health()['closing_prices'],0)
            w.close_events('2026-10-14T18:00:01Z');self.assertEqual(w.health()['closing_prices'],2)
            self.assertEqual(w.as_of_quotes('2026-10-14T18:00:01Z'),[])
    def test_error_payload_and_schema_drift_are_not_zero_features(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t)
            m=s.archive(provider='odds',endpoint='sports/x/odds',parameters={'endpoint_status':401},body=b'{}',fetched_at='2026-10-14T10:00:00Z')
            self.assertEqual(w.ingest_manifest(s,m)['status'],'PROVIDER_ERROR_EXCLUDED')
            with self.assertRaisesRegex(ValueError,'PROVIDER_ERROR'):w.record_odds(s,m)
    def test_offline_mode_blocks_dns_and_connections_but_warehouse_works(self):
        with tempfile.TemporaryDirectory() as t,offline_mode():
            with self.assertRaisesRegex(RuntimeError,'OFFLINE_NETWORK_FORBIDDEN'):socket.create_connection(('example.com',443))
            with self.assertRaisesRegex(RuntimeError,'OFFLINE_NETWORK_FORBIDDEN'):socket.getaddrinfo('example.com',443)
            self.assertEqual(Warehouse(t).health()['odds_quotes'],0)
    def test_content_tampering_detected(self):
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);w=Warehouse(t);m=archive(s);w.ingest_manifest(s,m)
            (Path(t)/m['raw_path']).write_bytes(b'[]')
            self.assertEqual(w.health()['hash_failures'],1)
    def test_historical_cache_survives_restart_and_prevents_network(self):
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'THE_ODDS_API_KEY':'fixture-only'}):
            s=ResearchStore(t);body=b'{"timestamp":"2025-10-04T15:55:00Z","data":[]}'
            args=('odds','historical/sports/americanfootball_ncaaf/odds',{'date':'2025-10-04T16:00:00Z'})
            first=ProviderValidator(s,lambda u,h:HTTPResponse(200,body,'2026-10-14T10:00:00Z',{'x-requests-last':30,'x-requests-remaining':100}))
            first.request(*args,historical=True,credit_cost=30)
            second=ProviderValidator(s,lambda u,h:self.fail('duplicate historical download'))
            record,_=second.request(*args,historical=True,credit_cost=30)
            self.assertTrue(record['cached']);self.assertEqual(second.ledger.summary()['duplicate_requests_prevented'],1)
