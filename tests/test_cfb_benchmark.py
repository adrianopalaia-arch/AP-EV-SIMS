import copy
from dataclasses import replace
import unittest
import test_cfb_training as training_helpers
from ap_evsims.cfb_training import build_training_dataset
from ap_evsims.cfb_benchmark import verified_consensus


class ConsensusEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=training_helpers.TrainingTests('test_verified_join_retains_denominator_and_one_real_source_row');self.fixture.setUp();self.fixture.sources()
        rows,_=build_training_dataset(self.fixture.store,self.fixture.w,'2026-10-18T00:00:00Z');self.row=rows[0]
    def tearDown(self):self.fixture.tearDown()
    def evidence(self,*,line=-2.5,period='full_game',at='2026-10-17T09:00:00Z',books=('fanduel','betmgm')):
        s=self.fixture.store;p=copy.deepcopy(s.payload(s.manifest(self.row.context.snapshot_id)))
        for key in books:
            b=copy.deepcopy(p[0]['bookmakers'][0]);b['key']=key;b['last_update']=at;b['markets'][0]['period']=period
            b['markets'][0]['outcomes'][0]['point']=line;b['markets'][0]['outcomes'][1]['point']=-line;p[0]['bookmakers'].append(b)
        m=self.fixture.capture('sports/americanfootball_ncaaf/odds',p,'2026-10-17T09:00:01Z',provider='odds')
        return replace(self.row,context=replace(self.row.context,snapshot_id=m['snapshot_id']))
    def test_independent_books_exact_price_pair(self):
        b=verified_consensus(self.fixture.store,self.evidence());self.assertEqual(b['probability'],.5);self.assertEqual(b['book_count'],2)
        self.assertNotIn('draftkings',[r['book'] for r in b['quotes']])
    def test_wrong_line_period_stale_or_missing_book(self):
        for opts in ({'line':-3.5},{'period':'first_half'},{'at':'2026-10-17T08:50:00Z'},{'books':('fanduel',)}):
            self.assertIsNone(verified_consensus(self.fixture.store,self.evidence(**opts))['probability'])
