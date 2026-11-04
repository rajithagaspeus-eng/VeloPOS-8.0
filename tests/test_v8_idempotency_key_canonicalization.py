"""Regression: canonical idempotency fingerprints must not alias JSON keys."""
import unittest

from velopos_qt.idempotency_ledger import request_fingerprint


class FingerprintKeySafetyTests(unittest.TestCase):
    def test_integer_and_string_keys_cannot_alias(self):
        canonical = request_fingerprint({"1": "sale"})
        self.assertEqual(canonical, request_fingerprint({"1": "sale"}))
        with self.assertRaisesRegex(ValueError, "keys must be strings"):
            request_fingerprint({1: "sale"})

    def test_nested_nonstring_keys_fail_closed(self):
        for payload in (
            {"lines": [{1: "item"}]},
            {"meta": {None: "value"}},
            {"meta": {True: "value"}},
            {"meta": ({2: "item"},)},
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "keys must be strings"):
                    request_fingerprint(payload)

    def test_nested_canonical_string_keys_are_order_independent(self):
        a = {"meta": {"branch": "A", "shift": "1"}, "lines": [{"qty": 2, "sku": "X"}]}
        b = {"lines": [{"sku": "X", "qty": 2}], "meta": {"shift": "1", "branch": "A"}}
        self.assertEqual(request_fingerprint(a), request_fingerprint(b))

    def test_non_object_payload_still_rejected(self):
        with self.assertRaises(ValueError):
            request_fingerprint([{"sku": "X"}])


if __name__ == "__main__":
    unittest.main()
