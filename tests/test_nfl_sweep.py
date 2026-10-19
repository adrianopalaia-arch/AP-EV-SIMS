import copy,json,math,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from types import SimpleNamespace
from urllib.parse import urlparse,parse_qs
from ap_evsims.nfl_schedule import reconcile,match_odds,kickoff
from ap_evsims.nfl_game_model import margin_mass,game_probs,prior_games,fit,mean,freeze,POLICY
from ap_evsims.nfl_sweep import price_age,featured_quotes,rankings
from ap_evsims.prop_prices import collect_nfl_slate,event_price_records
from ap_evsims.research_store import ResearchStore

def schedule_fixture():
    row=dict(game_id='2026_06_HOU_JAX',gameday='2026-10-18',gametime='09:30',game_type='REG',
        season='2026',week='6',espn='1',home_team='JAX',away_team='HOU',stadium='Wembley',location='Neutral')
    e=dict(id='1',date='2026-10-18T13:30Z',season=dict(year=2026,type=2),week=dict(number=6),
        competitions=[dict(competitors=[dict(homeAway='home',team=dict(id='30',abbreviation='JAX',displayName='Jacksonville Jaguars')),
            dict(homeAway='away',team=dict(id='34',abbreviation='HOU',displayName='Houston Texans'))])])
    return row,e

class ScheduleIntegrity(unittest.TestCase):
    def test_implicit_nfl_input_cannot_fall_back_to_one_event(self):
        from ap_evsims.prop_prospective import current_inputs
        with tempfile.TemporaryDirectory() as d:
            event,players,sources,reasons=current_inputs(d,'NFL')
            self.assertIsNone(event);self.assertEqual(reasons,['EXPLICIT_NFL_CANONICAL_EVENT_REQUIRED'])
    def test_default_challenger_dispatches_full_slate(self):
        from ap_evsims.challenger_delivery import run
        with patch('ap_evsims.challenger_delivery.run_nfl_slate',return_value={'scheduled_games':12}) as sweep:
            self.assertEqual(run('.','NFL')['scheduled_games'],12);sweep.assert_called_once_with('.')
    def test_default_availability_preserves_failed_games(self):
        from ap_evsims.prop_availability import capture
        games=[dict(event_id='a'),dict(event_id='b')]
        with tempfile.TemporaryDirectory() as d,patch('ap_evsims.nfl_schedule.next_slate',return_value=games),patch('ap_evsims.prop_availability.current_inputs',side_effect=ValueError('fixture')):
            r=capture(d,'NFL');self.assertEqual(len(r['events']),2);self.assertEqual(len(r['failures']),2)
    def test_international_eastern_to_utc(self):
        r,e=schedule_fixture();g=reconcile([r],{'events':[e]},'2026-10-18')[0]
        self.assertTrue(g['identity_verified']);self.assertTrue(g['neutral_site']);self.assertEqual(kickoff(r).hour,13)
    def test_sunday_night_is_next_utc_date(self):
        r,e=schedule_fixture();r['gametime']='20:20';e['date']='2026-10-19T00:20Z'
        self.assertTrue(reconcile([r],{'events':[e]},'2026-10-18')[0]['identity_verified'])
    def test_wrong_timezone_fails_identity(self):
        r,e=schedule_fixture();e['date']='2026-10-18T09:30Z'
        self.assertFalse(reconcile([r],{'events':[e]},'2026-10-18')[0]['identity_verified'])
    def test_missing_counterpart_retains_game(self):
        r,e=schedule_fixture();g=reconcile([r],{'events':[]},'2026-10-18')
        self.assertEqual(len(g),1);self.assertIn('SCHEDULE_CROSSCHECK_MISSING',g[0]['schedule_reasons'])
    def test_duplicate_schedule_rejected(self):
        r,e=schedule_fixture()
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):reconcile([r,r],{'events':[e]},'2026-10-18')
    def test_same_teams_different_games_never_cross_join(self):
        r,e=schedule_fixture();g=reconcile([r],{'events':[e]},'2026-10-18')[0]
        other=dict(id='wrong-week',home_team=g['home_team'],away_team=g['away_team'],commence_time='2026-10-25T13:30Z')
        self.assertIsNone(match_odds(g,[other])[0])
        exact=dict(other,id='correct',commence_time=g['kickoff'])
        self.assertEqual(match_odds(g,[other,exact])[0]['id'],'correct')
        self.assertIsNone(match_odds(g,[exact,exact])[0])

