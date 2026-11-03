"""Headless tests for Phase 6.3 (VAT / service charge, credit limit, overdue reminders, suppliers, GRN, payables).
Run from the project root:   python -m unittest tests.test_phase6_3 -v"""
import os, random, sys, tempfile, unittest
from datetime import date, datetime, timedelta

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test63_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_phase4 import fresh                                                       # noqa: E402
from velopos import assistant as A, backup as bk, database as dbm, printing as PR, services as svc   # noqa: E402

TODAY = date.today()
iso = lambda d: d.isoformat()                                                              # noqa: E731
ago = lambda n: iso(TODAY - timedelta(days=n))                                             # noqa: E731


def prod(b):
    return svc.get_product(b)


def count(table, where="1=1", args=()):
    with dbm.db() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]


def one(sql, args=()):
    with dbm.db() as c:
        r = c.execute(sql, args).fetchone()
    return r[0] if r else None


def P(b, name=None, **kw):
    kw.setdefault("sell", 100)
    kw.setdefault("cost", 60)
    kw.setdefault("stock", 100)
    return svc.save_product(b, name or f"Item {b}", "admin", **kw)


def sale(items, discount=0, redeem=0, paid=None, method="Cash", cid=None, override=None, sid=None):
    cart = [dict(barcode=b, name=prod(b)["name_en"], qty=q, price=p) for b, q, p in items]
    if paid is None:
        paid = 10 ** 7 if method != "Credit" else 0
    return svc.create_sale(cart, discount, redeem, paid, method, "", cid, "admin", sid, override_user=override)


def tax_on(mode="Exclusive", pct="18", service=None, vat_on_service=False):
    dbm.settings.set_many({"feat_vat": "1", "vat_mode": mode, "vat_percent": pct, "vat_on_service": "1" if vat_on_service else "0"})
    if service is not None:
        dbm.settings.set_many({"feat_service_charge": "1", "service_percent": str(service)})


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        dbm.settings.set_many({"feat_vat": "0", "feat_service_charge": "0", "vat_on_service": "0", "feat_credit_limit": "0", "feat_overdue_reminders": "0",
                               "feat_batches": "0", "feat_multi_unit": "0", "feat_shift": "1", "low_stock_level": "5", "purchase_cost_policy": "Last cost",
                               "grn_update_cost": "1", "overdue_days": "30", "reminder_cooldown_days": "7", "vat_number": "", "shop_name": "Test Shop"})

    def assertConsistent(self):
        self.assertEqual(svc.verify_stock_ledger(), [])
        self.assertEqual(svc.verify_batches(), [])


# ============================================================================ D) VAT + service charge
class BillMathTests(Base):
    def test_everything_off_is_the_old_arithmetic(self):
        rnd = random.Random(5)
        for _ in range(200):
            lines = [(rnd.randint(1, 900) * rnd.choice([0.5, 1, 1.25, 3.33]), rnd.choice([True, False])) for _ in range(rnd.randint(1, 5))]
            d, r = round(rnd.uniform(0, 50), 2), round(rnd.choice([0, 0, 12.34]), 2)
            old = round(max(0.0, round(sum(a for a, _ in lines), 2) - d - r), 2)
            t = svc.compute_bill(lines, d, r)
            self.assertEqual((t["net"], t["vat"], t["service"]), (old, 0.0, 0.0))

    def test_exclusive_vat_is_added(self):
        tax_on("Exclusive", "18")
        t = svc.compute_bill([(1000, True)])
        self.assertEqual((t["vat"], t["net"], t["base"], t["vat_mode"], t["vat_pct"]), (180.0, 1180.0, 1000.0, "Exclusive", 18.0))

    def test_inclusive_vat_is_extracted(self):
        tax_on("Inclusive", "18")
        t = svc.compute_bill([(1180, True)])
        self.assertEqual((t["vat"], t["net"]), (180.0, 1180.0))
        t = svc.compute_bill([(100, True)])
        self.assertEqual((t["vat"], t["net"]), (round(100 * 18 / 118, 2), 100.0))

    def test_non_taxable_items_and_discount_spread(self):
        tax_on("Exclusive", "18")
        t = svc.compute_bill([(600, True), (400, False)], discount=100)
        self.assertEqual((t["vat"], t["net"]), (97.2, 997.2))                                  # taxable 600 - 60 (its 60% of the discount) = 540
        t = svc.compute_bill([(400, False)], discount=0)
        self.assertEqual((t["vat"], t["net"]), (0.0, 400.0))
        t = svc.compute_bill([(100, True)], discount=500)                                      # discount larger than the bill
        self.assertEqual((t["net"], t["vat"]), (0.0, 0.0))

    def test_service_charge_and_vat_on_service(self):
        tax_on("Exclusive", "18", service=10)
        t = svc.compute_bill([(1000, True)])
        self.assertEqual((t["service"], t["vat"], t["net"]), (100.0, 180.0, 1280.0))           # service is NOT taxed by default
        dbm.settings.set_many({"vat_on_service": "1"})
        t = svc.compute_bill([(1000, True)])
        self.assertEqual((t["vat"], t["net"]), (198.0, 1298.0))
        t = svc.compute_bill([(500, True), (500, False)])                                      # only the taxable share of the service is taxed
        self.assertEqual((t["vat"], t["net"]), (99.0, 1199.0))
        dbm.settings.set_many({"vat_mode": "Inclusive"})
        t = svc.compute_bill([(1180, True)])
        self.assertEqual((t["vat"], t["net"]), (180.0, 1180.0 + 118.0))                        # Inclusive: service added, never taxed

    def test_service_only_and_percent_edge_cases(self):
        dbm.settings.set_many({"feat_service_charge": "1", "service_percent": "12.5"})
        self.assertEqual(svc.compute_bill([(200, True)])["net"], 225.0)
        dbm.settings.set_many({"feat_vat": "1", "vat_percent": "garbage"})
        t = svc.compute_bill([(100, True)])
        self.assertEqual(t["vat"], 0.0)                                                         # bad percent -> 0, never a crash
        dbm.settings.set_many({"vat_percent": "250"})
        self.assertEqual(svc.compute_bill([(100, True)])["vat_pct"], 100.0)                    # clamped to 100
        dbm.settings.set_many({"vat_percent": "18", "service_percent": "-5"})
        self.assertEqual(svc.compute_bill([(100, True)])["service"], 0.0)

    def test_rounding_is_per_bill(self):
        tax_on("Exclusive", "15")
        lines = [(33.33, True)] * 3
        t = svc.compute_bill(lines)
        self.assertEqual((t["sub"], t["vat"], t["net"]), (99.99, 15.0, 114.99))                # 99.99 x 15% = 14.9985 -> 15.00
        tax_on("Inclusive", "15")
        t = svc.compute_bill([(33.33, True)] * 3)
        self.assertEqual(t["vat"], round(99.99 * 15 / 115, 2))


