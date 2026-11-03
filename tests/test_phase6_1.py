"""Headless tests for Phase 6.1 (catalogue: categories, product save/import, price history, bulk price update, pictures, thumbnails).
Run from the project root:   python -m unittest tests.test_phase6_1 -v"""
import glob, os, sys, tempfile, time, unittest

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test61_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image                                                                     # noqa: E402

from tests.test_phase4 import fresh                                                       # noqa: E402
from velopos import database as dbm, services as svc, thumbs                              # noqa: E402


def count(table, where="1=1", args=()):
    with dbm.db() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]


def prod(b):
    return svc.get_product(b)


def make_picture(path, size=(3000, 2000), mode="RGB", color=(200, 30, 30)):
    Image.new(mode, size, color).save(path)
    return path


def wipe_pictures():
    for f in glob.glob(os.path.join(svc.image_dir(), "*")):
        if os.path.isfile(f):
            os.remove(f)
    thumbs.CACHE.clear()
    thumbs.clear_disk()


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        wipe_pictures()
        dbm.settings.set_many({"feat_price_history": "1", "low_stock_level": "5"})


# ============================================================================ categories
class CategoryTests(Base):
    def test_add_list_duplicates_and_validation(self):
        self.assertEqual(svc.add_category("  Dairy   Products ", "admin"), "Dairy Products")
        svc.add_category("Bakery", "admin")
        self.assertEqual([r["name"] for r in svc.list_categories()], ["Dairy Products", "Bakery"])
        for bad in ("dairy products", "DAIRY PRODUCTS", "Bakery"):
            with self.assertRaises(ValueError):
                svc.add_category(bad, "admin")
        for bad in ("", "   ", "a,b", "a;b", "a|b", "x" * 41):
            with self.assertRaises(ValueError):
                svc.add_category(bad, "admin")
        self.assertEqual(count("audit_log", "action='CATEGORY_ADD'"), 2)

    def test_rename_moves_the_products_too(self):
        svc.add_category("Drinks", "admin")
        svc.save_product("1", "Cola", "admin", sell=100, category="Drinks")
        svc.save_product("2", "Water", "admin", sell=50, category="drinks")               # different case -> same category
        svc.save_product("3", "Rice", "admin", sell=200, category="")
        self.assertEqual(prod("2")["category"], "Drinks")
        self.assertEqual(svc.rename_category("Drinks", "Beverages", "admin"), 2)
        self.assertEqual(prod("1")["category"], "Beverages")
        self.assertEqual(prod("3")["category"], "")
        svc.add_category("Food", "admin")
        with self.assertRaises(ValueError):
            svc.rename_category("Food", "beverages", "admin")                             # clash
        svc.rename_category("Beverages", "BEVERAGES", "admin")                            # only the case changes: allowed
        self.assertEqual(prod("1")["category"], "BEVERAGES")
        with self.assertRaises(ValueError):
            svc.rename_category("Nope", "X", "admin")

    def test_delete_keeps_the_products(self):
        svc.save_product("1", "Cola", "admin", sell=100, category="Drinks")
        self.assertEqual(svc.delete_category("Drinks", "admin"), 1)
        self.assertEqual(prod("1")["category"], "")
        self.assertEqual(count("products"), 1)
        self.assertEqual(svc.list_categories(), [])
        with self.assertRaises(ValueError):
            svc.delete_category("Drinks", "admin")

    def test_reorder(self):
        for n in ("A", "B", "C"):
            svc.add_category(n, "admin")
        svc.move_category("C", "up", "admin")
        self.assertEqual([r["name"] for r in svc.list_categories()], ["A", "C", "B"])
        svc.move_category("A", "up", "admin")                                              # already first: no change, no error
        svc.move_category("A", "down", "admin")
        self.assertEqual([r["name"] for r in svc.list_categories()], ["C", "A", "B"])
        svc.move_category("B", "down", "admin")
        self.assertEqual([r["name"] for r in svc.list_categories()], ["C", "A", "B"])

    def test_counts(self):
        svc.add_category("Empty", "admin")
        svc.save_product("1", "a", "admin", category="Drinks")
        svc.save_product("2", "b", "admin", category="drinks")
        svc.save_product("3", "c", "admin")
        self.assertEqual(svc.category_counts(), {"Drinks": 2, "Empty": 0, "": 1})

    def test_new_category_typed_in_the_product_form_is_created(self):
        svc.save_product("1", "Cola", "admin", category="Soft Drinks")
        self.assertEqual([r["name"] for r in svc.list_categories()], ["Soft Drinks"])
        svc.save_product("2", "Fanta", "admin", category="soft drinks")                    # reuses the stored spelling
        self.assertEqual(prod("2")["category"], "Soft Drinks")
        self.assertEqual(len(svc.list_categories()), 1)


