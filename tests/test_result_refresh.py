"""Synthetic mechanics fixtures only; no rows from these tests enter real reports."""
import json
import io
from contextlib import redirect_stdout,redirect_stderr
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ap_evsims.__main__ import main
from ap_evsims.operations import sync_data
from ap_evsims.offline import offline_mode
from ap_evsims.providers.live import HTTPResponse
from ap_evsims.research_store import ResearchStore
from ap_evsims.results import cfbd_results_as_of,reconcile_cfbd_replay
from ap_evsims.warehouse import Warehouse
from ap_evsims.replay import ReplayLedger
from ap_evsims.models.base import FeatureSnapshot,MarketContext,PredictionResult

PARAMS={'year':2026,'week':7,'seasonType':'regular'}

def game(score=None,**changes):
    row=dict(id=1,homeTeam='Home',awayTeam='Away',startDate='2026-10-14T12:00:00Z',
             completed=score is not None,homePoints=score,awayPoints=14 if score is not None else None)
    row.update(changes)
    return row

def capture(store,warehouse,at,rows,parameters=None):
    manifest=store.archive(provider='cfbd',endpoint='games',parameters=parameters or PARAMS,
        body=json.dumps(rows).encode(),fetched_at=at,observed_at=at,available_at=at,availability_basis='recorded_response')
    warehouse.ingest_manifest(store,manifest)
    return manifest

class ResultRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ResearchStore(self.temp.name);self.warehouse=Warehouse(self.temp.name)
        self.credentials=patch.dict('os.environ',{'CFBD_API_KEY':'fixture-only'})
        self.credentials.start();self.addCleanup(self.credentials.stop)

    def sync(self,transport,**kw):
        return sync_data(self.store,self.warehouse,cfbd_year=2026,cfbd_week=7,transport=transport,**kw)

    def test_default_reuses_query_and_explicit_refresh_preserves_both(self):
        old=capture(self.store,self.warehouse,'2026-10-14T10:00:00Z',[game()])
        original=(self.store.root/old['raw_path']).read_bytes()
        result=self.sync(lambda *args:self.fail('cached query fetched'),now='2026-10-14T16:00:00Z')
        self.assertEqual(result['cfbd_games_status'],'CACHED_QUERY')
        result=self.sync(lambda *args:HTTPResponse(200,json.dumps([game(21)]).encode(),'2026-10-14T16:00:01Z'),
            refresh_cfbd_games=True,now='2026-10-14T16:00:00Z')
        self.assertEqual(result['cfbd_games_status'],'REFRESHED')
        self.assertEqual(result['health']['snapshots'],2)
        self.assertEqual((self.store.root/old['raw_path']).read_bytes(),original)
        self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T15:00:00Z')[0]['status'],'unsettled')
        self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')[0]['home_score'],21)

    def test_refresh_cooldown_includes_failed_attempt(self):
        capture(self.store,self.warehouse,'2026-10-14T10:00:00Z',[game()])
        result=self.sync(lambda *args:self.fail('early fetch'),refresh_cfbd_games=True,now='2026-10-14T10:30:00Z')
        self.assertEqual(result['cfbd_games_status'],'REFRESH_COOLDOWN')
        result=self.sync(lambda *args:HTTPResponse(503,b'{}','2026-10-14T16:00:01Z'),
            refresh_cfbd_games=True,now='2026-10-14T16:00:00Z')
        self.assertEqual(result['cfbd_games_status'],'PROVIDER_UNAVAILABLE')
        result=self.sync(lambda *args:self.fail('failed request retried early'),refresh_cfbd_games=True,now='2026-10-14T16:10:00Z')
        self.assertEqual(result['cfbd_games_status'],'REFRESH_COOLDOWN')
        self.assertEqual(result['health']['snapshots'],1)

    def test_refresh_rejects_schema_without_replacing_valid_result(self):
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        result=self.sync(lambda *args:HTTPResponse(200,b'[{"id":1}]','2026-10-14T18:00:01Z'),
            refresh_cfbd_games=True,now='2026-10-14T18:00:00Z')
        self.assertEqual(result['cfbd_games_status'],'REJECTED_SNAPSHOT')
        self.assertEqual(result['health']['snapshots'],1)
        self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T19:00:00Z')[0]['home_score'],21)

    def test_refresh_requires_bounded_query_and_valid_interval(self):
        for params in ({},{'cfbd_year':2026}):
            with self.assertRaisesRegex(ValueError,'REFRESH_REQUIRES_YEAR_AND_WEEK'):
                sync_data(self.store,self.warehouse,refresh_cfbd_games=True,**params)
        for interval in (0,59,-1,True,1.5):
            with self.assertRaisesRegex(ValueError,'INVALID_REFRESH_INTERVAL'):
                self.sync(lambda *args:self.fail('invalid policy fetched'),min_refresh_seconds=interval)
        capture(self.store,self.warehouse,'2026-10-14T10:00:00Z',[game()])
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD_RISK'):
            self.sync(lambda *args:self.fail('future cache fetched'),refresh_cfbd_games=True,now='2026-10-14T09:00:00Z')

    def test_cli_rejects_offline_or_unbounded_refresh(self):
        for args in (['sync_data','--offline'],['sync_data','--cfbd-year','2026'],['collect_odds']):
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args+['--refresh-cfbd-games'])

    def test_cli_reconciles_existing_ledger_offline_and_does_not_create_missing_one(self):
        ledger_path=Path(self.temp.name)/'replay.sqlite'
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(['reconcile_results','--store',self.temp.name,'--replay-ledger',str(ledger_path),'--offline'])
        self.assertFalse(ledger_path.exists())
        ReplayLedger(ledger_path)
        output=io.StringIO()
        with offline_mode(),redirect_stdout(output):
            main(['reconcile_results','--store',self.temp.name,'--replay-ledger',str(ledger_path),'--offline'])
        self.assertEqual(json.loads(output.getvalue())['result_observations'],0)

    def test_correction_and_retracted_final_are_visible_only_after_capture(self):
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        corrected=capture(self.store,self.warehouse,'2026-10-14T18:00:00Z',[game(24)])
        capture(self.store,self.warehouse,'2026-10-14T20:00:00Z',[game()])
        with offline_mode():
            self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T15:59:59Z'),[])
            self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')[0]['home_score'],21)
            result=cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T19:00:00Z')[0]
            self.assertEqual(result['home_score'],24);self.assertEqual(result['snapshot_id'],corrected['snapshot_id'])
            self.assertEqual(cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T21:00:00Z')[0]['status'],'unsettled')

    def test_queries_are_merged_per_event_without_dropping_other_weeks(self):
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        capture(self.store,self.warehouse,'2026-10-14T17:00:00Z',[game(7,id=2)],dict(PARAMS,week=6))
        capture(self.store,self.warehouse,'2026-10-14T18:00:00Z',[game(24)])
        results=cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T19:00:00Z')
        self.assertEqual([(r['event_id'],r['home_score']) for r in results],[('1',24),('2',7)])

    def test_simultaneous_conflicting_revisions_are_rejected(self):
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(24)],dict(PARAMS,week=6))
        with self.assertRaisesRegex(ValueError,'CONFLICTING_RESULT_REVISION'):
            cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')

    def test_duplicate_result_ids_are_rejected(self):
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21),game(24)])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_RESULT_ID'):
            cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')

    def test_final_result_before_start_is_rejected(self):
        capture(self.store,self.warehouse,'2026-10-14T10:00:00Z',[game(21)])
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD_RISK'):
            cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T11:00:00Z')

    def test_raw_and_warehouse_availability_tampering_are_rejected(self):
        manifest=capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        with self.warehouse.connect() as db:db.execute('UPDATE snapshots SET available_at=?',['2026-10-14T15:00:00Z'])
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD_RISK'):
            cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')
        (self.store.root/manifest['raw_path']).write_bytes(b'[]')
        with self.assertRaisesRegex(ValueError,'PAYLOAD_HASH_MISMATCH'):
            cfbd_results_as_of(self.store,self.warehouse,'2026-10-14T17:00:00Z')

    def test_verified_replay_reconciliation_is_idempotent_and_preserves_prediction(self):
        source=capture(self.store,self.warehouse,'2026-10-14T10:00:00Z',[game()])
        features=FeatureSnapshot('1','CFB','2026-10-14T10:00:00Z',{})
        context=MarketContext('1','CFB','spread','home','draftkings',3.5,-110,-110,
            features.timestamp,'2026-10-14T10:01:00Z','2026-10-14T12:00:00Z',source['snapshot_id'],3.5)
        prediction=PredictionResult(None,None,None,None,None,'fixture-pass',None,features.timestamp,features.fingerprint,'spread',None,None)
        ledger=ReplayLedger(Path(self.temp.name)/'replay.sqlite')
        identity=ledger.freeze(features=features,context=context,prediction=prediction,decision={'status':'PASS'},
            decision_at=context.quote_timestamp,source_manifests=[source],provenance_store=self.store)
        before=ledger.predictions()
        self.assertEqual(reconcile_cfbd_replay(self.store,self.warehouse,ledger,'2026-10-14T11:00:00Z')['pending_prediction_ids'],[identity])
        capture(self.store,self.warehouse,'2026-10-14T16:00:00Z',[game(21)])
        reconcile_cfbd_replay(self.store,self.warehouse,ledger,'2026-10-14T17:00:00Z')
        capture(self.store,self.warehouse,'2026-10-14T18:00:00Z',[game(24)])
        for _ in range(2):reconcile_cfbd_replay(self.store,self.warehouse,ledger,'2026-10-14T19:00:00Z')
        self.assertEqual(len(ledger.results_as_of(identity,'2026-10-14T17:00:00Z')),1)
        self.assertEqual(len(ledger.results_as_of(identity,'2026-10-14T19:00:00Z')),2)
        self.assertEqual(ledger.predictions(),before)
        capture(self.store,self.warehouse,'2026-10-14T20:00:00Z',[game(24,startDate='2026-10-14T13:00:00Z')])
        with self.assertRaisesRegex(ValueError,'RESULT_EVENT_START_MISMATCH'):
            reconcile_cfbd_replay(self.store,self.warehouse,ledger,'2026-10-14T21:00:00Z')
