import unittest
from ap_evsims.providers.schema import validate_provider_payload

class ProviderSchemaTests(unittest.TestCase):
    def test_error_dictionary_missing_field_and_units_fail(self):
        for payload in ({'error':'partial'},[{'id':1}],[dict(id='p',gameId=1,offense='h',defense='a',playType='Rush',yardsGained='10')]):
            with self.assertRaisesRegex(ValueError,'SCHEMA_DRIFT'):validate_provider_payload('cfbd','plays',payload)
    def test_final_game_requires_both_real_scores(self):
        game=dict(id=1,homeTeam='h',awayTeam='a',startDate='2026-10-14T10:00:00Z',completed=True,homePoints=7,awayPoints=None)
        with self.assertRaisesRegex(ValueError,'SCHEMA_DRIFT'):validate_provider_payload('cfbd','games',[game])
        game['awayPoints']=0;validate_provider_payload('cfbd','games',[game])
        game['homePoints']=True
        with self.assertRaisesRegex(ValueError,'SCHEMA_DRIFT'):validate_provider_payload('cfbd','games',[game])
