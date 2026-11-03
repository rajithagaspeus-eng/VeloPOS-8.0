"""Headless tests for Phase 6.2 (stock ledger, adjustments, stock-take, batches/FEFO, multi-unit).
Run from the project root:   python -m unittest tests.test_phase6_2 -v"""
import csv, os, re, sqlite3, sys, tempfile, time, unittest
from datetime import datetime, timedelta

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test62_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_phase4 import fresh                                                       # noqa: E402
from velopos import assistant as A, backup as bk, database as dbm, services as svc       # noqa: E402

TODAY = datetime.now().strftime("%Y-%m-%d")
PAST = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
D10 = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
D100 = (datetime.now() + timedelta(days=100)).strftime("%Y-%m-%d")
D200 = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")


def prod(b):
    return svc.get_product(b)


def stock(b):
    return prod(b)["stock_qty"]


def count(table, where="1=1", args=()):
    with dbm.db() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]


def P(b, name=None, **kw):
    kw.setdefault("sell", 100)
    kw.setdefault("cost", 60)
    return svc.save_product(b, name or f"Item {b}", "admin", **kw)


def sell(b, qty, price=100, unit="", paid=None, cashier="admin"):
    it = dict(barcode=b, name=prod(b)["name_en"], qty=qty, price=price)
    if unit:
        it["unit"] = unit
    paid = paid if paid is not None else round(qty * price, 2) + 1
    return svc.create_sale([it], 0, 0, paid, "Cash", "", None, cashier, None)


def moves(b=None, reason=None):
    with dbm.db() as c:
        q, a = "SELECT * FROM stock_moves WHERE 1=1", []
        if b:
            q += " AND barcode=?"; a.append(b)
        if reason:
            q += " AND reason=?"; a.append(reason)
        return c.execute(q + " ORDER BY id", a).fetchall()


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        dbm.settings.set_many({"feat_batches": "0", "feat_multi_unit": "0", "feat_block_expired": "0", "feat_price_history": "1", "low_stock_level": "5"})

    def assertConsistent(self):
        self.assertEqual(svc.verify_stock_ledger(), [], "ledger does not reconcile")
        self.assertEqual(svc.verify_batches(), [], "batch invariant broken")


