"""Failure-mode fixtures only; never real performance observations."""
import copy,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ap_evsims.integrity import digest
from ap_evsims.research_store import ResearchStore
from ap_evsims.reliable_results import nhl_result,probability_scores,bands
from ap_evsims.reliable_engine import evidence_policy,current_candidate
from ap_evsims.prop_market_research import independent_prop_consensus,comparison
from ap_evsims.prop_price_evidence import close_for
from ap_evsims.prop_prices import collection_interval,future_research_events,collect_priority
from ap_evsims.reliable_results import paired_event_interval
from ap_evsims.book_rule_evidence import capture as rule_capture
from types import SimpleNamespace
from ap_evsims.reliable_handoff import sync as sync_handoff
from ap_evsims.product import read_card
from test_prop_market_research import inputs
from test_event_price_evidence import priced

AT='2026-10-16T01:01:00Z'

def final_box():
    f=dict(event_id='1',event_start='2026-10-17T17:00:00Z',generated_at='2026-10-16T00:00:00Z',
        player_id='10',player_name='Player',team_id='H',market='shots_on_goal')
    skater=dict(playerId=10,sog=3,toi='12:30')
    p=dict(id=1,startTimeUTC=f['event_start'],gameState='OFF',gameType=2,gameDate='2026-10-17',season=20262027,
        homeTeam={'abbrev':'H'},awayTeam={'abbrev':'A'},playerByGameStats={'homeTeam':{'forwards':[skater],'defense':[],
        'goalies':[dict(playerId=11,saves=29,shotsAgainst=31,toi='60:00')]}})
    m=dict(sport='NHL',url='https://api-web.nhle.com/v1/gamecenter/1/boxscore',manifest_id='a'*64,hash='b'*64,captured_at='2026-10-18T00:00:00Z')
    return f,p,m,'2026-10-18T01:00:00Z'

class OfficialResultTests(unittest.TestCase):
    def test_official_shots_and_ice_time(self):
        row=nhl_result(*final_box());self.assertEqual(row.outcome,3);self.assertEqual(row.opportunity,12.5)
    def test_goalie_opportunity_is_shots_faced(self):
        f,p,m,at=final_box();f.update(market='goalie_saves',player_id='11');r=nhl_result(f,p,m,at)
        self.assertEqual((r.outcome,r.opportunity),(29,31))
    def test_dnp_is_not_zero(self):
        f,p,m,at=final_box();p['playerByGameStats']['homeTeam']['forwards'][0]['toi']='00:00'
        with self.assertRaisesRegex(ValueError,'DID_NOT_PARTICIPATE'):nhl_result(f,p,m,at)
    def test_missing_or_duplicate_player_rejects(self):
        for rows in ([],[dict(playerId=10,sog=3,toi='12:00')]*2):
            f,p,m,at=final_box();p['playerByGameStats']['homeTeam']['forwards']=rows
            with self.assertRaisesRegex(ValueError,'PARTICIPATION'):nhl_result(f,p,m,at)
    def test_non_final_and_wrong_competition_reject(self):
        for update in ({'gameState':'LIVE'},{'gameType':3}):
            f,p,m,at=final_box();p.update(update)
            with self.assertRaisesRegex(ValueError,'FINAL_OR_MODEL_DOMAIN'):nhl_result(f,p,m,at)
    def test_schedule_revision_and_wrong_event_reject(self):
        for update in ({'id':2},{'startTimeUTC':'2026-10-17T18:00:00Z'}):
            f,p,m,at=final_box();p.update(update)
            with self.assertRaisesRegex(ValueError,'EVENT_START'):nhl_result(f,p,m,at)
    def test_source_identity_rejects(self):
        f,p,m,at=final_box();m['url']='https://example.com/boxscore'
        with self.assertRaisesRegex(ValueError,'SOURCE_IDENTITY'):nhl_result(f,p,m,at)
    def test_result_or_prediction_lookahead_rejects(self):
        for changed in ('prediction','result'):
            f,p,m,at=final_box()
            if changed=='prediction':f['generated_at']=f['event_start']
            else:m['captured_at']='2026-10-18T02:00:00Z'
            with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):nhl_result(f,p,m,at)
    def test_wrong_team_rejects(self):
        f,p,m,at=final_box();f['team_id']='X'
        with self.assertRaisesRegex(ValueError,'TEAM_MISMATCH'):nhl_result(f,p,m,at)
    def test_same_day_conservative_finality_guard_preserved(self):
        f,p,m,at=final_box();m['captured_at']='2026-10-17T23:00:00Z'
        with self.assertRaisesRegex(ValueError,'NOT_FINAL_BEFORE_CAPTURE'):nhl_result(f,p,m,at)

