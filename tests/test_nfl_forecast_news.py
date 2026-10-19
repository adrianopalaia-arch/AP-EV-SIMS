import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from pathlib import Path

from ap_evsims.integrity import digest
from ap_evsims.nfl_forecast_news import interpret_nfl, player_context, game_context, revise_prop
from ap_evsims.nfl_game_model import freeze
from ap_evsims.prop_prospective import freeze_prop
from ap_evsims.prop_market_research import comparison
from ap_evsims.research_store import ResearchStore
from tests.test_prop_market_research import inputs
from tests.test_nfl_sweep import schedule_fixture
from ap_evsims.nfl_schedule import reconcile


AT = '2026-10-17T12:00:00+00:00'
LATER = '2026-10-17T13:00:00+00:00'


def example(status=None, official=False):
    f, q, _, e = inputs()
    f.update(sport='NFL', generated_at='2026-10-17T10:00:00Z',
        model_status='UNVALIDATED', recommendations_enabled=False, calibrated_probability=None,
        p_low=None, pass_reasons=['MODEL_NOT_CALIBRATED'])
    q.update(sport='NFL', quote_timestamp=AT, captured_at=AT)
    person = dict(sport='NFL', event_id=f['event_id'], event_start=f['event_start'],
        player_id=f['player_id'], player_name=f['player_name'], team_id=f['team_id'],
        position='QB', available_at=AT, source_manifest='a'*64, source_hash='b'*64,
        availability_state='UNKNOWN', reasons=[], injury_evidence=[],
        roster_membership_verified=True, roster_status='active', role_confirmed=False,
        roster_source=dict(manifest_id='c'*64, hash='d'*64, captured_at=AT))
    if status:
        person['injury_evidence'] = [dict(event_id=f['event_id'], event_start=f['event_start'],
            player_id=f['player_id'], team_id=f['team_id'], status=status, observed_at=AT,
            available_at=AT, source_manifest='a'*64, source_hash='b'*64, usable=True, reason=None,
            source_kind='GAME_STATUS' if official else 'EVENT_INJURY_REPORT',
            source_authority='LEAGUE_OFFICIAL' if official else 'SECONDARY_AGGREGATOR')]
    return f, q, person, e


def snapshot(f, person):
    news = dict(event=dict(event_id=f['event_id'], event_start=f['event_start']),
        latest_source_capture=person['available_at'], records=[person])
    news['snapshot_hash'] = digest(news)
    return news