# ============================================================================ list / search / pagination
class ListTests(Base):
    def setUp(self):
        super().setUp()
        for i in range(25):
            svc.save_product(f"B{i:02d}", f"Item {i:02d}", "admin", sell=10 + i, stock=0 if i % 5 == 0 else 10, category="Odd" if i % 2 else "Even" if i % 4 == 0 else "")
        svc.save_product("PCT", "50% Off Sticker", "admin", sell=1, stock=3)
        svc.save_product("USC", "Under_score", "admin", sell=1, stock=3)

    def test_pagination(self):
        rows, total = svc.list_products(limit=10, offset=0)
        self.assertEqual((len(rows), total), (10, 27))
        rows2, _ = svc.list_products(limit=10, offset=10)
        rows3, _ = svc.list_products(limit=10, offset=20)
        self.assertEqual(len(rows3), 7)
        got = [r["barcode"] for r in rows + rows2 + rows3]
        self.assertEqual(len(set(got)), 27)                                               # no duplicates / gaps
        self.assertEqual(got, sorted(got, key=lambda b: (prod(b)["name_en"].lower(), b)))
        self.assertEqual(len(svc.list_products(limit=None)[0]), 27)
        self.assertEqual(svc.list_products(limit=10, offset=500)[0], [])

    def test_category_filter(self):
        self.assertEqual(svc.list_products(category="Odd", limit=None)[1], 12)
        self.assertEqual(svc.list_products(category="odd", limit=None)[1], 12)             # case-insensitive
        unc = svc.list_products(category="", limit=None)[1]
        self.assertEqual(unc, 27 - 12 - svc.list_products(category="Even", limit=None)[1])
        self.assertEqual(svc.list_products(category="Nothing", limit=None)[1], 0)

    def test_search_and_wildcards_are_literal(self):
        self.assertEqual(svc.list_products("item 07", limit=None)[1], 1)
        self.assertEqual([r["barcode"] for r in svc.list_products("50%", limit=None)[0]], ["PCT"])
        self.assertEqual([r["barcode"] for r in svc.list_products("_", limit=None)[0]], ["USC"])
        self.assertEqual(svc.list_products("B07", limit=None)[1], 1)                      # barcode
        self.assertEqual(svc.list_products("zzz", limit=None)[1], 0)

    def test_only_in_stock_and_combination(self):
        rows, total = svc.list_products(only_in_stock=True, limit=None)
        self.assertTrue(all(r["stock_qty"] > 0 for r in rows))
        self.assertEqual(total, 27 - 5)
        rows, total = svc.list_products("item", "Odd", 5, 0, True)
        self.assertEqual(total, 10)                                                          # 12 odd items, 2 of them (05, 15) out of stock
        self.assertEqual(len(rows), 5)


