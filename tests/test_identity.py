import unittest
from copy import deepcopy
from ap_evsims.identity import map_cfb_events

class IdentityTests(unittest.TestCase):
    def inputs(self):
        return dict(teams=[dict(id=1,school='Home',mascot='Cats'),dict(id=2,school='Away',mascot='Dogs')],
            games=[dict(id=10,homeId=1,awayId=2,homeTeam='Home',awayTeam='Away',startDate='2026-10-17T18:00:00Z',startTimeTBD=False,season=2026)],
            events=[dict(id='q',home_team='Home Cats',away_team='Away Dogs',commence_time='2026-10-17T18:00:00Z')],
            alias_snapshot='a'*64,game_snapshot='b'*64,available_at='2026-10-14T10:00:00Z')
    def test_exact_source_alias_and_offset_timestamp_match(self):
        args=self.inputs();args['events'][0]['commence_time']='2026-10-17T13:00:00-05:00'
        mapping,errors=map_cfb_events(**args);self.assertEqual(mapping['q']['event_id'],'10');self.assertEqual(errors,[])
    def test_ambiguous_name_rejected_without_fuzzy_guess(self):
        args=self.inputs();args['teams'].append(dict(id=3,school='Home',mascot='Cats'))
        mapping,errors=map_cfb_events(**args);self.assertFalse(mapping);self.assertIn('AMBIGUOUS',errors[0]['reason'])
    def test_reschedule_and_tbd_rejected(self):
        for field,value in [('startDate','2026-10-17T18:05:00Z'),('startTimeTBD',True)]:
            args=self.inputs();args['games'][0][field]=value
            mapping,errors=map_cfb_events(**args);self.assertFalse(mapping);self.assertTrue(errors)
    def test_double_event_collision_and_home_away_swap_rejected(self):
        args=self.inputs();game=deepcopy(args['games'][0]);game['id']=11;args['games'].append(game)
        self.assertFalse(map_cfb_events(**args)[0])
    def test_spelling_normalization_requires_unique_provider_id(self):
        args=self.inputs();args['teams'][0].update(school="The H\u00f3me",mascot="C'at\u2019s")
        self.assertTrue(map_cfb_events(**args)[0])
        args['teams'].append(dict(id=3,school='Home',mascot='Cats'))
        self.assertFalse(map_cfb_events(**args)[0])
        args=self.inputs();args['events'][0].update(home_team='Away Dogs',away_team='Home Cats')
        self.assertFalse(map_cfb_events(**args)[0])
