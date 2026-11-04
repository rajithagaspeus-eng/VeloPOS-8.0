"""Core V8 TEST-DATA-ONLY sale math, staged ledger and retry safety.

All integration tests run on disposable subprocesses. A rehearsal ALWAYS
rolls back sales, sale_items, stock_moves and request-journal changes.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path

from velopos_qt.sale_plan import canonical_decimal, plan_preview_sale
from velopos_qt.idempotency_ledger import request_fingerprint
from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE


class PreviewSalePlanTests(unittest.TestCase):
    def test_line_rounding_and_receipt_total_not_round_unrounded_sum(self):
        draft = [
            {"barcode": "RICE", "qty": "0.333", "price": "0.05"},
            {"barcode": "RICE", "qty": Decimal("0.333"), "price": Decimal("0.05")},
            {"barcode": "RICE", "qty": "0.333", "price": "0.05"},
        ]
        plan = plan_preview_sale(draft)
        self.assertEqual(plan.line_count, 3)
        self.assertEqual(plan.quantities, (("RICE", Decimal("0.999")),))
        self.assertEqual([v.line_total for v in plan.lines],
                         [Decimal("0.02")] * 3)
        self.assertEqual(plan.subtotal, Decimal("0.06"))
        self.assertNotEqual(
            plan.subtotal, (Decimal("0.999") * Decimal("0.05")).quantize(
                Decimal("0.01")
            )
        )

    def test_canonical_idempotency_payload_equivalent_numeric_representations(self):
        a = plan_preview_sale([{"barcode": "SOAP", "qty": 2,
                                "price": "25.00"}])
        b = plan_preview_sale([{"barcode": "SOAP", "qty": Decimal("2.000"),
                                "price": 25.0}])
        self.assertEqual(a.request_items(), b.request_items())
        self.assertEqual(
            request_fingerprint({"items": a.request_items()}),
            request_fingerprint({"items": b.request_items()}),
        )
        self.assertEqual(canonical_decimal(Decimal("-0")), "0")
        self.assertEqual(canonical_decimal(Decimal("1E+3")), "1000")
        self.assertEqual(a.subtotal, Decimal("50.00"))

    def test_untrusted_iterator_is_bounded_to_101_inputs(self):
        """A bad generator must not consume unbounded scan lines or hang."""
        row = {"barcode": "RICE", "qty": 1, "price": 25}
        pulled = []

        def untrusted_stream():
            for index in range(101):
                pulled.append(index)
                yield row
            raise AssertionError("Planner consumed beyond 101 draft entries")

        with self.assertRaisesRegex(ValueError, "1-100 lines"):
            plan_preview_sale(untrusted_stream())
        self.assertEqual(len(pulled), 101)

    def test_exactly_100_generator_lines_remain_supported(self):
        row = {"barcode": "RICE", "qty": "0.1", "price": "0.05"}
        generated = (dict(row) for _ in range(100))
        plan = plan_preview_sale(generated)
        self.assertEqual(plan.line_count, 100)
        self.assertEqual(plan.quantities, (("RICE", Decimal("10.0")),))
        self.assertEqual(plan.subtotal, Decimal("1.00"))

    def test_extreme_decimal_exponents_refused_before_plain_string_expansion(self):
        for raw in ("1E-999999999", "1E+999999999", "9" * 129):
            with self.subTest(value=raw[:32]):
                with self.assertRaises(ValueError):
                    canonical_decimal(raw)
                with self.assertRaises(ValueError):
                    plan_preview_sale([
                        {"barcode": "SAFE", "qty": raw, "price": "1"}
                    ])
        self.assertEqual(
            canonical_decimal(Decimal("1E-18")),
            "0.000000000000000001",
        )
        self.assertEqual(canonical_decimal("1E+3"), "1000")

    def test_invalid_lines_and_limits_fail_closed(self):
        good = {"barcode": "RICE", "qty": 1, "price": "25.00"}
        for bad in (
            [],
            "RICE",
            [good] * 101,
            [{"barcode": "", "qty": 1, "price": 1}],
            [{"barcode": "  RICE", "qty": 1, "price": 1}],
            [{"barcode": 123, "qty": 1, "price": 1}],
            [{"barcode": "RICE\nINJECT", "qty": 1, "price": 1}],
            [{"barcode": "RICE\tINJECT", "qty": 1, "price": 1}],
            [{"barcode": "RICE\x00INJECT", "qty": 1, "price": 1}],
            [{"barcode": "RICE\x1bINJECT", "qty": 1, "price": 1}],
            [{"barcode": "RICE", "qty": 0, "price": 1}],
            [{"barcode": "RICE", "qty": True, "price": 1}],
            [{"barcode": "RICE", "qty": "NaN", "price": 1}],
            [{"barcode": "RICE", "qty": "Inf", "price": 1}],
            [{"barcode": "RICE", "qty": -1, "price": 1}],
            [{"barcode": "RICE", "qty": 1, "price": -0.01}],
            [{"barcode": "RICE", "qty": 1, "price": "Infinity"}],
            [{"barcode": "RICE", "qty": 1, "price": True}],
            [{"barcode": "RICE", "qty": 1000000, "price": 1},
             {"barcode": "RICE", "qty": 1, "price": 1}],
        ):
            with self.subTest(bad=repr(bad)[:100]):
                with self.assertRaises(ValueError):
                    plan_preview_sale(bad)


class SaleLedgerRehearsalTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_plan_ledger_") as home:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(home) / "VeloPOS8PreviewData")
            p = subprocess.run(
                [sys.executable, "-c", FIXTURE + "\n" + textwrap.dedent(script)],
                env=env, text=True, capture_output=True, timeout=75,
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_staged_sale_ledger_and_claim_replay_never_persist(self):
        self.isolated("""
            rehearsal = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            for _ in range(2):
                staged = rehearsal.simulate(
                    identity=user, shift_id=shift, lines=lines,
                    request_id="sale-rehearsal-ledger-0001",
                    today="2026-11-04",
                )
                assert staged.persisted is False
                assert staged.subtotal == Decimal("250.00"), staged
                assert staged.staged_items == 3
                assert staged.staged_stock_movements == 2
                assert staged.invoice_preview.startswith("SIM-")
            with database.db() as c:
                assert snapshot(c) == before, (before, snapshot(c))
        """)

    def test_stock_ledger_invoice_and_request_completion_injection_roll_back(self):
        self.isolated("""
            rehearsal = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            for stage in ("after_stock", "after_stock_ledger",
                          "after_invoice", "after_journal_complete"):
                try:
                    rehearsal.simulate(
                        identity=user, shift_id=shift, lines=lines,
                        request_id="sale-failpoint-replay-0001",
                        today="2026-11-04", inject_failure_at=stage,
                    )
                except RuntimeError as exc:
                    assert "Injected failure" in str(exc)
                else:
                    raise AssertionError("Stage did not fail: " + stage)
                with database.db() as c:
                    assert snapshot(c) == before, (stage, snapshot(c))
            # A failed operation cannot strand a completed or pending claim.
            staged = rehearsal.simulate(
                identity=user, shift_id=shift, lines=lines,
                request_id="sale-failpoint-replay-0001", today="2026-11-04",
            )
            assert staged.staged_stock_movements == 2
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_preflight_and_rehearsal_agree_on_fractional_line_totals(self):
        self.isolated("""
            services.save_product("FRACTION", "Fractional test item", "demo",
                                  sell=0.05, stock=5)
            with database.db() as c:
                before = snapshot(c)
            pieces = [
                {"barcode":"FRACTION", "qty":"0.333", "price":"0.05"},
                {"barcode":"FRACTION", "qty":"0.333", "price":"0.05"},
                {"barcode":"FRACTION", "qty":"0.333", "price":"0.05"},
            ]
            from velopos_qt.checkout_preflight import PreviewCheckoutPreflight
            checked = PreviewCheckoutPreflight(database).inspect(
                identity=user, shift_id=shift, lines=pieces,
                request_id="sale-fractional-0001", today="2026-11-04",
            )
            assert checked.can_checkout is False
            assert checked.subtotal == Decimal("0.06"), checked
            staged = RollbackOnlySaleRehearsal(database).simulate(
                identity=user, shift_id=shift, lines=pieces,
                request_id="sale-fractional-0001", today="2026-11-04",
            )
            assert staged.subtotal == checked.subtotal, staged
            assert staged.staged_stock_movements == 1
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_stock_price_or_expiry_errors_preserve_full_ledger(self):
        self.isolated("""
            rehearsal = RollbackOnlySaleRehearsal(database)
            with database.db() as c:
                before = snapshot(c)
            for broken in (
                [{"barcode":"RICE","qty":11,"price":45}],
                [{"barcode":"RICE","qty":1,"price":44}],
                [{"barcode":"UNKNOWN","qty":1,"price":1}],
            ):
                try:
                    rehearsal.simulate(
                        identity=user, shift_id=shift, lines=broken,
                        request_id="sale-rejected-00001", today="2026-11-04",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Bad draft accepted")
                with database.db() as c:
                    assert snapshot(c) == before
            with database.db() as c:
                c.execute("INSERT INTO batches "
                          "(barcode,batch_no,expiry_date,qty_remaining) "
                          "VALUES('RICE','EXPIRED','2026-11-01',2)")
                expired_before = snapshot(c)
            try:
                rehearsal.simulate(
                    identity=user, shift_id=shift, lines=lines,
                    request_id="sale-expired-00001", today="2026-11-04",
                )
            except ValueError as exc:
                assert "expired_batch_review:RICE" in str(exc)
            else:
                raise AssertionError("Expired batch did not block rehearsal")
            with database.db() as c:
                assert snapshot(c) == expired_before
        """)


if __name__ == "__main__":
    unittest.main()
