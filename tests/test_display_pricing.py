"""Constructed calculation cases only; never empirical prediction observations."""
import json, tempfile, unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
from ap_evsims.display_pricing import opposite_side, market_calculations, outcome_ev, conditional_ev, dashboard_market
from ap_evsims.product import preflight as product_preflight, daily_card, read_card
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.offline import offline_mode
from test_warehouse import archive


def preflight(*args):
    # Assert by fixture identity, independently of the product's display sort.
    return sorted(product_preflight(*args),key=lambda r:r['candidate_id'])


def quotes(market='h2h',line=None,sport='CFB',a=-150,b=130):
    base=dict(sport=sport,event_id='fixture',event_start='2026-11-01T18:00:00Z',home_team='Home',away_team='Away',
        book='draftkings',market=market,period='full_game',snapshot_id='a'*64,raw_payload_hash='b'*64,
        pair_id='pair',settlement_rule_id=None,observed_at='2026-11-01T10:00:00Z',
        available_at='2026-11-01T10:00:01Z',ingested_at='2026-11-01T10:00:01Z')
    return [dict(base,quote_id='a',selection='Over' if market=='totals' else 'Home',line=line,american_odds=a),
        dict(base,quote_id='b',selection='Under' if market=='totals' else 'Away',line=-line if market=='spreads' else line,american_odds=b)]