# ============================================================================ A) ledger
class LedgerTests(Base):
    def test_apply_stock_move_basics(self):
        P("A", stock=10)
        with dbm.db() as c:
            self.assertEqual(svc.apply_stock_move(c, "A", -3, "DAMAGE", "r1", "bob", note="n"), 7)
            self.assertEqual(svc.apply_stock_move(c, "A", 0, "ADJUST"), 7)                    # zero change: ignored
            self.assertEqual(svc.apply_stock_move(c, "A", 0.5, "FOUND"), 7.5)
        m = moves("A")
        self.assertEqual([(x["reason"], x["qty_change"], x["qty_after"]) for x in m], [("OPENING", 10, 10), ("DAMAGE", -3, 7), ("FOUND", 0.5, 7.5)])
        self.assertEqual((m[1]["ref"], m[1]["user"], m[1]["note"]), ("r1", "bob", "n"))
        self.assertConsistent()

    def test_validation_and_rollback(self):
        P("A", stock=2)
        with dbm.db() as c:
            with self.assertRaises(ValueError):
                svc.apply_stock_move(c, "A", -3, "DAMAGE")                                    # below zero
            with self.assertRaises(ValueError):
                svc.apply_stock_move(c, "A", 1, "NONSENSE")
            with self.assertRaises(ValueError):
                svc.apply_stock_move(c, "ZZZ", 1, "FOUND")
        self.assertEqual(stock("A"), 2)
        try:
            with dbm.db() as c:                                                              # an exception after a move rolls the move back too
                svc.apply_stock_move(c, "A", -1, "DAMAGE")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertEqual((stock("A"), len(moves("A"))), (2, 1))

    def test_every_route_is_logged_and_the_ledger_reconciles(self):
        P("A", stock=10, sell=150)
        self.assertEqual([m["reason"] for m in moves("A")], ["OPENING"])
        P("A", stock=10, add=5, sell=150)                                                      # Inventory "+ add stock"
        P("A", stock=20, sell=150)                                                              # absolute edit to 20
        self.assertEqual(stock("A"), 20)
        s = sell("A", 2, 150)
        self.assertEqual(moves("A", "SALE")[0]["ref"], s["invoice"])
        self.assertEqual(stock("A"), 18)
        item = svc.returnable_items(s["invoice"])[0]
        r = svc.create_return(s["invoice"], [(item[0], 1)], "Cash", "test", "admin")
        self.assertEqual((stock("A"), moves("A", "RETURN")[0]["ref"]), (19, r["return_no"]))
        s2 = sell("A", 3, 150)
        svc.void_sale(s2["invoice"], "admin", "oops")
        self.assertEqual((stock("A"), moves("A", "VOID")[0]["ref"]), (19, s2["invoice"]))
        svc.import_products([["A", "Item A", "", "", "60", "150", "0", "6"]], True, "admin")
        self.assertEqual((stock("A"), moves("A", "IMPORT")[0]["qty_change"]), (25, 6))
        svc.import_products([["NEW", "New", "", "", "1", "2", "0", "4"]], True, "admin")
        self.assertEqual(moves("NEW")[0]["reason"], "IMPORT")
        self.assertConsistent()
        svc.factory_reset("sales_stock", "admin", "RESET")
        self.assertEqual((stock("A"), stock("NEW"), moves("A", "RESET")[0]["qty_change"]), (0, 0, -25))
        self.assertConsistent()

    def test_existing_sale_numbers_did_not_change(self):
        P("A", stock=10, cost=100, sell=150)
        s = sell("A", 2, 150)
        self.assertEqual((s["net"], stock("A")), (300, 8))
        with dbm.db() as c:
            row = c.execute("SELECT profit, subtotal FROM sales WHERE invoice_no=?", (s["invoice"],)).fetchone()
        self.assertEqual((row["profit"], row["subtotal"]), (100.0, 300.0))
        si = svc.returnable_items(s["invoice"])
        self.assertEqual(si[0][3:], (2, 0, 150))

    def test_failed_sales_leave_no_trace(self):
        P("A", stock=5)
        P("B", stock=1)
        before = (len(moves()), stock("A"), stock("B"))
        with self.assertRaises(ValueError):
            svc.create_sale([dict(barcode="A", name="A", qty=2, price=100), dict(barcode="B", name="B", qty=2, price=100)], 0, 0, 999, "Cash", "", None, "admin", None)
        self.assertEqual((len(moves()), stock("A"), stock("B")), before)
        with dbm.db() as c:                                                                  # make the 2nd stock move explode mid-sale
            c.execute("CREATE TRIGGER boom BEFORE INSERT ON stock_moves WHEN NEW.barcode='B' AND NEW.reason='SALE' BEGIN SELECT RAISE(ABORT,'boom'); END")
        with self.assertRaises(Exception):
            svc.create_sale([dict(barcode="A", name="A", qty=1, price=100), dict(barcode="B", name="B", qty=1, price=100)], 0, 0, 999, "Cash", "", None, "admin", None)
        self.assertEqual((len(moves()), stock("A"), stock("B")), before)
        self.assertEqual(count("sales"), 0)

    def test_void_and_return_of_a_deleted_product_do_not_crash(self):
        P("A", stock=5)
        s = sell("A", 2)
        item = svc.returnable_items(s["invoice"])[0]
        svc.delete_product("A", "admin")
        svc.create_return(s["invoice"], [(item[0], 1)], "Cash", "x", "admin")
        self.assertIsNone(prod("A"))

    def test_opening_balance_on_upgrade_is_written_exactly_once(self):
        with dbm.db() as c:                                                                  # build a "Phase 6.1" database by hand
            c.execute("DROP TABLE stock_moves")
            c.execute("DELETE FROM settings WHERE key='stock_ledger_ready'")
            c.execute("DELETE FROM products")
            c.execute("INSERT INTO products(barcode,name_en,stock_qty,selling_price) VALUES ('A','A',7,1),('B','B',0,1),('C','C',2.5,1)")
        dbm.init_db()
        m = moves()
        self.assertEqual(sorted((x["barcode"], x["qty_change"], x["reason"]) for x in m), [("A", 7, "OPENING"), ("C", 2.5, "OPENING")])
        dbm.init_db()
        self.assertEqual(len(moves()), 2)                                                      # not duplicated
        self.assertConsistent()
        sell("A", 1)                                                                          # and the shop keeps working
        self.assertConsistent()

    def test_verify_detects_and_repair_fixes_outside_changes(self):
        P("A", stock=10)
        with dbm.db() as c:
            c.execute("UPDATE products SET stock_qty = 13 WHERE barcode='A'")                # someone edited the database directly
        bad = svc.verify_stock_ledger()
        self.assertEqual([(b["barcode"], b["stock"], b["ledger"], b["diff"]) for b in bad], [("A", 13, 10, 3)])
        self.assertEqual(svc.repair_stock_ledger("admin"), 1)
        self.assertEqual((stock("A"), svc.verify_stock_ledger()), (13, []))
        self.assertEqual(moves("A", "EDIT")[-1]["ref"], "LEDGER_REPAIR")
        self.assertEqual(svc.repair_stock_ledger("admin"), 0)

    def test_stock_qty_is_only_written_by_apply_stock_move(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "velopos")
        hits = {}
        for dp, _, files in os.walk(root):
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(dp, f), encoding="utf-8") as fh:
                        src = fh.read()
                    n = len(re.findall(r"UPDATE\s+products\s+SET[^\"']*stock_qty", src, re.I))
                    if n:
                        hits[os.path.relpath(os.path.join(dp, f), root)] = n
        self.assertEqual(hits, {"services.py": 1})                                            # the single statement inside apply_stock_move

    def test_reset_scopes_for_the_new_tables(self):
        dbm.settings.set_many({"feat_batches": "1"})
        P("A", stock=10)
        svc.enable_batches("admin")
        svc.save_unit("A", "dozen", 12, 0, "admin")
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 4, "admin")
        svc.factory_reset("sales_stock", "admin", "RESET")
        self.assertEqual((count("stock_counts"), count("stock_count_lines")), (0, 0))
        self.assertEqual((count("batches"), count("product_units")), (1, 1))                  # batches stay (zeroed), units are product data
        self.assertEqual(svc.list_batches(include_empty=True)[0]["qty_remaining"], 0)
        self.assertGreater(count("stock_moves"), 0)                                            # the ledger keeps the RESET history
        svc.factory_reset("products", "admin", "RESET")
        self.assertEqual([count(t) for t in ("products", "batches", "product_units", "stock_moves")], [0, 0, 0, 0])
        P("B", stock=3)
        svc.factory_reset("everything", "admin", "RESET")
        self.assertEqual(count("stock_moves"), 0)


