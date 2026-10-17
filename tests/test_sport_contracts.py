import unittest
from dataclasses import replace
from ap_evsims.models.contracts import CONTRACTS,FIELDS,validate_contract
from ap_evsims.models.base import FeatureSnapshot,FeatureValue,MarketContext

class SportContractTests(unittest.TestCase):
    def inputs(self,contract):
        stamp='2026-10-14T10:00:00Z'
        values={n:FeatureValue(max(FIELDS[n].minimum,0),'fixture',stamp,stamp,'s','a'*64) for n in contract.required}
        market={'moneyline':'win','ML':'win','totals':'total'}.get(contract.market,contract.market)
        return dict(contract=contract,features=FeatureSnapshot('e',contract.sport,stamp,values),
            context=MarketContext('e',contract.sport,market,'over','book',2.5,-110,-110,stamp,stamp,'2026-10-14T18:00:00Z','q',2.5,stamp),
            units={n:FIELDS[n].unit for n in values},role=dict(requirement=contract.role_requirement,event_id='e',confirmed=True,source='fixture',available_at=stamp,limited=False),player_id='p',team_id='t')
    def test_every_requested_market_has_distinct_contract(self):
        self.assertEqual(len(CONTRACTS),24)
        self.assertEqual(len({c.version for c in CONTRACTS.values()}),24)
        for contract in CONTRACTS.values():
            with self.subTest(sport=contract.sport,market=contract.market):self.assertFalse(validate_contract(**self.inputs(contract))['wager_eligible'])
    def test_each_missing_feature_rejected(self):
        for contract in CONTRACTS.values():
            for missing in contract.required:
                args=self.inputs(contract);values=dict(args['features'].values);values.pop(missing);args['features']=replace(args['features'],values=values)
                with self.assertRaisesRegex(ValueError,'MISSING_FEATURES'):validate_contract(**args)
    def test_units_percent_fraction_range_and_role(self):
        c=CONTRACTS['NHL','SOG'];args=self.inputs(c);args['units']['projected_toi']='seconds'
        with self.assertRaisesRegex(ValueError,'UNIT_MISMATCH'):validate_contract(**args)
        args=self.inputs(c);args['features'].values['pp_share']=replace(args['features'].values['pp_share'],value=50)
        with self.assertRaisesRegex(ValueError,'RANGE_ERROR'):validate_contract(**args)
        args=self.inputs(c);args['role']['limited']=True
        with self.assertRaisesRegex(ValueError,'ROLE_LIMITATION'):validate_contract(**args)
    def test_goalie_player_identity_and_future_confirmation(self):
        c=CONTRACTS['NHL','goalie_saves'];args=self.inputs(c);args['role']['confirmed']=False
        with self.assertRaisesRegex(ValueError,'UNCONFIRMED_GOALIE'):validate_contract(**args)
        args=self.inputs(c);args['player_id']=None
        with self.assertRaisesRegex(ValueError,'PLAYER_IDENTITY'):validate_contract(**args)
        args=self.inputs(c);args['role']['available_at']='2026-10-14T11:00:00Z'
        with self.assertRaisesRegex(ValueError,'LOOKAHEAD'):validate_contract(**args)