class IndependentConsensusTests(unittest.TestCase):
    def test_entry_book_excluded_and_two_independent_books_required(self):
        _,q,_,_=inputs();fd=dict(q,book='fanduel',over_no_vig=.4);mgm=dict(q,book='betmgm',over_no_vig=.6)
        self.assertIsNone(independent_prop_consensus(q,[q,fd,fd],AT,'Over')['probability'])
        result=independent_prop_consensus(q,[q,fd,mgm],AT,'Over')
        self.assertEqual(result['book_count'],2);self.assertAlmostEqual(result['probability'],.5)
    def test_exact_identity_period_line_time_required(self):
        _,q,_,_=inputs();fd=dict(q,book='fanduel');mgm=dict(q,book='betmgm')
        for change in ({'line':5.5},{'period':'half'},{'market':'assists'},{'odds_event_id':'wrong'},
                       {'player_name':'Other'},{'event_start':'2026-10-20T20:00:00Z'},
                       {'quote_timestamp':'2026-10-16T00:58:00Z'},{'captured_at':'2026-10-16T01:02:00Z'}):
            self.assertIsNone(independent_prop_consensus(q,[fd,dict(mgm,**change)],AT,'Over')['probability'])
    def test_under_is_complement_and_conflicting_quotes_fail(self):
        _,q,_,_=inputs();fd=dict(q,book='fanduel',over_no_vig=.2);mgm=dict(q,book='betmgm',over_no_vig=.4)
        self.assertAlmostEqual(independent_prop_consensus(q,[fd,mgm],AT,'Under')['probability'],.7)
        self.assertEqual(independent_prop_consensus(q,[fd,dict(fd,over_no_vig=.6),mgm],AT,'Over')['reason'],'CONFLICTING_BOOK_QUOTES')
    def test_large_disagreement_investigated_not_promoted(self):
        f,q,a,e=inputs();peers=[dict(q,book=b,over_no_vig=.2) for b in ('fanduel','betmgm')]
        r=comparison(f,q,a,e,AT,peers)[0]
        self.assertIn('MODEL_MARKET_DISAGREEMENT',r['pass_reasons']);self.assertFalse(r['research_rank_eligible'])
        self.assertEqual(r['decision'],'PASS');self.assertIsNone(r['p_low'])

class ClosingIntegrityTests(unittest.TestCase):
    def close_inputs(self):
        _,c,_,q=priced();c['odds_event_id']='o';q.update(provider_market='player_rebounds',quote_timestamp='2026-10-20T18:59:00Z',captured_at='2026-10-20T18:59:10Z')
        return c,q
    def test_latest_changed_line_invalidates_old_exact_line(self):
        c,q=self.close_inputs();new=dict(q,line=5.5,quote_timestamp='2026-10-20T18:59:20Z',captured_at='2026-10-20T18:59:30Z')
        self.assertIsNone(close_for(c,[q,new],'2026-10-21T00:00:00Z'))
    def test_empty_later_market_snapshot_invalidates_close(self):
        c,q=self.close_inputs();snap=dict(odds_event_id='o',captured_at='2026-10-20T18:59:40Z',markets=['player_rebounds'],books=['draftkings'])
        self.assertIsNone(close_for(c,[q],'2026-10-21T00:00:00Z',captures=[snap]))
        snap['captured_at']='2026-10-20T19:00:01Z'
        self.assertEqual(close_for(c,[q],'2026-10-21T00:00:00Z',captures=[snap]),q)
    def test_other_market_snapshot_does_not_erase_close(self):
        c,q=self.close_inputs();snap=dict(odds_event_id='o',captured_at='2026-10-20T18:59:40Z',markets=['player_assists'],books=['draftkings'])
        self.assertEqual(close_for(c,[q],'2026-10-21T00:00:00Z',captures=[snap]),q)