# ============================================================================ B) adjustments + log
class AdjustTests(Base):
    def setUp(self):
        super().setUp()
        P("A", stock=10, cost=50)
        P("B", stock=4, cost=10)

    def test_each_adjustment_type(self):
        self.assertEqual(svc.adjust_stock("A", -2, "DAMAGE", "u1", "dropped"), 8)
        self.assertEqual(svc.adjust_stock("A", -1, "EXPIRED", "u1"), 7)
        self.assertEqual(svc.adjust_stock("A", -1, "LOST", "u1"), 6)
        self.assertEqual(svc.adjust_stock("A", 2, "FOUND", "u1"), 8)
        self.assertEqual(svc.adjust_stock("A", -3, "ADJUST", "u1", "own use"), 5)
        self.assertEqual(svc.adjust_stock("A", 1.5, "ADJUST", "u1"), 6.5)
        self.assertEqual([m["reason"] for m in moves("A")][1:], ["DAMAGE", "EXPIRED", "LOST", "FOUND", "ADJUST", "ADJUST"])
        self.assertEqual(count("audit_log", "action='STOCK_ADJUST'"), 6)
        self.assertConsistent()

    def test_validation(self):
        for args in (("A", 0, "DAMAGE"), ("A", 3, "DAMAGE"), ("A", 3, "LOST"), ("A", 3, "EXPIRED"), ("A", -3, "FOUND"), ("A", -1, "SALE"), ("A", -1, "NOPE"),
                     ("A", -11, "ADJUST"), ("ZZZ", -1, "DAMAGE")):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.adjust_stock(*args, "u1")
        self.assertEqual((stock("A"), len(moves("A"))), (10, 1))

    def test_log_filters(self):
        svc.adjust_stock("A", -2, "DAMAGE", "u1", "wet box")
        svc.adjust_stock("B", -1, "LOST", "u2", "50% sale item")
        sell("A", 1)
        self.assertEqual(len(svc.stock_log()), 5)                                              # 2 openings + 2 adjustments + 1 sale
        self.assertEqual([r["reason"] for r in svc.stock_log(reason="DAMAGE")], ["DAMAGE"])
        self.assertEqual([r["user"] for r in svc.stock_log(user="u2")], ["u2"])
        self.assertEqual(len(svc.stock_log(barcode="A")), 3)
        self.assertEqual([r["barcode"] for r in svc.stock_log(text="50%")], ["B"])             # literal %
        self.assertEqual([r["barcode"] for r in svc.stock_log(text="wet")], ["A"])
        self.assertEqual(len(svc.stock_log(date_from=TODAY, date_to=TODAY)), 5)
        self.assertEqual(svc.stock_log(date_from="2000-01-01", date_to="2000-01-02"), [])
        self.assertEqual(len(svc.stock_log(limit=2)), 2)
        self.assertEqual(svc.stock_log(limit=2)[0]["reason"], "SALE")                          # newest first

    def test_write_off_value_uses_cost(self):
        svc.adjust_stock("A", -2, "DAMAGE", "u", "")                                           # 2 x 50
        svc.adjust_stock("B", -3, "EXPIRED", "u", "")                                          # 3 x 10
        svc.adjust_stock("A", 1, "FOUND", "u", "")                                             # not a write-off
        self.assertEqual(svc.write_off_value(svc.stock_log()), 130.0)
        self.assertEqual(svc.write_off_value(svc.stock_log(reason="DAMAGE")), 100.0)

    def test_export_csv(self):
        svc.adjust_stock("A", -2, "DAMAGE", "u1", "wet, \"quoted\" box")
        d = tempfile.mkdtemp()
        p1, p2 = os.path.join(d, "a.csv"), os.path.join(d, "b.csv")
        self.assertEqual(svc.export_stock_log(p1, include_cost=False, reason="DAMAGE"), 1)
        svc.export_stock_log(p2, include_cost=True)
        with open(p1, encoding="utf-8-sig") as f1, open(p2, encoding="utf-8-sig") as f2:
            r1, r2 = list(csv.reader(f1)), list(csv.reader(f2))
        self.assertNotIn("value_at_cost", r1[0])
        self.assertEqual((r1[1][1], r1[1][3], r1[1][5], r1[1][9]), ("A", "-2", "DAMAGE", 'wet, "quoted" box'))
        self.assertIn("value_at_cost", r2[0])
        self.assertEqual(len(r2), 4)                                                           # header + 2 openings + 1 damage
        self.assertEqual([r for r in r2 if r[5] == "DAMAGE"][0][-1], "-100.00")