class SaleWithTaxTests(Base):
    def setUp(self):
        super().setUp()
        P("A", cost=60, sell=100)
        P("N", "NonTax", cost=10, sell=50, taxable=False)

    def row(self, inv):
        with dbm.db() as c:
            return c.execute("SELECT * FROM sales WHERE invoice_no=?", (inv,)).fetchone()

    def test_off_sale_is_unchanged(self):
        s = sale([("A", 2, 100)])
        r = self.row(s["invoice"])
        self.assertEqual((s["net"], s["vat"], s["service"], r["vat_amount"], r["service_amount"], r["profit"]), (200.0, 0.0, 0.0, 0.0, 0.0, 80.0))

    def test_exclusive_sale_is_stored_and_paid_checked(self):
        tax_on("Exclusive", "18", service=10)
        with self.assertRaises(ValueError):
            sale([("A", 10, 100)], paid=1000)                                                  # net is 1000 + 100 + 180 = 1280
        self.assertEqual(count("sales"), 0)
        s = sale([("A", 10, 100)], paid=1300)
        self.assertEqual((s["net"], s["vat"], s["service"], s["balance"], s["vat_mode"]), (1280.0, 180.0, 100.0, 20.0, "Exclusive"))
        r = self.row(s["invoice"])
        self.assertEqual((r["total_amount"], r["subtotal"], r["vat_amount"], r["service_amount"], r["vat_pct"], r["service_pct"], r["vat_mode"]),
                         (1280.0, 1000.0, 180.0, 100.0, 18.0, 10.0, "Exclusive"))
        self.assertEqual(r["profit"], 400.0)                                                    # tax and service charge pass through, they are not profit

    def test_inclusive_sale_profit_excludes_the_vat(self):
        tax_on("Inclusive", "18")
        s = sale([("A", 10, 118)])                                                              # prices contain VAT
        self.assertEqual((s["net"], s["vat"]), (1180.0, 180.0))
        self.assertEqual(self.row(s["invoice"])["profit"], 1180 - 600 - 180)

    def test_preview_equals_the_real_bill(self):
        tax_on("Exclusive", "18", service=10, vat_on_service=True)
        cart = [dict(barcode="A", name="A", qty=3, price=100), dict(barcode="N", name="N", qty=2, price=50)]
        pv = svc.preview_bill(cart, 25, 0)
        s = svc.create_sale(cart, 25, 0, 10 ** 6, "Cash", "", None, "admin", None)
        self.assertEqual((pv["net"], pv["vat"], pv["service"]), (s["net"], s["vat"], s["service"]))

    def test_non_taxable_flag_is_saved_and_survives_edits_and_imports(self):
        self.assertEqual((prod("A")["taxable"], prod("N")["taxable"]), (1, 0))
        svc.save_product("N", "NonTax", "admin", sell=55, stock=100)                           # taxable=None keeps the flag
        self.assertEqual(prod("N")["taxable"], 0)
        svc.import_products([["N", "NonTax", "", "", "10", "56", "0", "1"]], True, "admin")
        self.assertEqual(prod("N")["taxable"], 0)
        svc.save_product("N", "NonTax", "admin", sell=55, stock=100, taxable=True)
        self.assertEqual(prod("N")["taxable"], 1)
        tax_on("Exclusive", "10")
        self.assertEqual(sale([("N", 1, 50)])["vat"], 5.0)

    def test_credit_sale_includes_the_tax(self):
        tax_on("Exclusive", "18")
        with dbm.db() as c:
            cid = c.execute("INSERT INTO customers(name, phone) VALUES ('Kamal', '0771234567')").lastrowid
        s = sale([("A", 10, 100)], method="Credit", paid=500, cid=cid)
        self.assertEqual((s["net"], s["credit_due"]), (1180.0, 680.0))
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (cid,)), 680.0)

    def test_returns_reverse_tax_and_service_in_proportion(self):
        tax_on("Exclusive", "18", service=10)
        s = sale([("A", 10, 100)])                                                              # 1000 + 100 + 180 = 1280
        item = svc.returnable_items(s["invoice"])[0]
        r = svc.create_return(s["invoice"], [(item[0], 5)], "Cash", "x", "admin")
        self.assertEqual(r["amount"], 640.0)                                                    # half of the bill including its tax
        with dbm.db() as c:
            ret = c.execute("SELECT * FROM returns").fetchone()
        self.assertEqual((ret["vat_adj"], ret["service_adj"]), (90.0, 50.0))
        self.assertEqual(ret["profit_adj"], -(640 - 90 - 50 - 5 * 60))                          # only the real margin is taken back
        d = svc.report_data(iso(TODAY), iso(TODAY))
        self.assertEqual((d["vat"], d["service"]), (90.0, 50.0))
        self.assertEqual(d["profit"], round(400 - 200, 2))                                      # 400 profit - 200 margin returned

    def test_inclusive_return_and_void(self):
        tax_on("Inclusive", "18")
        s = sale([("A", 10, 118)])
        item = svc.returnable_items(s["invoice"])[0]
        svc.create_return(s["invoice"], [(item[0], 5)], "Cash", "x", "admin")
        d = svc.report_data(iso(TODAY), iso(TODAY))
        self.assertEqual(d["vat"], 90.0)
        s2 = sale([("A", 2, 118)])
        self.assertEqual(svc.report_data(iso(TODAY), iso(TODAY))["vat"], round(90 + 2 * 118 * 18 / 118, 2))
        svc.void_sale(s2["invoice"], "admin", "oops")
        self.assertEqual(svc.report_data(iso(TODAY), iso(TODAY))["vat"], 90.0)                  # voided bills carry no VAT
        self.assertConsistent()

    def test_reprint_data_keeps_the_tax(self):
        tax_on("Exclusive", "18", service=10)
        s = sale([("A", 1, 100)])
        again = svc.load_sale(s["invoice"])
        self.assertEqual((again["vat"], again["service"], again["vat_mode"], again["vat_pct"], again["service_pct"]), (18.0, 10.0, "Exclusive", 18.0, 10.0))

    def test_receipts_and_invoices_show_the_tax_lines(self):
        s = sale([("A", 1, 100)])
        shop = {"name": "S", "address": "a", "phone": "1"}
        off = svc.receipt_text(s, shop, 42, "Rs.")
        self.assertNotIn("VAT", off)
        tax_on("Exclusive", "18", service=10)
        dbm.settings.set_many({"vat_number": "VAT-123"})
        s = sale([("A", 1, 100)])
        txt = svc.receipt_text(s, shop, 42, "Rs.")
        self.assertIn("Service (10%)", txt)
        self.assertIn("VAT (18%)", txt)
        self.assertLess(txt.index("VAT (18%)"), txt.index("NET TOTAL"))
        doc = PR.sale_doc(dbm.settings, svc.load_sale(s["invoice"]))
        labels = [t[0] for t in doc["totals"]]
        self.assertEqual(labels[:5], ["Sub total", "Service charge (10%)", "VAT (18%)", "NET TOTAL", "Paid (Cash)"])
        self.assertEqual(doc["meta"][0], ("VAT No", "VAT-123"))
        tax_on("Inclusive", "18")
        s = sale([("A", 1, 118)])
        self.assertIn("incl. VAT (18%)", svc.receipt_text(s, shop, 42, "Rs."))
        self.assertIn("VAT included (18%)", [t[0] for t in PR.sale_doc(dbm.settings, svc.load_sale(s["invoice"]))["totals"]])

    def test_old_rows_without_tax_columns_still_load(self):
        s = sale([("A", 1, 100)])
        with dbm.db() as c:
            c.execute("UPDATE sales SET vat_amount=NULL, service_amount=NULL, vat_pct=NULL, service_pct=NULL, vat_mode=NULL")
        self.assertEqual(svc.load_sale(s["invoice"])["vat"], 0.0)
        item = svc.returnable_items(s["invoice"])[0]
        self.assertEqual(svc.create_return(s["invoice"], [(item[0], 1)], "Cash", "x", "admin")["amount"], 100.0)


