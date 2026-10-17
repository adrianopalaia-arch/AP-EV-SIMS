import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from ap_evsims.integrity import digest
from ap_evsims.research_store import ResearchStore
from ap_evsims.prop_market_research import benchmark_gate,comparison,freeze_comparison
from ap_evsims.prop_availability import injury_evidence,interpret
from ap_evsims.prop_prices import collect_priority
from ap_evsims.providers.validation import ProviderValidator
from ap_evsims.prop_settlement import cohort_metrics


def inputs():
    f=dict(sport='NBA',market='rebounds',event_id='1',event_start='2026-10-20T19:00:00Z',player_id='p',player_name='Player',team_id='A',
        model_version='test',artifact_hash='a'*64,forecast_hash='f'*64,generated_at='2026-10-16T00:00:00Z',latest_source_capture='2026-10-15T00:00:00Z',
        event_mapping=dict(odds_event_id='o',home_team='Home',away_team='Away'),
        projection=dict(last_team_id='A',projection=5,projected_opportunity=25,distribution={'3':.2,'5':.3,'7':.5}))
    q=dict(sport='NBA',market='rebounds',odds_event_id='o',event_start=f['event_start'],home_team='Home',away_team='Away',
        period='full_game',line=5,book='draftkings',over_odds=-110,under_odds=-110,over_no_vig=.5,probability_basis='conditional_on_non_push',
        quote_timestamp='2026-10-16T01:00:00Z',captured_at='2026-10-16T01:00:01Z',quote_id='q',snapshot_id='s'*64,payload_hash='h'*64,player_name='Player')
    a=dict(sport='NBA',event_id='1',event_start=f['event_start'],player_id='p',team_id='A',available_at='2026-10-16T00:59:00Z',availability_state='UNKNOWN',reasons=['ROLE_NOT_CONFIRMED'])
    e=dict(artifact_hash='a'*64,admission='RESEARCH_BENCHMARK_ADVANTAGE')
    return f,q,a,e


