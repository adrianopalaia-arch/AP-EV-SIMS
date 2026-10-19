import tempfile,unittest
from dataclasses import replace
from pathlib import Path
from ap_evsims.replay import ReplayLedger
from ap_evsims.models.base import PredictionResult
from ap_evsims.settlement import SettlementRule,grade,cashflow
from test_phase2_cfb import fixture_rows

class ReplaySettlementTests(unittest.TestCase):
    def inputs(self):
        row=fixture_rows(1)[0]
        p=PredictionResult(.5,None,None,None,None,'fixture-model','2023-12-01T00:00:00Z',row.features.timestamp,row.features.fingerprint,'spread',None,None)
        return dict(features=row.features,context=row.context,prediction=p,decision={'status':'PASS','reasons':['MODEL_NOT_CALIBRATED']},
            decision_at=row.context.quote_timestamp,source_manifests=[{'snapshot_id':'a'*64,'available_at':row.features.timestamp}],dataset_kind='synthetic_test')
    def test_freeze_is_idempotent_and_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=ReplayLedger(Path(t)/'replay.sqlite');args=self.inputs();identity=ledger.freeze(**args)
            self.assertEqual(ledger.freeze(**args),identity)
            args['decision']={'status':'PASS','reasons':['DIFFERENT']}
            with self.assertRaisesRegex(ValueError,'FROZEN_PREDICTION_MUTATION'):ledger.freeze(**args)
            self.assertEqual(len(ledger.predictions(dataset_kind='synthetic_test')),1)
            self.assertEqual(ledger.predictions(),[])
    def test_result_reveal_and_correction_do_not_rewrite_prediction(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=ReplayLedger(Path(t)/'replay.sqlite');identity=ledger.freeze(**self.inputs());before=ledger.predictions(dataset_kind='synthetic_test')
            with self.assertRaisesRegex(ValueError,'RESULT_NOT_YET_AVAILABLE'):
                ledger.reveal(identity,result={'score':1},available_at='2024-01-01T20:00:00Z',clock='2024-01-01T10:00:00Z',source_snapshot_id='result',source_hash='a'*64)
            ledger.reveal(identity,result={'score':1},available_at='2024-01-01T20:00:00Z',clock='2024-01-02T00:00:00Z',source_snapshot_id='result',source_hash='a'*64)
            ledger.reveal(identity,result={'score':2},available_at='2024-01-02T20:00:00Z',clock='2024-01-03T00:00:00Z',source_snapshot_id='correction',source_hash='b'*64)
            self.assertEqual(len(ledger.results_as_of(identity,'2024-01-02T00:00:00Z')),1)
            self.assertEqual(ledger.predictions(dataset_kind='synthetic_test'),before)
    def test_real_records_require_archived_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            args=self.inputs();args['dataset_kind']='provider_history'
            with self.assertRaisesRegex(ValueError,'PROVIDER_PROVENANCE_REQUIRED'):ReplayLedger(Path(t)/'r.sqlite').freeze(**args)
    def test_future_source_and_late_decision_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=ReplayLedger(Path(t)/'r.sqlite');args=self.inputs()
            args['source_manifests'][0]['available_at']='2025-01-01T00:00:00Z'
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):ledger.freeze(**args)
            args=self.inputs();args['decision_at']=args['context'].event_timestamp
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):ledger.freeze(**args)
    def rule(self):return SettlementRule('draftkings','CFB','spread','full_game',True,True,False,0,False,'fixture rule only','2023-01-01T00:00:00Z','fixture-v1')
    def test_push_unknown_rule_regulation_and_cancelled(self):
        context=replace(fixture_rows(1)[0].context,line=3,opposite_line=3)
        args=dict(context=context,observed_stat=-3,final_status='final',decision_at=context.prediction_timestamp)
        self.assertEqual(grade(self.rule(),**args),'PUSH')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_SETTLEMENT_RULE'):grade(None,**args)
        with self.assertRaisesRegex(ValueError,'REGULATION_RESULT_REQUIRED'):grade(replace(self.rule(),overtime_included=False),**args)
        args['final_status']='cancelled';self.assertEqual(grade(self.rule(),**args),'VOID')
    def test_listed_starter_and_participation(self):
        context=fixture_rows(1)[0].context
        args=dict(context=context,observed_stat=3,final_status='final',decision_at=context.prediction_timestamp)
        with self.assertRaisesRegex(ValueError,'UNVERIFIED_PITCHER'):grade(replace(self.rule(),listed_starter_required=True),**args)
        self.assertEqual(grade(replace(self.rule(),listed_starter_required=True),listed_starter_matches=False,**args),'VOID')
        with self.assertRaisesRegex(ValueError,'MISSING_PARTICIPATION'):grade(replace(self.rule(),nonparticipant_void=True),**args)
    def test_cash_bonus_push_void_denominators(self):
        self.assertEqual(cashflow('PUSH',-110,10)['cash_profit'],0)
        self.assertEqual(cashflow('VOID',-110,10)['roi_denominator'],0)
        self.assertEqual(cashflow('LOSS',-110,10)['cash_profit'],-10)
        bonus=cashflow('WIN',200,10,account='bonus');self.assertEqual(bonus['cash_return'],20)
        self.assertIsNone(bonus['roi_denominator'])
