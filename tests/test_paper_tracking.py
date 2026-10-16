"""Constructed mechanics fixtures; never counted as empirical performance."""
from pathlib import Path
import copy,json,tempfile,unittest
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.product import daily_card,research_prediction_rows
from ap_evsims.paper_market import archived_quotes,consensus,closing_evidence
from ap_evsims.paper_tracking import PaperLedger,start_paper,reconcile,report,score_comparison


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=ResearchStore(self.root/'data');self.w=Warehouse(self.s.root)
        self.start='2026-10-14T18:00:00Z';self.at='2026-10-14T10:01:01Z'
        self.game=dict(id=1,homeTeam='Home',awayTeam='Away',homeId=1,awayId=2,season=2026,week=7,homeClassification='fbs',awayClassification='fbs',
            startDate=self.start,startTimeTBD=False,completed=False,homePoints=None,awayPoints=None)
        self.capture('cfbd','games',[self.game],'2026-10-14T09:00:00Z')
        self.capture('cfbd','teams',[dict(id=1,school='Home'),dict(id=2,school='Away')],'2026-10-14T09:00:00Z')
        start_paper(self.root,'2026-10-14T10:00:00Z');self.l=PaperLedger(self.s.root/'predictions/paper-tracking.sqlite')
    def tearDown(self):self.tmp.cleanup()
    def capture(self,provider,endpoint,payload,at):
        m=self.s.archive(provider=provider,endpoint=endpoint,parameters={},body=json.dumps(payload).encode(),fetched_at=at,
            observed_at=at,available_at=at,availability_basis='recorded_response')
        self.w.ingest_manifest(self.s,m)
        if provider=='odds':self.w.record_odds(self.s,m)
        return m
    def prices(self,at='2026-10-14T10:01:00Z',line=3.5,books=('draftkings','fanduel','betmgm'),period='full_game',price=-110):
        event=dict(id='event',sport_key='americanfootball_ncaaf',commence_time=self.start,home_team='Home',away_team='Away',bookmakers=[])
        for b in books:event['bookmakers'].append(dict(key=b,last_update=at,markets=[dict(key='spreads',period=period,outcomes=[
            dict(name='Home',point=line,price=price if b=='draftkings' else -110),dict(name='Away',point=-line,price=-110)])]))
        return self.capture('odds','sports/americanfootball_ncaaf/odds',[event],at)
    def card(self,at=None):return daily_card(self.root,offline=True,now=at or self.at)['paper_tracking']
    def result(self,at='2026-10-14T21:00:00Z',home=24,away=20,completed=True):
        return self.capture('cfbd','games',[dict(self.game,completed=completed,homePoints=home,awayPoints=away)],at)
    def test_freezes_all_sides_one_direction_and_no_cash(self):
        self.prices();r=self.card();self.assertEqual(r['observations_logged'],2);self.assertEqual(r['cohort_candidates'],1)
        o=self.l.observations(cohort=True)[0];self.assertEqual(o['quote']['selection'],'Home');self.assertIsNone(o['opening_price'])
        self.assertIsNotNone(o['first_observed_price']);self.assertIsNone(o['recommended_price']);self.assertEqual(o['cash_committed'],0)
        self.assertEqual(r['reference_unit'],22);self.assertFalse(r['core_enabled']);self.assertIsNone(r['actual_cash_roi'])
        self.assertIsNone(o['model']['calibrated']);self.assertIsNone(o['model']['p_low'])
    def test_market_benchmark_excludes_dk_and_needs_two_other_books(self):
        self.prices(price=150);self.card();o=self.l.observations(cohort=True)[0]
        self.assertAlmostEqual(o['consensus']['probability'],.5);self.assertEqual(o['consensus']['book_count'],2)
        self.assertEqual({q['book'] for q in o['consensus']['quotes']},{'fanduel','betmgm'})
    def test_one_other_book_is_insufficient(self):
        self.prices(books=('draftkings','fanduel'));r=self.card();self.assertEqual(r['cohort_candidates'],0)
        self.assertEqual(r['cohort_rejections']['INSUFFICIENT_CONTEMPORANEOUS_BOOKS'],2)
    def test_stale_quotes_record_pass_without_joining_cohort(self):
        self.prices();r=self.card('2026-10-14T10:10:00Z');self.assertEqual(r['cohort_candidates'],0);self.assertEqual(r['observations_logged'],2)
        self.assertIn('STALE_PRICE',r['pass_reasons'])
    def test_period_and_exact_line_pairing(self):
        self.prices();q=archived_quotes(self.s,self.w,self.at);anchor=next(x for x in q if x['book']=='draftkings' and x['selection']=='Home')
        others=copy.deepcopy(q)
        for x in others:
            if x['book']=='fanduel':x['period']='first_half'
            if x['book']=='betmgm':x['line']+=1
        self.assertIsNone(consensus(anchor,others,self.at)['probability'])
    def test_repeat_and_moved_line_do_not_replace_original_cohort(self):
        self.prices();self.card();old=self.l.observations(cohort=True)[0]
        self.card('2026-10-14T10:01:02Z');self.assertEqual(len(self.l.observations()),2)
        self.prices(at='2026-10-14T10:02:00Z',line=2.5);self.card('2026-10-14T10:02:01Z')
        self.assertEqual(self.l.observations(cohort=True),[old]);self.assertEqual(len(self.l.observations()),4)
    def test_source_and_warehouse_mutations_are_rejected(self):
        m=self.prices()
        with self.w.connect() as db:db.execute('UPDATE odds_quotes SET line=100 WHERE book=\'draftkings\'')
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):archived_quotes(self.s,self.w,self.at)
        (self.s.root/m['raw_path']).write_text('[]')
        with self.assertRaisesRegex(ValueError,'HASH'):archived_quotes(self.s,self.w,self.at)
    def test_close_not_visible_early_and_old_quote_is_not_close(self):
        self.prices();self.card();o=self.l.observations(cohort=True)[0]
        q=archived_quotes(self.s,self.w,self.at)
        self.assertEqual(closing_evidence(self.s,o['quote'],q,self.at)['reason'],'EVENT_NOT_STARTED')
        self.assertEqual(closing_evidence(self.s,o['quote'],q,'2026-10-14T19:00:00Z')['reason'],'MISSING_NEAR_START_CLOSE')
    def test_point_clv_and_different_line_price_clv_remain_separate(self):
        self.prices();self.card();o=self.l.observations(cohort=True)[0]
        self.prices(at='2026-10-14T17:58:00Z',line=2.5)
        c=closing_evidence(self.s,o['quote'],archived_quotes(self.s,self.w,'2026-10-14T19:00:00Z'),'2026-10-14T19:00:00Z')
        self.assertEqual(c['point_clv'],1);self.assertIsNone(c['price_clv'])
    def test_same_line_price_clv_and_suspension(self):
        self.prices(price=150);self.card();o=self.l.observations(cohort=True)[0]
        self.prices(at='2026-10-14T17:58:00Z')
        c=closing_evidence(self.s,o['quote'],archived_quotes(self.s,self.w,'2026-10-14T19:00:00Z'),'2026-10-14T19:00:00Z')
        self.assertAlmostEqual(c['price_clv'],.1)
        self.capture('odds','sports/americanfootball_ncaaf/odds',[],'2026-10-14T17:59:00Z')
        c=closing_evidence(self.s,o['quote'],archived_quotes(self.s,self.w,'2026-10-14T19:00:00Z'),'2026-10-14T19:00:00Z')
        self.assertIsNone(c['closing_price']);self.assertIn('NOT_AVAILABLE',c['reason'])
    def test_results_corrections_and_retractions_do_not_rewrite_prediction(self):
        self.prices();self.card();frozen=self.l.observations(cohort=True)[0]
        self.result();reconcile(self.l,self.s,self.w,'2026-10-14T21:01:00Z');r,_=report(self.l,'2026-10-14T21:01:00Z')
        self.assertEqual(r['results'],{'WIN':1});self.assertEqual(r['baseline_probability_score']['n'],1)
        self.assertAlmostEqual(r['baseline_probability_score']['brier'],.25);self.assertIsNone(r['paired_model_comparison']['raw']['brier'])
        self.result(at='2026-10-14T22:00:00Z',home=10,away=24);reconcile(self.l,self.s,self.w,'2026-10-14T22:01:00Z')
        r,_=report(self.l,'2026-10-14T22:01:00Z');self.assertEqual(r['results'],{'LOSS':1})
        self.result(at='2026-10-14T23:00:00Z',home=None,away=None,completed=False);reconcile(self.l,self.s,self.w,'2026-10-14T23:01:00Z')
        r,_=report(self.l,'2026-10-14T23:01:00Z');self.assertEqual(r['settled_candidates'],0)
        self.assertEqual(self.l.observations(cohort=True)[0],frozen)
    def test_integer_push_is_refund_and_excluded_from_binary_scores(self):
        self.prices(line=4);self.card();self.result(home=20,away=24);reconcile(self.l,self.s,self.w,'2026-10-14T21:01:00Z')
        r,_=report(self.l,'2026-10-14T21:01:00Z');self.assertEqual(r['results'],{'PUSH':1})
        self.assertEqual(r['baseline_probability_score']['n'],0);self.assertEqual(r['hypothetical_fixed_direction_cohort']['roi'],0)
    def test_future_results_not_used_and_ledger_tampering_detected(self):
        self.prices();self.card();self.result();reconcile(self.l,self.s,self.w,'2026-10-14T19:00:00Z')
        r,_=report(self.l,'2026-10-14T19:00:00Z');self.assertEqual(r['settled_candidates'],0)
        from ap_evsims.integrity import database
        with database(self.l.path) as db:db.execute("UPDATE paper_observations SET body='{}'")
        with self.assertRaisesRegex(ValueError,'HASH'):self.l.observations()
    def test_cap_100_preserves_rejections_without_core(self):
        self.prices();self.card();base=self.l.observations(cohort=True)[0]
        for i in range(101):
            body=copy.deepcopy(base);body['quote']['event_id']=str(i);body['quote']['quote_id']=str(i)
            body['cohort_rejections']=[];self.l.observe(body,cohort_eligible=True)
        r,_=report(self.l,self.at);self.assertEqual(r['cohort_candidates'],100);self.assertEqual(r['models_validated'],0)
        self.assertFalse(r['core_enabled']);self.assertGreater(r['rejected_observations'],0)
    def test_core_cash_and_backdating_rejected(self):
        self.prices();self.card();body=self.l.observations()[0]
        with self.assertRaisesRegex(ValueError,'WAGER_AUTHORITY'):self.l.observe(dict(body,cash_committed=22),cohort_eligible=True)
        with self.assertRaisesRegex(ValueError,'WAGER_AUTHORITY'):self.l.observe(dict(body,core_label='CORE'),cohort_eligible=True)
        with self.assertRaisesRegex(ValueError,'BACKFILL'):self.l.observe(dict(body,decision_at='2026-10-13T10:00:00Z'),cohort_eligible=True)
    def test_scores_compare_identical_forecast_rows(self):
        rows=[dict(observation=dict(model={'raw':p},consensus={'probability':.5}),result={'outcome':y}) for p,y in ((.8,'WIN'),(None,'LOSS'),(.1,'PUSH'))]
        score=score_comparison(rows,'raw');self.assertEqual(score['n'],1);self.assertAlmostEqual(score['brier'],.04);self.assertAlmostEqual(score['market_brier'],.25)
    def test_prediction_publication_keeps_null_calibration_and_has_no_authority(self):
        rows=[dict(model_probability=None),dict(model_probability=.6,calibrated_probability=None,p_low=None,model_artifact_id='verified-artifact',feature_fingerprint='verified-fingerprint')]
        r=research_prediction_rows(rows);self.assertEqual(len(r),1);self.assertEqual(r[0]['raw_probability'],.6)
        self.assertIsNone(r[0]['calibrated_probability']);self.assertIsNone(r[0]['uncertainty_lower_bound']);self.assertFalse(r[0]['phase1_eligible'])
        with self.assertRaisesRegex(ValueError,'UNVERIFIED'):research_prediction_rows([dict(model_probability=.7)])

    def test_revisions_allow_a_return_to_prior_state_and_keep_asof_history(self):
        self.prices();self.card();identity=self.l.observations(cohort=True)[0]['observation_id']
        self.l.revise(identity,'result','2026-10-14T21:00:00Z',{'state':'A'})
        self.l.revise(identity,'result','2026-10-14T22:00:00Z',{'state':'B'})
        self.l.revise(identity,'result','2026-10-14T23:00:00Z',{'state':'A'})
        self.assertEqual(self.l.latest(identity,'result','2026-10-14T22:30:00Z'),{'state':'B'})
        self.assertEqual(self.l.latest(identity,'result','2026-10-14T23:30:00Z'),{'state':'A'})

    def test_group_metrics_keep_missing_confidence_and_same_comparison_sample(self):
        self.prices();self.card();self.result();reconcile(self.l,self.s,self.w,'2026-10-14T21:01:00Z')
        r,_=report(self.l,'2026-10-14T21:01:00Z');g=r['performance_groups']
        self.assertEqual(g['market']['spreads']['binary_n'],1)
        self.assertEqual(g['calibrated_probability_band']['UNAVAILABLE']['paired_calibrated']['n'],0)
        self.assertIsNone(g['market']['spreads']['paired_raw']['brier'])

    def test_all_card_views_share_a_generation_and_state_refresh_basis(self):
        self.prices();self.card()
        from ap_evsims.product import read_card
        summary,feeds=read_card(self.root)
        self.assertEqual(feeds['paper_tracking_status.json']['cohort_candidates'],1)
        for slot in ('MORNING','LUNCH','EVENING'):
            text=(self.root/'reports'/f'{slot}_CARD.md').read_text()
            self.assertIn(summary['publication_generation'],text)
            self.assertIn('LOCAL ARCHIVE ONLY',text)
            self.assertIn('NO QUALIFYING BETS',text)

    def test_older_collection_cannot_overwrite_fresh_provider_quota(self):
        from ap_evsims.providers.quota import QuotaLedger
        from ap_evsims.product import read_card
        old={'quota':{'requests_remaining':500,'provider_requests_used':0}}
        (self.s.root/'evaluations/odds-collection-latest.json').write_text(json.dumps(old))
        QuotaLedger(self.s.root/'quota.sqlite').record(dict(provider='odds',endpoint='sports',parameters={},status=200,
            checked_at=self.at,quota={'x-requests-remaining':419,'x-requests-used':81,'x-requests-last':0}))
        self.card();_,f=read_card(self.root)
        self.assertEqual(f['provider_status.json']['odds_api']['quota_metadata']['x-requests-remaining'],419)
