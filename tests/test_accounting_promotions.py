import tempfile,unittest
from pathlib import Path
from ap_evsims.accounting import AccountLedger
from ap_evsims.promotions import promotion_ev

class AccountingPromotionTests(unittest.TestCase):
    def test_unknown_balance_and_atomic_overdraft(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=AccountLedger(Path(t)/'a.sqlite');self.assertIsNone(ledger.state()['cash_bankroll'])
            common=dict(at='2026-10-14T10:00:00Z',reference='manual',source='fixture statement')
            with self.assertRaisesRegex(ValueError,'BANKROLL_NOT_RECONCILED'):ledger.append(transaction_id='x',kind='deposit',cash_delta=10,**common)
            ledger.append(transaction_id='o',kind='opening_reconciliation',cash_delta=100,bonus_delta=10,**common)
            with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):ledger.append(transaction_id='x',kind='bonus_stake',bonus_delta=-11,**common)
            self.assertEqual(ledger.state()['bonus_balance'],10)
    def test_idempotence_corrections_cash_bonus_and_precision(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=AccountLedger(Path(t)/'a.sqlite');common=dict(at='2026-10-14T10:00:00Z',source='fixture')
            opening=dict(transaction_id='o',kind='opening_reconciliation',cash_delta=100,bonus_delta=10,reference='statement',**common)
            ledger.append(**opening);ledger.append(**opening)
            self.assertEqual(ledger.state()['transaction_count'],1)
            with self.assertRaisesRegex(ValueError,'MUTATION'):ledger.append(**dict(opening,cash_delta=200))
            ledger.append(transaction_id='s',kind='cash_stake',cash_delta=-10,reference='bet1',**common)
            ledger.append(transaction_id='r',kind='settlement',cash_delta=20,reference='bet1',**common)
            ledger.append(transaction_id='c',kind='correction',cash_delta=-10,reference='r',**common)
            self.assertEqual(ledger.state()['cash_bankroll'],100)
            with self.assertRaisesRegex(ValueError,'PRECISION'):ledger.append(transaction_id='bad',kind='deposit',cash_delta=.001,reference='statement',**common)
    def test_promotion_changes_payoff_only(self):
        common=dict(p_win=.5,p_push=0,odds=100,stake=10,terms_verified=True)
        base=promotion_ev(**common);boost=promotion_ev(**common,kind='profit_boost',boost_fraction=.5)
        self.assertEqual(base['expected_cash_profit'],0);self.assertEqual(boost['expected_cash_profit'],2.5)
        self.assertEqual(boost['p_win'],base['p_win']);self.assertTrue(boost['phase1_eligibility_unchanged'])
        self.assertEqual(promotion_ev(**common,kind='free_bet')['expected_cash_profit'],5)
    def test_no_sweat_requires_conversion_and_terms(self):
        args=dict(p_win=.5,p_push=0,odds=100,stake=10,kind='no_sweat',refund_cap=10)
        with self.assertRaisesRegex(ValueError,'TERMS'):promotion_ev(**args)
        with self.assertRaisesRegex(ValueError,'CONVERSION'):promotion_ev(**args,terms_verified=True)
        self.assertEqual(promotion_ev(**args,terms_verified=True,refund_conversion=.7)['expected_cash_profit'],3.5)
