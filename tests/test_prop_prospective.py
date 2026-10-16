import json
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from ap_evsims.prop_prospective import freeze_prop,prop_mass
from ap_evsims.prop_settlement import settlement
from ap_evsims.prop_research import PlayerOutcome
from ap_evsims.integrity import digest
from ap_evsims.research_store import ResearchStore


def forecast():
    return dict(sport='NHL',market='goalie_saves',event_id='1',player_id='G',team_id='COL',model_version='test',
        latest_source_capture='2026-10-15T10:00:00Z',generated_at='2026-10-16T10:00:00Z',event_start='2026-10-17T01:00:00Z',
        artifact_hash='a'*64,model_status='UNVALIDATED',recommendations_enabled=False,p_low=None,
        projection=dict(projection=25,baseline=26,distribution={'20':.5,'30':.5}),priced_markets=[],
        pass_reasons=['UNCONFIRMED_GOALIE'],role_confirmed=False)


class ProspectiveTests(unittest.TestCase):
    def test_push_mass_and_alternate_lines(self):
        p={'2':.3,'3':.4,'4':.3}
        self.assertEqual(prop_mass(p,3)['p_push'],.4)
        self.assertEqual(prop_mass(p,3.5)['p_push'],0)
        self.assertGreaterEqual(prop_mass(p,2.5)['p_win'],prop_mass(p,3.5)['p_win'])
        self.assertAlmostEqual(sum(prop_mass(p,3).values()),1)
    def test_invalid_mass_rejects(self):
        with self.assertRaises(ValueError):prop_mass({'1':1.1},1)
    def test_uncalibrated_and_unknown_goalie_cannot_promote(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);f,n=freeze_prop(s,forecast());self.assertTrue(n);self.assertFalse(f['recommendations_enabled']);self.assertIn('UNCONFIRMED_GOALIE',f['pass_reasons'])
            for update in ({'p_low':.8},{'recommendations_enabled':True},{'model_status':'VALIDATED'}):
                with self.assertRaises(ValueError):freeze_prop(s,dict(forecast(),**update))
    def test_future_capture_and_after_start_reject(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d)
            for update in ({'latest_source_capture':'2026-10-17T00:00:00Z'},{'generated_at':'2026-10-17T02:00:00Z'}):
                with self.assertRaises(ValueError):freeze_prop(s,dict(forecast(),**update))
    def test_refreeze_does_not_rewrite_prior_forecast_or_role(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);old,_=freeze_prop(s,forecast());f=forecast();f.update(role_confirmed=True,projection={'projection':99})
            again,new=freeze_prop(s,f);self.assertFalse(new);self.assertEqual(old,again)
    def test_tampered_forecast_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            s=ResearchStore(d);freeze_prop(s,forecast());path=next((s.root/'predictions/props').glob('*.json'));p=json.loads(path.read_text());p['team_id']='PIT';path.write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError,'HASH'):freeze_prop(s,forecast())
    def test_result_revision_does_not_rewrite_prediction(self):
        f=forecast();f['forecast_hash']=digest(f)
        r=PlayerOutcome('NHL','goalie_saves','1','G','Goalie','COL','PIT','2026-10-16',2027,30.,28,'b'*64,'c'*64,'2026-10-17T05:00:00Z')
        a=settlement(f,r);b=settlement(f,replace(r,outcome=29,source_hash='d'*64))
        self.assertNotEqual(digest(a),digest(b));self.assertEqual(a['forecast_hash'],b['forecast_hash']);self.assertEqual(f['projection']['projection'],25)
    def test_wrong_player_team_or_game_cannot_settle(self):
        f=forecast();f['forecast_hash']=digest(f)
        r=PlayerOutcome('NHL','goalie_saves','1','G','Goalie','COL','PIT','2026-10-16',2027,30.,28,'b'*64,'c'*64,'2026-10-17T05:00:00Z')
        for changes in ({'player_id':'other'},{'event_id':'2'},{'team_id':'BOS'}):
            with self.assertRaisesRegex(ValueError,'IDENTITY'):settlement(f,replace(r,**changes))
    def test_pregame_result_capture_not_settleable(self):
        f=forecast();f['forecast_hash']=digest(f)
        r=PlayerOutcome('NHL','goalie_saves','1','G','Goalie','COL','PIT','2026-10-14',2027,30.,28,'b'*64,'c'*64,'2026-10-15T05:00:00Z')
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):settlement(f,r)