# ============================================================================ E) credit limit
class CreditLimitTests(Base):
    def setUp(self):
        super().setUp()
        P("A", cost=60, sell=100)
        with dbm.db() as c:
            self.cid = c.execute("INSERT INTO customers(name, phone, credit_limit) VALUES ('Kamal', '0771234567', 1000)").lastrowid
        dbm.settings.set_many({"feat_credit_limit": "1"})

    def bal(self):
        return one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,))

    def test_limit_is_enforced_with_a_clear_message_and_changes_nothing(self):
        sale([("A", 8, 100)], method="Credit", cid=self.cid)                                    # 800 on credit
        before = (prod("A")["stock_qty"], self.bal(), count("sales"))
        with self.assertRaises(svc.CreditLimitError) as cm:
            sale([("A", 3, 100)], method="Credit", cid=self.cid)                                # +300 = 1100 > 1000
        self.assertIsInstance(cm.exception, ValueError)
        self.assertIn("1,000.00", str(cm.exception))
        self.assertIn("1,100.00", str(cm.exception))
        self.assertEqual((cm.exception.limit, cm.exception.balance, cm.exception.add), (1000, 800, 300))
        self.assertEqual((prod("A")["stock_qty"], self.bal(), count("sales")), before)
        self.assertConsistent()

    def test_exactly_at_the_limit_and_partial_payments(self):
        sale([("A", 8, 100)], method="Credit", cid=self.cid)
        sale([("A", 2, 100)], method="Credit", cid=self.cid)                                    # exactly 1000: allowed
        self.assertEqual(self.bal(), 1000)
        with self.assertRaises(svc.CreditLimitError):
            sale([("A", 1, 100)], method="Credit", cid=self.cid)
        s = sale([("A", 1, 100)], method="Credit", cid=self.cid, paid=100)                      # nothing goes on credit -> no check
        self.assertEqual(s["credit_due"], 0)
        svc.settle_credit(self.cid, 600, "admin")
        sale([("A", 5, 100)], method="Credit", cid=self.cid, paid=100)                          # only 400 would be added: 400 + 400 = 800 OK
        self.assertEqual(self.bal(), 800)

    def test_limit_zero_means_no_limit_and_feature_off_ignores_it(self):
        svc.set_credit_limit(self.cid, 0, "admin")
        sale([("A", 50, 100)], method="Credit", cid=self.cid)
        self.assertEqual(self.bal(), 5000)
        svc.set_credit_limit(self.cid, 100, "admin")
        dbm.settings.set_many({"feat_credit_limit": "0"})
        sale([("A", 5, 100)], method="Credit", cid=self.cid)                                    # feature OFF: never blocked
        self.assertEqual(self.bal(), 5500)

    def test_the_tax_counts_towards_the_limit(self):
        tax_on("Exclusive", "20")
        with self.assertRaises(svc.CreditLimitError):
            sale([("A", 9, 100)], method="Credit", cid=self.cid)                                # 900 + 20% = 1080 > 1000
        sale([("A", 8, 100)], method="Credit", cid=self.cid)                                    # 960

    def test_admin_override_works_and_is_audited(self):
        sale([("A", 8, 100)], method="Credit", cid=self.cid)
        s = sale([("A", 5, 100)], method="Credit", cid=self.cid, override="admin")
        self.assertEqual((s["credit_due"], self.bal()), (500, 1300))
        self.assertEqual(count("audit_log", "action='CREDIT_LIMIT_OVERRIDE'"), 1)
        self.assertIn("Kamal", one("SELECT detail FROM audit_log WHERE action='CREDIT_LIMIT_OVERRIDE'"))
        with self.assertRaises(ValueError) as cm:                                               # a cashier cannot approve
            sale([("A", 5, 100)], method="Credit", cid=self.cid, override="cash")
        self.assertNotIsInstance(cm.exception, svc.CreditLimitError)
        with self.assertRaises(ValueError):
            sale([("A", 5, 100)], method="Credit", cid=self.cid, override="nobody")
        self.assertEqual(self.bal(), 1300)
        self.assertEqual(count("audit_log", "action='CREDIT_LIMIT_OVERRIDE'"), 1)

    def test_set_limit_validation(self):
        with self.assertRaises(ValueError):
            svc.set_credit_limit(self.cid, -1, "admin")
        with self.assertRaises(ValueError):
            svc.set_credit_limit(99999, 5, "admin")
        svc.set_credit_limit(self.cid, 250.456, "admin")
        self.assertEqual(one("SELECT credit_limit FROM customers WHERE id=?", (self.cid,)), 250.46)
        self.assertEqual(count("audit_log", "action='CREDIT_LIMIT_SET'"), 1)

    def test_admin_password_approval_with_persistent_lockout(self):
        self.assertEqual(svc.approve_with_admin_password("admin123"), "admin")
        self.assertIsNone(svc.approve_with_admin_password("cash123"))                           # a cashier's password is not enough
        for _ in range(4):
            self.assertIsNone(svc.approve_with_admin_password("wrong"))                         # 5 wrong tries in total (the cashier try counted)
        with self.assertRaises(ValueError) as cm:
            svc.approve_with_admin_password("admin123")                                         # locked even for the right password
        self.assertIn("Too many", str(cm.exception))
        svc.clear_fails("override")
        self.assertEqual(svc.approve_with_admin_password("admin123"), "admin")

    def test_walk_in_credit_is_still_refused(self):
        with self.assertRaises(ValueError):
            sale([("A", 1, 100)], method="Credit", cid=None)