class GameModelIntegrity(unittest.TestCase):
    def test_freeze_is_research_only_and_schedule_cannot_look_ahead(self):
        from ap_evsims.integrity import digest
        r,e=schedule_fixture();g=reconcile([r],{'events':[e]},'2026-10-18')[0];g['schedule_available_at']='2026-10-17T09:00:00Z'
        a=dict(model=dict(teams=['HOU','JAX'],coefficients=[0,0,2,0],data_cutoff='2026-10-10T17:00:00Z'),residual_sd=12.,
            latest_source_capture='2026-10-17T09:00:00Z',generated_at='2026-10-17T10:00:00Z',source_manifest='fixture',source_hash='fixture')
        with tempfile.TemporaryDirectory() as d:
            ResearchStore(Path(d)/'data');f=freeze(d,g,a,digest(a),[],'2026-10-17T12:00:00Z')
            self.assertEqual(f['decision'],'PASS');self.assertFalse(f['recommendations_enabled']);self.assertIsNone(f['p_low'])
            self.assertIsNone(f['calibrated_probability']);g['schedule_available_at']='2026-10-17T13:00:00Z'
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):freeze(d,g,a,digest(a),[],'2026-10-17T12:00:00Z')
    def test_cash_and_unproven_edge_fail_acceptance(self):
        from scripts.nfl_sweep_acceptance import check
        r=dict(schedule=dict(source='fixture',captured_at='2026-10-17T12:00Z',games=[]),games=[],quota=dict(credits_used=0,daily_cap=0),auto_bets_placed=1,validated_edges=1)
        result=check(r)
        self.assertIn('sweep must not place real-money bets',result['problems'])
        self.assertIn('validated edge claimed without prospective validation evidence',result['problems'])
    def test_integer_push_and_conditional_tie_mass(self):
        mass=margin_mass(3.,12.,-3.);self.assertGreater(mass['p_push'],0);self.assertAlmostEqual(sum(mass.values()),1.)
        self.assertEqual(margin_mass(3.,12.,-3.5)['p_push'],0)
        p=game_probs(3.,12.);self.assertAlmostEqual(p['p_home_win']+p['p_away_win'],1.)
        self.assertAlmostEqual(p['p_home_win_unconditional']+p['p_away_win_unconditional']+p['p_tie'],1.)
    def test_opposite_spreads_partition(self):
        h=margin_mass(2.,11.,-3.);a=margin_mass(2.,11.,3.,False)
        self.assertAlmostEqual(h['p_win'],a['p_loss']);self.assertAlmostEqual(h['p_push'],a['p_push'])
    def test_future_target_score_cannot_change_fit(self):
        rows=[dict(event_id=str(i),kickoff=f'2026-09-{i+1:02}T17:00:00Z',home_code='A',away_code='B',neutral_site=False,
            margin=float(i%7),prior_rest_difference=0.) for i in range(20)]
        with patch.dict(POLICY,minimum_training_games=5):
            a=fit(rows,'2026-09-15T12:00:00Z');changed=copy.deepcopy(rows)
            for r in changed:
                if r not in prior_games(rows,'2026-09-15T12:00:00Z'):r['margin']=999.
            b=fit(changed,'2026-09-15T12:00:00Z');self.assertEqual(a,b)
            self.assertNotIn('13',a['training_ids'])
    def test_stale_and_future_quote(self):
        age,fresh=price_age('2026-10-18T10:00:00Z','2026-10-18T10:05:00Z','2026-10-18T10:05:01Z','2026-10-18T13:00:00Z')
        self.assertFalse(fresh);self.assertEqual(age,301)
        with self.assertRaisesRegex(ValueError,'ORDER'):price_age('2026-10-18T10:06:00Z','2026-10-18T10:05:00Z','2026-10-18T10:05:01Z','2026-10-18T13:00:00Z')
    def test_stale_candidate_does_not_rank(self):
        self.assertEqual(rankings([dict(research_rank_eligible=True,price_fresh=False,conditional_model_ev=.5)]),[])

class BudgetIntegrity(unittest.TestCase):
    def test_wave_allocation_and_explicit_deferred_game(self):
        at=datetime.now(timezone.utc);future=(at+timedelta(days=2)).isoformat();requests=[]
        games=[dict(event_id=f'g{i}',identity_verified=True,home_team=f'H{i}',away_team=f'A{i}',kickoff=future) for i in range(3)]
        events=[dict(id=f'o{i}',home_team=f'H{i}',away_team=f'A{i}',commence_time=future) for i in range(3)]
        def transport(url,headers):
            p=urlparse(url);q=parse_qs(p.query);requests.append((p.path,q.get('markets')))
            if p.path.endswith('/events'):body=events;cost=0
            elif '/events/' in p.path:
                # Partial/empty bookmaker coverage still completes this event's attempt.
                body=dict(next(e for e in events if '/'+e['id']+'/' in p.path),sport_key='americanfootball_nfl',bookmakers=[]);cost=1
            else:body=events;cost=3
            return SimpleNamespace(status=200,body=json.dumps(body).encode(),fetched_at=datetime.now(timezone.utc).isoformat(),
                quota={'x-requests-last':cost,'x-requests-remaining':100-sum(3 if '/events/' not in x and x.endswith('/odds') else 1 if '/events/' in x else 0 for x,_ in requests)})
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,THE_ODDS_API_KEY='fixture-value'):
            r=collect_nfl_slate(d,games,daily_credit_cap=5,reserve_credits=50,transport=transport)
            self.assertEqual(len(r['events']),3);self.assertEqual(r['quota']['credits_used'],5)
            self.assertEqual(r['events']['g2']['attempts']['player_receptions']['status'],'BUDGET_DEFERRED')
            self.assertTrue(all(x['deferred_markets'] for x in r['events'].values()))
            prop_calls=[p for p,_ in requests if '/events/' in p];self.assertEqual(len(prop_calls),2)
            self.assertIn('/o1/',prop_calls[1])
    def test_event_snapshot_deduplicated(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data/evaluations';p.mkdir(parents=True)
            r=dict(status=200,snapshot_id='one');(p/'nfl-slate-price-access.json').write_text(json.dumps({'events':{'g':{'records':{'a':r,'b':r}}}}))
            self.assertEqual(len(event_price_records(d,'NFL',dict(event_id='g'))),1)

if __name__=='__main__':unittest.main()
