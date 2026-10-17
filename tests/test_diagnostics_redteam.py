import unittest,random
from dataclasses import replace
from ap_evsims.diagnostics import *
from ap_evsims.models.numerics import Ridge
from ap_evsims.models.base import FeatureSnapshot,FeatureValue
from ap_evsims.calibration import brier_score

class DiagnosticTests(unittest.TestCase):
    def test_no_data_never_becomes_positive_evidence(self):
        self.assertIsNone(proper_score_report([])['brier'])
        self.assertFalse(p_low_diagnostic([])['coverage_validated'])
        self.assertEqual(bankroll_stress([],starting_bankroll=100,unit=1)['status'],'MISSING_LOCAL_DATA')
        self.assertIsNone(latency_report([])['p50'])
    def test_critical_and_missing_audit_blocks_readiness(self):
        audit=[dict(id=i,severity='CRITICAL',tested=True,result='PASS') for i in range(1,51)]
        args=dict(empirical_n=1000,prospective_n=300,beats_market=True,coverage_validated=True)
        self.assertEqual(readiness_gate(audit,**args)['status'],'MANUAL_READINESS_REVIEW')
        audit[0]['tested']=False
        self.assertIn('CRITICAL_RED_TEAM_UNRESOLVED',readiness_gate(audit,**args)['reasons'])
        self.assertIn('INCOMPLETE_RED_TEAM_AUDIT',readiness_gate([],**args)['reasons'])
    def test_synthetic_metrics_excluded_and_selection_bias_visible(self):
        with self.assertRaisesRegex(ValueError,'NON_EMPIRICAL'):proper_score_report([dict(event_id='e',market='spread',selection='home',dataset_kind='synthetic_test')])
        universe=[dict(event_id=str(i),stratum='popular' if i<10 else 'other') for i in range(20)]
        self.assertEqual(inclusion_report(universe,[str(i) for i in range(10)])['selection_bias_flag'],'SAMPLE_SELECTION_BIAS')
    def test_latency_rejects_missing_and_reverse_order(self):
        fields=('published_at','available_at','ingested_at','feature_at','prediction_at','publication_at')
        row={k:'2026-10-14T10:00:00Z' for k in fields};row['publication_at']='2026-10-14T10:00:10Z'
        self.assertEqual(latency_report([row])['p99'],10)
        row['feature_at']='2026-10-14T11:00:00Z';self.assertEqual(latency_report([row])['invalid_order_or_missing'],1)
    def test_grouped_tail_stress_and_kelly_cap(self):
        positions=[dict(group='same_game',stake=10,probability=0,decimal_odds=2) for _ in range(2)]
        r=bankroll_stress(positions,starting_bankroll=100,unit=1,paths=100)
        self.assertEqual(r['p01'],-20);self.assertEqual(r['probability_20_unit_drawdown'],1)
        k=kelly_stress(.8,.52,.05,2);self.assertLessEqual(k['model_fraction'],.01);self.assertEqual(k['extra_error_fraction'],0)
        with self.assertRaisesRegex(ValueError,'STAKING'):kelly_stress(.8,.6,.01,2,fraction=1)
    def test_future_sources_and_postgame_names_rejected(self):
        stamp='2026-10-14T10:00:00Z';future='2026-10-14T11:00:00Z'
        for field in ('season_end_stat','retrospective_core','later_injury','later_lineup','observed_weather','revised_opponent'):
            features=FeatureSnapshot('e','CFB',stamp,{field:FeatureValue(1,'fixture',future,future,'s','a'*64)})
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):features.validate(stamp)
        for field in ('closing_odds','postgame_epa','final_score','settled_result','outcome_win'):
            features=FeatureSnapshot('e','CFB',stamp,{field:FeatureValue(1,'fixture',stamp,stamp,'s','a'*64)})
            with self.assertRaisesRegex(ValueError,'FORBIDDEN'):features.validate(stamp)
    def test_label_shuffle_and_noise_have_no_unseen_advantage(self):
        # Deterministic negative controls on the train-only preprocessing primitive.
        # This is a mechanics regression, not a real model validation result.
        rng=random.Random(921);x=[[rng.gauss(0,1),rng.random()] for _ in range(2000)]
        y=[int(row[0]>0) for row in x];training=list(y[:1000]);rng.shuffle(training)
        model=Ridge(10).fit(x[:1000],training)
        p=[max(.001,min(.999,model.predict(row))) for row in x[1000:]]
        self.assertGreater(brier_score(p,y[1000:]),.23)
        noise=[[rng.random()] for _ in x];model=Ridge(10).fit(noise[:1000],y[:1000])
        p=[max(.001,min(.999,model.predict(row))) for row in noise[1000:]]
        self.assertGreater(brier_score(p,y[1000:]),.23)
    def test_fit_transform_does_not_learn_future_extremes(self):
        model=Ridge().fit([[0],[1],[2]],[0,1,0]);means=list(model.means)
        model.predict([1000000]);self.assertEqual(model.means,means)
