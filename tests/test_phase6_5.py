"""Headless tests for Phase 6.5 (quality pass: input validation, credit-sale returns, product delete, expenses, customers, staff, CSV safety).
Run from the project root:   python -m unittest tests.test_phase6_5 -v"""
import csv, os, sys, tempfile, unittest

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test65_"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_phase4 import fresh                                   # noqa: E402
from velopos import database as dbm, services as svc, security        # noqa: E402

NAN, INF = float("nan"), float("inf")


def one(sql, args=()):
    with dbm.db() as c:
        r = c.execute(sql, args).fetchone()
    return r[0] if r else None


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        svc.save_product("A", "Soap", "admin", cost=20, sell=33.33, stock=100)
        self.cid = svc.add_customer("Kamal", "0771234567", "admin")
        self.sid = svc.open_shift("admin", 1000)

    def sale(self, qty=1, price=100, disc=0, red=0, paid=None, method="Cash", cid=None, sid="default", barcode="A"):
        paid = qty * price - disc if paid is None else paid
        return svc.create_sale([dict(barcode=barcode, name="x", qty=qty, price=price)], disc, red, paid, method, "", cid,
                               "admin", self.sid if sid == "default" else sid)


class SaleValidation(Base):
    def test_bad_lines_are_refused_and_nothing_is_saved(self):
        for kw in (dict(qty=-3), dict(qty=0), dict(price=-50), dict(price=NAN), dict(qty=NAN), dict(price=INF)):
            with self.assertRaises(ValueError, msg=str(kw)):
                self.sale(**kw)
        self.assertEqual(one("SELECT COUNT(*) FROM sales"), 0)
        self.assertEqual(one("SELECT stock_qty FROM products WHERE barcode='A'"), 100)

    def test_discount_redeem_method_and_shift_checks(self):
        with self.assertRaises(ValueError):
            self.sale(price=150, disc=400)
        with self.assertRaises(ValueError):
            self.sale(price=150, red=400, cid=self.cid)
        with self.assertRaises(ValueError):
            self.sale(method="Bitcoin")
        with self.assertRaises(ValueError):
            self.sale(sid=9999)
        svc.close_shift(self.sid, 1000, "", "admin")
        with self.assertRaises(ValueError):
            self.sale()                                                # closed shift
        self.assertEqual(one("SELECT COUNT(*) FROM sales"), 0)

    def test_redeem_does_not_burn_points_on_refusal(self):
        with dbm.db() as c:
            c.execute("UPDATE customers SET loyalty_points=500 WHERE id=?", (self.cid,))
        with self.assertRaises(ValueError):
            self.sale(price=150, red=400, cid=self.cid)
        self.assertEqual(one("SELECT loyalty_points FROM customers WHERE id=?", (self.cid,)), 500)

    def test_a_normal_sale_still_works(self):
        s = self.sale(qty=2, price=100, disc=10)
        self.assertEqual(s["net"], 190.0)


class NumberParsing(Base):
    def test_num_rejects_nan_inf_and_text(self):
        for bad in ("nan", "inf", "-inf", "abc", "", None, NAN, INF):
            with self.assertRaises(ValueError, msg=repr(bad)):
                svc.num(bad)
        self.assertEqual(svc.num(" 12.5 "), 12.5)
        self.assertEqual(svc.num("", allow_blank=True), 0.0)
        with self.assertRaises(ValueError):
            svc.num(-1, minimum=0)

    def test_every_money_and_stock_entry_point_refuses_nan(self):
        calls = [lambda: svc.settle_credit(self.cid, NAN, "admin"),
                 lambda: svc.adjust_stock("A", NAN, "ADJUST", "admin"),
                 lambda: svc.save_product("N", "N", "admin", sell=NAN, stock=1),
                 lambda: svc.save_product("N2", "N2", "admin", sell=1, stock=INF),
                 lambda: svc.open_shift("cashier", NAN),
                 lambda: svc.cash_move(self.sid, "OUT", NAN, "x", "admin"),
                 lambda: svc.add_expense("Rent", "x", NAN, "admin"),
                 lambda: svc.pay_supplier(1, NAN, "Cash", "admin"),
                 lambda: svc.set_credit_limit(self.cid, NAN, "admin")]
        for i, fn in enumerate(calls):
            with self.assertRaises(ValueError, msg=f"call #{i}"):
                fn()
        self.assertIsNone(svc.get_product("N"))
        self.assertIsNone(svc.get_product("N2"))
        self.assertEqual(one("SELECT stock_qty FROM products WHERE barcode='A'"), 100)

    def test_blank_cost_in_save_product_is_zero(self):
        svc.save_product("B", "Blank cost", "admin", cost="", sell="10", stock="", add="")
        self.assertEqual(svc.get_product("B")["cost_price"], 0.0)