# ============================================================================ save / delete / import
class SaveTests(Base):
    def test_create_update_and_stock_add(self):
        r = svc.save_product("1", " Sugar ", "admin", name_local="සීනි", cost=100, sell=150, wholesale=140, stock=10, add=5, expiry="2030-01-31", warranty="x")
        self.assertEqual((r["created"], r["stock"], r["price_changed"]), (True, 15, False))
        p = prod("1")
        self.assertEqual((p["name_en"], p["stock_qty"], p["cost_price"], p["wholesale_price"], p["category"]), ("Sugar", 15, 100, 140, ""))
        r = svc.save_product("1", "Sugar", "admin", cost=100, sell=160, wholesale=140, stock=15, add=0)
        self.assertEqual((r["created"], r["price_changed"]), (False, True))
        self.assertEqual(count("audit_log", "action='PRODUCT_SAVE'"), 2)

    def test_validation_changes_nothing(self):
        svc.save_product("1", "Sugar", "admin", sell=150, stock=10)
        for kw in (dict(stock=5, add=-6), dict(sell=-1), dict(wholesale=-1), dict(cost=-1), dict(expiry="31/12/2030"), dict(expiry="2030-13-40")):
            with self.assertRaises(ValueError):
                svc.save_product("1", "Hacked", "admin", **{"sell": 150, **kw})
        for b, n in (("", "x"), ("1", ""), ("  ", "x")):
            with self.assertRaises(ValueError):
                svc.save_product(b, n, "admin")
        p = prod("1")
        self.assertEqual((p["name_en"], p["stock_qty"], p["selling_price"]), ("Sugar", 10, 150))

    def test_user_without_see_cost_cannot_change_cost(self):
        svc.save_product("1", "Sugar", "admin", cost=100, sell=150)
        svc.save_product("1", "Sugar", "cashier", cost=None, sell=170)                    # cost not supplied -> kept
        self.assertEqual(prod("1")["cost_price"], 100)
        h = svc.price_history("1")
        self.assertEqual((h[0]["cost_old"], h[0]["cost_new"]), (100, 100))
        svc.save_product("2", "New", "cashier", cost=None, sell=10)
        self.assertEqual(prod("2")["cost_price"], 0)

    def test_category_none_keeps_and_empty_clears(self):
        svc.save_product("1", "Sugar", "admin", category="Groceries")
        svc.save_product("1", "Sugar", "admin")                                           # None -> keep
        self.assertEqual(prod("1")["category"], "Groceries")
        svc.save_product("1", "Sugar", "admin", category="")                              # explicit empty -> clear
        self.assertEqual(prod("1")["category"], "")

    def test_picture_survives_a_save(self):
        svc.save_product("1", "Sugar", "admin")
        src = make_picture(os.path.join(tempfile.mkdtemp(), "p.png"), (800, 600))
        name = svc.set_product_image("1", src, "admin")
        svc.save_product("1", "Sugar 2", "admin", sell=5)
        self.assertEqual(prod("1")["image_path"], name)

    def test_delete_removes_history_and_picture(self):
        svc.save_product("1", "Sugar", "admin", sell=100)
        svc.save_product("1", "Sugar", "admin", sell=120)
        src = make_picture(os.path.join(tempfile.mkdtemp(), "p.png"), (400, 400))
        name = svc.set_product_image("1", src, "admin")
        path = os.path.join(svc.image_dir(), name)
        self.assertTrue(os.path.isfile(path))
        svc.delete_product("1", "admin")
        self.assertIsNone(prod("1"))
        self.assertEqual(count("price_history", "barcode='1'"), 0)
        self.assertFalse(os.path.exists(path))
        with self.assertRaises(ValueError):
            svc.delete_product("1", "admin")