class NewsPolicyTests(unittest.TestCase):
    def test_active_roster_is_not_confirmed_game_active(self):
        f, _, a, _ = example()
        c = player_context(f, a, AT)
        self.assertEqual(c['availability_state'], 'UNKNOWN')
        self.assertFalse(c['scoring_recommendation_eligible'])

    def test_confirmed_active_does_not_guarantee_workload(self):
        f, _, a, _ = example('Active', True)
        c = player_context(f, a, AT)
        self.assertEqual(c['availability_state'], 'CONFIRMED_ACTIVE')
        self.assertFalse(c['role_confirmed'])
        self.assertIsNone(c['eligible_projected_opportunity'])
        self.assertEqual(c['baseline_projected_opportunity'], 25)

    def test_questionable_out_active_and_unknown_are_distinct(self):
        observed = []
        for value in (None, 'Questionable', 'Out', 'Active'):
            f, _, a, _ = example(value, True)
            observed.append(player_context(f, a, AT)['availability_state'])
        self.assertEqual(observed, ['UNKNOWN', 'QUESTIONABLE', 'CONFIRMED_OUT', 'CONFIRMED_ACTIVE'])

    def test_secondary_out_not_claimed_officially_confirmed(self):
        f, _, a, _ = example('Out')
        self.assertEqual(player_context(f, a, AT)['availability_state'], 'REPORTED_OUT')

    def test_caller_state_and_role_flags_do_not_authorize(self):
        f, _, a, _ = example()
        a.update(availability_state='CONFIRMED_ACTIVE', role_confirmed=True, confirmed_starter=True)
        c = player_context(f, a, AT)
        self.assertEqual(c['availability_state'], 'UNKNOWN')
        self.assertFalse(c['scoring_recommendation_eligible'])

    def test_out_player_has_no_eligible_scoring_ev(self):
        f, q, a, e = example('Out', True)
        for c in comparison(f, q, a, e, AT):
            self.assertIsNone(c['raw_model_outcome_mass'])
            self.assertIsNone(c['conditional_model_ev'])
            self.assertFalse(c['research_rank_eligible'])
            self.assertIn('PLAYER_REPORTED_OUT', c['pass_reasons'])

    def test_news_after_original_applies_to_price_comparison(self):
        f, q, a, e = example('Out')
        self.assertLess(f['generated_at'], a['available_at'])
        c = comparison(f, q, a, e, AT)[0]
        self.assertIsNone(c['conditional_model_ev'])

    def test_injury_event_start_and_embedded_identity_rejected(self):
        for key,value in (('event_id','OTHER'),('team_id','OTHER'),('player_id','OTHER'),('event_start','2026-10-21T19:00:00Z')):
            f,_,a,_=example('Out')
            a['injury_evidence'][0][key]=value
            with self.assertRaisesRegex(ValueError,'IDENTITY'):
                player_context(f,a,AT)

    def test_missing_injury_provenance_is_not_confirmation(self):
        f,_,a,_=example('Active',True)
        a['injury_evidence'][0].pop('source_hash')
        c=player_context(f,a,AT)
        self.assertEqual(c['availability_state'],'UNKNOWN')
        self.assertIn('INJURY_PROVENANCE_UNVERIFIED',c['reasons'])

    def test_team_change_blocks_historical_workload(self):
        f, q, a, e = example('Active', True)
        f['projection']['last_team_id'] = 'TRADED_FROM'
        c = comparison(f, q, a, e, AT)[0]
        self.assertIn('TEAM_CHANGE_ROLE_UNVERIFIED', c['pass_reasons'])
        self.assertIsNone(c['conditional_model_ev'])

    def test_cross_game_player_team_identity_rejected(self):
        for key in ('player_id', 'event_id', 'team_id'):
            f, _, a, _ = example('Out')
            a[key] = 'OTHER'
            with self.assertRaisesRegex(ValueError, 'MISMATCH'):
                player_context(f, a, AT)

    def test_future_injury_cannot_rewrite_earlier_forecast(self):
        for key in ('observed_at', 'available_at'):
            f, _, a, _ = example('Out')
            a['injury_evidence'][0][key] = LATER
            with self.assertRaisesRegex(ValueError, 'LOOKAHEAD'):
                player_context(f, a, AT)

    def test_stale_report_and_snapshot_cannot_establish_active(self):
        f, _, a, _ = example('Active', True)
        a['injury_evidence'][0]['observed_at'] = '2026-10-10T12:00:00Z'
        c = player_context(f, a, AT)
        self.assertEqual(c['availability_state'], 'UNKNOWN')
        self.assertIn('STALE_INJURY_REPORT', c['reasons'])
        f, _, a, _ = example('Active', True)
        c = player_context(f, a, '2026-10-18T12:00:00Z')
        self.assertEqual(c['availability_state'], 'UNKNOWN')
        self.assertIn('STALE_AVAILABILITY_SNAPSHOT', c['reasons'])

    def test_confirmed_starter_out_retains_game_mean_no_invented_adjustment(self):
        f, _, a, _ = example('Out', True)
        a['injury_evidence'][0]['confirmed_starter'] = True
        g = dict(event_id=f['event_id'], event_start=f['event_start'], home_code='A', away_code='B')
        context = game_context(g, snapshot(f, a), AT)
        self.assertIn('STARTING_QB_OUT', context['reasons'])
        self.assertIn('QB_REPLACEMENT_MODEL_UNAVAILABLE', context['reasons'])
        self.assertFalse(context['adjustment_applied'])
        self.assertTrue(context['baseline_retained'])

    def test_game_freeze_consumes_news_and_preserves_original(self):
        r, e = schedule_fixture()
        g = reconcile([r], {'events':[e]}, '2026-10-18')[0]
        g['schedule_available_at'] = '2026-10-17T09:00:00Z'
        art = dict(model=dict(teams=['HOU','JAX'], coefficients=[0,0,2,0],data_cutoff='2026-10-10T17:00:00Z'),
            residual_sd=12.,latest_source_capture='2026-10-17T09:00:00Z',generated_at='2026-10-17T10:00:00Z',source_manifest='x',source_hash='y')
        f, _, a, _ = example('Out', True)
        f.update(event_id=g['event_id'], event_start=g['event_start'], team_id='JAX')
        a.update(event_id=g['event_id'], event_start=g['event_start'], team_id='JAX')
        a['injury_evidence'][0].update(event_id=g['event_id'],event_start=g['event_start'],team_id='JAX',confirmed_starter=True)
        with tempfile.TemporaryDirectory() as d:
            ResearchStore(Path(d)/'data')
            old = freeze(d,g,art,digest(art),[],AT)
            path = Path(d)/'data/predictions/nfl-games'/(old['forecast_hash']+'.json')
            raw = path.read_bytes()
            new = freeze(d,g,art,digest(art),[],LATER,availability=snapshot(f,a))
            self.assertEqual(raw,path.read_bytes())
            self.assertEqual(old['projected_home_margin'],new['projected_home_margin'])
            self.assertEqual(new['parent_forecast_hash'],old['forecast_hash'])
            self.assertIn('STARTING_QB_OUT',new['pass_reasons'])

    def test_append_prop_revision_preserves_frozen_projection_and_bytes(self):
        f, _, a, _ = example('Out')
        f.pop('forecast_hash')
        with tempfile.TemporaryDirectory() as d:
            store = ResearchStore(d)
            original, _ = freeze_prop(store,f)
            file = next((store.root/'predictions/props').glob('*.json')); raw = file.read_bytes()
            new = revise_prop(store,original,a,snapshot(f,a),AT)
            self.assertEqual(new['projection'],original['projection'])
            self.assertEqual(new['parent_forecast_hash'],original['forecast_hash'])
            self.assertEqual(raw,file.read_bytes())
            self.assertIn('PLAYER_REPORTED_OUT',new['revision_reasons'])
            self.assertFalse(new['scoring_recommendation_eligible'])
            self.assertIsNone(new['eligible_projected_opportunity'])
            self.assertEqual(len(list((store.root/'predictions/news').rglob('*.json'))),1)
            same=revise_prop(store,original,a,snapshot(f,a),AT)
            self.assertEqual(same['forecast_hash'],new['forecast_hash'])
            a2=copy.deepcopy(a);a2['available_at']=LATER
            newer=revise_prop(store,original,a2,snapshot(f,a2),LATER)
            self.assertEqual(newer['parent_forecast_hash'],new['forecast_hash'])
            self.assertEqual(newer['original_forecast_hash'],original['forecast_hash'])
            self.assertEqual(raw,file.read_bytes())

    def test_revisions_cannot_be_backdated_after_kickoff(self):
        f, _, a, _ = example('Out');f['forecast_hash']=digest({k:v for k,v in f.items() if k!='forecast_hash'})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'PREGAME'):
                revise_prop(ResearchStore(d),f,a,snapshot(f,a),f['event_start'])

    def test_policy_refresh_keeps_one_numerical_settlement_cohort(self):
        from ap_evsims.prop_market_research import freeze_comparison
        from ap_evsims.prop_price_evidence import first_comparisons
        f,q,a,e=example('Active',True);f.pop('forecast_hash')
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);original,_=freeze_prop(s,f)
            first=freeze_comparison(s,comparison(original,q,a,e,AT)[0])
            revision=revise_prop(s,original,a,snapshot(f,a),LATER)
            second=freeze_comparison(s,comparison(revision,q,a,e,LATER)[0])
            self.assertEqual(second['forecast_hash'],original['forecast_hash'])
            self.assertEqual(second['availability_revision_hash'],revision['forecast_hash'])
            self.assertEqual(len(first_comparisons([first,second])),1)

    def test_delivery_explicitly_withdraws_player_removed_from_current_roster(self):
        from ap_evsims.challenger_delivery import run,VERSION
        now=datetime.now(timezone.utc);early=(now-timedelta(hours=2)).isoformat();news_at=(now-timedelta(hours=1)).isoformat()
        f,_,_,_=example();f.pop('forecast_hash')
        f.update(model_version=VERSION,generated_at=early,latest_source_capture=early,event_start=(now+timedelta(days=2)).isoformat(),role_confirmed=False)
        event=dict(event_id=f['event_id'],event_start=f['event_start'])
        news=dict(event=event,latest_source_capture=news_at,identities=[],records=[],event_identity_reasons=[])
        news['snapshot_hash']=digest(news)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);store=ResearchStore(root/'data');old,_=freeze_prop(store,f)
            (root/'outputs').mkdir();(root/'outputs/nfl_challenger_status.json').write_text(json.dumps(dict(markets={})))
            with patch('ap_evsims.challenger_delivery.event_price_records',return_value=[]):
                result=run(root,'NFL',simulate_forecasts=False,canonical_event=event,availability_record=news)
            self.assertEqual(result['frozen_forecasts'],1)
            self.assertEqual(result['predictions'][0]['original_forecast_hash'],old['forecast_hash'])
            self.assertIn('PLAYER_NOT_ON_VERIFIED_CURRENT_ROSTER',result['predictions'][0]['pass_reasons'])
            self.assertEqual(result['new_frozen'],0)

    def test_missing_current_roster_player_blocks(self):
        f, _, _, _ = example()
        c = player_context(f,None,AT)
        self.assertIn('PLAYER_NOT_ON_VERIFIED_CURRENT_ROSTER',c['reasons'])
        self.assertFalse(c['scoring_recommendation_eligible'])

    def test_tampered_news_hash_rejected(self):
        f, _, a, _ = example(); n = snapshot(f,a);n['records'][0]['position']='RB'
        with self.assertRaisesRegex(ValueError,'HASH'):
            game_context(dict(event_id=f['event_id'],event_start=f['event_start'],home_code='A',away_code='B'),n,AT)

    def test_record_not_bound_to_snapshot_rejected(self):
        f,_,a,_=example('Out');f['forecast_hash']=digest({k:v for k,v in f.items() if k!='forecast_hash'})
        news=snapshot(f,a);news['records']=[];news['snapshot_hash']=digest({k:v for k,v in news.items() if k!='snapshot_hash'})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'NOT_IN_SNAPSHOT'):
                revise_prop(ResearchStore(d),f,a,news,AT)

    def test_calibration_replay_does_not_fit_or_invent_observations(self):
        from ap_evsims.nfl_news_replay import calibration
        rows=[dict(margin=m,ridge=dict(p_home_win=p)) for m,p in ((1,.8),(-1,.2),(0,.5))]
        c=calibration(rows,'ridge')
        self.assertEqual(c['non_tie_n'],2)
        self.assertEqual(sum(b['n'] for b in c['bins']),2)
        self.assertAlmostEqual(c['expected_calibration_error'],.2)
        self.assertFalse(c['calibrated_probability_fitted'])


