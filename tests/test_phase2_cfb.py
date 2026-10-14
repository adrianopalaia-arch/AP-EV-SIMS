"""Synthetic mechanics tests, explicitly excluded from historical performance reports."""
import unittest
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from ap_evsims.models.base import FeatureValue,FeatureSnapshot,MarketContext
from ap_evsims.models.cfb import CFBSpreadModel,CFBTotalModel,CFBWinModel,DiscreteTilt,market_mass
from ap_evsims.historical import HistoricalObservation

def fixture_rows(n=90,start='2024-01-01',market_type='spread'):
    base=datetime.fromisoformat(start).replace(tzinfo=timezone.utc); out=[]
    for i in range(n):
        day=base+timedelta(days=i); time=lambda hour:(day+timedelta(hours=hour)).isoformat()
        event='test-event-'+day.date().isoformat(); x=(i%5)-2
        features=FeatureSnapshot(event,'CFB',time(9),{
            'home_field':FeatureValue(x,'synthetic_test_only',time(8),time(8),'fixture-'+event,'a'*64),
            'pace_sum':FeatureValue(120+x*5,'synthetic_test_only',time(8),time(8),'fixture-'+event,'a'*64)})
        c=MarketContext(event,'CFB',market_type,'over' if market_type=='total' else 'home','draftkings',
            50.5 if market_type=='total' else None if market_type=='win' else 3.5,-110,-110,time(10),time(10),time(12),'odds-'+event,
            50.5 if market_type=='total' else None if market_type=='win' else 3.5)
        home=25+x*3+(i%3); away=25-x+(i%2)
        out.append(HistoricalObservation('r-'+event,features,c,home,away,time(20),'result-'+event,'b'*64,'final'))
    return out

class CFBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=fixture_rows()
        cls.model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(cls.rows,training_cutoff='2024-04-01T00:00:00Z')
        cls.future=fixture_rows(1,start='2024-05-01')[0]
    def test_model_predicts_probability_only(self):
        p=self.model.predict(self.future.features,self.future.context)
        self.assertTrue(0<p.raw_probability<1); self.assertIsNone(p.calibrated_probability)
        self.assertIn('MODEL_NOT_CALIBRATED',p.reasons); self.assertNotIn('status',p.to_dict())
        self.assertIn('model_fair_spread',p.explanation); self.assertIn('features_used',p.explanation)
    def test_key_number_mass_not_equal_point_moves(self):
        # Constructed frequency table, not a claim about real CFB key-number frequency.
        dist=DiscreteTilt([-3]*80+[-6]*10+[10]*10)
        pmf=dist.pmf(sum(k*p for k,p in zip(dist.support,dist.base)))
        c=self.future.context
        a=market_mass(pmf,replace(c,line=2.5))[0]; b=market_mass(pmf,replace(c,line=3))[0]
        push3=market_mass(pmf,replace(c,line=3))[1]
        plus35=market_mass(pmf,replace(c,line=3.5))[0]
        plus55=market_mass(pmf,replace(c,line=5.5))[0]; plus65=market_mass(pmf,replace(c,line=6.5))[0]
        self.assertAlmostEqual(b,a); self.assertGreater(push3,.7)
        self.assertGreater(plus35-a,plus65-plus55)
    def test_spread_monotonic_and_push_mass(self):
        pmf=self.model.distribution.pmf(0)
        probs=[market_mass(pmf,replace(self.future.context,line=line))[0] for line in (-7.5,-3.5,0,3.5,7.5)]
        self.assertEqual(probs,sorted(probs))
        self.assertGreater(market_mass(pmf,replace(self.future.context,line=3))[1],0)
    def test_no_future_or_missing_features(self):
        future=replace(self.future.features,timestamp='2025-01-01T00:00:00Z')
        self.assertIn('LOOKAHEAD_RISK',self.model.predict(future,self.future.context).reasons)
        missing=replace(self.future.features,values={})
        self.assertIn('MISSING_FEATURES',self.model.predict(missing,self.future.context).reasons)
    def test_training_cutoff_and_sample_gate(self):
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(self.rows,training_cutoff='2024-02-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'): CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(self.rows[:10],training_cutoff='2024-04-01T00:00:00Z')
    def test_total_and_win_are_separate_models(self):
        total=CFBTotalModel(feature_keys=('pace_sum',),minimum_train=20,bootstrap_samples=10).fit(fixture_rows(market_type='total'),training_cutoff='2024-04-01T00:00:00Z')
        future=fixture_rows(1,start='2024-05-01',market_type='total')[0]
        p=total.predict(future.features,future.context)
        self.assertTrue(0<p.raw_probability<1); self.assertIsNotNone(p.explanation['expected_total'])
        win=CFBWinModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(fixture_rows(market_type='win'),training_cutoff='2024-04-01T00:00:00Z')
        self.assertNotEqual(total.model_version,win.model_version); self.assertNotEqual(win.model_version,self.model.model_version)
    def test_changed_market_line_and_price(self):
        a=self.model.predict(self.future.features,self.future.context)
        context=replace(self.future.context,line=2.5,opposite_line=2.5,odds=-120)
        b=self.model.predict(self.future.features,context)
        self.assertGreater(a.raw_probability,b.raw_probability)
        # Exact payout changes belong to Phase 1, not the forecast.
        c=self.model.predict(self.future.features,replace(self.future.context,odds=110))
        self.assertAlmostEqual(c.raw_probability,a.raw_probability)
    def test_artifact_changes_with_training_and_recipe(self):
        other=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10,ridge_penalty=20)
        self.assertNotEqual(other.model_version,self.model.model_version)
        other.fit(self.rows,training_cutoff='2024-04-01T00:00:00Z'); self.assertNotEqual(other.artifact_id,self.model.artifact_id)
    def test_probability_mass_normalized(self):
        for mean in (-90,0,90):
            p=self.model.distribution.pmf(mean)
            self.assertAlmostEqual(sum(p.values()),1)
            self.assertAlmostEqual(sum(k*v for k,v in p.items()),mean,places=5)