# ============================================================================ F) overdue + reminders
class OverdueTests(Base):
    def setUp(self):
        super().setUp()
        P("A")
        with dbm.db() as c:
            self.cid = c.execute("INSERT INTO customers(name, phone) VALUES ('Nimal', '077 123 4567')").lastrowid

    def credit(self, amount, days_ago):
        sale([("A", 1, amount)], method="Credit", cid=self.cid)
        with dbm.db() as c:
            c.execute("UPDATE credit_logs SET date=? WHERE id=(SELECT MAX(id) FROM credit_logs WHERE type='CREDIT_SALE')", (ago(days_ago),))

    def row(self, **kw):
        return next((r for r in svc.overdue_customers(only_overdue=False, **kw) if r["id"] == self.cid), None)

    def test_fifo_payments_settle_the_oldest_credit_first(self):
        self.credit(500, 40)
        self.credit(300, 10)
        r = self.row()
        self.assertEqual((r["balance"], r["overdue"], r["oldest_days"]), (800, 500, 40))
        svc.settle_credit(self.cid, 200, "admin")
        r = self.row()
        self.assertEqual((r["balance"], r["overdue"], r["oldest_days"]), (600, 300, 40))        # the payment went to the 40-day-old bill
        svc.settle_credit(self.cid, 300, "admin")
        self.assertEqual((self.row()["overdue"], self.row()["balance"]), (0, 300))
        self.assertEqual([x["id"] for x in svc.overdue_customers()], [])                         # nothing overdue any more
        svc.settle_credit(self.cid, 300, "admin")
        self.assertIsNone(self.row())                                                            # fully paid: not listed

    def test_threshold_boundaries_and_overrides(self):
        self.credit(100, 30)
        self.assertEqual(self.row()["overdue"], 100)                                             # exactly N days = overdue
        self.assertEqual(self.row(days=31)["overdue"], 0)
        self.assertEqual(self.row(days=0)["overdue"], 100)
        self.assertEqual(self.row(today=TODAY - timedelta(days=5))["overdue"], 0)
        dbm.settings.set_many({"overdue_days": "45"})
        self.assertEqual(self.row()["overdue"], 0)

    def test_sorting_and_filtering(self):
        with dbm.db() as c:
            c2 = c.execute("INSERT INTO customers(name, phone) VALUES ('Alpha', '0771111111')").lastrowid
            c3 = c.execute("INSERT INTO customers(name, phone) VALUES ('Zed', '0772222222')").lastrowid
        self.credit(100, 60)
        for cid, amt, d in ((c2, 400, 50), (c3, 50, 2)):
            sale([("A", 1, amt)], method="Credit", cid=cid)
            with dbm.db() as c:
                c.execute("UPDATE credit_logs SET date=? WHERE customer_id=?", (ago(d), cid))
        self.assertEqual([r["name"] for r in svc.overdue_customers()], ["Alpha", "Nimal"])
        self.assertEqual(len(svc.overdue_customers(only_overdue=False)), 3)

    def test_message_template_is_safe(self):
        self.credit(250, 45)
        r = self.row()
        self.assertEqual(svc.reminder_message(r, "Hi {name}: {amount} for {days}d from {shop}. {unknown} {"), "Hi Nimal: 250.00 for 45d from Test Shop. {unknown} {")
        self.assertIn("Nimal", svc.reminder_message(r))

    def test_reminder_link_log_and_cooldown(self):
        self.credit(250, 45)
        now = datetime.now()
        r = svc.create_reminder(self.cid, "admin")
        self.assertTrue(r["url"].startswith("https://wa.me/94771234567?text="))
        self.assertIn("250.00", r["url"])
        self.assertEqual((r["amount"], count("reminder_log"), count("audit_log", "action='REMINDER'")), (250, 1, 1))
        with self.assertRaises(svc.ReminderCooldown):
            svc.create_reminder(self.cid, "admin")
        self.assertEqual(count("reminder_log"), 1)
        self.assertEqual(svc.create_reminder(self.cid, "admin", force=True)["amount"], 250)
        self.assertEqual(count("reminder_log"), 2)
        self.assertFalse(svc.reminder_allowed(self.cid, now)[0])
        self.assertTrue(svc.reminder_allowed(self.cid, now + timedelta(days=8))[0])
        self.assertTrue(svc.reminder_allowed(self.cid, now + timedelta(days=8))[1])
        self.assertIsNotNone(self.row()["last_reminder"])
        svc.create_reminder(self.cid, "admin", now=now + timedelta(days=8))                      # after the cool-down it is allowed again

    def test_refusals(self):
        with self.assertRaises(ValueError):
            svc.create_reminder(self.cid, "admin")                                               # nothing owed
        self.credit(100, 3)
        with self.assertRaises(ValueError):
            svc.create_reminder(self.cid, "admin")                                               # owed but not overdue
        with dbm.db() as c:
            c.execute("UPDATE credit_logs SET date=?", (ago(60),))
            c.execute("UPDATE customers SET phone=''")
        with self.assertRaises(ValueError) as cm:
            svc.create_reminder(self.cid, "admin")
        self.assertIn("phone", str(cm.exception))
        with self.assertRaises(ValueError):
            svc.create_reminder(99999, "admin")


