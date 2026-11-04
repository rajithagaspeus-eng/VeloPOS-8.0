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

    def test_cyclic_container_fails_closed(self):
        recursive = []
        recursive.append(recursive)
        with self.assertRaisesRegex(ValueError, "Cyclic request payload"):
            request_fingerprint({"lines": recursive})
        mapping = {}
        mapping["self"] = mapping
        with self.assertRaisesRegex(ValueError, "Cyclic request payload"):
            request_fingerprint(mapping)

    def test_excessive_nesting_fails_closed(self):
        nested = "item"
        for _ in range(70):
            nested = [nested]
        with self.assertRaisesRegex(ValueError, "nesting too deep"):
            request_fingerprint({"lines": nested})

    def test_shared_noncyclic_container_is_allowed(self):
        line = {"sku": "A", "qty": 1}
        self.assertEqual(
            request_fingerprint({"lines": [line, line]}),
            request_fingerprint({"lines": [dict(line), dict(line)]}),
        )

    def test_non_object_payload_still_rejected(self):
        with self.assertRaises(ValueError):
            request_fingerprint([{"sku": "X"}])


if __name__ == "__main__":
    unittest.main()