# ============================================================================ D) batches
class BatchTests(Base):
    def setUp(self):
        super().setUp()
        dbm.settings.set_many({"feat_batches": "1"})

    def make(self, b="A", loose=0.0):
        P(b, stock=loose)
        ids = {}
        ids["late"] = svc.receive_batch(b, "L1", D200, 5, 10, "admin")
        ids["early"] = svc.receive_batch(b, "E1", D100, 5, 10, "admin")
        ids["none"] = svc.receive_batch(b, "N1", "", 5, 10, "admin")
        return ids

    def qty(self, bid):
        with dbm.db() as c:
            return c.execute("SELECT qty_remaining FROM batches WHERE id=?", (bid,)).fetchone()[0]

    def test_enable_creates_opening_batches_once_and_trims(self):
        dbm.settings.set_many({"feat_batches": "0"})
        P("A", stock=10, expiry=D100)
        P("B", stock=0)
        P("C", stock=4)
        r = svc.enable_batches("admin")
        self.assertEqual((r["created"], r["trimmed"]), (2, 0))
        b = svc.list_batches("A")
        self.assertEqual((len(b), b[0]["batch_no"], b[0]["expiry_date"], b[0]["qty_remaining"], b[0]["source"]), (1, "OPENING", D100, 10, "MIGRATION"))
        self.assertEqual(svc.enable_batches("admin"), dict(created=0, trimmed=0))              # repeating is harmless
        self.assertEqual(svc.list_batches("B"), [])
        dbm.settings.set_many({"feat_batches": "0"})
        svc.adjust_stock("A", -4, "DAMAGE", "u")                                               # stock changes while tracking is OFF...
        self.assertEqual(svc.list_batches("A")[0]["qty_remaining"], 10)
        self.assertNotEqual(svc.verify_batches(), [])
        dbm.settings.set_many({"feat_batches": "1"})
        self.assertEqual(svc.enable_batches("admin")["trimmed"], 1)                            # ...and switching ON again repairs it
        self.assertEqual((svc.list_batches("A")[0]["qty_remaining"], stock("A")), (6, 6))
        self.assertConsistent()

    def test_receive_batch(self):
        P("A", stock=0)
        bid = svc.receive_batch("A", "  LOT  7 ", D100, 12, 55, "admin")
        b = svc.list_batches("A")[0]
        self.assertEqual((b["id"], b["batch_no"], b["qty_remaining"], b["cost_price"], stock("A")), (bid, "LOT 7", 12, 55, 12))
        self.assertEqual(moves("A")[-1]["batch_id"], bid)
        auto = svc.list_batches("A")[0]["batch_no"]
        svc.receive_batch("A", "", "", 1, 0, "admin")
        self.assertTrue(any(x["batch_no"].startswith("B20") for x in svc.list_batches("A")), auto)
        for args in (("A", "x", "", 0, 0), ("A", "x", "", -1, 0), ("A", "x", "31/12/2030", 1, 0), ("A", "x", "", 1, -5), ("NOPE", "x", "", 1, 0)):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.receive_batch(*args, "admin")
        self.assertEqual(stock("A"), 13)
        self.assertConsistent()

    def test_fefo_takes_the_earliest_expiry_first_then_undated_then_loose(self):
        ids = self.make(loose=5)                                                              # batches 15 + loose 5 = 20
        self.assertEqual(stock("A"), 20)
        s = sell("A", 7)
        self.assertEqual((self.qty(ids["early"]), self.qty(ids["late"]), self.qty(ids["none"])), (0, 3, 5))
        with dbm.db() as c:
            m = c.execute("SELECT batch_id, qty_base FROM sale_item_batches ORDER BY id").fetchall()
        self.assertEqual([(x["batch_id"], x["qty_base"]) for x in m], [(ids["early"], 5), (ids["late"], 2)])
        sell("A", 10)                                                                         # late 3, undated 5, loose 2
        self.assertEqual((self.qty(ids["late"]), self.qty(ids["none"]), stock("A")), (0, 0, 3))
        self.assertEqual(svc.list_batches("A"), [])
        sell("A", 3)                                                                          # only loose stock is left
        self.assertEqual(stock("A"), 0)
        self.assertConsistent()
        self.assertEqual([m["batch_id"] for m in moves("A", "SALE")][:2], [ids["early"], ids["late"]])

    def test_not_enough_stock_changes_nothing(self):
        ids = self.make()
        with self.assertRaises(ValueError):
            sell("A", 16)
        self.assertEqual((stock("A"), self.qty(ids["early"]), count("sale_item_batches"), count("sales")), (15, 5, 0, 0))
        self.assertConsistent()

    def test_void_and_partial_returns_go_back_to_the_same_batches(self):
        ids = self.make()
        s = sell("A", 8)                                                                      # early 5 + late 3
        item = svc.returnable_items(s["invoice"])[0]
        svc.create_return(s["invoice"], [(item[0], 2)], "Cash", "r", "admin")                 # returns go back in allocation order: early first
        self.assertEqual((self.qty(ids["early"]), self.qty(ids["late"])), (2, 2))
        svc.create_return(s["invoice"], [(item[0], 4)], "Cash", "r", "admin")                 # early +3 (to 5), late +1
        self.assertEqual((self.qty(ids["early"]), self.qty(ids["late"])), (5, 3))
        with self.assertRaises(ValueError):
            svc.create_return(s["invoice"], [(item[0], 3)], "Cash", "r", "admin")             # only 2 left to return
        self.assertConsistent()
        s2 = sell("A", 9)
        svc.void_sale(s2["invoice"], "admin", "x")
        self.assertConsistent()
        self.assertEqual([self.qty(ids[k]) for k in ("early", "late", "none")], [5, 3, 5])         # the void put the 9 back where they came from
        self.assertEqual(stock("A"), 13)

    def test_void_restores_exact_batches(self):
        ids = self.make()
        s = sell("A", 12)                                                                     # early 5, late 5, none 2
        self.assertEqual([self.qty(ids[k]) for k in ("early", "late", "none")], [0, 0, 3])
        svc.void_sale(s["invoice"], "admin", "wrong")
        self.assertEqual([self.qty(ids[k]) for k in ("early", "late", "none")], [5, 5, 5])
        self.assertEqual(stock("A"), 15)
        self.assertConsistent()

    def test_blocking_expired_batches(self):
        P("A", stock=0)
        old = svc.receive_batch("A", "OLD", PAST, 5, 1, "admin")
        new = svc.receive_batch("A", "NEW", D100, 5, 1, "admin")
        dbm.settings.set_many({"feat_block_expired": "1"})
        sell("A", 4)                                                                          # skips the expired batch (it would be FEFO-first)
        self.assertEqual((self.qty(old), self.qty(new)), (5, 1))
        with self.assertRaises(ValueError) as cm:
            sell("A", 2)
        self.assertIn("NON-EXPIRED", str(cm.exception))
        self.assertEqual((self.qty(old), self.qty(new), stock("A")), (5, 1, 6))
        dbm.settings.set_many({"feat_block_expired": "0"})
        sell("A", 2)                                                                          # allowed again: expired batch goes first
        self.assertEqual((self.qty(old), self.qty(new)), (3, 1))
        self.assertConsistent()

    def test_expiry_alerts_use_batches_when_on_and_products_when_off(self):
        P("A", stock=0, expiry=D200)                                                          # product-level date is far away
        svc.receive_batch("A", "L9", D10, 3, 1, "admin")
        svc.receive_batch("A", "ZERO", PAST, 1, 1, "admin")
        rows = svc.expiry_alert_rows()
        self.assertEqual({r["name_en"] for _, r in rows}, {"Item A [L9]", "Item A [ZERO]"})
        self.assertEqual(svc.product_expiry_map()["A"], PAST)
        txt = A.respond("expiring soon", A.Ctx(lang="English")).text
        self.assertIn("Item A [L9]", txt)
        dbm.settings.set_many({"feat_batches": "0"})
        self.assertEqual(svc.expiry_alert_rows(), [])                                          # product expiry is 200 days away
        self.assertEqual(svc.product_expiry_map(), {})
        P("A", stock=4, expiry=D10)
        self.assertEqual([r["name_en"] for _, r in svc.expiry_alert_rows()], ["Item A"])

    def test_empty_batches_are_ignored_by_alerts_and_map(self):
        P("A", stock=0)
        b = svc.receive_batch("A", "X", PAST, 2, 1, "admin")
        svc.adjust_stock("A", -2, "DAMAGE", "u", "", batch_id=b)
        self.assertEqual((svc.expiry_alert_rows(), svc.product_expiry_map()), ([], {}))

    def test_inventory_edits_keep_the_invariant(self):
        ids = self.make(loose=2)                                                              # 17 total
        P("A", stock=12)                                                                       # absolute edit DOWN by 5 -> FEFO: early batch
        self.assertEqual((stock("A"), self.qty(ids["early"])), (12, 0))
        P("A", stock=14)                                                                       # up by 2 -> loose stock
        self.assertEqual((stock("A"), self.qty(ids["late"]), self.qty(ids["none"])), (14, 5, 5))
        self.assertConsistent()

    def test_adjustment_from_a_chosen_batch_and_errors(self):
        ids = self.make()
        svc.adjust_stock("A", -2, "DAMAGE", "u", "", batch_id=ids["late"])
        self.assertEqual((self.qty(ids["late"]), self.qty(ids["early"]), stock("A")), (3, 5, 13))
        with self.assertRaises(ValueError):
            svc.adjust_stock("A", -9, "DAMAGE", "u", "", batch_id=ids["late"])                 # that batch has only 3
        svc.adjust_stock("A", 4, "FOUND", "u", "", batch_id=ids["late"])
        self.assertEqual(self.qty(ids["late"]), 7)
        svc.adjust_stock("A", -6, "LOST", "u", "")                                             # automatic: FEFO
        self.assertEqual((self.qty(ids["early"]), self.qty(ids["late"])), (0, 6))
        with self.assertRaises(ValueError):
            svc.adjust_stock("A", -1, "DAMAGE", "u", "", batch_id=99999)
        self.assertConsistent()

    def test_verify_batches_detects_problems(self):
        ids = self.make()
        with dbm.db() as c:
            c.execute("UPDATE batches SET qty_remaining = 50 WHERE id=?", (ids["early"],))
        self.assertEqual(len(svc.verify_batches()), 1)
        with dbm.db() as c:
            c.execute("UPDATE batches SET qty_remaining = -2 WHERE id=?", (ids["early"],))
        self.assertTrue(any("negative" in p["problem"] for p in svc.verify_batches()))

    def test_batches_off_means_old_behaviour(self):
        dbm.settings.set_many({"feat_batches": "0"})
        P("A", stock=10, expiry=D100)
        sell("A", 3)
        self.assertEqual((count("sale_item_batches"), count("batches"), stock("A")), (0, 0, 7))
        self.assertConsistent()