# ============================================================================ A/B) suppliers + GRN
class SupplierTests(Base):
    def test_add_update_validation(self):
        sid = svc.add_supplier("  Lanka   Foods ", "admin", "Mr Silva", "011", "077", "Colombo", "n")
        r = svc.get_supplier(sid)
        self.assertEqual((r["name"], r["contact"], r["active"]), ("Lanka Foods", "Mr Silva", 1))
        for bad in ("lanka foods", "LANKA FOODS"):
            with self.assertRaises(ValueError):
                svc.add_supplier(bad, "admin")
        for bad in ("", "   ", "x" * 61):
            with self.assertRaises(ValueError):
                svc.add_supplier(bad, "admin")
        sid2 = svc.add_supplier("Other", "admin")
        with self.assertRaises(ValueError):
            svc.update_supplier(sid2, "admin", "Lanka Foods")
        svc.update_supplier(sid, "admin", "Lanka Foods Ltd", active=False)
        self.assertEqual([s["name"] for s in svc.list_suppliers(active_only=True)], ["Other"])
        self.assertEqual(len(svc.list_suppliers()), 2)
        with self.assertRaises(ValueError):
            svc.update_supplier(9999, "admin", "X")
        self.assertEqual(count("audit_log", "action='SUPPLIER_ADD'"), 2)