class DisplayPricingTests(unittest.TestCase):
    def test_moneyline_implied_normalization_and_ev(self):
        qs=quotes();r=preflight(qs,'2026-11-01T10:01:00Z')
        self.assertAlmostEqual(r[0]['market_implied_probability'],.6)
        self.assertAlmostEqual(r[1]['market_implied_probability'],100/230)
        self.assertAlmostEqual(sum(x['market_no_vig_probability'] for x in r),1)
        p=.6/(.6+100/230)
        self.assertAlmostEqual(r[0]['market_baseline_ev'],p*(100/150)-(1-p))
        self.assertEqual(r[0]['market_push_probability'],0)
        self.assertEqual(r[0]['probability_source'],'MARKET BASELINE ONLY')
        self.assertIsNone(r[0]['model_probability']);self.assertIsNone(r[0]['p_low'])

    def test_integer_lines_never_invent_push_mass_or_unconditional_ev(self):
        for market,line in (('spreads',3),('spreads',0),('totals',48)):
            q=quotes(market,line,a=-110,b=-110);r=preflight(q,'2026-11-01T10:01:00Z')[0]
            self.assertEqual(r['market_no_vig_probability'],.5)
            self.assertIsNone(r['market_baseline_ev']);self.assertIsNone(r['market_push_probability'])
            self.assertIsNone(r['market_win_probability']);self.assertIsNone(r['market_loss_probability'])
            self.assertAlmostEqual(r['market_conditional_ev'],-1/22)
            self.assertIn('PUSH_PROBABILITY_UNKNOWN',r['pass_reason'])
        self.assertAlmostEqual(outcome_ev(.5,.4,.1,-110),.5*100/110-.4)
        self.assertAlmostEqual(conditional_ev(.6,-110,.1),.54*100/110-.36)
        with self.assertRaises(ValueError):outcome_ev(.5,.5,.1,-110)
        with self.assertRaises(ValueError):conditional_ev(.6,-110,None)

    def test_half_lines_and_tie_capable_moneyline(self):
        for market,line in (('spreads',-3.5),('totals',47.5)):
            q=quotes(market,line);r=market_calculations(q[0],q[1])
            self.assertEqual(r['market_push_probability'],0)
            self.assertIsNotNone(r['market_baseline_ev'])
        for q in (quotes(sport='NFL'),quotes('spreads',3.25)):
            self.assertIsNone(market_calculations(q[0],q[1])['market_baseline_ev'])
        q=quotes('spreads',3.25)
        self.assertIsNone(market_calculations(q[0],q[1])['market_conditional_ev'])
        q=quotes(sport='NHL');q[0]['period']=q[1]['period']='first_period'
        self.assertIsNone(market_calculations(q[0],q[1])['market_push_probability'])

    def test_pair_requires_exact_identity_line_period_and_capture(self):
        for field,value in [('book','fanduel'),('period','first_half'),('event_id','other'),('market','totals'),
            ('line',-4.5),('snapshot_id','c'*64),('raw_payload_hash','d'*64),('sport','NFL'),
            ('pair_id','different'),('observed_at','2026-11-01T10:00:02Z'),
            ('available_at','2026-11-01T10:00:03Z'),('settlement_rule_id','other')]:
            with self.subTest(field=field):
                q=quotes('spreads',3.5);q[1][field]=value
                self.assertIsNone(opposite_side(q[0],q))
                self.assertIsNone(preflight(q,'2026-11-01T10:01:00Z')[0]['market_no_vig_probability'])
        q=quotes('totals',48.5);q[1]['line']=49.5
        self.assertIsNone(opposite_side(q[0],q))
        q=quotes();self.assertIsNone(opposite_side(q[0],q+[dict(q[1],quote_id='duplicate')]))

    def test_missing_opposite_and_invalid_odds_fail_closed(self):
        q=quotes();row=preflight(q[:1],'2026-11-01T10:01:00Z')[0]
        self.assertEqual(row['market_implied_probability'],.6)
        self.assertIsNone(row['market_no_vig_probability']);self.assertIn('NO_MARKET_PAIR',row['pass_reason'])
        for bad in (0,99,True,float('nan'),-110.0,'-110'):
            with self.subTest(bad=bad):
                q=quotes(a=bad);rows=preflight(q,'2026-11-01T10:01:00Z')
                self.assertIsNone(rows[0]['market_implied_probability'])
                self.assertIsNone(rows[1]['market_no_vig_probability'])
                self.assertTrue(all(r['decision']=='PASS' for r in rows))

    def test_stale_price_retains_math_and_price_move_recalculates(self):
        q=quotes();old=preflight(q,'2026-11-01T10:01:00Z')
        stale=preflight(q,'2026-11-01T10:10:00Z')
        self.assertEqual(old[0]['market_baseline_ev'],stale[0]['market_baseline_ev'])
        self.assertIn('STALE_PRICE',stale[0]['pass_reason'])
        self.assertEqual(dashboard_market(old[0],'2026-11-01T10:10:00Z')['Status'],'PASS: STALE_PRICE')
        moved=preflight(quotes(a=-175),'2026-11-01T10:01:00Z',old)
        self.assertNotEqual(old[0]['market_baseline_ev'],moved[0]['market_baseline_ev'])
        self.assertIn('PRICE_MOVED',moved[0]['pass_reason'])
        self.assertIsNone(moved[0]['calibrated_probability']);self.assertIsNone(moved[0]['p_low'])
        self.assertFalse(moved[0]['phase1_eligible'])

    def test_ingestion_preserves_single_valid_quote_and_offline_recalculation(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);s=ResearchStore(repo/'data');w=Warehouse(s.root)
            m=archive(s);payload=s.payload(m)
            payload[0]['bookmakers'][0]['markets'][0]['outcomes']=payload[0]['bookmakers'][0]['markets'][0]['outcomes'][:1]
            m=s.archive(provider='odds',endpoint=m['endpoint'],parameters={},body=json.dumps(payload).encode(),
                fetched_at='2026-10-14T10:00:01Z',observed_at='2026-10-14T10:00:00Z',
                available_at='2026-10-14T10:00:01Z',availability_basis='recorded_response')
            with offline_mode():
                daily_card(repo,offline=True,now='2026-10-14T10:01:00Z')
                _,feeds=read_card(repo)
            row=feeds['latest_passes.json'][0]
            self.assertEqual(len(feeds['latest_passes.json']),1)
            self.assertIsNotNone(row['market_implied_probability'])
            self.assertIsNone(row['market_no_vig_probability'])
            self.assertEqual(feeds['latest_edges.json'],[])
            self.assertEqual(feeds['latest_predictions.json'],[])

    def test_existing_research_model_ev_never_authorizes_wager(self):
        from test_phase2_cfb import fixture_rows
        from ap_evsims.models.cfb import CFBSpreadModel
        from ap_evsims.research_display import attach_prediction,ResearchQuoteContext
        model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10)
        model.fit(fixture_rows(),training_cutoff='2024-04-01T00:00:00Z')
        sample=fixture_rows(1,start='2024-05-01')[0]
        # The current-research context records the actual later calculation time.
        values=sample.context.__dict__|{'odds':1000,'line':3,'opposite_line':3,
            'prediction_timestamp':'2024-05-01T10:01:00Z','snapshot_available_at':'2024-05-01T10:00:01Z'}
        context=ResearchQuoteContext(**values)
        p=model.predict(sample.features,context)
        self.assertIsNotNone(p.raw_probability)
        row=preflight(quotes('spreads',3,a=1000),'2026-11-01T10:01:00Z')[0]
        row.update(event_id=context.event_id,event_start=context.event_timestamp,quote_timestamp=context.quote_timestamp)
        row['data_timestamps']['provider_available']=context.snapshot_available_at
        attach_prediction(row,p,'2024-05-01T10:01:00Z')
        self.assertGreater(row['ap_raw_ev'],0)
        self.assertGreater(row['ap_push_probability'],0)
        self.assertAlmostEqual(row['ap_model_expected_value'],row['ap_win_probability']*10-row['ap_loss_probability'])
        self.assertIsNone(row['calibrated_probability']);self.assertIsNone(row['p_low'])
        self.assertIn('MODEL_NOT_CALIBRATED',row['pass_reason'])
        self.assertEqual(row['decision'],'PASS');self.assertFalse(row['phase1_eligible'])
        self.assertIsNone(row['stake']);self.assertIsNone(row['expected_value'])
        original=row['ap_model_expected_value'];row['odds']=110
        attach_prediction(row,p,'2024-05-01T10:01:00Z')
        self.assertNotEqual(original,row['ap_model_expected_value'])
        with self.assertRaises(ValueError):
            attach_prediction(row,replace(p,uncertainty_lower_bound=.8),'2024-05-01T10:01:00Z')
        with self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):
            attach_prediction(row,replace(p,event_id='wrong-game'),'2024-05-01T10:01:00Z')
        with self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):
            attach_prediction(row,replace(p,explanation=p.explanation|{'market_line':4}),'2024-05-01T10:01:00Z')
        self.assertEqual(p.prediction_timestamp,'2024-05-01T10:01:00Z')
        self.assertIn('LOOKAHEAD_RISK',model.predict(sample.features,replace(context,prediction_timestamp='2024-05-01T09:59:59Z')).reasons)

    def test_real_display_rejects_synthetic_artifact_and_caller_claims(self):
        from test_phase2_cfb import fixture_rows
        from ap_evsims.models.cfb import CFBSpreadModel
        from ap_evsims.models.artifacts import save_model
        from ap_evsims.research_display import verified_models
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t)
            self.assertEqual(verified_models(s,'2026-01-01T00:00:00Z')[0],{})
            model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10)
            rows=fixture_rows();model.fit(rows,training_cutoff='2024-04-01T00:00:00Z')
            save_model(model,s.root/'models/test-only.json')
            (s.root/'normalized/test-only.jsonl').write_text('\n'.join(json.dumps(asdict(r)) for r in rows))
            (s.root/'models/dashboard-models.json').write_text(json.dumps({'models':[{
                'artifact':'models/test-only.json','training_dataset':'normalized/test-only.jsonl',
                'validated':True,'real_data':True}]}))
            models,issues=verified_models(s,'2026-01-01T00:00:00Z')
            self.assertEqual(models,{})
            self.assertIn('RESEARCH_MODEL_PROVENANCE_UNVERIFIED',issues)

    def test_artifact_coefficients_must_reproduce_from_declared_training(self):
        from test_phase2_cfb import fixture_rows
        from ap_evsims.models.cfb import CFBSpreadModel
        from ap_evsims.models.artifacts import save_model
        from ap_evsims.research_display import verified_models
        from ap_evsims.integrity import digest
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as t:
            s=ResearchStore(t);rows=fixture_rows()
            model=CFBSpreadModel(feature_keys=('home_field',),minimum_train=20,bootstrap_samples=10).fit(rows,training_cutoff='2024-04-01T00:00:00Z')
            path=s.root/'models/test-only.json';save_model(model,path)
            (s.root/'normalized/test-only.jsonl').write_text('\n'.join(json.dumps(asdict(r)) for r in rows))
            (s.root/'models/dashboard-models.json').write_text(json.dumps({'models':[{
                'artifact':'models/test-only.json','training_dataset':'normalized/test-only.jsonl'}]}))
            # Isolate training reproduction with constructed data; the preceding
            # test independently verifies fixtures fail the real source gate.
            with patch('ap_evsims.research_display.verify_provider_dataset'):
                self.assertEqual(set(verified_models(s,'2026-01-01T00:00:00Z')[0]),{'spread'})
                payload=json.loads(path.read_text())
                payload['state']['fitted']['regression']['coefficients'][0]+=10
                payload['state']['artifact_id']=digest(payload['state']['fitted'])
                payload['fingerprint']=digest(payload['state'])
                path.write_text(json.dumps(payload))
                self.assertEqual(verified_models(s,'2026-01-01T00:00:00Z')[0],{})

    def test_requested_ui_columns_and_offline_recalculate_button(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);s=ResearchStore(repo/'data')
            m=archive(s);payload=s.payload(m);payload[0]['commence_time']='2099-01-01T18:00:00Z'
            s.archive(provider='odds',endpoint=m['endpoint'],parameters={},body=json.dumps(payload).encode(),
                fetched_at='2026-10-14T10:00:01Z',observed_at='2026-10-14T10:00:00Z',
                available_at='2026-10-14T10:00:01Z',availability_basis='recorded_response')
            daily_card(repo,offline=True)
            code='from pathlib import Path\nfrom ap_evsims.dashboard import main\nmain(Path('+repr(str(repo))+'))'
            app=AppTest.from_string(code,default_timeout=30).run()
            self.assertFalse(app.exception)
            table=app.dataframe[0].value
            requested={'Sport','Game','Market','Selection','Book','Line','Odds','Break-even %','Market no-vig %',
                'Market-baseline EV %','AP raw probability %','AP calibrated probability %','AP p_low %',
                'AP model EV %','Data quality','Quote age','Status','PASS reason'}
            self.assertTrue(requested<=set(table.columns))
            self.assertTrue(table['Market no-vig %'].notna().all())
            self.assertTrue(table['AP raw probability %'].isna().all())
            self.assertTrue((table['Probability source']=='MARKET BASELINE ONLY').all())
            self.assertTrue((table['Status']=='PASS: STALE_PRICE').all())
            with patch('ap_evsims.dashboard.daily_card',wraps=daily_card) as build,patch('ap_evsims.product.collect_odds',side_effect=AssertionError('unexpected API collection')) as collect:
                next(b for b in app.button if b.label=='Recalculate').click().run()
                self.assertTrue(build.call_args.kwargs['offline'])
                collect.assert_not_called()
            self.assertFalse(app.exception)
            with patch('ap_evsims.dashboard.daily_card',return_value={}) as build:
                next(b for b in app.button if b.label=='Refresh Quotes').click().run()
                self.assertFalse(build.call_args.kwargs['offline'])
                self.assertTrue(build.call_args.kwargs['force_refresh'])


if __name__=='__main__':unittest.main()