class CreditSaleReturns(Base):
    def test_cash_refund_of_a_credit_sale_reduces_the_debt_first(self):
        s = self.sale(qty=2, price=100, method="Credit", paid=0, cid=self.cid)          # customer owes 200
        item = svc.returnable_items(s["invoice"])[0][0]
        before = svc.shift_summary(self.sid)["expected"]
        r = svc.create_return(s["invoice"], [(item, 2)], "Cash", "x", "admin", self.sid)
        self.assertEqual((r["credit_offset"], r["cash_out"]), (200.0, 0.0))
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 0.0)
        self.assertEqual(svc.shift_summary(self.sid)["expected"], before)                # no cash left the drawer

    def test_only_the_unpaid_part_is_offset(self):
        s = self.sale(qty=2, price=100, method="Credit", paid=150, cid=self.cid)         # owes 50, paid 150 in cash
        item = svc.returnable_items(s["invoice"])[0][0]
        r = svc.create_return(s["invoice"], [(item, 2)], "Cash", "x", "admin", self.sid)
        self.assertEqual((r["credit_offset"], r["cash_out"]), (50.0, 150.0))
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 0.0)

    def test_two_partial_returns_never_offset_more_than_the_unpaid_part(self):
        s = self.sale(qty=2, price=100, method="Credit", paid=100, cid=self.cid)         # owes 100
        item = svc.returnable_items(s["invoice"])[0][0]
        r1 = svc.create_return(s["invoice"], [(item, 1)], "Cash", "x", "admin", self.sid)
        r2 = svc.create_return(s["invoice"], [(item, 1)], "Cash", "x", "admin", self.sid)
        self.assertEqual(r1["credit_offset"] + r2["credit_offset"], 100.0)
        self.assertEqual(r1["cash_out"] + r2["cash_out"], 100.0)

    def test_cash_sale_refund_is_unchanged(self):
        s = self.sale(qty=1, price=100)
        item = svc.returnable_items(s["invoice"])[0][0]
        r = svc.create_return(s["invoice"], [(item, 1)], "Cash", "x", "admin", self.sid)
        self.assertEqual((r["credit_offset"], r["cash_out"]), (0.0, 100.0))

    def test_unknown_refund_method_is_refused(self):
        s = self.sale()
        item = svc.returnable_items(s["invoice"])[0][0]
        with self.assertRaises(ValueError):
            svc.create_return(s["invoice"], [(item, 1)], "Bitcoin", "x", "admin", self.sid)


class VoidAfterSettlement(Base):
    def test_void_is_refused_when_it_would_swallow_a_customer_payment(self):
        s = self.sale(qty=1, price=100, method="Credit", paid=0, cid=self.cid)
        svc.settle_credit(self.cid, 60, "admin", self.sid)
        with self.assertRaises(ValueError):
            svc.void_sale(s["invoice"], "admin", "mistake")
        self.assertEqual(one("SELECT status FROM sales WHERE invoice_no=?", (s["invoice"],)), "OK")
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 40.0)

    def test_void_still_works_when_nothing_was_paid_back(self):
        s = self.sale(qty=1, price=100, method="Credit", paid=0, cid=self.cid)
        svc.void_sale(s["invoice"], "admin", "mistake")
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 0.0)


