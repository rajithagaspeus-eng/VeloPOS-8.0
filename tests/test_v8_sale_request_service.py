"""Read-only V8 sale request rehearsal service contract."""
import re
import unittest

from velopos_qt.sale_request_service import (
    PreviewSaleRequestService, rehearse_sale_request,
)


class PreviewSaleRequestServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = PreviewSaleRequestService()
        self.lines = [
            {"barcode": "RICE", "qty": "2", "price": "12.50"},
            {"barcode": "SOAP", "qty": "1", "price": "0.10"},
        ]

    def test_deterministic_canonical_fingerprint(self):
        first = self.service.inspect(request_id="request-sale-0001", lines=self.lines)
        second = self.service.inspect(
            request_id="request-sale-0001",
            lines=[{"price": "12.500", "qty": "2.0", "barcode": "RICE"},
                   {"price": "0.1", "barcode": "SOAP", "qty": "1.00"}],
        )
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertRegex(first.fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(first.subtotal_cents, 2510)
        self.assertEqual(first.line_count, 2)
        self.assertFalse(first.can_checkout)
        self.assertFalse(first.can_post)
        self.assertEqual(first.canonical_lines, second.canonical_lines)

    def test_changed_intent_or_amount_changes_fingerprint(self):
        base = rehearse_sale_request(request_id="request-sale-0001", lines=self.lines)
        different_id = rehearse_sale_request(
            request_id="request-sale-0002", lines=self.lines
        )
        different_amount = rehearse_sale_request(
            request_id="request-sale-0001",
            lines=[self.lines[0], {"barcode": "SOAP", "qty": "1", "price": "0.11"}],
        )
        self.assertEqual(len({base.fingerprint, different_id.fingerprint,
                              different_amount.fingerprint}), 3)

    def test_invalid_inputs_fail_closed(self):
        for request_id in (None, True, "short", "bad request id", "a" * 129):
            with self.subTest(request_id=request_id):
                with self.assertRaises(ValueError):
                    self.service.inspect(request_id=request_id, lines=self.lines)
        for lines in ([], [{"barcode": "RICE", "qty": "-1", "price": "2"}],
                      [{"barcode": "RICE", "qty": "1", "price": "NaN"}]):
            with self.subTest(lines=lines):
                with self.assertRaises(ValueError):
                    self.service.inspect(request_id="request-sale-0001", lines=lines)

    def test_commit_never_posts_even_with_forged_claims(self):
        for claims in ({}, {"license_valid": True, "open_shift": True},
                       {"authenticated_session": object(), "is_admin": True}):
            with self.subTest(claims=tuple(claims)):
                with self.assertRaises(PermissionError):
                    self.service.commit(
                        request_id="request-sale-0001", lines=self.lines, **claims
                    )

    def test_duplicate_barcode_over_limit_fails_closed(self):
        # Two individually valid lines must not bypass aggregate stock bounds.
        with self.assertRaises(ValueError):
            self.service.inspect(
                request_id="request-duplicate-limit-0001",
                lines=[
                    {"barcode": "RICE", "qty": "600000", "price": "1.00"},
                    {"barcode": "RICE", "qty": "400001", "price": "1.00"},
                ],
            )

    def test_overprecise_prices_have_distinct_fingerprints(self):
        # Fingerprints must retain significant digits beyond Decimal's
        # default 28-digit context, even when cent totals match.
        first = self.service.inspect(
            request_id="request-precision-0001",
            lines=[{"barcode": "RICE", "qty": "1",
                    "price": "0.1234567890123456789012345678901"}],
        )
        second = self.service.inspect(
            request_id="request-precision-0001",
            lines=[{"barcode": "RICE", "qty": "1",
                    "price": "0.1234567890123456789012345678902"}],
        )
        self.assertNotEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.subtotal_cents, second.subtotal_cents)
        self.assertFalse(first.can_checkout)
        self.assertFalse(second.can_post)

    def test_line_rounding_is_per_item_not_aggregate(self):
        result = self.service.inspect(
            request_id="request-rounding-0001",
            lines=[{"barcode": "RICE", "qty": "1", "price": "0.005"},
                   {"barcode": "RICE", "qty": "1", "price": "0.005"}],
        )
        self.assertEqual(result.subtotal_cents, 2)
        self.assertEqual(result.line_count, 2)


if __name__ == "__main__":
    unittest.main()
