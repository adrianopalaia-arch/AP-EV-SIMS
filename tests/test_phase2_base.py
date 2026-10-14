import unittest
from dataclasses import replace
from ap_evsims.models.base import FeatureValue, FeatureSnapshot, MarketContext, PredictionResult

def feature(value=1, **kw):
    d=dict(value=value,source='explicit_test_fixture',observed_at='2024-08-01T00:00:00Z',available_at='2024-08-02T00:00:00Z',snapshot_id='fixture-snapshot',payload_hash='a'*64); d.update(kw)
    return FeatureValue(**d)

def snapshot(**kw):
    d=dict(event_id='g1',sport='CFB',timestamp='2024-08-03T00:00:00Z',values={'home_field':feature()}); d.update(kw)
    return FeatureSnapshot(**d)

def market(**kw):
    d=dict(event_id='g1',sport='CFB',market_type='spread',selection='home',book='draftkings',line=3.5,opposite_line=3.5,odds=-110,opposite_odds=-110,prediction_timestamp='2024-08-03T01:00:00Z',quote_timestamp='2024-08-03T01:00:00Z',event_timestamp='2024-08-03T04:00:00Z',snapshot_id='odds-fixture'); d.update(kw)
    return MarketContext(**d)

class FrameworkTests(unittest.TestCase):
    def test_provenance_and_roundtrip(self):
        s=snapshot(); s.validate(market().prediction_timestamp,('home_field',))
        from dataclasses import asdict
        self.assertEqual(FeatureSnapshot.from_dict(asdict(s)),s)
        self.assertEqual(s.fingerprint,FeatureSnapshot.from_dict(asdict(s)).fingerprint)
    def test_future_and_unknown_availability(self):
        with self.assertRaisesRegex(ValueError,'UNVERIFIED'): feature(available_at=None).validate('2024-08-04T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): feature(available_at='2024-09-01T00:00:00Z').validate('2024-08-04T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): snapshot().validate('2024-08-02T00:00:00Z')
    def test_missing_and_forbidden_feature(self):
        with self.assertRaisesRegex(ValueError,'MISSING_FEATURES'): snapshot().validate(market().prediction_timestamp,('epa',))
        with self.assertRaisesRegex(ValueError,'FORBIDDEN'): snapshot(values={'closing_spread':feature()}).validate(market().prediction_timestamp)
    def test_market_pairs_and_ordering(self):
        market().validate()
        for kw in (dict(opposite_odds=None),dict(opposite_line=2.5)):
            with self.assertRaisesRegex(ValueError,'MISSING_MARKET_PAIR'): market(**kw).validate()
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): market(prediction_timestamp='2024-08-03T05:00:00Z').validate()
    def test_model_result_has_no_decision_authority(self):
        r=PredictionResult(None,None,None,None,None,'v',None,'2024-08-03T00:00:00Z','h','spread',None,None)
        self.assertNotIn('status',r.to_dict()); self.assertNotIn('stake',r.to_dict())
