"""Mechanical fixtures only; real performance is produced by the executed job."""
from dataclasses import replace
from datetime import datetime,timedelta
import unittest
import numpy as np
from ap_evsims.prop_research import PlayerOutcome
from ap_evsims.prop_challenger import features,evaluate,distribution,distribution_scores,Ridge,POLICY
from ap_evsims.history_expansion import roster_cohort
from ap_evsims.challenger_delivery import project,simulate
from ap_evsims.integrity import digest
from ap_evsims.prop_prices import future_research_events
from ap_evsims.p0_results import paired_comparison


def sample(i):
    day=(datetime(2023,1,1)+timedelta(days=i//10)).date().isoformat()
    return PlayerOutcome('NFL','receptions',str(i),str(i%10),'Fixture','A','B',day,2025,
                         float(2+i%5),1+i%3,'a'*64,'b'*64,'2026-10-16T00:00:00Z')


class ChallengerTests(unittest.TestCase):
    def test_target_and_target_opportunity_never_enter_forecast(self):
        rows=[sample(i) for i in range(420)];_,a,_=evaluate(rows,'NFL','receptions')
        _,b,_=evaluate(rows[:-1]+[replace(rows[-1],outcome=100,opportunity=150)],'NFL','receptions')
        self.assertTrue(a);self.assertEqual(a[-1]['projection'],b[-1]['projection'])
        self.assertEqual(a[-1]['projected_opportunity'],b[-1]['projected_opportunity'])
        self.assertEqual(a[-1]['feature_hash'],b[-1]['feature_hash']);self.assertEqual(a[:-1],b[:-1])
    def test_same_day_outcome_embargo(self):
        rows=[sample(i) for i in range(420)];_,a,_=evaluate(rows,'NFL','receptions')
        altered=list(rows);altered[-10]=replace(altered[-10],outcome=100)
        _,b,_=evaluate(altered,'NFL','receptions');self.assertEqual(a[-1]['projection'],b[-1]['projection'])
    def test_duplicate_rows_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):evaluate([sample(0),sample(0)],'NFL','receptions')
    def test_cross_sport_rejected(self):
        with self.assertRaisesRegex(ValueError,'CROSS_SPORT'):evaluate([sample(0)],'NBA','receptions')
    def test_future_feature_rejected(self):
        with self.assertRaisesRegex(ValueError,'LEAKAGE'):features([sample(i) for i in range(50)],'2023-01-04')
    def test_missing_history_not_invented(self):
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):features([],'2026-10-16')
    def test_count_distribution_and_tail(self):
        d=distribution(2,[0.]*100,'receptions');x,p=d
        self.assertAlmostEqual(float(p.sum()),1);self.assertTrue(np.all(p>=0));self.assertGreaterEqual(x.min(),0)
        self.assertGreater(p[x==10][0],0);self.assertIsNone(distribution(2,[],'receptions'))
    def test_yards_allow_negative_outcomes(self):
        x,p=distribution(-1,[-.5]*100,'rushing_yards');self.assertGreater(float(p[x<0].sum()),0)
    def test_scores_and_intervals(self):
        d=(np.array([0,1,2]),np.array([.2,.5,.3]));s=distribution_scores(d,1,1.5)
        self.assertAlmostEqual(s['brier'],.09);self.assertAlmostEqual(s['nll'],-np.log(.5))
        self.assertGreaterEqual(s['crps'],0);self.assertTrue(s['coverage_80'])
    def test_predictive_distribution_reproducible(self):
        a=distribution(2,np.linspace(-2,2,100),'receptions');b=distribution(2,np.linspace(-2,2,100),'receptions')
        np.testing.assert_array_equal(a[1],b[1])
    def test_ridge_missing_and_nonfinite(self):
        r=Ridge()
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):r.predict(np.zeros(11))
        with self.assertRaisesRegex(ValueError,'NONFINITE'):r.update(np.full(11,np.nan),2,3)
    def test_no_betting_authority_in_artifact(self):
        a,_,_=evaluate([sample(i) for i in range(420)],'NFL','receptions')
        self.assertFalse(a['cash_authority']);self.assertEqual(a['model_status'],'UNVALIDATED')
        self.assertEqual(a['policy'],POLICY);self.assertEqual(len(a['feature_dataset_fingerprint']),64)
    def test_projection_has_no_invented_calibration(self):
        a,_,_=evaluate([sample(i) for i in range(420)],'NFL','receptions')
        p=project(a,'1','2026-10-17T02:00:00Z');self.assertIsNone(p['calibrated_probability']);self.assertIsNone(p['p_low'])
        self.assertFalse(p['recommendations_enabled']);self.assertAlmostEqual(sum(p['distribution'].values()),1)
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):project(a,'1','2024-01-01T00:00:00Z')
    def test_before_after_scores_only_identical_outcomes(self):
        a=[dict(event_id='1',player_id='a',outcome=3,projection=2),dict(event_id='2',player_id='a',outcome=1,projection=2)]
        b=[dict(event_id='1',player_id='a',outcome=3,projection=3),dict(event_id='2',player_id='a',outcome=2,projection=2)]
        r=paired_comparison(a,b);self.assertEqual(r['common_sample_n'],1);self.assertEqual(r['revised_outcome_exclusions'],1)
        self.assertEqual(r['before']['mae'],1);self.assertEqual(r['after']['mae'],0)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):paired_comparison(a+a,b)
    def test_simulation_records_seed_draws_and_marginal_scope(self):
        f={'projection':{'distribution':{'0':.25,'1':.75}},'sport':'NFL','market':'receptions','forecast_hash':'a'*64}
        a=simulate(f,20000);self.assertEqual(a,simulate(f,20000));self.assertEqual(a['exact_distribution_mean'],.75)
        self.assertEqual(len(digest(a)),64)
        self.assertEqual(len(a['runs']),2);self.assertTrue(a['convergence_passed'])
        with self.assertRaisesRegex(ValueError,'DRAWS'):simulate(f,10)
    def test_roster_selection_order_invariant_and_bounded(self):
        roster={'roster':[{'person':{'id':i},'position':{'abbreviation':'P' if i<5 else 'OF'}} for i in range(15)]}
        a=roster_cohort(roster,1);roster['roster'].reverse();self.assertEqual(a,roster_cohort(roster,1))
        self.assertEqual(len(a),3);self.assertEqual(sum(g=='hitting' for _,g in a),2)
    def test_research_collection_excludes_near_start_boundary(self):
        events=[{'id':'near','commence_time':'2026-10-17T02:10:00Z'},{'id':'next','commence_time':'2026-10-17T03:00:00Z'}]
        self.assertEqual([e['id'] for e in future_research_events(events,'2026-10-17T02:00:00Z')],['next'])


if __name__=='__main__':unittest.main()
