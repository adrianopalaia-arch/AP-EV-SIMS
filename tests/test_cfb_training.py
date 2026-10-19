"""Synthetic pipeline checks are excluded from every empirical research metric."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from ap_evsims.cfb_training import build_training_dataset, collect_prior_weeks, research_run
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.historical import FoldWindow


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=ResearchStore(self.root/'data');self.w=Warehouse(self.store.root)
    def tearDown(self):self.tmp.cleanup()
    def capture(self,endpoint,rows,at,params=None,provider='cfbd'):
        m=self.store.archive(provider=provider,endpoint=endpoint,parameters=params or {},body=json.dumps(rows).encode(),fetched_at=at,
            observed_at=at,available_at=at,availability_basis='recorded_response')
        self.w.ingest_manifest(self.store,m)
        if provider=='odds':self.w.record_odds(self.store,m)
        return m
    def sources(self,*,play_capture='2026-10-14T11:00:00Z',period='full_game',quote='2026-10-17T09:00:00Z',price=-110):
        games=[dict(id=i,homeId=1,awayId=2,homeTeam='Home',awayTeam='Away',completed=i<4,homePoints=20 if i<4 else None,
                    awayPoints=10 if i<4 else None,season=2026,week=i,seasonType='regular',homeClassification='fbs',awayClassification='fbs',
                    startTimeTBD=False,startDate=f'2026-09-{i:02d}T10:00:00Z' if i<4 else '2026-10-17T10:00:00Z') for i in range(1,5)]
        self.capture('games',games,'2026-10-14T10:00:00Z')
        self.capture('teams',[dict(id=1,school='Home'),dict(id=2,school='Away')],'2026-10-14T10:00:00Z')
        for i in range(1,4):
            rows=[dict(id=n,gameId=i,offense=t,defense='Away' if t=='Home' else 'Home',playType='Rush',down=1,distance=10,
                       yardsGained=6,ppa=.1) for n,t in enumerate(['Home']*40+['Away']*40)]
            self.capture('plays',rows,play_capture,dict(year=2026,week=i,seasonType='regular'))
        event=dict(id='odds1',sport_key='americanfootball_ncaaf',home_team='Home',away_team='Away',commence_time=games[-1]['startDate'],
            bookmakers=[dict(key='draftkings',last_update=quote,markets=[dict(key='spreads',period=period,outcomes=[
                dict(name='Home',price=price,point=-2.5),dict(name='Away',price=-110,point=2.5)])])])
        self.capture('sports/americanfootball_ncaaf/odds',[event],'2026-10-17T09:00:01Z',provider='odds')
        games[-1].update(completed=True,homePoints=27,awayPoints=21)
        self.capture('games',games,'2026-10-17T13:00:00Z')
    def test_verified_join_retains_denominator_and_one_real_source_row(self):
        self.sources();rows,audit=build_training_dataset(self.store,self.w,'2026-10-18T00:00:00Z')
        self.assertEqual(len(rows),1);self.assertEqual(audit['completed_fbs_game_denominator'],4)
        self.assertEqual(audit['rejection_counts']['NO_ELIGIBLE_ARCHIVED_PRICE'],3)
        self.assertEqual(rows[0].context.event_id,'4');self.assertEqual(rows[0].context.odds,-110)
        self.assertFalse(rows[0].lineup_verified)
    def test_later_download_does_not_train_historical_game(self):
        self.sources(play_capture='2026-10-17T14:00:00Z')
        rows,audit=build_training_dataset(self.store,self.w,'2026-10-18T00:00:00Z')
        self.assertEqual(rows,[]);self.assertEqual(audit['games_with_eligible_archived_price'],1)
        self.assertEqual(audit['rejection_counts']['HISTORICAL_AVAILABILITY_UNVERIFIED'],1)
    def test_period_and_stale_quotes_cannot_enter_training(self):
        self.sources(period='first_half')
        rows,audit=build_training_dataset(self.store,self.w,'2026-10-18T00:00:00Z')
        self.assertFalse(rows);self.assertEqual(audit['games_with_eligible_archived_price'],0)
    def test_old_quote_is_not_executable(self):
        self.sources(quote='2026-10-17T08:55:00Z')
        rows,audit=build_training_dataset(self.store,self.w,'2026-10-18T00:00:00Z')
        self.assertFalse(rows);self.assertEqual(audit['games_with_eligible_archived_price'],0)
    def test_future_results_not_revealed_at_historical_cutoff(self):
        self.sources();rows,audit=build_training_dataset(self.store,self.w,'2026-10-17T09:30:00Z')
        self.assertFalse(rows);self.assertEqual(audit['completed_fbs_game_denominator'],3)
    def test_sparse_data_blocks_model_fit_and_metrics_stay_null(self):
        self.sources();report=research_run(self.root,at='2026-10-18T00:00:00Z')
        self.assertEqual(report['eligible_training']['n'],1);self.assertEqual(report['real_model_predictions'],0)
        self.assertEqual(report['evaluation_status'],'BLOCKED_INSUFFICIENT_VERIFIED_HISTORY')
        self.assertEqual(report['models_validated'],0);self.assertIsNone(report['summary']['raw']['brier'])
        self.assertFalse(list((self.store.root/'evaluations').rglob('model-*.json')))
    def test_bounded_collector_reuses_captures_and_does_not_spend_past_budget(self):
        params=dict(year=2026,seasonType='regular',classification='fbs')
        self.capture('games',[],'2026-10-14T10:00:00Z',params)
        validator=Mock()
        result=collect_prior_weeks(self.store,self.w,validator,year=2026,through_week=6,max_requests=0)
        validator.request.assert_not_called();self.assertEqual(result['records'][0]['cached'],True)
        self.assertEqual(result['records'][1]['status'],'REQUEST_BUDGET_LIMIT')
        with self.assertRaisesRegex(ValueError,'BOUNDED'):collect_prior_weeks(self.store,self.w,validator,year=2026,through_week=99)
    def test_future_evaluation_window_is_rejected_before_work(self):
        window=FoldWindow('2025-08-01T00:00:00Z','2026-02-01T00:00:00Z','2026-08-01T00:00:00Z','2026-12-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'FUTURE_EVALUATION_WINDOW'):research_run(self.root,at='2026-10-18T00:00:00Z',windows=[window])
