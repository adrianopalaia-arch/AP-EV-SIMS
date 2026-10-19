import unittest
from scripts.nfl_sweep_acceptance import check


def report(n=12):
    dt='2026-10-18T17:00:00Z'; observed='2026-10-17T20:00:00Z'
    schedule=[{'event_id':f'e{i}', 'home_team':f'Home {i}', 'away_team':f'Away {i}', 'kickoff':dt} for i in range(n)]
    games=[{'event_id':f'e{i}', 'forecast_status':'FORECASTED', 'p_home_win':.57, 'p_away_win':.43,
            'model_version':'test-ridge', 'model_data_cutoff':observed,
            'main_market_status':'FETCHED', 'prop_market_status':'SCANNED', 'quotes': []}
           for i in range(n)]
    return {'target_date':'2026-10-18','schedule':{'source':'official-fixture','captured_at':observed,'games':schedule},
            'games':games,'quota':{'credits_used':15,'daily_cap':24}, 'auto_bets_placed':0}

class TestSweep(unittest.TestCase):
    def test_full_slate_passes(self):
        self.assertTrue(check(report(),expected=12,require_probabilities=True)['ok'])
    def test_single_event_sweep_rejected(self):
        r=report();r['games']=r['games'][:1]
        x=check(r,expected=12);self.assertFalse(x['ok']);self.assertEqual(x['covered_games'],1)
    def test_missing_forecast_is_explicit_not_faked(self):
        r=report();r['games'][2].update(forecast_status='NO_TRAINED_GAME_MODEL',p_home_win=None,p_away_win=None,model_version=None)
        self.assertTrue(check(r,expected=12)['ok'])
        self.assertFalse(check(r,expected=12,require_probabilities=True)['ok'])
    def test_missing_model_must_not_be_50_50(self):
        r=report();r['games'][2].update(forecast_status='NO_TRAINED_GAME_MODEL',p_home_win=.5,p_away_win=.5)
        self.assertFalse(check(r,expected=12)['ok'])
    def test_quota_enforced(self):
        r=report();r['quota']['credits_used']=25
        self.assertFalse(check(r,expected=12)['ok'])
    def test_cross_game_quote_rejected(self):
        r=report();r['games'][0]['quotes']=[{'event_id':'e1','book':'draftkings','market':'h2h','line':0,
            'selection':'Home 0','american_odds':-110,'observed_at':'2026-10-17T19:30:00Z','captured_at':'2026-10-17T20:00:00Z'}]
        self.assertFalse(check(r,expected=12)['ok'])
    def test_late_price_rejected(self):
        r=report();r['games'][0]['quotes']=[{'event_id':'e0','book':'draftkings','market':'h2h','line':0,
            'selection':'Home 0','american_odds':-110,'observed_at':'2026-10-18T19:30:00Z','captured_at':'2026-10-18T20:00:00Z'}]
        self.assertFalse(check(r,expected=12)['ok'])
    def test_invalid_probabilities_rejected(self):
        r=report();r['games'][3]['p_home_win']=.87
        self.assertFalse(check(r,expected=12)['ok'])

if __name__ == '__main__':
    unittest.main()