class GrnTests(Base):
    def setUp(self):
        super().setUp()
        self.sup = svc.add_supplier("Lanka Foods", "admin", phone="011")
        P("A", "Sugar", cost=100, sell=150, stock=10)
        P("B", "Rice", cost=50, sell=80, stock=0)

    def grn(self, items, **kw):
        return svc.create_purchase(self.sup, items, "admin", **kw)

    def test_basic_grn_stock_cost_history_and_numbers(self):
        r = self.grn([dict(barcode="A", qty=10, cost=120), dict(barcode="B", qty=20, cost=55)], supplier_invoice="SI-9", discount=50)
        self.assertEqual((r["total"], r["paid"], r["due"], r["supplier"]), (2250.0, 0, 2250.0, "Lanka Foods"))     # 1200 + 1100 - 50
        self.assertRegex(r["grn_no"], r"^GRN\d{8}-0001$")
        self.assertEqual((prod("A")["stock_qty"], prod("B")["stock_qty"]), (20, 20))
        self.assertEqual((prod("A")["cost_price"], prod("A")["selling_price"]), (120, 150))                      # last cost; retail price untouched
        m = [x for x in svc.stock_log(barcode="A") if x["reason"] == "PURCHASE"]
        self.assertEqual((len(m), m[0]["qty_change"], m[0]["ref"]), (1, 10, r["grn_no"]))
        h = svc.price_history("A")
        self.assertEqual((h[0]["cost_old"], h[0]["cost_new"], h[0]["reason"]), (100, 120, f"GRN {r['grn_no']}"))
        g = svc.get_purchase(r["purchase_id"])
        self.assertEqual((g["header"]["supplier_invoice"], g["header"]["status"], len(g["items"]), g["items"][0]["line_total"]), ("SI-9", "OK", 2, 1200.0))
        self.assertEqual(self.grn([dict(barcode="A", qty=1, cost=120)])["grn_no"][-4:], "0002")
        self.assertConsistent()

    def test_weighted_average_cost(self):
        dbm.settings.set_many({"purchase_cost_policy": "Weighted average"})
        self.grn([dict(barcode="A", qty=10, cost=200)])                                       # 10 @100 + 10 @200
        self.assertEqual(prod("A")["cost_price"], 150)
        self.grn([dict(barcode="A", qty=20, cost=150), dict(barcode="A", qty=20, cost=250)])  # lines are applied one after another
        self.assertEqual(prod("A")["cost_price"], round((20 * 150 + 20 * 150 + 20 * 250) / 60, 4))
        self.grn([dict(barcode="B", qty=5, cost=70)])                                         # no stock before -> simply the new cost
        self.assertEqual(prod("B")["cost_price"], 70)

    def test_cost_update_can_be_switched_off(self):
        dbm.settings.set_many({"grn_update_cost": "0"})
        self.grn([dict(barcode="A", qty=5, cost=999)])
        self.assertEqual((prod("A")["cost_price"], prod("A")["stock_qty"], count("price_history")), (100, 15, 0))

    def test_batches_and_expiry(self):
        dbm.settings.set_many({"feat_batches": "1"})
        r = self.grn([dict(barcode="B", qty=12, cost=50, batch_no="LOT-7", expiry="2031-05-01")])
        b = svc.list_batches("B")[0]
        self.assertEqual((b["batch_no"], b["expiry_date"], b["qty_remaining"], b["source"], b["ref"], b["cost_price"]), ("LOT-7", "2031-05-01", 12, "PURCHASE", r["grn_no"], 50))
        self.assertEqual(svc.get_purchase(r["purchase_id"])["items"][0]["batch_id"], b["id"])
        self.assertConsistent()
        dbm.settings.set_many({"feat_batches": "0"})                                           # simple mode: the expiry goes onto the product
        self.grn([dict(barcode="A", qty=1, cost=100, expiry="2032-01-01")])
        self.assertEqual(prod("A")["expiry_date"], "2032-01-01")

    def test_units(self):
        dbm.settings.set_many({"feat_multi_unit": "1"})
        svc.save_unit("A", "dozen", 12, 0, "admin")
        r = self.grn([dict(barcode="A", qty=2, cost=240, unit="dozen")])                       # 2 dozen at 240 each = 480
        self.assertEqual((r["total"], prod("A")["stock_qty"], prod("A")["cost_price"]), (480.0, 34, 20.0))
        it = svc.get_purchase(r["purchase_id"])["items"][0]
        self.assertEqual((it["unit"], it["factor"], it["base_qty"], it["cost_price"]), ("dozen", 12, 24, 240))
        with self.assertRaises(ValueError):
            self.grn([dict(barcode="A", qty=1, cost=1, unit="carton")])
        self.assertConsistent()

    def test_payment_now_and_the_cash_drawer(self):
        sid = svc.open_shift("admin", 1000)
        before = svc.shift_summary(sid)["expected"]
        r = self.grn([dict(barcode="A", qty=10, cost=100)], paid_now=400, method="Cash", shift_id=sid)
        self.assertEqual((r["due"], one("SELECT SUM(amount) FROM supplier_payments")), (600.0, 400.0))
        self.assertEqual(svc.shift_summary(sid)["expected"], before - 400)                      # the cash left the drawer
        self.assertEqual(one("SELECT reason FROM cash_moves WHERE kind='OUT'"), "Supplier payment: Lanka Foods")
        self.grn([dict(barcode="A", qty=1, cost=100)], paid_now=100, method="Bank", shift_id=sid)
        self.assertEqual(count("cash_moves", "kind='OUT'"), 1)                                  # Bank payments never touch the drawer
        self.grn([dict(barcode="A", qty=1, cost=100)], paid_now=100, method="Cash", shift_id=None)
        self.assertEqual(count("cash_moves", "kind='OUT'"), 1)                                  # cash NOT from the drawer: no cash move
        self.assertEqual(svc.supplier_balances()[0]["balance"], 600 + 0 + 0)

    def test_validation_and_all_or_nothing(self):
        P("C", "Salt", stock=5, cost=10)
        before = (prod("A")["stock_qty"], prod("A")["cost_price"], count("purchases"), count("stock_moves"))
        bad = [([], {}), ([dict(barcode="A", qty=0, cost=1)], {}), ([dict(barcode="A", qty=-1, cost=1)], {}), ([dict(barcode="A", qty=1, cost=-1)], {}),
               ([dict(barcode="ZZ", qty=1, cost=1)], {}), ([dict(barcode="A", qty=1, cost=10)], dict(discount=11)), ([dict(barcode="A", qty=1, cost=10)], dict(paid_now=11)),
               ([dict(barcode="A", qty=1, cost=10)], dict(discount=-1)), ([dict(barcode="A", qty=1, cost=10)], dict(date="31/12/2030")),
               ([dict(barcode="A", qty=1, cost=10, expiry="soon")], {}), ([dict(barcode="A", qty=1, cost=10)], dict(method="Barter", paid_now=1)),
               ([dict(barcode="A", qty=5, cost=777), dict(barcode="C", qty=0, cost=1)], {})]          # a valid first line must NOT survive a bad second line
        for items, kw in bad:
            with self.assertRaises(ValueError, msg=str((items, kw))):
                self.grn(items, **kw)
        with self.assertRaises(ValueError):
            svc.create_purchase(99999, [dict(barcode="A", qty=1, cost=1)], "admin")
        svc.update_supplier(self.sup, "admin", "Lanka Foods", active=False)
        with self.assertRaises(ValueError):
            self.grn([dict(barcode="A", qty=1, cost=1)])                                         # inactive supplier
        self.assertEqual((prod("A")["stock_qty"], prod("A")["cost_price"], count("purchases"), count("stock_moves")), before)

    def test_failure_in_the_middle_rolls_everything_back(self):
        with dbm.db() as c:
            c.execute("CREATE TRIGGER boom BEFORE INSERT ON purchase_items WHEN NEW.barcode='B' BEGIN SELECT RAISE(ABORT,'boom'); END")
        before = (prod("A")["stock_qty"], prod("A")["cost_price"], count("stock_moves"), count("price_history"))
        with self.assertRaises(Exception):
            self.grn([dict(barcode="A", qty=5, cost=300), dict(barcode="B", qty=5, cost=1)], paid_now=100)
        self.assertEqual((prod("A")["stock_qty"], prod("A")["cost_price"], count("stock_moves"), count("price_history")), before)
        self.assertEqual((count("purchases"), count("purchase_items"), count("supplier_payments"), count("audit_log", "action='PURCHASE'")), (0, 0, 0, 0))
        self.assertConsistent()

    def test_void_when_the_stock_is_untouched(self):
        r = self.grn([dict(barcode="A", qty=10, cost=100)], paid_now=300, method="Bank")
        svc.void_purchase(r["purchase_id"], "admin", "wrong supplier")
        self.assertEqual(prod("A")["stock_qty"], 10)
        h = svc.get_purchase(r["purchase_id"])["header"]
        self.assertEqual((h["status"], h["void_reason"], h["void_user"]), ("VOID", "wrong supplier", "admin"))
        self.assertEqual(svc.supplier_balances()[0]["balance"], -300)                            # the payment stays as an advance
        self.assertEqual(count("audit_log", "action='PURCHASE_VOID'"), 1)
        for fn in (lambda: svc.void_purchase(r["purchase_id"], "admin", "again"), lambda: svc.void_purchase(9999, "admin", "x")):
            with self.assertRaises(ValueError):
                fn()
        self.assertConsistent()

    def test_void_is_refused_when_the_stock_was_sold_or_the_batch_used(self):
        r = self.grn([dict(barcode="A", qty=5, cost=100)])
        sale([("A", 12, 150)])                                                                   # 15 in stock, 12 sold -> only 3 left of the 5 received
        with self.assertRaises(ValueError) as cm:
            svc.void_purchase(r["purchase_id"], "admin", "x")
        self.assertIn("already been sold", str(cm.exception))
        self.assertEqual((prod("A")["stock_qty"], svc.get_purchase(r["purchase_id"])["header"]["status"]), (3, "OK"))
        svc.save_product("B", "Rice", "admin", cost=50, sell=80, stock=10)                          # loose stock, so the product stock alone would be enough
        dbm.settings.set_many({"feat_batches": "1"})
        r2 = self.grn([dict(barcode="B", qty=10, cost=50, batch_no="L1")])
        sale([("B", 4, 80)])                                                                         # FEFO takes these 4 from the batch
        with self.assertRaises(ValueError) as cm:
            svc.void_purchase(r2["purchase_id"], "admin", "x")
        self.assertIn("batch", str(cm.exception).lower())
        with self.assertRaises(ValueError):
            svc.void_purchase(r2["purchase_id"], "admin", "  ")                                  # a reason is required
        self.assertConsistent()

    def test_void_takes_the_stock_out_of_the_right_batch(self):
        dbm.settings.set_many({"feat_batches": "1"})
        r = self.grn([dict(barcode="B", qty=10, cost=50, batch_no="L1", expiry="2030-01-01")])
        svc.void_purchase(r["purchase_id"], "admin", "mistake")
        self.assertEqual((prod("B")["stock_qty"], svc.list_batches("B")), (0, []))
        self.assertConsistent()

    def test_list_purchases_and_the_printable_document(self):
        r = self.grn([dict(barcode="A", qty=2, cost=100, batch_no="Q", expiry="2030-02-02")], supplier_invoice="X1", discount=20, paid_now=50, method="Bank")
        rows = svc.list_purchases()
        self.assertEqual((rows[0]["supplier"], rows[0]["paid_total"], rows[0]["total"]), ("Lanka Foods", 50, 180))
        self.assertEqual(len(svc.list_purchases(status="VOID")), 0)
        self.assertEqual(len(svc.list_purchases(supplier_id=self.sup)), 1)
        doc = PR.grn_doc(dbm.settings, svc.get_purchase(r["purchase_id"]))
        self.assertEqual(doc["title"], "GOODS RECEIVED NOTE")
        self.assertIn(("Supplier invoice", "X1"), doc["meta"])
        self.assertEqual([t[0] for t in doc["totals"]], ["Sub total", "Discount", "TOTAL", "Paid", "Balance due"])
        self.assertEqual(doc["totals"][-1][1].replace(",", "").split()[-1], "130.00")
        self.assertIn("Batch Q", doc["items"][0][4])
        self.assertTrue(PR.open_html.__name__)