class SourceBindingTests(unittest.TestCase):
    def setup_source(self):
        r,e = schedule_fixture();g = reconcile([r],{'events':[e]},'2026-10-18')[0]
        e['competitions'][0]['date']=e['date']
        m=dict(manifest_id='a'*64,hash='b'*64,captured_at=AT)
        p=dict(player_id='gsis1',provider_player_id='espn1',name='Fixture QB',team_id='JAX',position='QB',status='active',
            injuries=[dict(status='Out',date='2026-10-17T11:00:00Z')],roster_source=dict(m,manifest_id='c'*64))
        payload=dict(header=e,injuries=[])
        return g,p,payload,m

    def test_roster_news_retains_actual_roster_source_not_summary_time(self):
        g,p,payload,m=self.setup_source()
        p['roster_source']['captured_at']='2026-10-17T11:30:00Z'
        row=interpret_nfl(g,[p],payload,m)[0]
        self.assertEqual(row['availability_state'],'REPORTED_OUT')
        evidence=row['injury_evidence'][0]
        self.assertEqual(evidence['available_at'],'2026-10-17T11:30:00Z')
        self.assertEqual(evidence['source_manifest'],'c'*64)

    def test_summary_wrong_team_player_rejected(self):
        g,p,payload,m=self.setup_source()
        payload['injuries']=[dict(team=dict(id='34'),injuries=[dict(athlete=dict(id='espn1'),status='Out',date=AT)])]
        with self.assertRaisesRegex(ValueError,'TEAM_MISMATCH'):
            interpret_nfl(g,[p],payload,m)

    def test_undated_and_stale_reports_are_not_current_out_evidence(self):
        for stamp in (None,'2026-08-01T00:00:00Z'):
            g,p,payload,m=self.setup_source();p['injuries'][0]['date']=stamp
            row=interpret_nfl(g,[p],payload,m)[0]
            self.assertEqual(row['availability_state'],'UNKNOWN')
            self.assertFalse(row['injury_evidence'][0]['usable'])

    def test_duplicate_player_across_rosters_rejected(self):
        g,p,payload,m=self.setup_source()
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            interpret_nfl(g,[p,dict(p,team_id='HOU')],payload,m)

    def test_conflicting_same_time_reports_do_not_claim_confirmation(self):
        g,p,payload,m=self.setup_source()
        p['injuries']=[dict(status=s,date=AT) for s in ('Out','Active')]
        row=interpret_nfl(g,[p],payload,m)[0]
        self.assertEqual(row['availability_state'],'UNKNOWN')
        self.assertIn('CONFLICTING_AVAILABILITY_REPORTS',row['reasons'])


if __name__=='__main__':unittest.main()
