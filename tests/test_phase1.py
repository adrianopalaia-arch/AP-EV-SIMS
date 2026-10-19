import unittest
import tempfile
from pathlib import Path
from dataclasses import replace
from ap_evsims.integrity import ValidationRegistry, SnapshotStore, utc
from ap_evsims.exposure import ExposureLedger, ExposureLimits
from ap_evsims.decision import ResearchCandidate, decide
from ap_evsims.features import CFB, NHL
from ap_evsims.providers.contracts import FixtureProvider
from ap_evsims.ledger import Ledger

NOW='2026-10-14T01:00:00Z'
def observations():
    return [dict(id=str(i),sport='CFB',market='spread',mode='pregame',model_version='cfb-v1',
                 feature_time='2026-10-01T00:00:00Z',prediction_time='2026-10-01T00:01:00Z',
                 quote_time='2026-10-01T00:02:00Z',event_start='2026-10-01T01:00:00Z',
                 outcome_time='2026-10-01T04:00:00Z',p=.7 if i%2 else .3,market_p=.5,outcome=i%2)
            for i in range(300)]

class Phase1(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); p=Path(self.temp.name)
        self.registry=ValidationRegistry(p/'validation.db'); self.exposure=ExposureLedger(p/'exposure.db')
        self.ledger=Ledger(p/'decisions.jsonl'); self.limits=ExposureLimits(1000)
        self.evidence=self.registry.evaluate(sport='CFB',market='spread',model_version='cfb-v1',mode='pregame',
            training_cutoff='2026-09-30T00:00:00Z',expires='2026-11-01T00:00:00Z',observations=observations())
        features={k:dict(value=.5,source='fixture',available_at='2026-10-14T00:58:00Z') for k in CFB}
        features['american_odds']['value']=110; features['market_line']['value']=3.5
        self.c=ResearchCandidate(candidate_id='c1',event_id='g1',sport='CFB',market='spread',selection='A +3.5',model_version='cfb-v1',mode='pregame',dataset_fingerprint=self.evidence.dataset_fingerprint,training_cutoff=self.evidence.training_cutoff,
            event_start='2026-10-14T01:30:00Z',quote_time='2026-10-14T00:59:00Z',opposite_quote_time='2026-10-14T00:59:00Z',availability_time='2026-10-14T00:57:00Z',feature_time='2026-10-14T00:58:00Z',prediction_time='2026-10-14T00:58:30Z',p_model=.63,p_low=.58,american_odds=110,opposite_odds=-140,book='fixture',market_line=3.5,opposite_market_line=3.5,lineup_verified=True,live_state_verified=False,binary_settlement_verified=True,exposure_groups=('GAME:g1','TEAM:a'),features=features)
    def tearDown(self): self.temp.cleanup()
    def run_decision(self,c=None,e=None,**kw):
        return decide(c or self.c,e or self.evidence,registry=self.registry,exposure=self.exposure,limits=self.limits,ledger=self.ledger,now=kw.pop('now',NOW),**kw)
    def test_valid_and_audit_fields(self):
        r=self.run_decision(); self.assertEqual(r['status'],'RESEARCH_CANDIDATE')
        self.assertEqual(len(r['timestamps']),7); self.assertEqual(r['model_version'],'cfb-v1')
        self.assertIsNotNone(r['fair_odds']); self.assertEqual(len(self.ledger.read()),1)
    def test_caller_cannot_authenticate(self):
        r=self.run_decision(e={'validated':True}); self.assertIn('MODEL_NOT_CALIBRATED',r['reasons'])
    def test_evidence_tampering_and_scope(self):
        for e in (replace(self.evidence,brier=0),replace(self.evidence,market='total'),replace(self.evidence,model_version='other'),replace(self.evidence,mode='live'),replace(self.evidence,dataset_fingerprint='x'),replace(self.evidence,training_cutoff='2026-01-01T00:00:00Z')):
            with self.subTest(e=e): self.assertIn('MODEL_NOT_CALIBRATED',self.run_decision(e=e)['reasons'])
    def test_candidate_evidence_mismatch(self):
        for changes in (dict(dataset_fingerprint='bad'),dict(training_cutoff='2026-01-01T00:00:00Z'),dict(model_version='other'),dict(market='total'),dict(mode='live')):
            with self.subTest(changes=changes): self.assertIn('MODEL_NOT_CALIBRATED',self.run_decision(replace(self.c,**changes))['reasons'])
    def test_expired_and_future_evidence(self):
        for t in ('2026-09-30T00:00:00Z','2026-11-02T00:00:00Z'):
            c=replace(self.c,feature_time=t)
            self.assertIn('MODEL_NOT_CALIBRATED',self.run_decision(c)['reasons'])
    def test_timestamp_failure_conditions(self):
        cases=[('quote_time','2026-10-14T01:01:00Z','LOOKAHEAD_RISK'),
               ('quote_time','2026-10-14T00:50:00Z','STALE_PRICE'),
               ('opposite_quote_time','2026-10-14T00:50:00Z','STALE_PRICE'),
               ('opposite_quote_time','2026-10-14T01:00:00Z','LOOKAHEAD_RISK'),
               ('availability_time','2026-10-14T00:59:00Z','LOOKAHEAD_RISK'),
               ('availability_time','2026-10-14T00:40:00Z','STALE_DATA'),
               ('feature_time','2026-10-14T01:01:00Z','LOOKAHEAD_RISK'),
               ('prediction_time','2026-10-14T01:01:00Z','LOOKAHEAD_RISK'),
               ('event_start','2026-10-14T00:30:00Z','MODE_MISMATCH'),
               ('quote_time','2026-10-14T00:59:00','LOOKAHEAD_RISK'),
               ('feature_time','bad','LOOKAHEAD_RISK')]
        for field,value,reason in cases:
            with self.subTest(field=field,value=value): self.assertIn(reason,self.run_decision(replace(self.c,**{field:value}))['reasons'])
    def test_explicit_pass_conditions(self):
        cases=[(dict(lineup_verified=False),'UNVERIFIED_LINEUP'),(dict(p_low=.48),'INVALID_PROBABILITY'),
               (dict(p_low=.53,p_model=.6,american_odds=-110),'EDGE_TOO_SMALL'),
               (dict(model_disagreement=.1),'MODEL_DISAGREEMENT'),(dict(american_odds=120),'PRICE_MOVED'),
               (dict(features={}),'MISSING_FEATURES'),(dict(binary_settlement_verified=False),'UNVERIFIED_SETTLEMENT'),
               (dict(account='bonus'),'BONUS_EV_NOT_IMPLEMENTED'),(dict(opposite_market_line=2.5),'PRICE_MOVED'),
               (dict(market_line=3),'PUSH_MODEL_REQUIRED'),(dict(american_odds=0),'INVALID_PRICE'),
               (dict(p_model=float('nan')),'INVALID_PROBABILITY'),(dict(exposure_groups=()),'MISSING_EXPOSURE_GROUPS')]
        for changes,reason in cases:
            with self.subTest(changes=changes):
                r=self.run_decision(replace(self.c,**changes)); self.assertIn(reason,r['reasons']); self.assertEqual(r['stake_usd'],0)
    def test_missing_each_feature(self):
        for k in CFB:
            f=dict(self.c.features); f.pop(k)
            with self.subTest(k=k): self.assertIn('MISSING_FEATURES',self.run_decision(replace(self.c,features=f))['reasons'])
    def test_feature_lookahead(self):
        f=dict(self.c.features); f['weather']=dict(value=.5,source='fixture',available_at='2026-10-14T01:10:00Z')
        self.assertIn('LOOKAHEAD_RISK',self.run_decision(replace(self.c,features=f))['reasons'])
    def test_goalie_and_nhl_feature_contract(self):
        from ap_evsims.features import feature_reasons
        f={k:dict(value=.5,source='fixture',available_at='2026-10-14T00:57:00Z') for k in NHL}
        f['confirmed_starting_goalie']['value']=False
        self.assertIn('UNCONFIRMED_GOALIE',feature_reasons('NHL',f,self.c.feature_time))
        f['confirmed_starting_goalie']['value']=True
        self.assertEqual(feature_reasons('NHL',f,self.c.feature_time),[])
        for k in NHL:
            missing=dict(f); missing.pop(k)
            self.assertIn('MISSING_FEATURES',feature_reasons('NHL',missing,self.c.feature_time))
    def test_duplicate_and_prior_card_exposure(self):
        self.run_decision()
        self.assertIn('DUPLICATE_POSITION',self.run_decision()['reasons'])
        self.assertIn('CORRELATION_LIMIT',self.run_decision(replace(self.c,candidate_id='c2'))['reasons'])
        self.exposure.transition('c1','open',NOW)
        reloaded=ExposureLedger(self.exposure.path)
        self.assertEqual(reloaded.positions()[0]['state'],'open')
        self.assertIn('CORRELATION_LIMIT',self.run_decision(replace(self.c,candidate_id='c3',event_id='g2',exposure_groups=('GAME:g2','TEAM:a')))['reasons'])
    def test_total_exposure(self):
        self.run_decision()
        self.run_decision(replace(self.c,candidate_id='c2',event_id='g2',exposure_groups=('GAME:g2','TEAM:b')))
        r=self.run_decision(replace(self.c,candidate_id='c3',event_id='g3',exposure_groups=('GAME:g3','TEAM:c')))
        self.assertIn('EXPOSURE_LIMIT',r['reasons'])
    def test_team_player_game_slip_groups(self):
        for group in ('TEAM:a','PLAYER:a','GAME:a','SLIP:a'):
            with self.subTest(group=group):
                p=Path(self.temp.name)/(group.replace(':','_')+'.db'); e=ExposureLedger(p)
                args=dict(account='cash',amount=10,at=NOW,limits=self.limits)
                self.assertIsNone(e.reserve(position_id='a',groups=('GAME:1',group),**args))
                self.assertEqual(e.reserve(position_id='b',groups=('GAME:2',group),**args),'CORRELATION_LIMIT')
    def test_bonus_separate_and_settlement_release(self):
        limits=ExposureLimits(1000,bonus_total=20,bonus_group=10)
        self.assertIsNone(self.exposure.reserve(position_id='b',account='bonus',amount=10,groups=('GAME:g9','TEAM:x'),at=NOW,limits=limits))
        self.assertEqual(self.exposure.reserve(position_id='b2',account='cash',amount=10,groups=('GAME:g9','TEAM:x'),at=NOW,limits=limits),'CORRELATION_LIMIT')
        self.assertEqual(self.run_decision()['status'],'RESEARCH_CANDIDATE')
        self.exposure.transition('c1','open',NOW); self.exposure.transition('c1','settled',NOW)
        self.assertEqual(self.run_decision(replace(self.c,candidate_id='c2'))['status'],'RESEARCH_CANDIDATE')
    def test_invalid_exposure_and_transitions(self):
        for amount in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): self.exposure.reserve(position_id='x',account='cash',amount=amount,groups=('GAME:x',),at=NOW,limits=self.limits)
        self.run_decision()
        with self.assertRaises(ValueError): self.exposure.transition('c1','settled',NOW)
        with self.assertRaises(ValueError): self.exposure.transition('c1','open','2026-10-13T00:00:00Z')
    def test_snapshot_and_all_fixture_providers(self):
        s=SnapshotStore(Path(self.temp.name)/'snapshots.db')
        for kind in ('odds','availability','weather','cfb','nhl','results'):
            s.append(kind=kind,key='x',observed='2026-10-01T00:00:00Z',available='2026-10-02T00:00:00Z',payload={'price':110})
            s.append(kind=kind,key='x',observed='2026-10-03T00:00:00Z',available='2026-10-04T00:00:00Z',payload={'price':120})
            p=FixtureProvider(s,kind)
            self.assertIsNone(p.as_of('x','2026-10-01T12:00:00Z'))
            self.assertEqual(p.as_of('x','2026-10-03T12:00:00Z').payload['price'],110)
            self.assertEqual(p.as_of('x','2026-10-05T00:00:00Z').payload['price'],120)
        with self.assertRaises(ValueError): s.append(kind='odds',key='x',observed='2026-10-03T00:00:00Z',available='2026-10-02T00:00:00Z',payload={})
    def test_bad_evaluation_inputs(self):
        for changes in (dict(p=float('nan')),dict(outcome=2),dict(model_version='x'),dict(feature_time='2026-09-01T00:00:00Z'),dict(outcome_time='2026-10-01T00:00:00Z')):
            rows=observations(); rows[0].update(changes)
            with self.assertRaises(ValueError): self.registry.evaluate(sport='CFB',market='spread',model_version='cfb-v1',mode='pregame',training_cutoff=self.c.training_cutoff,expires='2026-11-01T00:00:00Z',observations=rows)
    def test_deterministic_fingerprint(self):
        e=self.registry.evaluate(sport='CFB',market='spread',model_version='cfb-v1',mode='pregame',training_cutoff=self.c.training_cutoff,expires='2026-11-01T00:00:00Z',observations=list(reversed(observations())))
        self.assertEqual(e,self.evidence)
    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError): utc('2026-10-14T01:00:00')

    def test_import_overbudget_open_bet(self):
        self.exposure.record_open(position_id='external',account='cash',amount=100,groups=('GAME:external','TEAM:x'),at=NOW)
        self.assertIn('EXPOSURE_LIMIT',self.run_decision()['reasons'])
        self.assertEqual(ExposureLedger(self.exposure.path).positions()[0]['state'],'open')

    def test_atomic_concurrent_reservations(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(i):
            return self.exposure.reserve(position_id=str(i),account='cash',amount=10,groups=('GAME:race','TEAM:race'),at=NOW,limits=self.limits)
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(attempt,range(4)))
        self.assertEqual(results.count(None),1)
        self.assertEqual(results.count('CORRELATION_LIMIT'),3)

    def test_cli_evaluate_and_decide(self):
        import json, sys, io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from dataclasses import asdict
        from ap_evsims.cli import main
        root=Path(self.temp.name)
        request=root/'candidate.json'
        request.write_text(json.dumps(dict(candidate=asdict(self.c),report_id=self.evidence.report_id)))
        args=['ap-evisims','decide',str(request),'--registry',self.registry.path,'--exposure',self.exposure.path,'--ledger',str(self.ledger.path),'--bankroll','1000','--now',NOW]
        with patch.object(sys,'argv',args),redirect_stdout(io.StringIO()) as output: main()
        self.assertEqual(json.loads(output.getvalue())['status'],'RESEARCH_CANDIDATE')
        ev=root/'evaluation.json'
        ev.write_text(json.dumps(dict(sport='CFB',market='spread',model_version='cfb-v1',mode='pregame',training_cutoff=self.c.training_cutoff,expires='2026-11-01T00:00:00Z',observations=observations())))
        with patch.object(sys,'argv',['ap-evisims','evaluate',str(ev),'--registry',self.registry.path]),redirect_stdout(io.StringIO()) as output: main()
        self.assertEqual(json.loads(output.getvalue())['report_id'],self.evidence.report_id)

    def test_unregistered_report_and_insufficient_sample(self):
        other=ValidationRegistry(Path(self.temp.name)/'empty.db')
        kwargs=dict(sport=self.c.sport,market=self.c.market,model_version=self.c.model_version,mode=self.c.mode,dataset_fingerprint=self.c.dataset_fingerprint,training_cutoff=self.c.training_cutoff,as_of=self.c.feature_time)
        self.assertFalse(other.verify(self.evidence,**kwargs))
        self.assertFalse(self.registry.verify(self.evidence,minimum_n=301,**kwargs))

    def test_no_reservation_is_pass(self):
        self.assertIn('EXPOSURE_NOT_RESERVED',self.run_decision(reserve=False)['reasons'])

    def test_numeric_hygiene(self):
        from ap_evsims.odds import american_to_decimal, american_to_implied, expected_value
        from ap_evsims.calibration import brier_score, log_loss, calibration_bins
        for bad in (float('nan'),float('inf'),0,99,True,110.5):
            for f in (american_to_decimal,american_to_implied):
                with self.assertRaises(ValueError): f(bad)
        for bad in (float('nan'),float('inf'),-1,2):
            with self.assertRaises(ValueError): expected_value(bad,110)
            for f in (brier_score,log_loss,calibration_bins):
                with self.assertRaises(ValueError): f([bad],[1])
        for f in (brier_score,log_loss,calibration_bins):
            with self.assertRaises(ValueError): f([.5],[2])
            with self.assertRaises(ValueError): f([.5],[])

if __name__=='__main__': unittest.main()