class ImportTests(Base):
    def test_old_ten_column_files_still_work(self):
        rows = [["barcode", "name_en", "name_local", "keywords", "cost_price", "selling_price", "wholesale_price", "stock_qty", "expiry_date", "warranty"],
                ["1001", "Sample", "", "kw", "200", "250", "230", "50", "2027-12-31", "1 Year"]]
        self.assertEqual(svc.import_products(rows, True, "admin"), (1, 0))
        p = prod("1001")
        self.assertEqual((p["stock_qty"], p["selling_price"], p["category"]), (50, 250, ""))

    def test_category_column_creates_categories_and_blank_keeps_the_old_one(self):
        svc.save_product("1", "Old", "admin", category="Keep Me", sell=10, stock=1)
        rows = [["1", "Old", "", "", "0", "10", "0", "4", "", "", ""],                      # blank category -> keep
                ["2", "New", "", "", "0", "20", "0", "4", "", "", "Fresh"],
                ["3", "Other", "", "", "0", "30", "0", "4", "", "", "fresh"]]
        self.assertEqual(svc.import_products(rows, True, "admin"), (3, 0))
        self.assertEqual(prod("1")["category"], "Keep Me")
        self.assertEqual((prod("2")["category"], prod("3")["category"]), ("Fresh", "Fresh"))
        self.assertEqual([r["name"] for r in svc.list_categories()], ["Keep Me", "Fresh"])

    def test_add_versus_replace_stock(self):
        svc.save_product("1", "A", "admin", sell=1, stock=10)
        svc.import_products([["1", "A", "", "", "0", "1", "0", "5"]], True, "admin")
        self.assertEqual(prod("1")["stock_qty"], 15)
        svc.import_products([["1", "A", "", "", "0", "1", "0", "5"]], False, "admin")
        self.assertEqual(prod("1")["stock_qty"], 5)

    def test_bad_rows_are_skipped_and_counted(self):
        rows = [["", "no barcode"], ["1", ""], ["2", "ok", "", "", "x", "1"], ["3", "neg", "", "", "0", "-5"], ["4", "date", "", "", "0", "1", "0", "1", "bad-date"],
                ["5", "fine", "", "", "0", "9", "0", "2"], [], ["6", "negstock", "", "", "0", "1", "0", "-3"]]
        ok, bad = svc.import_products(rows, True, "admin")
        self.assertEqual((ok, bad), (1, 6))
        self.assertEqual(count("products"), 1)

    def test_price_changes_are_logged_with_a_reason(self):
        svc.save_product("1", "A", "admin", cost=10, sell=20)
        svc.import_products([["1", "A", "", "", "10", "25", "0", "1"]], True, "admin")
        h = svc.price_history("1")
        self.assertEqual((h[0]["sell_old"], h[0]["sell_new"], h[0]["reason"]), (20, 25, "CSV import"))
        svc.import_products([["1", "A", "", "", "10", "25", "0", "1"]], True, "admin")      # same prices -> no new row
        self.assertEqual(len(svc.price_history("1")), 1)


