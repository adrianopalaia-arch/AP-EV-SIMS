import unittest,tempfile,json
from pathlib import Path
from dataclasses import replace
from datetime import timedelta
from ap_evsims.backtest import run_walk_forward,summarize
from ap_evsims.historical import FoldWindow
from ap_evsims.market import market_consensus,movement,closing_line_value
from ap_evsims.integrity import utc
from ap_evsims.ensemble import ensemble_diagnostics
from ap_evsims.cfb_features import PlayFact,rolling_matchup_features,normalize_cfbd_plays
from test_phase2_cfb import fixture_rows
from test_phase2_base import market

class BacktestTests(unittest.TestCase):
    def test_walk_forward_preserves_decision_authority(self):
        rows=fixture_rows(240)
        window=FoldWindow('2024-04-01T00:00:00Z','2024-06-01T00:00:00Z','2024-07-15T00:00:00Z','2024-09-01T00:00:00Z')
        with tempfile.TemporaryDirectory() as t:
            result=run_walk_forward(rows,[window],market_type='spread',output_dir=t,feature_keys=('home_field',),
                minimum_train=20,minimum_calibration=20,minimum_selection=20,bootstrap_samples=10,dataset_kind='synthetic_test')
            self.assertEqual(result['dataset_kind'],'synthetic_test'); self.assertFalse(result['profitability_demonstrated'])
            self.assertGreater(result['summary']['raw']['n'],0); self.assertGreater(result['summary']['calibrated']['n'],0)
            self.assertEqual(result['summary']['bet_count'],0); self.assertIsNone(result['summary']['roi'])
            records=[json.loads(line) for line in (Path(t)/'predictions.jsonl').read_text().splitlines()]
            self.assertTrue(all(r['status']=='PASS' for r in records))
            self.assertTrue(all(utc(r['training_cutoff'])<utc(r['feature_timestamp']) for r in records))
            self.assertTrue(all('MODEL_NOT_CALIBRATED' in r['pass_reasons'] for r in records))
            self.assertTrue((Path(t)/'ranking.csv').exists())
            with self.assertRaisesRegex(ValueError,'NOT_EMPTY'): run_walk_forward(rows,[window],market_type='spread',output_dir=t,dataset_kind='synthetic_test')
    def test_provider_history_requires_archive_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'PROVIDER_PROVENANCE_REQUIRED'):
                run_walk_forward(fixture_rows(20),[],market_type='spread',output_dir=t)
    def test_empty_data_has_no_fake_metrics(self):
        with tempfile.TemporaryDirectory() as t:
            result=run_walk_forward([],[],market_type='spread',output_dir=t)
            self.assertEqual(result['summary']['historical_sample_size'],0)
            for field in ('roi','max_drawdown','point_clv_mean','price_clv_mean'): self.assertIsNone(result['summary'][field])
            self.assertIsNone(result['summary']['calibrated']['brier'])
    def test_insufficient_training_still_records_passes(self):
        rows=fixture_rows(12,start='2024-08-01')
        w=FoldWindow('2024-04-01T00:00:00Z','2024-06-01T00:00:00Z','2024-07-15T00:00:00Z','2024-09-01T00:00:00Z')
        with tempfile.TemporaryDirectory() as t:
            result=run_walk_forward(rows,[w],market_type='spread',output_dir=t,feature_keys=('home_field',),bootstrap_samples=10,dataset_kind='synthetic_test')
            self.assertEqual(result['summary']['prediction_count'],12)
            self.assertIn('INSUFFICIENT_TRAINING',result['folds'][0]['reason'])
    def test_consensus_keeps_different_lines_separate(self):
        a=market(); b=replace(a,book='fanduel',odds=110,opposite_odds=-130)
        c=replace(a,book='other',line=2.5,opposite_line=2.5)
        rows=market_consensus([a,b,c],as_of=a.quote_timestamp)
        self.assertEqual(len(rows),2); self.assertEqual(sorted(r['book_count'] for r in rows),[1,2])
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'): market_consensus([a],as_of='2024-01-01T00:00:00Z')
    def test_movement_and_clv_do_not_compare_mismatched_price_lines(self):
        a=market(); b=replace(a,line=2.5,opposite_line=2.5,odds=-120,quote_timestamp='2024-08-03T02:00:00Z')
        clv=closing_line_value(a,b); self.assertEqual(clv['point_clv'],1); self.assertIsNone(clv['price_clv'])
        m=movement([a,b],as_of=b.quote_timestamp); self.assertEqual(m['line_movement'],-1); self.assertFalse(m['true_opener_verified'])
        self.assertIsNone(closing_line_value(a,None)['price_clv'])
    def test_ensemble_agreement_is_not_independent_value(self):
        base=[.7 if i%2 else .3 for i in range(300)]; y=[i%2 for i in range(300)]
        result=ensemble_diagnostics(base,base,y,baseline_clv=[.01]*300,additional_clv=[.02]*300)
        self.assertEqual(result['weight'],0); self.assertFalse(result['deployment_approved'])
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'): ensemble_diagnostics(base[:2],base[:2],y[:2],baseline_clv=None,additional_clv=None)