class MarketResearchTests(unittest.TestCase):
    def test_two_sides_keep_push_mass(self):
        f,q,a,e=inputs();over,under=comparison(f,q,a,e,'2026-10-16T01:01:00Z')
        self.assertAlmostEqual(over['raw_model_outcome_mass']['p_push'],.3)
        self.assertAlmostEqual(under['raw_model_outcome_mass']['p_push'],.3)
        self.assertAlmostEqual(over['conditional_model_ev'],.5/1.1-.2)
        self.assertEqual(over['decision'],'PASS');self.assertIsNone(over['p_low'])
    def test_mismatch_cannot_attach_probability(self):
        f,q,a,e=inputs();q['event_start']='2026-10-20T19:10:00Z'
        r=comparison(f,q,a,e,'2026-10-16T01:01:00Z')[0]
        self.assertIsNone(r['raw_model_outcome_mass']);self.assertIsNone(r['conditional_model_ev']);self.assertFalse(r['research_rank_eligible'])
    def test_wrong_event_period_player_model_reject(self):
        for location,field,value in [(1,'odds_event_id','other'),(1,'period','first_half'),(2,'player_id','other'),(3,'artifact_hash','b'*64)]:
            values=list(inputs());values[location][field]=value
            with self.assertRaises(ValueError):comparison(*values,'2026-10-16T01:01:00Z')
    def test_news_or_quote_from_future_reject(self):
        for location,field in [(1,'captured_at'),(2,'available_at'),(0,'generated_at')]:
            v=list(inputs());v[location][field]='2026-10-16T02:00:00Z'
            with self.assertRaises(ValueError):comparison(*v,'2026-10-16T01:01:00Z')
    def test_started_game_reject(self):
        with self.assertRaises(ValueError):comparison(*inputs(),'2026-10-20T19:00:00Z')
    def test_new_schedule_revision_blocks_old_forecast(self):
        f,q,a,e=inputs();a['event_start']='2026-10-20T18:00:00Z'
        with self.assertRaisesRegex(ValueError,'SCHEDULE'):comparison(f,q,a,e,'2026-10-16T01:01:00Z')
    def test_quote_cannot_be_newer_than_capture(self):
        f,q,a,e=inputs();q['captured_at']='2026-10-16T00:59:59Z'
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):comparison(f,q,a,e,'2026-10-16T01:01:00Z')
    def test_stale_research_retains_math_but_no_execution(self):
        r=comparison(*inputs(),'2026-10-16T02:00:00Z')[0]
        self.assertIsNotNone(r['conditional_model_ev']);self.assertIn('STALE_PRICE',r['pass_reasons']);self.assertFalse(r['price_fresh']);self.assertFalse(r['recommendations_enabled'])
    def test_reported_out_and_team_change_excluded(self):
        for changed in ('out','team'):
            f,q,a,e=inputs()
            if changed=='out':a['availability_state']='REPORTED_UNAVAILABLE'
            else:f['projection']['last_team_id']='B'
            self.assertFalse(comparison(f,q,a,e,'2026-10-16T01:01:00Z')[0]['research_rank_eligible'])
    def test_failed_benchmark_never_ranks_even_positive_ev(self):
        f,q,a,e=inputs();e['admission']='FAILED_SIMPLE_BASELINE'
        r=comparison(f,q,a,e,'2026-10-16T01:01:00Z')[0]
        self.assertGreater(r['conditional_model_ev'],0);self.assertFalse(r['research_rank_eligible'])
    def test_peer_must_have_exact_line_and_time(self):
        f,q,a,e=inputs();peer=dict(q,book='fanduel',line=5.5)
        self.assertFalse(comparison(f,q,a,e,'2026-10-16T01:01:00Z',[peer])[0]['descriptive_other_books'])
        peer['line']=5;peer['quote_timestamp']='2026-10-16T00:00:00Z'
        self.assertFalse(comparison(f,q,a,e,'2026-10-16T01:01:00Z',[peer])[0]['descriptive_other_books'])
    def test_freeze_updates_preserve_parent_and_first_record(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);r=comparison(*inputs(),'2026-10-16T01:01:00Z')[0];first=freeze_comparison(s,r)
            later=copy.deepcopy(r);later['decision_timestamp']='2026-10-16T02:00:00Z';later['pass_reasons'].append('STALE_PRICE')
            second=freeze_comparison(s,later,first['comparison_hash'])
            self.assertNotEqual(first['comparison_hash'],second['comparison_hash']);self.assertEqual(second['parent_comparison_hash'],first['comparison_hash'])
            self.assertEqual(len(list((s.root/'predictions/market-research').glob('*.json'))),2)
    def test_freeze_blocks_confidence_escalation(self):
        with tempfile.TemporaryDirectory() as d:
            for update in ({'recommendations_enabled':True},{'p_low':.7},{'calibrated_probability':.8},{'decision':'CORE'}):
                r=comparison(*inputs(),'2026-10-16T01:01:00Z')[0];r.update(update)
                with self.assertRaises(ValueError):freeze_comparison(ResearchStore(d),r)
    def test_benchmark_evidence_rejects_worse_or_uncertain_model(self):
        e=dict(n=100,mae=1,rmse=2,baseline_mae=1.1,baseline_rmse=2.1,paired_mae_difference_95_week_bootstrap=[-.2,-.01])
        self.assertEqual(benchmark_gate(e),'RESEARCH_BENCHMARK_ADVANTAGE')
        self.assertEqual(benchmark_gate(dict(e,mae=1.2)),'FAILED_SIMPLE_BASELINE')
        self.assertEqual(benchmark_gate(dict(e,paired_mae_difference_95_week_bootstrap=[-.2,.01])),'BENCHMARK_ADVANTAGE_INCONCLUSIVE')
    def test_reference_and_model_settlement_cannot_be_pooled(self):
        r=dict(model_version='model',market='receptions',absolute_error=2,squared_error=4,baseline_absolute_error=1,crps=1,artifact_hash='a')
        groups=cohort_metrics([r,dict(r,model_version='reference',absolute_error=1,squared_error=1)],[])
        self.assertEqual(len(groups),2);self.assertEqual([g['mae'] for g in groups],[2,1])
    def test_different_market_units_are_separate(self):
        rows=[dict(model_version='same',market=m,absolute_error=e,squared_error=e*e,baseline_absolute_error=e,crps=e,artifact_hash='a') for m,e in [('receptions',1),('receiving_yards',20)]]
        self.assertEqual(len(cohort_metrics(rows,[])),2)


