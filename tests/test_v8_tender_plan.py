"""Pure V8 preview multi-tender allocation tests: never payment acceptance."""
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal

from velopos_qt.tender_plan import plan_preview_tender


class PreviewTenderPlanTests(unittest.TestCase):
    def test_cash_change_is_only_cash_generated(self):
        x = plan_preview_tender("250.00", [
            {"method": "Cash", "amount": "300.00"},
        ])
        self.assertEqual(x.change_due, Decimal("50.00"))
        self.assertEqual(x.cash_total, Decimal("300.00"))
        self.assertEqual(x.noncash_total, Decimal("0.00"))
        self.assertEqual(x.credit_due, Decimal("0.00"))
        self.assertFalse(x.can_settle or x.persisted)

    def test_mixed_tenders_and_external_reference_never_prove_payment(self):
        x = plan_preview_tender("250.00", [
            {"method": "Cash", "amount": "100.00"},
            {"method": "Card", "amount": "75.00", "reference": "CARD-TEST-001"},
            {"method": "QR", "amount": "75.00", "reference": "QR-TEST-002"},
        ])
        self.assertEqual(x.change_due, Decimal("0.00"))
        self.assertEqual(x.noncash_total, Decimal("150.00"))
        self.assertTrue(x.has_unverified_external_payments)
        self.assertFalse(x.can_settle)
        self.assertEqual(len(x.tenders), 3)
        with self.assertRaises(FrozenInstanceError):
            x.can_settle = True

    def test_credit_requires_customer_but_does_not_certify_credit_limit(self):
        x = plan_preview_tender("250.00", [
            {"method": "Cash", "amount": "100"},
            {"method": "Credit", "amount": "150"},
        ], customer_id=42)
        self.assertEqual(x.credit_due, Decimal("150.00"))
        self.assertTrue(x.credit_limit_unverified)
        self.assertFalse(x.can_settle)
        for bad_customer in (None, True, 0, -1, "42"):
            with self.subTest(customer=bad_customer):
                with self.assertRaises(ValueError):
                    plan_preview_tender("250", [
                        {"method": "Credit", "amount": "250"}
                    ], customer_id=bad_customer)

    def test_underpayment_and_noncash_overpayment_fail_closed(self):
        bad = [
            ("200", [{"method": "Cash", "amount": "199.99"}]),
            ("200", [{"method": "Card", "amount": "201", "reference": "CARD-001"}]),
            ("200", [{"method": "Card", "amount": "180", "reference": "CARD-001"},
                     {"method": "Cash", "amount": "30"},
                     {"method": "QR", "amount": "25", "reference": "QR-TEST"}]),
        ]
        for due, tenders in bad:
            with self.subTest(due=due, tenders=tenders):
                with self.assertRaises(ValueError):
                    plan_preview_tender(due, tenders)

    def test_invalid_currency_formats_and_values_do_not_silently_round(self):
        for amt in ("2.005", "NaN", "Inf", "-1", "0", None, True,
                    "10000000001", "unavailable"):
            with self.subTest(amount=amt):
                with self.assertRaises(ValueError):
                    plan_preview_tender("250.00", [
                        {"method": "Cash", "amount": amt},
                    ])
        for due in ("NaN", "-1", 0, "10.001", True):
            with self.subTest(total=due):
                with self.assertRaises(ValueError):
                    plan_preview_tender(due, [
                        {"method": "Cash", "amount": "10.00"},
                    ])

    def test_reject_invalid_refs_entries_and_unsupported_methods(self):
        invalid = (
            [{"method": "Card", "amount": "250", "reference": ""}],
            [{"method": "QR", "amount": "250", "reference": "ab"}],
            [{"method": "Cash", "amount": "250", "reference": "fake"}],
            [{"method": "Credit", "amount": "250", "reference": "fake"}],
            [{"method": "Cryptocurrency", "amount": "250"}],
            [{"method": "Cash", "amount": "250", "reference": "line\nbreak"}],
            [{"method": "Cash", "amount": "250.001"}],
            [{"method": "Cash", "amount": "250", "reference": " x"}],
            ["invalid"],
            [{"method": "Cash", "amount": "25"}] * 11,
        )
        for tenders in invalid:
            with self.subTest(tenders=str(tenders)[:100]):
                with self.assertRaises(ValueError):
                    plan_preview_tender("250", tenders)


if __name__ == "__main__":
    unittest.main()