# ============================================================================ C) payments + payables
class PayablesTests(Base):
    def setUp(self):
        super().setUp()
        self.s1 = svc.add_supplier("Alpha", "admin")
        self.s2 = svc.add_supplier("Beta", "admin")
        P("A", cost=10, sell=20, stock=0)

    def buy(self, sup, amount, days_ago=0, **kw):
        r = svc.create_purchase(sup, [dict(barcode="A", qty=1, cost=amount)], "admin", date=ago(days_ago), **kw)
        return r

    def test_balances_and_payments(self):
        self.buy(self.s1, 1000)
        self.buy(self.s1, 500)
        self.buy(self.s2, 200)
        self.assertEqual([(b["name"], b["balance"]) for b in svc.supplier_balances()], [("Alpha", 1500), ("Beta", 200)])
        self.assertEqual(svc.pay_supplier(self.s1, 600, "Bank", "admin", "TT-1", "part"), 900)
        self.assertEqual(svc.payables_total(), 1100)
        p = svc.list_supplier_payments(self.s1)
        self.assertEqual((len(p), p[0]["amount"], p[0]["method"], p[0]["ref"], p[0]["user"]), (1, 600, "Bank", "TT-1", "admin"))
        self.assertEqual(count("audit_log", "action='SUPPLIER_PAYMENT'"), 1)

    def test_payment_validation(self):
        r = self.buy(self.s1, 1000)
        for args in ((0, "Cash"), (-5, "Cash"), (10, "Barter")):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.pay_supplier(self.s1, args[0], args[1], "admin")
        with self.assertRaises(ValueError) as cm:
            svc.pay_supplier(self.s1, 1000.01, "Cash", "admin")
        self.assertIn("more than the balance", str(cm.exception))
        with self.assertRaises(ValueError):
            svc.pay_supplier(99999, 5, "Cash", "admin")
        with self.assertRaises(ValueError):
            svc.pay_supplier(self.s2, 5, "Cash", "admin", purchase_id=r["purchase_id"])          # that GRN belongs to another supplier
        svc.pay_supplier(self.s1, 1000, "Cash", "admin", purchase_id=r["purchase_id"])
        self.assertEqual(svc.list_purchases()[0]["paid_total"], 1000)
        self.assertEqual(svc.pay_supplier(self.s1, 50, "Cash", "admin", allow_advance=True), -50)  # advance only when asked for
        self.assertEqual(svc.payables_total(), 0)                                                # an advance does not reduce what is owed elsewhere
        self.assertEqual(count("supplier_payments"), 2)

    def test_cash_payments_leave_the_drawer_only_with_a_shift(self):
        self.buy(self.s1, 1000)
        sid = svc.open_shift("admin", 500)
        e0 = svc.shift_summary(sid)["expected"]
        svc.pay_supplier(self.s1, 100, "Cash", "admin", shift_id=sid)
        self.assertEqual(svc.shift_summary(sid)["expected"], e0 - 100)
        svc.pay_supplier(self.s1, 100, "Cash", "admin")
        svc.pay_supplier(self.s1, 100, "Cheque", "admin", shift_id=sid)
        self.assertEqual((count("cash_moves", "kind='OUT'"), svc.shift_summary(sid)["expected"]), (1, e0 - 100))

    def test_voided_purchases_are_not_owed(self):
        r = self.buy(self.s1, 1000)
        self.buy(self.s1, 300)
        svc.void_purchase(r["purchase_id"], "admin", "dup")
        self.assertEqual(svc.supplier_balances()[0]["balance"], 300)

    def test_ageing_buckets_with_fifo_payments(self):
        self.buy(self.s1, 100, 100)                                                              # 90+
        self.buy(self.s1, 200, 70)                                                               # 61-90
        self.buy(self.s1, 400, 40)                                                               # 31-60
        self.buy(self.s1, 800, 5)                                                                # 0-30
        self.buy(self.s2, 50, 31)
        rows, tot = svc.payables_ageing()
        a = next(r for r in rows if r["name"] == "Alpha")
        self.assertEqual((a["b0"], a["b1"], a["b2"], a["b3"], a["balance"]), (800, 400, 200, 100, 1500))
        svc.pay_supplier(self.s1, 250, "Bank", "admin")                                          # settles 100 (90+) and 150 of the 200
        a = next(r for r in svc.payables_ageing()[0] if r["name"] == "Alpha")
        self.assertEqual((a["b0"], a["b1"], a["b2"], a["b3"]), (800, 400, 50, 0))
        self.assertEqual(tot["balance"], 1550)
        rows, tot = svc.payables_ageing(today=TODAY + timedelta(days=60))
        self.assertEqual(rows[0]["name"], "Alpha")
        self.assertGreater(tot["b3"], 0)
        svc.pay_supplier(self.s2, 50, "Bank", "admin")
        self.assertEqual([r["name"] for r in svc.payables_ageing()[0]], ["Alpha"])               # fully paid suppliers disappear