class RollingFeatureTests(unittest.TestCase):
    def plays(self):
        out=[]
        for i in range(20):
            for offense,defense,ppa in (('Home','Away',.2),('Away','Home',-.1)):
                out.append(PlayFact(str(i)+offense,'prior-'+str(i//5),offense,defense,1,10,6,'Rush',None,ppa,
                    '2024-07-01T00:00:00Z','2024-07-02T00:00:00Z','fixture','a'*64))
        return out
    def test_ppa_never_becomes_epa_and_unknown_features_remain_missing(self):
        s=rolling_matchup_features(self.plays(),event_id='future',home_team='Home',away_team='Away',as_of='2024-08-01T00:00:00Z',minimum_plays=10,minimum_games=3)
        self.assertIn('ppa_diff',s.values); self.assertNotIn('offensive_epa_diff',s.values)
        self.assertNotIn('pressure_rate_diff',s.values); self.assertNotIn('wind',s.values)
    def test_future_or_unverified_prior_data_excluded(self):
        for plays in ([replace(p,available_at=None) for p in self.plays()],
                      [replace(p,available_at='2024-09-01T00:00:00Z') for p in self.plays()]):
            with self.assertRaisesRegex(ValueError,'INSUFFICIENT'): rolling_matchup_features(plays,event_id='future',home_team='Home',away_team='Away',as_of='2024-08-01T00:00:00Z',minimum_plays=10,minimum_games=3)
    def test_current_game_plays_never_enter_pregame_features(self):
        past=self.plays(); leaked=[replace(p,play_id=p.play_id+'future',event_id='future',ppa=999) for p in past]
        args=dict(event_id='future',home_team='Home',away_team='Away',as_of='2024-08-01T00:00:00Z',minimum_plays=10,minimum_games=3)
        self.assertEqual(rolling_matchup_features(past,**args).values['ppa_diff'].value,rolling_matchup_features(past+leaked,**args).values['ppa_diff'].value)
    def test_missing_completion_and_cfbd_ppa_label(self):
        payload=[dict(id='p',gameId=1,offense='Home',defense='Away',down=1,distance=10,yardsGained=6,playType='Rush',ppa=.2)]
        manifest=dict(available_at='2024-07-02T00:00:00Z',snapshot_id='fixture',payload_hash='a'*64)
        rows,reasons=normalize_cfbd_plays(payload,manifest,game_observed_times={})
        self.assertEqual(rows,[]); self.assertIn('UNVERIFIED',reasons[0]['reason'])
        rows,_=normalize_cfbd_plays(payload,manifest,game_observed_times={'1':'2024-07-01T00:00:00Z'})
        self.assertIsNone(rows[0].epa); self.assertEqual(rows[0].ppa,.2)