class ProductDelete(Base):
    def test_recreating_a_deleted_barcode_starts_clean(self):
        dbm.settings.set_many({"feat_batches": "1", "feat_multi_unit": "1"})
        svc.save_product("B", "Rice", "admin", cost=10, sell=20, stock=10)
        svc.enable_batches("admin")
        svc.save_unit("B", "box", 12, 0, "admin")
        svc.delete_product("B", "admin")
        self.assertEqual(one("SELECT COUNT(*) FROM batches WHERE barcode='B'"), 0)
        self.assertEqual(one("SELECT COUNT(*) FROM product_units WHERE barcode='B'"), 0)
        svc.save_product("B", "Rice", "admin", cost=10, sell=20, stock=3)
        self.assertEqual(svc.verify_stock_ledger(), [])
        self.assertEqual(svc.verify_batches(), [])
        self.assertEqual([u["name"] for u in svc.list_units("B")], ["pcs"])

    def test_plain_delete_and_recreate_keeps_the_ledger_balanced(self):
        svc.delete_product("A", "admin")
        svc.save_product("A", "Soap again", "admin", cost=1, sell=2, stock=5)
        self.assertEqual(svc.verify_stock_ledger(), [])

    def test_old_bill_can_still_be_returned_after_the_product_is_deleted(self):
        s = self.sale(qty=2, price=100)
        svc.delete_product("A", "admin")
        item = svc.returnable_items(s["invoice"])[0][0]
        self.assertEqual(svc.create_return(s["invoice"], [(item, 1)], "Cash", "x", "admin", self.sid)["amount"], 100.0)


class Expenses(Base):
    def test_drawer_expense_is_one_unit_and_delete_puts_the_cash_back(self):
        base = svc.shift_summary(self.sid)["expected"]
        eid = svc.add_expense("Rent", "shop rent", "250", "admin", self.sid)
        self.assertEqual(svc.shift_summary(self.sid)["expected"], base - 250)
        self.assertTrue(svc.delete_expense(eid, "admin"))
        self.assertEqual(svc.shift_summary(self.sid)["expected"], base)
        self.assertIn("EXPENSE_DELETE", one("SELECT group_concat(action) FROM audit_log"))
        self.assertIn("250.00", one("SELECT detail FROM audit_log WHERE action='EXPENSE_DELETE'"))

    def test_non_drawer_expense_does_not_touch_the_drawer(self):
        base = svc.shift_summary(self.sid)["expected"]
        eid = svc.add_expense("Salary", "x", 100, "admin", None)
        self.assertEqual(svc.shift_summary(self.sid)["expected"], base)
        self.assertFalse(svc.delete_expense(eid, "admin"))

    def test_closed_shift_expense_cannot_be_added_and_nothing_is_saved(self):
        svc.close_shift(self.sid, 1000, "", "admin")
        with self.assertRaises(ValueError):
            svc.add_expense("Rent", "x", 10, "admin", self.sid)
        self.assertEqual(one("SELECT COUNT(*) FROM expenses"), 0)

    def test_zero_and_negative_are_refused(self):
        for bad in (0, -5, "abc"):
            with self.assertRaises(ValueError):
                svc.add_expense("Rent", "x", bad, "admin")


class Customers(Base):
    def test_same_number_in_different_formats_is_a_duplicate(self):
        for dup in ("077 123 4567", "+94771234567", "0771234567"):
            with self.assertRaises(ValueError, msg=dup):
                svc.add_customer("Other", dup, "admin")

    def test_validation(self):
        for name, phone in (("", "0771111111"), ("X", "12"), ("X", "abc")):
            with self.assertRaises(ValueError):
                svc.add_customer(name, phone, "admin")

    def test_edit_and_delete(self):
        svc.update_customer(self.cid, "Kamal P", "0719999999", "admin", "Colombo")
        with dbm.db() as c:
            r = dict(c.execute("SELECT * FROM customers WHERE id=?", (self.cid,)).fetchone())
        self.assertEqual((r["name"], r["phone"], r["address"]), ("Kamal P", "0719999999", "Colombo"))
        other = svc.add_customer("Nimal", "0712222222", "admin")
        with self.assertRaises(ValueError):
            svc.update_customer(other, "Nimal", "0719999999", "admin")                  # takes Kamal's number
        svc.update_customer(self.cid, "Kamal P", "0719999999", "admin")                 # keeping its own number is fine
        svc.delete_customer(other, "admin")
        self.assertIsNone(one("SELECT id FROM customers WHERE id=?", (other,)))

    def test_cannot_delete_a_customer_who_owes_money(self):
        self.sale(price=100, method="Credit", paid=0, cid=self.cid)
        with self.assertRaises(ValueError):
            svc.delete_customer(self.cid, "admin")