# ============================================================================ price history + bulk update
class PriceTests(Base):
    def setUp(self):
        super().setUp()
        svc.save_product("A", "Sugar", "admin", cost=100, sell=150, wholesale=140, stock=5, category="Food")
        svc.save_product("B", "Rice", "admin", cost=80, sell=125, wholesale=0, stock=5, category="Food")
        svc.save_product("C", "Soap", "admin", cost=40, sell=60, wholesale=55, stock=5, category="Home")

    def test_history_logged_only_for_real_changes_and_when_enabled(self):
        self.assertEqual(count("price_history"), 0)                                         # creation is not a "change"
        svc.save_product("A", "Sugar", "admin", cost=100, sell=150, wholesale=140)
        self.assertEqual(count("price_history"), 0)
        svc.save_product("A", "Sugar", "admin", cost=100, sell=155, wholesale=140, reason="Supplier increase")
        h = svc.price_history("A")
        self.assertEqual((len(h), h[0]["sell_old"], h[0]["sell_new"], h[0]["reason"], h[0]["user"]), (1, 150, 155, "Supplier increase", "admin"))
        dbm.settings.set_many({"feat_price_history": "0"})
        svc.save_product("A", "Sugar", "admin", cost=100, sell=170, wholesale=140)
        self.assertEqual(len(svc.price_history("A")), 1)                                    # switched off -> not logged
        self.assertEqual(prod("A")["selling_price"], 170)                                   # ...but the price still saved

    def test_preview_percent_amount_set_and_rounding(self):
        pv = {x["barcode"]: x for x in svc.bulk_price_preview("selling_price", "percent", 10)}
        self.assertEqual((pv["A"]["old"], pv["A"]["new"]), (150, 165))
        self.assertEqual(pv["B"]["new"], 137.5)
        pv = {x["barcode"]: x for x in svc.bulk_price_preview("selling_price", "percent", 10, rounding=5)}
        self.assertEqual((pv["B"]["new"], pv["C"]["new"]), (140, 65))
        pv = {x["barcode"]: x for x in svc.bulk_price_preview("selling_price", "amount", -10)}
        self.assertEqual((pv["A"]["new"], pv["B"]["new"]), (140, 115))
        pv = svc.bulk_price_preview("selling_price", "set", 99)
        self.assertTrue(all(x["new"] == 99 for x in pv))
        self.assertEqual(len(pv), 3)
        self.assertEqual(prod("A")["selling_price"], 150)                                   # preview changes nothing

    def test_scopes(self):
        self.assertEqual({x["barcode"] for x in svc.bulk_price_preview("selling_price", "percent", 5, ("category", "food"))}, {"A", "B"})
        self.assertEqual({x["barcode"] for x in svc.bulk_price_preview("selling_price", "percent", 5, ("barcodes", ["C"]))}, {"C"})
        self.assertEqual(svc.bulk_price_preview("selling_price", "percent", 5, ("barcodes", [])), [])
        self.assertEqual(svc.bulk_price_preview("selling_price", "percent", 5, ("category", "Nope")), [])

    def test_wholesale_not_set_is_skipped_except_in_set_mode(self):
        self.assertEqual({x["barcode"] for x in svc.bulk_price_preview("wholesale_price", "percent", 10)}, {"A", "C"})
        self.assertEqual(len(svc.bulk_price_preview("wholesale_price", "set", 100)), 3)

    def test_warnings(self):
        pv = {x["barcode"]: x["warn"] for x in svc.bulk_price_preview("selling_price", "amount", -50)}
        self.assertEqual(pv["A"], "")                                                       # 100 = cost, not below
        self.assertEqual(pv["B"], "below cost")                                             # 75 < 80
        self.assertEqual(pv["C"], "below cost")                                             # 10 < 40
        pv = {x["barcode"]: x["warn"] for x in svc.bulk_price_preview("selling_price", "amount", -150)}
        self.assertEqual(pv["A"], "ZERO / NEGATIVE")

    def test_validation(self):
        for args in (("nonsense", "percent", 5), ("selling_price", "nonsense", 5), ("selling_price", "percent", -95), ("selling_price", "percent", 501),
                     ("selling_price", "amount", 2_000_000), ("selling_price", "set", 0), ("selling_price", "set", -5)):
            with self.assertRaises(ValueError):
                svc.bulk_price_preview(*args)

    def test_cost_prices_need_permission(self):
        with self.assertRaises(PermissionError):
            svc.bulk_price_preview("cost_price", "percent", 5)
        pv = svc.bulk_price_preview("cost_price", "percent", 5, allow_cost=True)
        with self.assertRaises(PermissionError):
            svc.bulk_price_apply(pv, "cost_price", "cashier")
        self.assertEqual(prod("A")["cost_price"], 100)
        self.assertEqual(svc.bulk_price_apply(pv, "cost_price", "admin", allow_cost=True), 3)
        self.assertEqual(prod("A")["cost_price"], 105)

    def test_apply_updates_logs_and_audits(self):
        pv = svc.bulk_price_preview("selling_price", "percent", 10, ("category", "Food"))
        self.assertEqual(svc.bulk_price_apply(pv, "selling_price", "admin", "Festival season"), 2)
        self.assertEqual((prod("A")["selling_price"], prod("B")["selling_price"], prod("C")["selling_price"]), (165, 137.5, 60))
        h = svc.price_history("A")
        self.assertEqual((h[0]["sell_old"], h[0]["sell_new"], h[0]["cost_old"], h[0]["cost_new"], h[0]["reason"]), (150, 165, 100, 100, "Festival season"))
        self.assertEqual(count("audit_log", "action='BULK_PRICE'"), 1)
        self.assertEqual(prod("A")["cost_price"], 100)                                      # other columns untouched

    def test_stale_preview_is_refused_and_nothing_changes(self):
        pv = svc.bulk_price_preview("selling_price", "percent", 10)
        svc.save_product("B", "Rice", "admin", cost=80, sell=130, wholesale=0)              # someone edits meanwhile
        with self.assertRaises(ValueError) as cm:
            svc.bulk_price_apply(pv, "selling_price", "admin")
        self.assertIn("preview again", str(cm.exception))
        self.assertEqual((prod("A")["selling_price"], prod("C")["selling_price"]), (150, 60))
        self.assertEqual(count("audit_log", "action='BULK_PRICE'"), 0)

    def test_failure_in_the_middle_rolls_everything_back(self):
        pv = svc.bulk_price_preview("selling_price", "percent", 10)
        with dbm.db() as c:                                                                  # make the 2nd history insert explode
            c.execute("CREATE TRIGGER boom BEFORE INSERT ON price_history WHEN NEW.barcode='B' BEGIN SELECT RAISE(ABORT,'boom'); END")
        with self.assertRaises(Exception):
            svc.bulk_price_apply(pv, "selling_price", "admin")
        self.assertEqual((prod("A")["selling_price"], prod("B")["selling_price"], prod("C")["selling_price"]), (150, 125, 60))
        self.assertEqual(count("price_history"), 0)
        self.assertEqual(count("audit_log", "action='BULK_PRICE'"), 0)

    def test_apply_refuses_empty_or_invalid(self):
        with self.assertRaises(ValueError):
            svc.bulk_price_apply([], "selling_price", "admin")
        bad = svc.bulk_price_preview("selling_price", "amount", -150)
        with self.assertRaises(ValueError):
            svc.bulk_price_apply(bad, "selling_price", "admin")
        self.assertEqual(prod("A")["selling_price"], 150)

    def test_field_name_cannot_be_used_for_sql_injection(self):
        pv = svc.bulk_price_preview("selling_price", "percent", 10)
        with self.assertRaises(ValueError):
            svc.bulk_price_apply(pv, "selling_price=1; DROP TABLE products; --", "admin")
        self.assertEqual(count("products"), 3)