# ============================================================================ E) multi-unit
class UnitTests(Base):
    def setUp(self):
        super().setUp()
        dbm.settings.set_many({"feat_multi_unit": "1"})
        P("RICE", "Rice", stock=10, cost=150, sell=200)                                       # base unit: kg
        svc.set_base_unit("RICE", "kg", "admin")
        svc.save_unit("RICE", "g", 0.001, 0, "admin")
        P("EGG", "Egg", stock=60, cost=20, sell=25)                                           # base unit: pcs
        svc.save_unit("EGG", "dozen", 12, 270, "admin")

    def test_unit_management_and_validation(self):
        u = svc.list_units("RICE")
        self.assertEqual([(x["name"], x["factor"], x["base"]) for x in u], [("kg", 1.0, True), ("g", 0.001, False)])
        self.assertEqual(svc.list_units("NOPE"), [])
        self.assertEqual(svc.unit_price(200, 0.001, 0), 0.2)
        self.assertEqual(svc.unit_price(25, 12, 270), 270)
        self.assertEqual(svc.unit_price(25, 12, 0), 300)
        svc.save_unit("RICE", "G", 0.002, 0, "admin")                                         # same name (case-insensitive) updates
        self.assertEqual(len(svc.list_units("RICE")), 2)
        self.assertEqual(svc.list_units("RICE")[1]["factor"], 0.002)
        for args in (("RICE", "", 1, 0), ("RICE", "x" * 13, 1, 0), ("RICE", "a[b]", 1, 0), ("RICE", "bag", 0, 0), ("RICE", "bag", -1, 0),
                     ("RICE", "bag", 2_000_000, 0), ("RICE", "bag", 5, -1), ("RICE", "KG", 1, 0), ("NOPE", "bag", 1, 0)):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.save_unit(*args, "admin")
        svc.delete_unit("RICE", "g", "admin")
        with self.assertRaises(ValueError):
            svc.delete_unit("RICE", "g", "admin")
        with self.assertRaises(ValueError):
            svc.set_base_unit("EGG", "dozen", "admin")

    def test_sale_in_grams(self):
        s = sell("RICE", 250, price=0.2, unit="g")
        self.assertEqual((s["net"], stock("RICE")), (50.0, 9.75))
        self.assertEqual(s["items"][0][0], "Rice [g]")
        with dbm.db() as c:
            it = c.execute("SELECT * FROM sale_items").fetchone()
            profit = c.execute("SELECT profit FROM sales").fetchone()[0]
        self.assertEqual((it["unit"], it["factor"], it["qty"], it["selling_price"], round(it["cost_price"], 6)), ("g", 0.001, 250, 0.2, 0.15))
        self.assertEqual(profit, 12.5)                                                         # 250 x (0.20 - 0.15)
        self.assertEqual(moves("RICE", "SALE")[0]["qty_change"], -0.25)
        self.assertConsistent()

    def test_sale_in_dozens_with_a_fixed_price(self):
        s = sell("EGG", 2, price=270, unit="dozen")
        self.assertEqual((s["net"], stock("EGG")), (540.0, 36))
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT profit FROM sales").fetchone()[0], 2 * 270 - 24 * 20)

    def test_the_factor_comes_from_the_database_not_the_cart(self):
        s = svc.create_sale([dict(barcode="EGG", name="Egg", qty=1, price=270, unit="dozen", factor=999)], 0, 0, 300, "Cash", "", None, "admin", None)
        self.assertEqual(stock("EGG"), 48)
        with self.assertRaises(ValueError):
            sell("EGG", 1, unit="carton")
        self.assertEqual(stock("EGG"), 48)

    def test_unit_sales_respect_stock_in_base_units(self):
        with self.assertRaises(ValueError):
            sell("RICE", 10001, price=0.2, unit="g")                                            # 10.001 kg > 10 kg
        sell("RICE", 10000, price=0.2, unit="g")                                                # exactly 10 kg
        self.assertEqual(stock("RICE"), 0)
        cart = [dict(barcode="EGG", name="Egg", qty=4, price=270, unit="dozen"), dict(barcode="EGG", name="Egg", qty=15, price=25)]
        with self.assertRaises(ValueError):                                                      # 48 + 15 = 63 > 60 in ONE cart
            svc.create_sale(cart, 0, 0, 9999, "Cash", "", None, "admin", None)
        self.assertEqual(stock("EGG"), 60)

    def test_quantity_decimals_and_rounding(self):
        with self.assertRaises(ValueError):
            sell("RICE", 0.1234, price=200)
        for _ in range(3):
            sell("RICE", 0.333, price=200)
        self.assertEqual(stock("RICE"), 9.001)                                                  # no float noise
        sell("RICE", 1.5, price=200, unit="kg")                                                 # explicit base unit
        self.assertEqual(stock("RICE"), 7.501)
        self.assertConsistent()

    def test_returns_and_voids_in_units(self):
        s = sell("EGG", 2, price=270, unit="dozen")
        item = svc.returnable_items(s["invoice"])[0]
        self.assertEqual((item[2], item[3], item[5]), ("Egg [dozen]", 2, 270))
        r = svc.create_return(s["invoice"], [(item[0], 1)], "Cash", "broken", "admin")
        self.assertEqual((r["amount"], stock("EGG")), (270, 48))                                 # 60 - 24 + 12
        with self.assertRaises(ValueError):
            svc.create_return(s["invoice"], [(item[0], 1.5)], "Cash", "x", "admin")
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT profit_adj FROM returns").fetchone()[0], -(270 - 12 * 20))
        s2 = sell("RICE", 500, price=0.2, unit="g")
        svc.void_sale(s2["invoice"], "admin", "x")
        self.assertEqual(stock("RICE"), 10)
        self.assertConsistent()

    def test_feature_off_ignores_units_completely(self):
        dbm.settings.set_many({"feat_multi_unit": "0"})
        s = sell("EGG", 2, price=25, unit="dozen")                                               # the unit key is ignored
        self.assertEqual((s["net"], stock("EGG"), s["items"][0][0]), (50.0, 58, "Egg"))
        sell("RICE", 0.1234, price=200)                                                          # legacy: no 3-decimal limit
        with dbm.db() as c:
            row = c.execute("SELECT unit, factor FROM sale_items ORDER BY id").fetchone()
        self.assertEqual((row["unit"], row["factor"]), ("", 1))

    def test_units_with_batches_fefo_in_base_units(self):
        dbm.settings.set_many({"feat_batches": "1"})
        P("MILK", "Milk", stock=0, cost=1, sell=10)
        svc.save_unit("MILK", "box", 6, 0, "admin")
        b1 = svc.receive_batch("MILK", "X", D100, 8, 1, "admin")
        b2 = svc.receive_batch("MILK", "Y", D200, 8, 1, "admin")
        sell("MILK", 2, price=60, unit="box")                                                    # 12 base: batch X 8 + batch Y 4
        self.assertEqual([x["qty_remaining"] for x in svc.list_batches("MILK")], [4])
        self.assertEqual(stock("MILK"), 4)
        self.assertConsistent()

    def test_unit_name_is_hidden_when_it_is_the_base_unit(self):
        s = sell("RICE", 2, price=200, unit="kg")
        self.assertEqual(s["items"][0][0], "Rice")