class AvailabilityTests(unittest.TestCase):
    def test_future_injury_date_never_usable(self):
        r=injury_evidence([dict(status='Out',date='2026-10-17T00:00:00Z')],'2026-10-16T00:00:00Z')
        self.assertFalse(r[0]['usable']);self.assertEqual(r[0]['reason'],'LOOKAHEAD_RISK')
    def test_empty_injuries_do_not_confirm_health_or_starter(self):
        event=dict(event_id='1',event_start='2026-10-17T01:00:00Z');p=dict(player_id='G',name='Goalie',team_id='A',position='G',injuries=[])
        m=dict(captured_at='2026-10-16T00:00:00Z',manifest_id='a'*64,hash='b'*64)
        payload=dict(id=1,startTimeUTC=event['event_start'],gameType=2,matchup={'goalieComparison':{'leaders':['G']}})
        r=interpret('NHL',event,[p],payload,m)[0]
        self.assertIsNone(r['confirmed_starter']);self.assertFalse(r['role_confirmed']);self.assertIn('STARTING_GOALIE_NOT_CONFIRMED',r['reasons'])
    def test_mlb_requires_complete_unique_batting_order(self):
        event=dict(event_id='1',event_start='2026-10-17T01:00:00Z',home_team='Home',away_team='Away')
        p=dict(player_id='1',name='Hitter',team_id='A',position='OF',injuries=None)
        m=dict(captured_at='2026-10-16T00:00:00Z',manifest_id='a'*64,hash='b'*64)
        payload={'teams':{'home':{'team':{'id':'A','name':'Home'},'battingOrder':[1]},'away':{'team':{'id':'B','name':'Away'}}}}
        self.assertFalse(interpret('MLB',event,[p],payload,m)[0]['role_confirmed'])
        payload['teams']['home']['battingOrder']=list(range(1,10))
        self.assertTrue(interpret('MLB',event,[p],payload,m)[0]['role_confirmed'])


class PriorityCollectionTests(unittest.TestCase):
    def test_cooldown_checks_do_not_restart_the_request_clock(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(Path(d)/'data');at=datetime.now(timezone.utc).isoformat()
            old={'sport':'NBA','record':{'status':200,'checked_at':'2020-01-01T00:00:00Z'},'latest_attempt':{'status':'REFRESH_COOLDOWN','checked_at':at}}
            (s.root/'evaluations/prop-price-access.json').write_text(json.dumps({'sports':[old]}))
            r=collect_priority(d,daily_credit_cap=0,transport=lambda *args: self.fail('Unexpected network request'))
            nba=next(v for v in r['sports'] if v['sport']=='NBA')
            self.assertEqual(nba['latest_attempt']['status'],'DAILY_QUOTA_BUDGET_LIMIT')
            self.assertEqual(nba['last_request_at'],old['record']['checked_at'])
    def test_budget_block_preserves_last_quote_and_event(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(Path(d)/'data');old={'sport':'NBA','event':{'id':'old'},'record':{'status':200,'snapshot_id':'a'*64}}
            (s.root/'evaluations/prop-price-access.json').write_text(json.dumps({'sports':[old]}))
            def blocked(*args):raise AssertionError('Network must not be called with zero allowance')
            r=collect_priority(d,daily_credit_cap=0,transport=blocked)
            nba=next(v for v in r['sports'] if v['sport']=='NBA')
            self.assertEqual(nba['event'],old['event']);self.assertEqual(nba['record'],old['record']);self.assertEqual(nba['latest_attempt']['status'],'DAILY_QUOTA_BUDGET_LIMIT')
    def test_refresh_cooldown_blocks_even_free_event_call(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(Path(d)/'data');at=datetime.now(timezone.utc).isoformat()
            (s.root/'evaluations/prop-price-access.json').write_text(json.dumps({'sports':[{'sport':s,'latest_attempt':{'checked_at':at}} for s in ['NFL','NBA','NHL','MLB']]}))
            def blocked(*args):raise AssertionError('Cooldown bypass')
            r=collect_priority(d,transport=blocked)
            self.assertTrue(all(v['latest_attempt']['status']=='REFRESH_COOLDOWN' for v in r['sports']))
