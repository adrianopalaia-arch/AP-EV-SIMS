"""Synthetic integrity checks; these observations never enter real evaluation."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile
import unittest
from ap_evsims.cfb_scores import *
from ap_evsims.cfb_score_research import freeze
from ap_evsims.research_store import ResearchStore


def game(i=1,**kw):
    values=dict(event_id=str(i),home_id='1',away_id='2',kickoff=(datetime(2024,1,1,tzinfo=timezone.utc)+timedelta(days=i)).isoformat(),
        season=2024,home_score=24,away_score=17,final_status='final',neutral=False,source_id='a'*64,source_hash='b'*64,
        captured_at='2026-10-16T00:00:00Z',available_at='2026-10-16T00:00:00Z',revision_hashes=('c'*64,))
    values.update(kw);return CompletedGameScoreObservation(**values)


class ScoreTests(unittest.TestCase):
    def test_score_only_fit_needs_no_odds(self):
        m=ScoreMarginModel().fit([game(i) for i in range(100)],'2024-06-01T00:00:00Z',2024)
        self.assertGreater(m.predict('1','2',False),0);self.assertEqual(m.state['training_n'],100)
    def test_target_and_future_are_excluded(self):
        rows=[game(i) for i in range(100)];at='2024-06-01T00:00:00Z'
        base=ScoreMarginModel().fit(rows,at,2024)
        other=ScoreMarginModel().fit(rows+[game(999,kickoff=at,home_score=99)],at,2024)
        self.assertEqual(base.state,other.state)
    def test_duplicate_game_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):unique_games([game(),game()])
    def test_prospective_cannot_use_later_capture(self):
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):ScoreMarginModel().fit([game(i) for i in range(100)],'2024-06-01T00:00:00Z',2024,prospective=True)
    def test_no_backdated_availability(self):
        with self.assertRaisesRegex(ValueError,'UNPROVEN'):replace(game(),available_at='2024-01-03T00:00:00Z').validate()
    def test_provenance_not_promotable(self):
        with self.assertRaisesRegex(ValueError,'UNPROVEN'):replace(game(),provenance='VERIFIED_HISTORICAL').validate()
    def test_nonfinal_missing_score(self):
        for changes in ({'final_status':'live'},{'home_score':None},{'home_score':True},{'home_score':-1}):
            with self.assertRaises(ValueError):replace(game(),**changes).validate()
    def test_unknown_and_sparse_teams(self):
        m=ScoreMarginModel().fit([game(i) for i in range(100)],'2024-06-01T00:00:00Z',2024)
        with self.assertRaisesRegex(ValueError,'UNKNOWN'):m.predict('3','2',False)
    def test_neutral_removes_home_advantage(self):
        m=ScoreMarginModel().fit([game(i) for i in range(100)],'2024-06-01T00:00:00Z',2024)
        self.assertAlmostEqual(m.predict('1','2',False)-m.predict('1','2',True),m.state['home_advantage'])
    def test_season_shrink(self):
        rows=[game(i) for i in range(100)];a=ScoreMarginModel().fit(rows,'2024-06-01T00:00:00Z',2024)
        b=ScoreMarginModel().fit(rows,'2024-06-01T00:00:00Z',2025)
        self.assertLess(abs(b.state['team_strengths']['1']),abs(a.state['team_strengths']['1']))
    def test_distribution_mass_and_integer_push(self):
        pmf=margin_distribution(3,[0]*40+[4]*40)
        m=market_mass(pmf,-3);self.assertEqual(m['p_push'],.5);self.assertAlmostEqual(sum(m.values()),1)
        self.assertEqual(market_mass(pmf,-3.5)['p_push'],0)
        self.assertEqual(market_mass(pmf,3,'away')['p_push'],.5)
    def test_no_residual_invention(self):self.assertIsNone(margin_distribution(0,[1]*79))
    def test_cfb_overtime_removes_impossible_final_ties(self):
        pmf=margin_distribution(0,[0]*40+[3]*40)
        self.assertNotIn(0,pmf);self.assertEqual(market_mass(pmf)['p_push'],0)
    def test_crps_exact(self):self.assertEqual(crps({3:.5,7:.5},3),1)
    def test_invalid_distribution(self):
        with self.assertRaises(ValueError):market_mass({3:.4,7:.4})
    def test_chronology_unchanged_by_future_result(self):
        rows=[game(i) for i in range(210)]
        a,_=chronological_evaluation(rows)
        b,_=chronological_evaluation(rows+[game(400,home_score=100)])
        self.assertEqual(a,[r for r in b if r['event_id']!='400'])
        self.assertTrue(a)
    def test_freeze_preserves_first_and_rejects_late_or_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(Path(d));r=dict(event_id='1',model_version=VERSION,latest_source_capture='2026-10-15T10:00:00Z',generated_at='2026-10-16T10:00:00Z',
                event_start='2026-10-17T10:00:00Z',model_status='UNVALIDATED',recommendations_enabled=False,p_low=None,calibrated_probability=None,expected_home_margin=3,margin_distribution={-3:.5,10:.5})
            f,new=freeze(s,r);self.assertTrue(new)
            again,new=freeze(s,dict(r,expected_home_margin=8));self.assertFalse(new);self.assertEqual(again['expected_home_margin'],3)
            for changes in ({'generated_at':'2026-10-18T00:00:00Z'},{'recommendations_enabled':True},{'p_low':.6}):
                with self.assertRaises(ValueError):freeze(s,dict(r,**changes))
    def test_source_revision_and_fbs_scope(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(Path(d));g=dict(id=1,homeId=1,awayId=2,homeTeam='Home',awayTeam='Away',startDate='2024-09-01T00:00:00Z',season=2024,
                homeClassification='fbs',awayClassification='fbs',startTimeTBD=False,neutralSite=False,completed=True,homePoints=24,awayPoints=17)
            sources=[]
            for day,points in ((15,24),(16,27)):
                body=[dict(g,homePoints=points),dict(g,id=2,awayClassification='fcs')]
                at=f'2026-10-{day}T00:00:00Z';m=s.archive(provider='cfbd',endpoint='games',parameters={},body=json.dumps(body).encode(),fetched_at=at,observed_at=at,available_at=at,availability_basis='recorded_response');sources.append((m,body))
            rows,_,audit=score_observations(sources,'2026-10-17T00:00:00Z')
            self.assertEqual(len(rows),1);self.assertEqual(rows[0].home_score,27);self.assertEqual(len(rows[0].revision_hashes),2)
            self.assertEqual(audit['exclusions']['OUTSIDE_FBS_VS_FBS_SCOPE'],1)
            duplicate=[(sources[0][0],[g,g])]
            self.assertFalse(score_observations(duplicate,'2026-10-17T00:00:00Z')[0])