# ============================================================================ C) stock-take
class CountTests(Base):
    def setUp(self):
        super().setUp()
        P("A", stock=10, cost=50, category="Food")
        P("B", stock=4, cost=10, category="Food")
        P("C", stock=7, cost=20, category="Home")

    def test_start_validation_and_single_open_session(self):
        for args in (("bogus", ""), ("category", ""), ("category", "Nothing")):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.start_count(*args, "admin")
        cid = svc.start_count("all", "", "admin", "monthly")
        with self.assertRaises(ValueError):
            svc.start_count("all", "", "admin")
        svc.cancel_count(cid, "admin")
        cid2 = svc.start_count("category", "Food", "admin")
        self.assertGreater(cid2, cid)
        self.assertEqual([r["status"] for r in svc.list_counts()], ["OPEN", "CANCELLED"])

    def test_recording_counts_and_scope(self):
        cid = svc.start_count("category", "Food", "admin")
        svc.record_count(cid, "A", 9, "admin")
        svc.record_count(cid, "A", 8.1234, "admin")                                            # replaces, rounded to 3 decimals
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT counted_qty, system_qty FROM stock_count_lines").fetchone()[:], (8.123, 10))
        for args in (("C", 1), ("NOPE", 1), ("A", -1)):
            with self.assertRaises(ValueError, msg=str(args)):
                svc.record_count(cid, *args, "admin")
        self.assertEqual(count("stock_count_lines"), 1)

    def test_import_counts(self):
        cid = svc.start_count("all", "", "admin")
        rows = [["barcode", "counted"], ["A", "9"], ["B", "x"], ["ZZ", "1"], ["C", "-2"], [], ["C", "6.5"], ["B"]]
        self.assertEqual(svc.import_counts(cid, rows, "admin"), (2, 4))
        self.assertEqual(count("stock_count_lines"), 2)

    def test_report_numbers(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 8, "admin")                                                  # -2 x 50 = -100
        svc.record_count(cid, "B", 6, "admin")                                                  # +2 x 10 = +20
        r = svc.count_report(cid)
        by = {x["barcode"]: x for x in r["lines"]}
        self.assertEqual((by["A"]["variance"], by["A"]["value"], by["B"]["variance"], by["B"]["value"]), (-2, -100, 2, 20))
        self.assertIsNone(by["C"]["counted"])
        t = r["totals"]
        self.assertEqual((t["counted"], t["uncounted"], t["with_variance"], t["net_qty"], t["net_value"], t["shortage_value"], t["surplus_value"]), (2, 1, 2, 0, -80, -100, 20))

    def test_finalize_applies_variances_in_one_transaction(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 8, "admin")
        svc.record_count(cid, "B", 6, "admin")
        svc.record_count(cid, "C", 7, "admin")                                                  # no variance
        res = svc.finalize_count(cid, "boss")
        self.assertEqual((res["adjusted"], res["net_qty"], res["net_value"]), (2, 0, -80))
        self.assertEqual((stock("A"), stock("B"), stock("C")), (8, 6, 7))
        m = moves("A", "COUNT")
        self.assertEqual((len(m), m[0]["qty_change"], m[0]["ref"], m[0]["user"]), (1, -2, f"COUNT#{cid}", "boss"))
        self.assertEqual(moves("C", "COUNT"), [])
        self.assertEqual((svc.list_counts()[0]["status"], count("audit_log", "action='COUNT_FINAL'")), ("FINAL", 1))
        self.assertConsistent()

    def test_uncounted_items_ignore_or_zero(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 10, "admin")
        svc.finalize_count(cid, "admin")
        self.assertEqual((stock("B"), stock("C")), (4, 7))
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 10, "admin")
        svc.finalize_count(cid, "admin", uncounted="zero")
        self.assertEqual((stock("A"), stock("B"), stock("C")), (10, 0, 0))
        self.assertConsistent()
        with self.assertRaises(ValueError):
            svc.finalize_count(svc.start_count("all", "", "admin"), "admin", uncounted="weird")

    def test_nothing_counted_cannot_be_finalized(self):
        cid = svc.start_count("all", "", "admin")
        with self.assertRaises(ValueError):
            svc.finalize_count(cid, "admin")
        self.assertEqual(svc.list_counts()[0]["status"], "OPEN")

    def test_closed_sessions_are_read_only_and_cancel_changes_no_stock(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 1, "admin")
        svc.cancel_count(cid, "admin")
        self.assertEqual(stock("A"), 10)
        cid2 = svc.start_count("all", "", "admin")
        svc.record_count(cid2, "A", 9, "admin")
        svc.finalize_count(cid2, "admin")
        for c_ in (cid, cid2):
            for fn in (lambda: svc.record_count(c_, "A", 1, "admin"), lambda: svc.import_counts(c_, [["A", "1"]], "admin"),
                       lambda: svc.finalize_count(c_, "admin"), lambda: svc.cancel_count(c_, "admin")):
                with self.assertRaises(ValueError):
                    fn()
        with self.assertRaises(ValueError):
            svc.count_report(9999)

    def test_sales_during_a_count_variance_is_against_current_stock(self):
        cid = svc.start_count("all", "", "admin")
        self.assertEqual(svc.count_warnings(cid), [])
        svc.record_count(cid, "A", 10, "admin")                                                 # shelf had 10 when counted
        sell("A", 2)                                                                            # ...then 2 were sold: stock is 8
        w = svc.count_warnings(cid)
        self.assertEqual([(x["barcode"], x["net"], x["moves"]) for x in w], [("A", -2, 1)])
        self.assertEqual(svc.count_report(cid)["lines"][0]["variance"], 2)                      # open report: counted - CURRENT stock
        res = svc.finalize_count(cid, "admin")
        self.assertEqual((stock("A"), res["net_qty"]), (10, 2))                                 # documented behaviour: the count wins
        self.assertEqual(svc.count_warnings(cid)[0]["barcode"], "A")

    def test_warnings_ignore_out_of_scope_items(self):
        cid = svc.start_count("category", "Home", "admin")
        sell("A", 1)
        self.assertEqual(svc.count_warnings(cid), [])
        sell("C", 1)
        self.assertEqual([x["barcode"] for x in svc.count_warnings(cid)], ["C"])

    def test_finished_report_is_frozen(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 8, "admin")
        svc.finalize_count(cid, "admin")
        svc.adjust_stock("A", 5, "FOUND", "u")
        line = [x for x in svc.count_report(cid)["lines"] if x["barcode"] == "A"][0]
        self.assertEqual((line["system"], line["counted"], line["variance"]), (10, 8, -2))

    def test_failure_while_finalizing_rolls_everything_back(self):
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "A", 8, "admin")
        svc.record_count(cid, "B", 6, "admin")
        with dbm.db() as c:
            c.execute("CREATE TRIGGER boom BEFORE INSERT ON stock_moves WHEN NEW.barcode='B' AND NEW.reason='COUNT' BEGIN SELECT RAISE(ABORT,'boom'); END")
        with self.assertRaises(Exception):
            svc.finalize_count(cid, "admin")
        self.assertEqual((stock("A"), stock("B"), svc.list_counts()[0]["status"], moves(reason="COUNT")), (10, 4, "OPEN", []))
        self.assertConsistent()

    def test_shortages_use_fefo_when_batches_are_on(self):
        dbm.settings.set_many({"feat_batches": "1"})
        P("M", stock=0)
        late = svc.receive_batch("M", "L", D200, 5, 1, "admin")
        early = svc.receive_batch("M", "E", D100, 5, 1, "admin")
        cid = svc.start_count("all", "", "admin")
        svc.record_count(cid, "M", 6, "admin")
        svc.finalize_count(cid, "admin")
        left = {b["batch_no"]: b["qty_remaining"] for b in svc.list_batches("M")}
        self.assertEqual(left, {"L": 5, "E": 1})
        self.assertConsistent()
        self.assertEqual(moves("M", "COUNT")[0]["batch_id"], early)