# ============================================================================ G) assistant, summary, resets, upgrade
class IntegrationTests(Base):
    def setUp(self):
        super().setUp()
        self.s1 = svc.add_supplier("Alpha Foods", "admin")
        P("A", cost=10, sell=20, stock=0)
        svc.create_purchase(self.s1, [dict(barcode="A", qty=10, cost=100)], "admin", paid_now=250, method="Bank")

    def ask(self, q, lang="English", can=None):
        return A.respond(q, A.Ctx(lang=lang, can=can or (lambda p: True), cfg=dbm.settings))

    def test_payables_questions_in_every_language(self):
        table = [("who do I owe", "English"), ("supplier balances", "English"), ("supplier naya kiyada", "Auto (match my question)"),
                 ("සැපයුම්කරුවන්ට ගෙවිය යුතු මුදල", "Auto (match my question)"), ("சப்ளையருக்கு செலுத்த வேண்டிய தொகை", "Auto (match my question)"),
                 ("सप्लायर को कितना देना है", "Auto (match my question)"), ("المستحقات للموردين", "Auto (match my question)"), ("a quién debo", "Auto (match my question)")]
        for q, lang in table:
            r = self.ask(q, lang)
            self.assertEqual(r.intent, "payables", q)
            self.assertIn("750.00", r.text, q)
            self.assertIn("Alpha Foods", r.text, q)
        self.assertEqual(self.ask("who owes the most").intent, "credit_owed")                    # customers are still customers
        self.assertEqual(self.ask("who do I owe", can=lambda p: False).intent, "denied")
        svc.pay_supplier(self.s1, 750, "Bank", "admin")
        self.assertIn("do not owe", self.ask("who do I owe").text)

    def test_daily_summary_shows_payables_and_vat(self):
        txt = A.build_daily_summary(A.Ctx(lang="English", cfg=dbm.settings), "en")["text"]
        self.assertIn("Owed to suppliers: Rs. 750.00", txt)
        self.assertNotIn("VAT collected", txt)
        tax_on("Exclusive", "18")
        sale([("A", 2, 20)])
        txt = A.build_daily_summary(A.Ctx(lang="English", cfg=dbm.settings), "en")["text"]
        self.assertIn("VAT collected: Rs. 7.20", txt)
        for lg in ("si", "ta", "hi", "ar", "es"):
            t = A.build_daily_summary(A.Ctx(lang="English", cfg=dbm.settings), lg)["text"]
            self.assertIn("750.00", t)
            self.assertIn("7.20", t)
        cashier = A.build_daily_summary(A.Ctx(lang="English", can=lambda p: False, cfg=dbm.settings), "en")["text"]
        self.assertNotIn("supplier", cashier.lower())

    def test_factory_reset_scopes(self):
        svc.pay_supplier(self.s1, 10, "Bank", "admin")
        with dbm.db() as c:
            cid = c.execute("INSERT INTO customers(name, phone) VALUES ('K', '0771')").lastrowid
            c.execute("INSERT INTO reminder_log(customer_id, ts, channel, amount, message, user) VALUES (?, 'x', 'WhatsApp', 1, 'm', 'a')", (cid,))
        svc.factory_reset("products", "admin", "RESET")
        self.assertEqual((count("suppliers"), count("purchases"), count("supplier_payments")), (1, 1, 2))   # money records survive a products-only wipe
        svc.factory_reset("sales_stock", "admin", "RESET")
        self.assertEqual((count("suppliers"), count("purchases"), count("purchase_items"), count("supplier_payments"), count("reminder_log")), (1, 0, 0, 0, 0))
        self.assertEqual(svc.payables_total(), 0)
        svc.factory_reset("everything", "admin", "RESET")
        self.assertEqual(count("suppliers"), 0)

    def test_backup_and_restore_keep_the_new_tables(self):
        sid = svc.open_shift("admin", 100)
        svc.pay_supplier(self.s1, 10, "Cash", "admin", shift_id=sid)
        b = bk.create("manual")
        svc.factory_reset("everything", "admin", "RESET")
        bk.restore(b, "admin")
        self.assertEqual((count("suppliers"), count("purchases"), count("supplier_payments"), svc.payables_total()), (1, 1, 2, 740))

    def test_an_older_database_is_upgraded(self):
        sale([("A", 1, 20)])
        with dbm.db() as c:                                                                        # strip everything Phase 6.3 added
            for t in ("suppliers", "purchases", "purchase_items", "supplier_payments", "reminder_log"):
                c.execute(f"DROP TABLE {t}")
            for tbl, col in (("sales", "vat_amount"), ("sales", "service_amount"), ("sales", "vat_pct"), ("sales", "service_pct"), ("sales", "vat_mode"),
                             ("returns", "vat_adj"), ("returns", "service_adj"), ("products", "taxable"), ("customers", "credit_limit")):
                c.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
        dbm.init_db()
        self.assertEqual((prod("A")["taxable"], count("sales")), (1, 1))
        s = sale([("A", 1, 20)])
        self.assertEqual(s["vat"], 0.0)
        tax_on("Exclusive", "10")
        self.assertEqual(sale([("A", 1, 20)])["net"], 22.0)
        self.assertConsistent()

    def test_toggles_and_defaults(self):
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_suppliers", "feat_vat", "feat_service_charge", "vat_on_service", "feat_credit_limit", "feat_overdue_reminders"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)
        for k in ("feat_vat", "feat_service_charge", "feat_credit_limit", "feat_overdue_reminders", "vat_on_service"):
            self.assertEqual(dbm.DEFAULTS[k], "0", k)                                              # everything that changes billing ships OFF
        self.assertEqual(dbm.DEFAULTS["feat_suppliers"], "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
