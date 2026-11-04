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


    def test_hostile_payload_size_and_node_limits_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "too large"):
            request_fingerprint({"comment": "X" * 300000})
        with self.assertRaisesRegex(ValueError, "too large"):
            request_fingerprint({"lines": "€" * 100000})
        with self.assertRaisesRegex(ValueError, "too many nodes"):
            request_fingerprint({"lines": [0] * 10001})

    def test_invalid_unicode_is_caught_as_request_validation_error(self):
        # Use chr(), not an escaped string literal: "\\ud800" is a valid
        # six-character string and must not be mistaken for a surrogate.
        high_surrogate = chr(0xD800)
        low_surrogate = chr(0xDFFF)
        self.assertEqual(len(high_surrogate), 1)
        self.assertEqual(ord(low_surrogate), 0xDFFF)
        with self.assertRaisesRegex(ValueError, "encoding"):
            request_fingerprint({"barcode": high_surrogate})
        with self.assertRaisesRegex(ValueError, "encoding"):
            request_fingerprint({low_surrogate: "entry"})
        # The literal backslash-u sequence remains a legitimate barcode.
        self.assertEqual(
            request_fingerprint({"barcode": r"\\ud800"}),
            request_fingerprint({"barcode": chr(92) + "ud800"}),
        )

    def test_boundary_sized_normal_request_fingerprint_is_stable(self):
        draft = {"lines": [{"sku": "ABC", "qty": 1}],
                 "request_id": "sale-limited-0001"}
        self.assertEqual(request_fingerprint(draft), request_fingerprint(dict(draft)))

    def test_non_object_payload_still_rejected(self):
        with self.assertRaises(ValueError):
            request_fingerprint([{"sku": "X"}])


if __name__ == "__main__":
    unittest.main()