class PolicyAndFreshnessTests(unittest.TestCase):
    def test_handoff_updates_real_counts_without_validation_escalation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ResearchStore(root/'data');out=root/'outputs';out.mkdir()
            values={'model_status.json':[dict(sport='NHL',market='shots_on_goal',model_version='test')], 'provider_status.json':{}}
            for name,value in values.items():(out/name).write_text(json.dumps(value))
            (out/'last_update.json').write_text(json.dumps(dict(feed_hashes={n:digest(v) for n,v in values.items()})))
            (out/'reliability_status.json').write_text(json.dumps(dict(generated_at=AT,activity={},quota={})))
            (out/'prospective_settlements.json').write_text(json.dumps(dict(cohorts=[dict(sport='NHL',market='shots_on_goal',model_version='test',n=2)],settled_forecast_observations=2,distinct_games=1,priced_settled_observations=0)))
            for sport in ('nhl','nba','nfl','mlb'):(out/(sport+'_challenger_prospective.json')).write_text(json.dumps(dict(predictions=[])))
            (out/'week_ahead_game_probabilities.json').write_text(json.dumps(dict(game_forecasts=[])))
            (out/'live_research_candidates.json').write_text(json.dumps(dict(candidates=[])))
            sync_handoff(root);summary,feeds=read_card(root)
            self.assertEqual(summary['prospective_distinct_games'],1);self.assertEqual(summary['qualified_edges'],0)
            self.assertEqual(feeds['model_status.json'][0]['prospective_scored_n'],2)
            self.assertFalse(feeds['model_status.json'][0]['betting_validated'])
            (out/'model_status.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):read_card(root)
    def test_paired_uncertainty_counts_games_not_players(self):
        rows=[dict(event_id='one',absolute_error=1,baseline_absolute_error=2)]*100
        self.assertIsNone(paired_event_interval(rows)['interval_95'])
        rows=[dict(event_id=str(i),absolute_error=i%3,baseline_absolute_error=1) for i in range(30)]
        a=paired_event_interval(rows);self.assertEqual(a,paired_event_interval(rows));self.assertEqual(a['event_clusters'],30)
    def test_rule_document_capture_cannot_backdate_or_authorize(self):
        with tempfile.TemporaryDirectory() as d:
            now=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
            r=rule_capture(d,transport=lambda *a:SimpleNamespace(status=200,body=b'Fixture rules',fetched_at=now))
            self.assertFalse(r['settlement_authority']);self.assertTrue(all(x['available_at']==now and not x['historical_backdating_allowed'] for x in r['sources']))
            again=rule_capture(d,transport=lambda *a:self.fail('Unexpected repeat request'))
            self.assertEqual(r['sources'],again['sources'])
            (Path(d)/'data'/r['sources'][0]['path']).write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'HASH'):rule_capture(d)
    def test_policy_immutable_and_future_phases_disjoint(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);p=evidence_policy(s,AT);self.assertEqual(p,evidence_policy(s,'2026-10-18T00:00:00Z'))
            self.assertEqual(p['calibration_end'],p['selection_start']);self.assertEqual(p['selection_end'],p['untouched_holdout_start'])
            self.assertFalse(p['cash_authority']);self.assertFalse(p['automatic_promotion'])
            path=s.root/'evaluations/reliable-evidence-policy.json';p['cash_authority']=True;path.write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError,'CHANGED'):evidence_policy(s,AT)
    def test_republished_old_price_retains_math_not_freshness(self):
        c=comparison(*inputs(),AT)[0];r=current_candidate(c,'2026-10-16T01:04:00Z')
        self.assertIn('STALE_PRICE',r['pass_reasons']);self.assertFalse(r['current_price_fresh'])
        self.assertEqual(r['conditional_model_ev'],c['conditional_model_ev']);self.assertIsNone(r['conservative_ev'])
        self.assertIsNone(r['p_low']);self.assertIsNone(r['rank']);self.assertEqual(r['decision'],'PASS')
    def test_started_event_and_future_quote_fail(self):
        c=comparison(*inputs(),AT)[0]
        self.assertIn('EVENT_STARTED',current_candidate(c,'2026-10-21T00:00:00Z')['pass_reasons'])
        self.assertIn('LOOKAHEAD_RISK',current_candidate(c,'2026-10-16T00:00:00Z')['pass_reasons'])
    def test_probability_scores_reject_nonfinite_values(self):
        for p in (float('nan'),float('inf'),-1,2):
            with self.assertRaises(ValueError):probability_scores(p,1)
        self.assertAlmostEqual(probability_scores(.5,1)['log_loss'],math.log(2))
    def test_calibration_bands_do_not_count_unresolved_results(self):
        result=bands([dict(raw_probability=.5,observed_binary=1),dict(raw_probability=.5,observed_binary=None)])
        self.assertEqual(sum(r['n'] for r in result),1)
    def test_closing_capture_window_admits_last_minute(self):
        self.assertEqual(collection_interval(60),60)
        events=[dict(id='a',commence_time='2026-10-16T01:02:00Z')]
        self.assertEqual(future_research_events(events,AT,minimum_lead_seconds=0),events)
        self.assertEqual(future_research_events(events,AT),[])
    def test_invalid_priority_market_cannot_call_provider(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'PRIORITY'):
                collect_priority(d,priority_markets={'NFL':['imagined']},transport=lambda *a:self.fail('Unexpected network'))

if __name__=='__main__':unittest.main()