# ============================================================================ upgrade / backup / performance
class SafetyTests(Base):
    def test_a_phase_6_1_database_is_upgraded_without_losing_data(self):
        P("A", stock=5, cost=2, sell=3, category="Food")
        sell("A", 1, 3)
        with dbm.db() as c:                                                                  # strip everything Phase 6.2 added
            for t in ("stock_moves", "batches", "sale_item_batches", "stock_counts", "stock_count_lines", "product_units"):
                c.execute(f"DROP TABLE {t}")
            for col, tbl in (("base_unit", "products"), ("unit", "sale_items"), ("factor", "sale_items")):
                c.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
            c.execute("DELETE FROM settings WHERE key='stock_ledger_ready'")
        dbm.init_db()
        self.assertEqual((stock("A"), prod("A")["category"], prod("A")["base_unit"]), (4, "Food", "pcs"))
        self.assertEqual([(m["reason"], m["qty_change"]) for m in moves("A")], [("OPENING", 4)])
        self.assertEqual(count("sales"), 1)
        s = sell("A", 1, 3)                                                                   # new sales work on the upgraded database
        svc.void_sale(s["invoice"], "admin", "x")
        self.assertConsistent()

    def test_old_sale_rows_without_unit_data_can_still_be_returned_and_voided(self):
        P("A", stock=10)
        s = sell("A", 2)
        with dbm.db() as c:
            c.execute("UPDATE sale_items SET unit=NULL, factor=NULL")                         # rows written before Phase 6.2
        item = svc.returnable_items(s["invoice"])[0]
        svc.create_return(s["invoice"], [(item[0], 1)], "Cash", "x", "admin")
        self.assertEqual(stock("A"), 9)
        s2 = sell("A", 1)
        with dbm.db() as c:
            c.execute("UPDATE sale_items SET unit=NULL, factor=NULL")
        svc.void_sale(s2["invoice"], "admin", "x")
        self.assertEqual(stock("A"), 9)

    def test_backup_and_restore_keep_the_ledger_batches_and_units(self):
        dbm.settings.set_many({"feat_batches": "1"})
        P("A", stock=0)
        svc.receive_batch("A", "B1", D100, 5, 1, "admin")
        svc.save_unit("A", "box", 6, 0, "admin")
        b = bk.create("manual")
        svc.factory_reset("everything", "admin", "RESET")
        bk.restore(b, "admin")
        self.assertEqual((count("stock_moves"), count("batches"), count("product_units"), stock("A")), (1, 1, 1, 5))
        self.assertConsistent()

    def test_new_features_default_off_with_toggles(self):
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_stock_screen", "feat_batches", "feat_block_expired", "feat_multi_unit"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)
        self.assertEqual([dbm.DEFAULTS[k] for k in ("feat_batches", "feat_block_expired", "feat_multi_unit")], ["0", "0", "0"])

    def test_performance_with_many_products_and_batches(self):
        dbm.settings.set_many({"feat_batches": "1"})
        with dbm.db() as c:
            for i in range(3000):
                c.execute("INSERT INTO products(barcode,name_en,stock_qty,selling_price,cost_price) VALUES (?,?,?,?,?)", (f"B{i:05d}", f"Item {i}", 0, 10, 5))
        t = time.time()
        with dbm.db() as c:
            for i in range(0, 3000, 3):
                svc._add_batch(c, f"B{i:05d}", "L1", D100, 20, 5, "admin")
                svc._add_batch(c, f"B{i:05d}", "L2", D200, 20, 5, "admin")
        build = time.time() - t
        t = time.time()
        cart = [dict(barcode=f"B{i:05d}", name="x", qty=25, price=10) for i in range(0, 150, 3)]                # 50 lines, each spans two batches
        svc.create_sale(cart, 0, 0, 99999, "Cash", "", None, "admin", None)
        sale = time.time() - t
        t = time.time()
        self.assertEqual(svc.verify_stock_ledger(), [])
        self.assertEqual(svc.verify_batches(), [])
        verify = time.time() - t
        self.assertLess(sale, 1.0, f"sale {sale:.2f}s")
        self.assertLess(verify, 1.5, f"verify {verify:.2f}s")
        self.assertLess(build, 6.0, f"build {build:.2f}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