class StaffAccounts(Base):
    def test_last_admin_cannot_be_demoted_or_deleted_and_nobody_changes_their_own_role(self):
        with self.assertRaises(ValueError):
            svc.save_user("admin", "", "Cashier", "someone-else")
        with self.assertRaises(ValueError):
            svc.delete_user("admin", "someone-else")
        svc.save_user("boss2", "secret1", "Admin", "admin")
        with self.assertRaises(ValueError):
            svc.save_user("boss2", "", "Cashier", "boss2")                              # own role
        svc.save_user("boss2", "", "Cashier", "admin")                                  # now allowed: another Admin remains
        with self.assertRaises(ValueError):
            svc.save_user("admin", "", "Cashier", "boss2")                              # admin is the last Admin again

    def test_username_and_password_rules(self):
        for u, p in (("a", "secret1"), ("bad name", "secret1"), ("ok.user", "123")):
            with self.assertRaises(ValueError, msg=u):
                svc.save_user(u, p, "Cashier", "admin")
        self.assertTrue(svc.save_user("kasun", "secret1", "Cashier", "admin")["created"])

    def test_user_with_an_open_shift_cannot_be_deleted(self):
        svc.save_user("kasun", "secret1", "Cashier", "admin")
        svc.open_shift("kasun", 0)
        with self.assertRaises(ValueError):
            svc.delete_user("kasun", "admin")


class LoginLock(Base):
    def test_lock_is_stored_in_the_database(self):
        for _ in range(5):
            svc.login_failed("kasun")
        self.assertGreater(svc.login_locked_for("kasun"), 0)
        self.assertEqual(svc.login_locked_for("someone-else"), 0)
        svc.login_ok("kasun")
        self.assertEqual(svc.login_locked_for("kasun"), 0)


class NumberingAndImport(Base):
    def test_invoice_numbers_keep_counting_past_9999(self):
        from datetime import datetime
        pre = "INV" + datetime.now().strftime("%Y%m%d")
        with dbm.db() as c:
            c.execute("INSERT INTO sales(invoice_no, date, time, total_amount, status) VALUES (?,?,?,?,'OK')",
                      (f"{pre}-9999", datetime.now().strftime("%Y-%m-%d"), "10:00:00", 1))
        self.assertEqual(self.sale()["invoice"], f"{pre}-10000")

    def test_scientific_notation_barcodes_are_rejected_but_normal_rows_import(self):
        ok, bad = svc.import_products([["barcode", "name_en"], ["8.90123E+12", "Excel mangled", "", "", "1", "2", "", "5"],
                                       ["8901230000001", "Fine", "", "", "1", "2", "", "5"], ["X1", "NaN price", "", "", "1", "nan", "", "5"]], False, "admin")
        self.assertEqual((ok, bad), (1, 2))
        self.assertIsNotNone(svc.get_product("8901230000001"))


class ReportsAndExports(Base):
    def test_voided_bills_do_not_count_in_insights(self):
        svc.save_product("V", "Void only", "admin", cost=1, sell=10, stock=5)
        s = self.sale(qty=1, price=10, barcode="V")
        svc.void_sale(s["invoice"], "admin", "oops")
        top, low, dead = svc.insights()
        self.assertEqual(list(top), [])                                                 # the only bill was voided
        self.assertIn("V", [r["barcode"] for r in dead])                                # never really sold -> dead stock

    def test_csv_safe_blocks_formulas_but_keeps_numbers(self):
        self.assertEqual(svc.csv_safe("=1+1"), "'=1+1")
        self.assertEqual(svc.csv_safe("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(svc.csv_safe("-5"), "-5")
        self.assertEqual(svc.csv_safe("Kamal"), "Kamal")
        self.assertEqual(svc.csv_safe(12.5), 12.5)

    def test_stock_log_export_is_formula_safe(self):
        svc.adjust_stock("A", -1, "DAMAGE", "admin", note="=cmd|' /C calc'!A0")
        p = os.path.join(tempfile.mkdtemp(), "log.csv")
        svc.export_stock_log(p)
        with open(p, encoding="utf-8-sig") as f:
            text = f.read()
        self.assertNotIn(",=cmd", text)
        self.assertIn("'=cmd", text)


if __name__ == "__main__":
    unittest.main()