# ============================================================================ pictures + thumbnails
class PictureTests(Base):
    def setUp(self):
        super().setUp()
        svc.save_product("A/1 b", "Weird Barcode", "admin", sell=10)
        self.tmp = tempfile.mkdtemp()

    def test_picture_is_resized_converted_and_linked(self):
        src = make_picture(os.path.join(self.tmp, "big.png"), (4000, 3000), "RGBA", (255, 0, 0, 128))
        name = svc.set_product_image("A/1 b", src, "admin")
        self.assertRegex(name, r"^A_1_b_[0-9a-f]{6}\.jpg$")                                  # safe file name
        path = svc.product_image_path(prod("A/1 b"))
        self.assertEqual(os.path.dirname(path), svc.image_dir())
        with Image.open(path) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 640)
            self.assertEqual(im.size, (640, 480))
        self.assertTrue(os.path.exists(src))                                                 # the original is untouched

    def test_replace_and_remove(self):
        a = make_picture(os.path.join(self.tmp, "a.jpg"), (500, 500))
        b = make_picture(os.path.join(self.tmp, "b.png"), (300, 600))
        n1 = svc.set_product_image("A/1 b", a, "admin")
        n2 = svc.set_product_image("A/1 b", b, "admin")
        self.assertEqual(n1, n2)
        self.assertEqual(len(glob.glob(os.path.join(svc.image_dir(), "*.jpg"))), 1)
        svc.clear_product_image("A/1 b", "admin")
        self.assertEqual(prod("A/1 b")["image_path"], "")
        self.assertEqual(glob.glob(os.path.join(svc.image_dir(), "*.jpg")), [])
        self.assertEqual(svc.product_image_path(prod("A/1 b")), "")

    def test_bad_files_and_unknown_product(self):
        junk = os.path.join(self.tmp, "x.png")
        with open(junk, "wb") as f:
            f.write(b"this is not an image" * 50)
        with self.assertRaises(ValueError) as cm:
            svc.set_product_image("A/1 b", junk, "admin")
        self.assertIn("not a picture", str(cm.exception))
        with self.assertRaises(ValueError):
            svc.set_product_image("A/1 b", os.path.join(self.tmp, "missing.png"), "admin")
        with self.assertRaises(ValueError):
            svc.set_product_image("NOPE", make_picture(os.path.join(self.tmp, "ok.png"), (10, 10)), "admin")
        self.assertEqual(prod("A/1 b")["image_path"], "")

    def test_missing_file_means_no_picture(self):
        a = make_picture(os.path.join(self.tmp, "a.jpg"), (100, 100))
        name = svc.set_product_image("A/1 b", a, "admin")
        os.remove(os.path.join(svc.image_dir(), name))
        self.assertEqual(svc.product_image_path(prod("A/1 b")), "")


