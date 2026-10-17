import unittest,tempfile,json
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from pathlib import Path
from ap_evsims.models.probability_calibration import CalibrationMap,CalibrationObservation,select_calibration
from ap_evsims.models.cfb import CFBSpreadModel
from ap_evsims.models.artifacts import save_model,load_model
from ap_evsims.models.scenarios import predict_scenarios
from test_phase2_cfb import fixture_rows

def cal_rows(n,start,version='v1',artifact='a1'):
    day=datetime.fromisoformat(start).replace(tzinfo=timezone.utc); rows=[]
    for i in range(n):
        d=day+timedelta(days=i); p=.65 if i%2 else .35
        rows.append(CalibrationObservation('cal-'+d.date().isoformat(),p,i%2,version,artifact,'2023-12-01T00:00:00Z',
            (d+timedelta(hours=10)).isoformat(),(d+timedelta(hours=9)).isoformat(),(d+timedelta(hours=20)).isoformat()))
    return rows

class CalibrationTests(unittest.TestCase):
    def test_all_maps_monotone_and_finite(self):
        p=[.1,.1,.3,.5,.7,.9,.9]; y=[0,0,1,0,1,1,1]
        for kind in ('identity','platt','beta','isotonic'):
            mapping=CalibrationMap(kind).fit(p,y); v=[mapping.transform(i/100) for i in range(101)]
            self.assertEqual(v,sorted(v)); self.assertTrue(all(0<x<1 for x in v))
            self.assertEqual(CalibrationMap.from_state(mapping.state()).transform(.4),mapping.transform(.4))
    def test_default_sample_minimum_cannot_silently_calibrate(self):
        with self.assertRaisesRegex(ValueError,'MODEL_NOT_CALIBRATED'):
            select_calibration(cal_rows(20,'2024-01-01'),cal_rows(20,'2024-03-01'),model_version='v1',model_artifact_id='a1',selection_end='2024-04-01T00:00:00Z')
    def test_oos_selection_and_conservative_bound(self):
        c=select_calibration(cal_rows(300,'2024-01-01'),cal_rows(100,'2025-01-01'),model_version='v1',model_artifact_id='a1',selection_end='2025-05-01T00:00:00Z')
        self.assertEqual(c.sample_sizes,dict(fit=300,selection=100)); self.assertIn(c.map.kind,('platt','beta','isotonic','identity'))
        self.assertTrue(0<=c.lower_bound(.65,[.6,.62,.65,.68])<=c.transform(.65))
        self.assertFalse(c.uncertainty_components(.65,[.6,.65])['coverage_validated'])
    def test_no_overlap_future_or_mismatched_model(self):
        fit=cal_rows(40,'2024-01-01'); selection=cal_rows(40,'2024-04-01')
        for s in ([replace(selection[0],model_version='other')]+selection[1:],
                  [replace(selection[0],feature_timestamp='2026-01-01T00:00:00Z')]+selection[1:],
                  [replace(selection[0],event_id=fit[0].event_id)]+selection[1:]):
            with self.assertRaises(ValueError): select_calibration(fit,s,model_version='v1',model_artifact_id='a1',selection_end='2024-06-01T00:00:00Z',minimum_fit=20,minimum_selection=20)
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):
            select_calibration(fit,selection,model_version='v1',model_artifact_id='a1',selection_end='2024-04-02T00:00:00Z',minimum_fit=20,minimum_selection=20)
    def test_model_attachment_persistence_and_future_calibration(self):
        model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(fixture_rows(),training_cutoff='2024-04-01T00:00:00Z')
        fit=cal_rows(40,'2024-04-02',model.model_version,model.artifact_id); select=cal_rows(40,'2024-06-01',model.model_version,model.artifact_id)
        fit=[replace(r,training_cutoff=model.training_cutoff) for r in fit]; select=[replace(r,training_cutoff=model.training_cutoff) for r in select]
        c=select_calibration(fit,select,model_version=model.model_version,model_artifact_id=model.artifact_id,selection_end='2024-08-01T00:00:00Z',minimum_fit=20,minimum_selection=20)
        with self.assertRaisesRegex(ValueError,'MISMATCH'): model.attach_calibration(replace_calibration_identity(c,'other'))
        model.attach_calibration(c); future=fixture_rows(1,start='2024-09-01')[0]; pred=model.predict(future.features,future.context)
        self.assertIsNotNone(pred.calibrated_probability); self.assertLessEqual(pred.uncertainty_lower_bound,pred.calibrated_probability)
        earlier=fixture_rows(1,start='2024-07-01')[0]
        self.assertIn('CALIBRATION_LOOKAHEAD_RISK',model.predict(earlier.features,earlier.context).reasons)
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'model.json'; save_model(model,path); restored=load_model(path)
            self.assertEqual(restored.predict(future.features,future.context),pred)
            payload=json.loads(path.read_text()); payload['state']['fitted']['regression']['coefficients'][0]+=100; path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'): load_model(path)
    def test_injury_scenarios_do_not_bypass_calibration(self):
        model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(fixture_rows(),training_cutoff='2024-04-01T00:00:00Z')
        future=fixture_rows(1,start='2024-05-01')[0]
        starter=replace(future.features,values={**future.features.values,'home_field':replace(future.features.values['home_field'],value=2)})
        absence=replace(future.features,values={**future.features.values,'home_field':replace(future.features.values['home_field'],value=-2)})
        a=model.predict(starter,future.context); b=model.predict(absence,future.context)
        self.assertGreater(a.raw_probability,b.raw_probability)
        mixture=predict_scenarios(model,[(.5,starter),(.5,absence)],future.context)
        self.assertIn('SCENARIO_MIXTURE_NOT_CALIBRATED',mixture.reasons); self.assertIsNone(mixture.calibrated_probability)
        with self.assertRaisesRegex(ValueError,'WEIGHTS'): predict_scenarios(model,[(.2,starter)],future.context)

def replace_calibration_identity(c,version):
    from ap_evsims.models.probability_calibration import CalibratedProbability
    return CalibratedProbability(**{**c.state(),'model_version':version})
