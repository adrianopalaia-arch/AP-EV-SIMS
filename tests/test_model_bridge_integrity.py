"""Even otherwise eligible fixture inputs cannot turn unapproved bounds into stakes."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from ap_evsims.exposure import ExposureLedger,ExposureLimits
from ap_evsims.features import CFB
from ap_evsims.historical import HistoricalObservation
from ap_evsims.integrity import ValidationRegistry
from ap_evsims.ledger import Ledger
from ap_evsims.models.base import FeatureValue,FeatureSnapshot,MarketContext,PredictionResult
from ap_evsims.model_bridge import decide_prediction,pipeline_version
from test_phase1 import observations,NOW


class ModelBridgeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.registry=ValidationRegistry(root/'validation.sqlite');self.exposure=ExposureLedger(root/'exposure.sqlite')
        self.ledger=Ledger(root/'decisions.jsonl')
        at='2026-10-14T00:58:00Z'
        values={k:FeatureValue(.5,'fixture',at,at,'fixture','a'*64) for k in CFB}
        values['american_odds']=replace(values['american_odds'],value=110)
        values['market_line']=replace(values['market_line'],value=3.5)
        features=FeatureSnapshot('g1','CFB',at,values)
        context=MarketContext('g1','CFB','spread','home','fixture',3.5,110,-140,
            '2026-10-14T00:58:30Z','2026-10-14T00:59:00Z','2026-10-14T01:30:00Z','quote',3.5)
        self.row=HistoricalObservation('fixture',features,context,21,14,'2026-10-14T06:00:00Z','result','b'*64,'final',
            availability_timestamp='2026-10-14T00:57:00Z',lineup_verified=True,binary_settlement_verified=True,risk_groups=('GAME:g1','TEAM:a'))
        self.prediction=PredictionResult(.63,.63,.58,None,None,'fixture','2026-09-30T00:00:00Z',at,features.fingerprint,'spread','calibration','artifact',
            event_id='g1',sport='CFB',prediction_timestamp=context.prediction_timestamp,model_disagreement=0.0)
        version=pipeline_version(self.prediction)
        self.evidence=self.registry.evaluate(sport='CFB',market='spread',model_version=version,mode='pregame',
            training_cutoff=self.prediction.training_cutoff,expires='2026-11-01T00:00:00Z',
            observations=[dict(r,model_version=version) for r in observations()])

    def decide(self,prediction):
        result=decide_prediction(self.row,prediction,self.evidence,registry=self.registry,exposure=self.exposure,
            limits=ExposureLimits(1000),ledger=self.ledger,now=NOW)
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['stake_usd'],0)
        self.assertEqual(self.exposure.positions(),[])
        return result

    def test_self_asserted_coverage_cannot_authorize_exposure(self):
        for components in ({},{'coverage_validated':False},{'coverage_validated':True}):
            result=self.decide(replace(self.prediction,uncertainty_components=components))
            self.assertIn('P_LOW_COVERAGE_UNVERIFIED',result['reasons'])
            # Phase 1 evidence is otherwise valid: the new guard supplies the rejection.
            self.assertNotIn('MODEL_NOT_CALIBRATED',result['reasons'])
        self.assertEqual(self.ledger.read()[0]['prediction']['calibrated_probability'],.63)

    def test_feature_and_context_mismatch_rejected_before_reservation(self):
        for fields,reason in (({'data_fingerprint':'wrong'},'PREDICTION_FEATURE_MISMATCH'),
                ({'event_id':'other'},'PREDICTION_CONTEXT_MISMATCH'),({'market_type':'total'},'PREDICTION_CONTEXT_MISMATCH'),
                ({'sport':'NHL'},'PREDICTION_CONTEXT_MISMATCH'),({'prediction_timestamp':NOW},'PREDICTION_CONTEXT_MISMATCH')):
            self.assertIn(reason,self.decide(replace(self.prediction,**fields))['reasons'])

    def test_disagreement_is_not_silently_replaced_with_zero(self):
        for value in (.2,None):
            result=self.decide(replace(self.prediction,model_disagreement=value))
            self.assertIn('MODEL_DISAGREEMENT',result['reasons'])