class ThumbTests(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.cache = thumbs.ThumbCache(max_items=3)

    def test_placeholder_is_stable_and_exact_size(self):
        a, b = thumbs.placeholder("Sugar", 80), thumbs.placeholder("Sugar", 80)
        self.assertEqual(a.size, (80, 80))
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertNotEqual(thumbs.placeholder("Sugar", 80).getpixel((2, 2)), thumbs.placeholder("Zebra Crossing", 80).getpixel((2, 2)))
        self.assertEqual(thumbs.initials("coconut oil"), "CO")
        self.assertEqual(thumbs.initials("   "), "?")
        self.assertEqual(thumbs.initials("Sugar"), "S")

    def test_real_picture_is_letterboxed_and_cached_on_disk_then_memory(self):
        p = make_picture(os.path.join(self.tmp, "wide.jpg"), (3000, 1000))
        im = self.cache.get(p, 80, "x")
        self.assertEqual(im.size, (80, 80))
        self.assertEqual(im.getpixel((40, 5)), thumbs.BG)                                    # letter-box band on top
        self.assertEqual((self.cache.misses, self.cache.hits, self.cache.disk_hits), (1, 0, 0))
        self.assertEqual(len(os.listdir(thumbs.cache_dir())), 1)
        self.cache.get(p, 80, "x")
        self.assertEqual(self.cache.hits, 1)                                                 # memory hit
        fresh_cache = thumbs.ThumbCache()
        fresh_cache.get(p, 80, "x")
        self.assertEqual(fresh_cache.disk_hits, 1)                                           # a new "session" reads the small disk copy
        self.assertEqual(len(os.listdir(thumbs.cache_dir())), 1)

    def test_changed_file_is_rebuilt(self):
        p = make_picture(os.path.join(self.tmp, "a.jpg"), (400, 400), color=(255, 0, 0))
        first = self.cache.get(p, 64, "x").getpixel((32, 32))
        time.sleep(0.02)
        make_picture(p, (400, 400), color=(0, 0, 255))
        os.utime(p, (time.time() + 5, time.time() + 5))
        second = self.cache.get(p, 64, "x").getpixel((32, 32))
        self.assertNotEqual(first, second)

    def test_broken_or_missing_files_give_placeholders_not_errors(self):
        junk = os.path.join(self.tmp, "junk.jpg")
        with open(junk, "wb") as f:
            f.write(b"not a jpeg" * 20)
        for path in (junk, os.path.join(self.tmp, "gone.jpg"), ""):
            im = self.cache.get(path, 64, "Sugar")
            self.assertEqual(im.size, (64, 64))

    def test_lru_evicts_the_oldest(self):
        paths = [make_picture(os.path.join(self.tmp, f"{i}.jpg"), (50, 50)) for i in range(5)]
        for p in paths:
            self.cache.get(p, 32, "x")
        self.assertEqual(len(self.cache._m), 3)
        before = self.cache.misses
        self.cache.get(paths[4], 32, "x")
        self.assertEqual(self.cache.misses, before)                                          # newest still cached
        self.cache.get(paths[0], 32, "x")
        self.assertEqual(self.cache.misses, before + 1)                                      # oldest was evicted

    def test_prune_and_clear_disk(self):
        for i in range(6):
            self.cache.get(make_picture(os.path.join(self.tmp, f"{i}.jpg"), (50, 50)), 32, "x")
        self.assertEqual(len(os.listdir(thumbs.cache_dir())), 6)
        self.assertEqual(thumbs.prune_disk(max_files=4), 2)
        self.assertEqual(len(os.listdir(thumbs.cache_dir())), 4)
        self.assertEqual(thumbs.clear_disk(), 4)

    def test_speed_big_photos_are_fast_the_second_time(self):
        p = make_picture(os.path.join(self.tmp, "huge.jpg"), (6000, 4000))
        t = time.time(); self.cache.get(p, 80, "x"); cold = time.time() - t
        t = time.time(); self.cache.get(p, 80, "x"); warm = time.time() - t
        self.assertLess(warm, 0.01)
        self.assertLess(cold, 3.0)


# ============================================================================ interaction with older features
class IntegrationTests(Base):
    def test_factory_reset_wipes_the_new_tables_with_the_right_scope(self):
        svc.add_category("Food", "admin")
        svc.save_product("1", "A", "admin", sell=10, category="Food")
        svc.save_product("1", "A", "admin", sell=12, category="Food")
        self.assertEqual((count("categories"), count("price_history")), (1, 1))
        svc.factory_reset("sales_stock", "admin", "RESET")
        self.assertEqual((count("categories"), count("price_history"), count("products")), (1, 1, 1))
        svc.factory_reset("products", "admin", "RESET")
        self.assertEqual((count("categories"), count("price_history"), count("products")), (1, 0, 0))     # categories kept
        svc.save_product("1", "A", "admin", sell=10)
        svc.save_product("1", "A", "admin", sell=12)
        svc.factory_reset("everything", "admin", "RESET")
        self.assertEqual((count("categories"), count("price_history"), count("products"), count("users")), (0, 0, 0, 2))     # users kept

    def test_an_older_database_is_upgraded_without_losing_data(self):
        svc.save_product("1", "Sugar", "admin", cost=1, sell=2, stock=3, category="X")
        with dbm.db() as c:                                                                  # pretend this is a Phase 5 database
            c.execute("DROP INDEX IF EXISTS idx_products_cat")
            c.execute("ALTER TABLE products DROP COLUMN category")
            c.execute("DROP TABLE categories")
            c.execute("DROP TABLE price_history")
        dbm.init_db()
        p = prod("1")
        self.assertEqual((p["name_en"], p["selling_price"], p["stock_qty"], p["category"]), ("Sugar", 2, 3, ""))
        svc.add_category("New", "admin")
        svc.save_product("1", "Sugar", "admin", sell=3, category="New")
        self.assertEqual(len(svc.price_history("1")), 1)

    def test_backup_and_restore_keep_categories_and_history(self):
        from velopos import backup as bk
        svc.save_product("1", "A", "admin", sell=10, category="Food")
        svc.save_product("1", "A", "admin", sell=12, category="Food")
        b = bk.create("manual")
        svc.factory_reset("everything", "admin", "RESET")
        bk.restore(b, "admin")
        self.assertEqual((count("categories"), count("price_history"), prod("1")["category"]), (1, 1, "Food"))

    def test_new_features_have_toggles_with_safe_defaults(self):
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_categories", "feat_item_grid", "feat_price_history"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)
        self.assertEqual(dbm.DEFAULTS["feat_item_grid"], "0")                               # the grid is opt-in: billing looks the same after upgrading
        self.assertEqual(dbm.DEFAULTS["feat_categories"], "1")

    def test_assistant_stock_lookup_still_works_with_categories(self):
        from velopos import assistant as A
        svc.save_product("1", "Sugar", "admin", sell=10, stock=3, category="Food")
        r = A.respond("stock of sugar", A.Ctx(lang="English"))
        self.assertIn("Sugar: only 3 left", r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
