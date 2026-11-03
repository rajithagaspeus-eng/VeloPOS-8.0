"""Headless tests for Phase 6.4 (barcodes + labels, shortcut registry, cloud backup sync, update checker, customer-display model).
Run from the project root:   python -m unittest tests.test_phase6_4 -v"""
import io, json, os, random, re, sys, tempfile, unittest, urllib.error, urllib.request
from datetime import datetime, timedelta

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test64_"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image                                                                      # noqa: E402

from tests.test_phase4 import fresh                                                        # noqa: E402
from velopos import (backup as bk, barcodes as B, database as dbm, poledisplay as PD, services as svc, shortcuts as SC,   # noqa: E402
                     updates as UP)


def count(table):
    with dbm.db() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def read(rel):
    with open(os.path.join(ROOT, "velopos", rel), encoding="utf-8") as f:
        return f.read()


# ============================================================================ A) barcodes
class Ean13Tests(unittest.TestCase):
    def test_check_digit_known_vectors(self):
        for d12, cd in (("590123412345", 7), ("400638133393", 1), ("978020137962", 4), ("000000000000", 0), ("629104150021", 3), ("501234567890", 0)):
            self.assertEqual(B.ean13_check_digit(d12), cd, d12)
        for bad in ("12345678901", "1234567890123", "12345678901a", ""):
            with self.assertRaises(ValueError):
                B.ean13_check_digit(bad)

    def test_digits_complete_and_verify(self):
        self.assertEqual(B.ean13_digits("590123412345"), "5901234123457")
        self.assertEqual(B.ean13_digits(" 5901234123457 "), "5901234123457")
        with self.assertRaises(ValueError) as cm:
            B.ean13_digits("5901234123458")
        self.assertIn("should be 7", str(cm.exception))
        for bad in ("12345", "abcdefghijkl", "59012341234571"):
            with self.assertRaises(ValueError):
                B.ean13_digits(bad)

    def test_the_standard_tables_have_their_known_invariants(self):
        L, G, R = B._L, B._G, B._R
        self.assertEqual(len({*L}), 10), self.assertEqual(len({*G}), 10), self.assertEqual(len({*R}), 10)
        comp = lambda s: "".join("1" if c == "0" else "0" for c in s)                       # noqa: E731
        for d in range(10):
            self.assertEqual(R[d], comp(L[d]), d)                                            # R = complement of L
            self.assertEqual(G[d], R[d][::-1], d)                                            # G = R reversed
            self.assertEqual(L[d].count("1") % 2, 1, d)                                      # L codes have odd parity
            self.assertEqual(G[d].count("1") % 2, 0, d)                                      # G / R codes have even parity
            self.assertTrue(L[d].startswith("0") and L[d].endswith("1") and len(L[d]) == 7)
        self.assertEqual(B._PARITY[0], "LLLLLL")
        self.assertEqual(len(set(B._PARITY)), 10)
        for p in B._PARITY[1:]:
            self.assertEqual((p.count("L"), p.count("G")), (3, 3))

    def test_encoding_matches_an_independent_transcription(self):
        # 5 | 901234 | 123457  (first digit 5 -> parity LGGLLG).  Written out by hand from the EAN-13 standard tables.
        expected = ("101"
                    "0001011" "0100111" "0110011" "0010011" "0111101" "0011101"             # 9 L, 0 G, 1 G, 2 L, 3 L, 4 G
                    "01010"
                    "1100110" "1101100" "1000010" "1011100" "1001110" "1000100"             # 1 2 3 4 5 7 (R)
                    "101")
        self.assertEqual(B.ean13_bits("5901234123457"), expected)
        self.assertEqual(len(expected), 95)

    def test_round_trip_for_many_numbers_and_corruption_is_caught(self):
        rnd = random.Random(11)
        for _ in range(300):
            d12 = "".join(rnd.choice("0123456789") for _ in range(12))
            full = B.ean13_digits(d12)
            bits = B.ean13_bits(full)
            self.assertEqual((len(bits), bits[:3], bits[45:50], bits[-3:]), (95, "101", "01010", "101"))
            self.assertEqual(B.decode_ean13_bits(bits), full)
        bits = B.ean13_bits("4006381333931")
        for pos in (5, 20, 40, 60, 75, 90):
            flipped = bits[:pos] + ("1" if bits[pos] == "0" else "0") + bits[pos + 1:]
            with self.assertRaises(ValueError, msg=str(pos)):
                B.decode_ean13_bits(flipped)
        with self.assertRaises(ValueError):
            B.decode_ean13_bits("1" * 94)


class Code39Tests(unittest.TestCase):
    def test_pattern_table_invariants(self):
        self.assertEqual(len(B._C39), 44)                                                   # 43 characters + the '*' start/stop
        self.assertEqual(len(set(B._C39.values())), 44)
        for ch, pat in B._C39.items():
            self.assertEqual((len(pat), pat.count("W")), (9, 3), ch)                        # 9 elements, exactly 3 wide
        self.assertEqual(B._C39["*"], "NWNNWNWNN")
        self.assertEqual(B._C39["1"], "WNNWNNNNW")
        self.assertEqual(B.CODE39_CHARS, "".join(k for k in B._C39 if k != "*"))

    def test_encoding_matches_a_hand_expansion(self):
        star, a = "100010111011101", "111010100010111"                                     # '*' = NWNNWNWNN, 'A' = WNNNNWNNW (bar,space,bar...)
        self.assertEqual(B.code39_bits("A"), star + "0" + a + "0" + star)
        self.assertEqual(len(B.code39_bits("A")), 15 * 3 + 2)
        self.assertEqual(len(B.code39_bits("ABC")), 15 * 5 + 4)

    def test_round_trip_and_cleaning(self):
        rnd = random.Random(4)
        for _ in range(200):
            v = "".join(rnd.choice(B.CODE39_CHARS) for _ in range(rnd.randint(1, 20))).strip() or "X"
            self.assertEqual(B.decode_code39_bits(B.code39_bits(v)), B.code39_clean(v))
        self.assertEqual(B.code39_clean(" ab-12 "), "AB-12")
        for bad in ("", "   ", "x" * 41):
            with self.assertRaises(ValueError):
                B.code39_clean(bad)
        with self.assertRaises(ValueError) as cm:
            B.code39_clean("ab_c#é")
        self.assertIn("'_'", str(cm.exception))
        self.assertIn("'#'", str(cm.exception))
        with self.assertRaises(ValueError):
            B.decode_code39_bits("1010101")

    def test_choose_symbology(self):
        self.assertEqual(B.choose_symbology("4006381333931"), ("EAN13", "4006381333931"))
        self.assertEqual(B.choose_symbology("012345678905"), ("EAN13", "0012345678905"))        # a UPC-A is an EAN-13 with a leading 0
        self.assertEqual(B.choose_symbology("4006381333932")[0], "CODE39")                      # wrong check digit: not an EAN
        self.assertEqual(B.choose_symbology("1001"), ("CODE39", "1001"))
        self.assertEqual(B.choose_symbology("sku-9"), ("CODE39", "SKU-9"))
        self.assertEqual(B.choose_symbology("590123412345", "EAN-13"), ("EAN13", "5901234123457"))
        self.assertEqual(B.choose_symbology("4006381333931", "Code 39"), ("CODE39", "4006381333931"))
        with self.assertRaises(ValueError):
            B.choose_symbology("සීනි-1")
        with self.assertRaises(ValueError):
            B.choose_symbology("ABC", "EAN-13")


def scan_bits(img, row):
    """Read the bar pattern back from a rendered image (module width = the shortest run)."""
    px = [1 if img.getpixel((x, row)) < 128 else 0 for x in range(img.width)]
    first, last = px.index(1), len(px) - 1 - px[::-1].index(1)
    runs, i = [], first
    while i <= last:
        j = i
        while j <= last and px[j] == px[i]:
            j += 1
        runs.append((px[i], j - i))
        i = j
    mod = min(n for _, n in runs)
    return "".join(str(b) * round(n / mod) for b, n in runs), mod


class RenderTests(unittest.TestCase):
    SPEC = dict(width_mm=50, height_mm=30, dpi=203, symbology="Auto", shop="Test Shop", show_name=True, show_price=True, currency="Rs.")

    def test_the_rendered_bars_decode_back_to_the_same_number(self):
        for kind, val, w in (("EAN13", "5901234123457", 380), ("EAN13", "4006381333931", 250), ("CODE39", "SKU-100", 420), ("CODE39", "A", 300)):
            img = B.barcode_image(kind, val, w, 90)
            self.assertEqual(img.size, (w, 90))
            bits, mod = scan_bits(img, 10)
            self.assertGreaterEqual(mod, 1)
            if kind == "EAN13":
                self.assertEqual(B.decode_ean13_bits(bits), val)
            else:
                self.assertEqual(B.decode_code39_bits(bits), B.code39_clean(val))

    def test_too_narrow_is_reported_not_garbled(self):
        with self.assertRaises(ValueError) as cm:
            B.barcode_image("EAN13", "5901234123457", 100, 60)                               # 95 + 18 modules do not fit 100 dots
        self.assertIn("too narrow", str(cm.exception))

    def test_label_size_follows_mm_and_dpi(self):
        for w, h, dpi in ((50, 30, 203), (40, 25, 300), (58, 40, 203)):
            im = B.render_label(dict(barcode="5901234123457", name="Coconut Oil", price=1250), dict(self.SPEC, width_mm=w, height_mm=h, dpi=dpi))
            self.assertEqual(im.size, (B.mm_to_px(w, dpi), B.mm_to_px(h, dpi)))
            self.assertEqual(im.mode, "L")
        self.assertEqual(B.mm_to_px(25.4, 203), 203)

    def test_content_switches_and_long_names(self):
        item = dict(barcode="SKU-1", name="A very very long product name that can never fit on a small label " * 3, price=99.5)
        full = B.render_label(item, self.SPEC)
        plain = B.render_label(item, dict(self.SPEC, shop="", show_name=False, show_price=False))
        self.assertNotEqual(full.tobytes(), plain.tobytes())                                 # the switches change the picture (plain gets a taller barcode)
        self.assertEqual(plain.size, full.size)
        top = lambda im: [im.getpixel((x, y)) for y in range(3, 30) for x in range(im.width // 4, im.width * 3 // 4)]       # noqa: E731
        self.assertTrue(any(p < 128 for p in top(full)))                                      # the shop name is drawn at the top
        self.assertTrue(any(p < 128 for p in full.crop((0, full.height - 40, full.width, full.height)).getdata()))   # the price is at the bottom

    def test_errors_are_clear(self):
        item = dict(barcode="5901234123457", name="X", price=1)
        with self.assertRaises(ValueError):
            B.render_label(item, dict(self.SPEC, width_mm=8, height_mm=5))                    # label too small
        with self.assertRaises(ValueError):
            B.render_label(dict(item, barcode="සීනි"), self.SPEC)
        with self.assertRaises(ValueError) as cm:
            B.render_label(item, dict(self.SPEC, width_mm=12, height_mm=30))                  # EAN needs more dots than the label has
        self.assertIn("narrow", str(cm.exception))

    def test_queue_expand_and_render(self):
        q = [dict(barcode="1001", name="A", price=1, copies=3), dict(barcode="bad_é", name="Bad", price=1, copies=2), dict(barcode="5901234123457", name="C", price=2, copies=1)]
        self.assertEqual(len(B.expand_queue(q)), 6)
        imgs, errors = B.render_queue(q, self.SPEC)
        self.assertEqual(len(imgs), 4)
        self.assertEqual(len(errors), 1)
        self.assertIn("Bad", errors[0])
        for n in (0, 501, -1):
            with self.assertRaises(ValueError):
                B.expand_queue([dict(barcode="1", name="x", price=1, copies=n)])

    def test_printer_canvas_centres_and_refuses_wide_labels(self):
        im = Image.new("L", (400, 50), 0)
        out = B.printer_canvas(im, 576)
        self.assertEqual(out.size, (576, 50))
        self.assertEqual((out.getpixel((87, 10)), out.getpixel((88, 10)), out.getpixel((487, 10)), out.getpixel((488, 10))), (255, 0, 0, 255))
        with self.assertRaises(ValueError):
            B.printer_canvas(Image.new("L", (600, 10)), 576)

    def test_a4_sheet(self):
        im = B.render_label(dict(barcode="1001", name="A", price=1), self.SPEC)
        page = B.sheet_html([im] * 25, self.SPEC, 3, 8, 8)
        self.assertEqual(page.count("<img "), 25)
        self.assertEqual(page.count("class='pg'"), 2)                                           # 24 labels per page -> 2 pages
        self.assertIn("repeat(3,50.0mm)", page)
        self.assertIn("@page{size:A4;margin:0}", page)
        self.assertIn("data:image/png;base64,", page)
        with self.assertRaises(ValueError) as cm:
            B.sheet_html([im], self.SPEC, 5, 8, 8)                                              # 5 x 50 mm + margins > 210 mm
        self.assertIn("do not fit", str(cm.exception))
        with self.assertRaises(ValueError):
            B.sheet_html([im], self.SPEC, 0, 1)
        self.assertIn("&lt;b&gt;", B.sheet_html([im], self.SPEC, 1, 1, 5, title="<b>x"))


# ============================================================================ C) shortcuts
class ShortcutTests(unittest.TestCase):
    def test_registry_is_consistent(self):
        keys = [(s.scope, s.seq) for s in SC.REGISTRY]
        self.assertEqual(len(keys), len(set(keys)), "two shortcuts share a key in the same place")
        every = [s.seq for s in SC.REGISTRY if s.scope == "Everywhere"]
        for seq in every:                                                                       # an 'Everywhere' key may not be reused anywhere else
            self.assertEqual([s.scope for s in SC.REGISTRY if s.seq == seq], ["Everywhere"], seq)
        glob = {s.seq for s in SC.global_shortcuts()}
        self.assertEqual(glob, {"<F1>", "<F2>", "<F4>", "<F5>"})                                # the keys that existed before + F1
        self.assertEqual(len(glob), len(SC.global_shortcuts()))
        for s in SC.REGISTRY:
            self.assertTrue(s.label and s.desc and s.scope and s.seq.startswith("<"), s)

    def test_every_global_shortcut_has_a_handler(self):
        billing = read("screens/billing.py")
        for s in SC.global_shortcuts():
            if s.action == "help":
                self.assertIn("def show_shortcuts", read("main.py"))
                self.assertIn('if action == "help"', read("main.py"))
            else:
                self.assertEqual(s.scope, "Billing")
                self.assertRegex(billing, rf"def {s.action}\(")                                 # the method the key calls really exists

    def test_every_local_shortcut_really_is_bound_in_its_file(self):
        for s in SC.local_shortcuts():
            if s.where == "*":
                continue
            self.assertIn(f'bind("{s.seq}"', read(s.where), f"{s.scope}: {s.seq} is not bound in {s.where}")

    def test_no_special_key_is_bound_without_being_registered(self):
        """The sheet cannot lie: scan the source for .bind(...) and fail on any key that is not in the registry."""
        generic = {"<KeyRelease>", "<<TreeviewSelect>>", "<Double-1>", "<Button-1>", "<Return>", "<Configure>", "<Enter>", "<Leave>", "<MouseWheel>"}
        files = ["main.py", "dialogs.py"] + ["screens/" + f for f in sorted(os.listdir(os.path.join(ROOT, "velopos", "screens"))) if f.endswith(".py")]
        found = []
        for rel in files:
            for m in re.finditer(r"\.bind(?:_all)?\(\s*[\"'](<[^\"']+>)[\"']", read(rel)):
                if m.group(1) in generic:
                    continue
                reg = [s for s in SC.REGISTRY if s.seq == m.group(1) and (s.where == rel or s.where == "*")]
                self.assertTrue(reg, f"{rel} binds {m.group(1)} but it is not in velopos/shortcuts.py")
                found.append((rel, m.group(1)))
        self.assertIn(("screens/billing.py", "<Escape>"), found)                                # the audit really found something
        self.assertNotRegex(read("main.py"), r'self\.bind\("<F\d')                              # no raw function-key binding is left in main.py

    def test_sheet_lists_everything_and_escapes(self):
        text = SC.sheet_text()
        for s in SC.REGISTRY:
            self.assertIn(s.desc, text)
            self.assertIn(s.label, text)
        page = SC.sheet_html("<Shop & Co>")
        self.assertIn("&lt;Shop &amp; Co&gt;", page)
        self.assertEqual(page.count("<tr>"), len(SC.REGISTRY) + len({s.scope for s in SC.REGISTRY}))
        self.assertNotIn("F1", "".join(r[1] for r in SC.sheet_rows(include_help=False)))
        self.assertEqual(SC.sheet_rows()[0][0], "Everywhere")


# ============================================================================ D) cloud backups
class CloudTests(unittest.TestCase):
    def setUp(self):
        fresh()
        svc.save_product("A", "Item A", "admin", sell=10, stock=5)
        self.t1, self.t2 = tempfile.mkdtemp(prefix="cloud1_"), tempfile.mkdtemp(prefix="cloud2_")
        dbm.settings.set_many({"feat_cloud_sync": "1", "cloud_dirs": f"{self.t1}|{self.t2}", "feat_backup_gdrive": "0", "backup_gdrive_dir": "",
                               "backup_keep": "3", "cloud_last_ok": ""})

    def test_targets(self):
        cfg = dbm.settings
        self.assertEqual(bk.cloud_targets(cfg), [self.t1, self.t2])
        cfg.set_many({"cloud_dirs": f" {self.t1} | |{self.t1}|{self.t2}/ ", "feat_backup_gdrive": "1", "backup_gdrive_dir": self.t2})
        self.assertEqual(bk.cloud_targets(cfg), [self.t1, self.t2 + "/"])                       # blanks and duplicates removed
        cfg.set_many({"feat_cloud_sync": "0"})
        self.assertEqual(bk.cloud_targets(cfg), [self.t2])                                     # the old Google Drive folder still counts
        cfg.set_many({"feat_backup_gdrive": "0"})
        self.assertEqual(bk.cloud_targets(cfg), [])

    def test_verified_copy(self):
        b = bk.create("manual")
        dest = bk.copy_verified(b, self.t1)
        self.assertEqual(bk.sha256_file(dest), bk.sha256_file(b))
        self.assertTrue(bk.verify(dest)[0])
        self.assertEqual(os.path.dirname(dest), os.path.join(self.t1, "VeloPOS_Backups"))
        with self.assertRaises(FileNotFoundError):
            bk.copy_verified(b, os.path.join(self.t1, "missing_folder"))

    def test_a_corrupted_copy_is_detected_and_removed(self):
        b = bk.create("manual")
        real = bk.shutil.copy2

        def bad_copy(src, dst, *a, **k):
            real(src, dst, *a, **k)
            with open(dst, "r+b") as f:
                f.seek(2000)
                f.write(b"\x00\x01\x02\x03")                                                    # same size, different bytes
        bk.shutil.copy2 = bad_copy
        try:
            with self.assertRaises(OSError) as cm:
                bk.copy_verified(b, self.t1)
        finally:
            bk.shutil.copy2 = real
        self.assertIn("SHA-256", str(cm.exception))
        self.assertEqual(os.listdir(os.path.join(self.t1, "VeloPOS_Backups")), [])

    def test_offline_folder_goes_to_the_retry_queue_and_is_retried(self):
        offline = os.path.join(self.t2, "usb_not_plugged")
        dbm.settings.set_many({"cloud_dirs": f"{self.t1}|{offline}"})
        b = bk.create("manual")
        res = bk.sync_to_clouds(b, dbm.settings)
        self.assertEqual((res["ok"], [f[0] for f in res["failed"]]), ([self.t1], [offline]))
        self.assertEqual(bk.pending_count(), 1)
        self.assertTrue(dbm.settings.get("cloud_last_ok"))
        st = bk.cloud_status(dbm.settings)
        self.assertEqual([(t["dir"] == offline, t["reachable"]) for t in st["targets"]], [(False, True), (True, False)])
        self.assertEqual((len(st["pending"]), st["pending"][0]["attempts"]), (1, 1))
        bk.sync_to_clouds(b, dbm.settings)                                                      # same backup, same folder: ONE row, attempts count up
        self.assertEqual((bk.pending_count(), bk.cloud_status(dbm.settings)["pending"][0]["attempts"]), (1, 2))
        self.assertEqual(bk.process_queue(dbm.settings), dict(done=0, pending=1, dropped=0))   # still offline
        os.makedirs(offline)                                                                    # "USB plugged in"
        self.assertEqual(bk.process_queue(dbm.settings), dict(done=1, pending=0, dropped=0))
        self.assertTrue(bk.verify(os.path.join(offline, "VeloPOS_Backups", os.path.basename(b)))[0])

    def test_queue_drops_what_no_longer_matters(self):
        offline = os.path.join(self.t2, "gone")
        dbm.settings.set_many({"cloud_dirs": offline})
        b = bk.create("manual")
        bk.sync_to_clouds(b, dbm.settings)
        os.remove(b)                                                                            # the local backup was deleted / pruned
        os.makedirs(offline)
        self.assertEqual(bk.process_queue(dbm.settings), dict(done=0, pending=0, dropped=1))
        b2 = bk.create("manual")
        os.rmdir(offline)
        bk.sync_to_clouds(b2, dbm.settings)
        dbm.settings.set_many({"cloud_dirs": self.t1})                                          # the folder was removed from the settings
        self.assertEqual(bk.process_queue(dbm.settings), dict(done=0, pending=0, dropped=1))

    def test_automatic_backup_copies_prunes_and_reports(self):
        offline = os.path.join(self.t2, "off")
        dbm.settings.set_many({"cloud_dirs": f"{self.t1}|{offline}", "backup_keep": "2"})
        for _ in range(4):
            res = bk.run_auto(dbm.settings, "auto")
        self.assertEqual(len(os.listdir(os.path.join(self.t1, "VeloPOS_Backups"))), 2)         # pruned like the local folder
        self.assertTrue(any("Cloud copy to" in e and "queued for retry" in e for e in res["errors"]))
        self.assertIn("queued for retry", dbm.settings.get("last_backup_msg"))
        self.assertEqual(res["copied"], self.t1)
        self.assertGreaterEqual(bk.pending_count(), 1)

    def test_list_and_restore_from_the_cloud_folder(self):
        b = bk.create("manual")
        bk.sync_to_clouds(b, dbm.settings)
        svc.save_product("A", "Changed", "admin", sell=99, stock=1)
        found = bk.list_cloud_backups(self.t1)
        self.assertEqual([x["name"] for x in found], [os.path.basename(b)])
        bk.restore(found[0]["path"], "admin")
        self.assertEqual((svc.get_product("A")["name_en"], svc.get_product("A")["stock_qty"]), ("Item A", 5))
        self.assertEqual(bk.list_cloud_backups(os.path.join(self.t1, "nothing")), [])

    def test_the_queue_survives_an_older_database(self):
        with dbm.db() as c:
            c.execute("DROP TABLE cloud_queue")
        dbm.init_db()
        self.assertEqual(bk.pending_count(), 0)


# ============================================================================ E) update checker
class FakeResp:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]


class FakeOpener:
    def __init__(self, payload=None, exc=None):
        self.payload, self.exc, self.calls, self.urls = payload, exc, 0, []

    def open(self, req, timeout=None):
        self.calls += 1
        self.urls.append((req.full_url, timeout, req.get_header("User-agent")))
        if self.exc:
            raise self.exc
        data = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return FakeResp(data)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        fresh()
        dbm.settings.set_many({"feat_update_check": "1", "update_url": "https://example.com/version.json", "last_update_check": "", "update_info": ""})
        self.good = dict(version="99.1.0", notes="Many fixes\nand features", download="https://example.com/velopos_99.zip")

    def test_version_parsing_and_comparison(self):
        self.assertEqual(UP.parse_version("6.4.0"), (6, 4, 0, 0, 1))
        self.assertEqual(UP.parse_version("v6.4"), (6, 4, 0, 0, 1))
        self.assertEqual(UP.parse_version("6.0.0-phase4"), (6, 0, 0, 0, 0))
        self.assertEqual(UP.parse_version("6.4.0+build7"), UP.parse_version("6.4.0"))
        for bad in ("", "abc", "6..4", "6.4.x", "1.2.3.4.5", "6.4.0 beta"):
            with self.assertRaises(ValueError, msg=bad):
                UP.parse_version(bad)
        for remote, local, newer in (("6.4.1", "6.4.0", True), ("6.10.0", "6.9.9", True), ("6.4.0", "6.4.0-beta", True), ("6.4", "6.4.0", False), ("v6.4.0", "6.4.0", False),
                                     ("6.3.9", "6.4.0", False), ("7.0.0", "6.99.99", True), ("6.4.0-rc1", "6.4.0", False), ("6.4.0.1", "6.4.0", True)):
            self.assertEqual(UP.is_newer(remote, local), newer, (remote, local))

    def test_manifest_validation(self):
        m = UP.validate_manifest(dict(version=" 6.5.0 ", notes="ok\x00\x07 text\nline2", download="https://x.org/a.zip"))
        self.assertEqual((m["version"], m["notes"], m["download"]), ("6.5.0", "ok text\nline2", "https://x.org/a.zip"))
        self.assertEqual(len(UP.validate_manifest(dict(self.good, notes="x" * 5000))["notes"]), 2000)
        self.assertEqual(UP.validate_manifest(dict(version="6.5.0", download="https://x.org/a"))["notes"], "")
        bad = [None, [], "x", {}, dict(self.good, version=6), dict(self.good, version="nope"), dict(self.good, notes=5), dict(self.good, download="http://x.org/a.zip"),
               dict(self.good, download="ftp://x.org/a.zip"), dict(self.good, download="javascript:alert(1)"), dict(self.good, download="https://x.org/a b"),
               dict(self.good, download="https://x.org/<script>"), dict(self.good, download=""), dict(self.good, download="https://x.org/" + "a" * 600)]
        for obj in bad:
            with self.assertRaises(ValueError, msg=str(obj)[:60]):
                UP.validate_manifest(obj)

    def test_fetch_only_over_https_and_with_limits(self):
        op = FakeOpener(self.good)
        for url in ("http://example.com/v.json", "file:///etc/passwd", "ftp://x/v.json", "example.com/v.json", ""):
            with self.assertRaises(ValueError):
                UP.fetch_manifest(url, op)
        self.assertEqual(op.calls, 0)                                                          # nothing was even attempted
        m = UP.fetch_manifest("https://example.com/v.json", op, timeout=3)
        self.assertEqual(m["version"], "99.1.0")
        self.assertEqual((op.urls[0][1], op.urls[0][2].startswith("VeloPOS/")), (3, True))
        with self.assertRaises(ValueError):
            UP.fetch_manifest("https://example.com/v.json", FakeOpener(b"x" * (UP.MAX_BYTES + 5)))
        with self.assertRaises(ValueError):
            UP.fetch_manifest("https://example.com/v.json", FakeOpener(b"<html>not json</html>"))
        with self.assertRaises(ValueError):
            UP.fetch_manifest("https://example.com/v.json", FakeOpener(b"\xff\xfe\x00"))
        with self.assertRaises(urllib.error.URLError):
            UP.fetch_manifest("https://example.com/v.json", FakeOpener(exc=urllib.error.URLError("offline")))

    def test_redirects_to_plain_http_are_refused(self):
        h = UP._HttpsOnly()
        req = urllib.request.Request("https://example.com/version.json")
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(req, None, 302, "Found", {}, "http://evil.example/x.json")
        ok = h.redirect_request(req, None, 302, "Found", {}, "https://cdn.example.com/x.json")
        self.assertEqual(ok.full_url, "https://cdn.example.com/x.json")

    def test_check_statuses_and_the_daily_limit(self):
        cfg = dbm.settings
        now = datetime(2026, 11, 1, 9, 0, 0)
        op = FakeOpener(self.good)
        r = UP.check(cfg, now, op)
        self.assertEqual((r["status"], r["version"], r["download"]), ("newer", "99.1.0", "https://example.com/velopos_99.zip"))
        self.assertEqual(json.loads(cfg.get("update_info"))["version"], "99.1.0")
        self.assertEqual(UP.check(cfg, now + timedelta(hours=5), op)["status"], "skipped")      # once a day
        self.assertEqual(op.calls, 1)
        self.assertEqual(UP.check(cfg, now + timedelta(hours=25), FakeOpener(dict(self.good, version="0.0.1")))["status"], "current")
        self.assertEqual(cfg.get("update_info"), "")
        self.assertEqual(UP.check(cfg, now + timedelta(hours=60), op)["status"], "newer")
        self.assertEqual(op.calls, 2)

    def test_off_no_url_and_force(self):
        cfg = dbm.settings
        cfg.set_many({"feat_update_check": "0"})
        op = FakeOpener(self.good)
        self.assertEqual(UP.check(cfg, opener=op)["status"], "off")
        self.assertEqual(op.calls, 0)
        self.assertEqual(UP.check(cfg, opener=op, force=True)["status"], "newer")               # the manual button works even when the daily check is off
        cfg.set_many({"update_url": ""})
        self.assertEqual(UP.check(cfg, opener=op, force=True)["status"], "no_url")
        cfg.set_many({"feat_update_check": "1"})
        self.assertEqual(UP.check(cfg, opener=op)["status"], "no_url")

    def test_offline_is_silent_and_not_retried_every_minute(self):
        cfg = dbm.settings
        now = datetime(2026, 11, 1, 9, 0, 0)
        for exc in (urllib.error.URLError("no route"), TimeoutError("timed out"), OSError("network unreachable"), ConnectionResetError()):
            cfg.set_many({"last_update_check": ""})
            r = UP.check(cfg, now, FakeOpener(exc=exc))
            self.assertEqual(r["status"], "error")
            self.assertTrue(cfg.get("last_update_check"))
            self.assertEqual(UP.check(cfg, now + timedelta(minutes=1), FakeOpener(self.good))["status"], "skipped")
        self.assertEqual(UP.check(cfg, now + timedelta(days=2), FakeOpener(b"garbage"))["status"], "error")     # a broken file is an error, never a crash

    def test_it_can_only_tell_it_can_never_install(self):
        src = read("updates.py")
        for forbidden in ("urlretrieve", "subprocess", "os.system", "startfile", "zipfile", "exec(", "eval(", "webbrowser", "shutil", "extractall"):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertEqual(dbm.DEFAULTS["feat_update_check"], "0")


# ============================================================================ B) customer display model
class PoleTests(unittest.TestCase):
    def cart(self, n, qty=1, price=10):
        return [dict(name=f"Item {i}", qty=qty, price=price, unit="kg" if i % 2 else "") for i in range(n)]

    def test_idle_and_bill_snapshots(self):
        m = PD.DisplayModel("My Shop", "Welcome!", "Rs.")
        s = m.snapshot()
        self.assertEqual((s["mode"], s["shop"], s["promo"], s["lines"], s["total"]), ("idle", "My Shop", "Welcome!", [], 0.0))
        v0 = m.version
        m.set_cart([dict(name="Rice", qty=2.5, price=120, unit="kg"), dict(name="Soap", qty=3, price=60.5)])
        s = m.snapshot()
        self.assertEqual((s["mode"], s["total"], s["hidden"], len(s["lines"])), ("bill", 481.5, 0, 2))
        self.assertEqual(s["lines"][0], ("Rice", 2.5, "kg", 120.0, 300.0))
        self.assertGreater(m.version, v0)
        m.set_cart([dict(name="Rice", qty=1, price=100)], total=123.45)                          # the Billing screen can pass the real total (VAT, service ...)
        self.assertEqual(m.snapshot()["total"], 123.45)

    def test_only_the_last_lines_are_shown(self):
        m = PD.DisplayModel()
        m.set_cart(self.cart(12))
        s = m.snapshot()
        self.assertEqual((len(s["lines"]), s["hidden"], s["total"]), (8, 4, 120.0))
        self.assertEqual(s["lines"][-1][0], "Item 11")

    def test_empty_cart_goes_back_to_idle(self):
        m = PD.DisplayModel()
        m.set_cart(self.cart(2))
        m.set_cart([])
        self.assertEqual(m.snapshot()["mode"], "idle")
        v = m.version
        m.set_cart([])
        self.assertEqual(m.version, v)                                                           # no change -> no redraw

    def test_thank_you_screen_survives_the_cart_being_cleared_then_times_out(self):
        m = PD.DisplayModel()
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        m.set_cart(self.cart(2))
        m.show_thanks(1180.0, 20.0, now=t0)
        s = m.snapshot()
        self.assertEqual((s["mode"], s["total"], s["change"], s["lines"]), ("thanks", 1180.0, 20.0, []))
        m.set_cart([], now=t0 + timedelta(seconds=1))                                            # billing clears the cart right after payment
        self.assertEqual(m.snapshot()["mode"], "thanks")
        self.assertFalse(m.tick(t0 + timedelta(seconds=PD.DisplayModel.THANKS_SECONDS - 1)))
        self.assertTrue(m.tick(t0 + timedelta(seconds=PD.DisplayModel.THANKS_SECONDS)))
        self.assertEqual(m.snapshot()["mode"], "idle")
        self.assertFalse(m.tick(t0 + timedelta(minutes=5)))
        m.show_thanks(5, now=t0)
        m.set_cart(self.cart(1), now=t0 + timedelta(seconds=2))                                  # the next customer starts: show the new bill at once
        self.assertEqual(m.snapshot()["mode"], "bill")

    def test_bad_input_and_speed(self):
        m = PD.DisplayModel()
        m.set_cart([dict(name="x" * 200, qty=1, price=1), dict(qty=2, price=3)])
        s = m.snapshot()
        self.assertEqual((len(s["lines"][0][0]), s["lines"][1][0]), (40, ""))
        import time
        big = self.cart(5000)
        t = time.time()
        for _ in range(20):
            m.set_cart(big)
        self.assertLess(time.time() - t, 1.0)                                                    # 100,000 cart lines pushed in well under a second
        m.configure(shop="New", promo="P")
        self.assertEqual((m.snapshot()["shop"], m.snapshot()["promo"]), ("New", "P"))


class DefaultsTests(unittest.TestCase):
    def test_toggles_exist_and_ship_safe(self):
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_shortcut_help", "feat_labels", "feat_pole_display", "pole_fullscreen", "feat_cloud_sync", "feat_update_check"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)
        for k in ("feat_pole_display", "pole_fullscreen", "feat_cloud_sync", "feat_update_check"):
            self.assertEqual(dbm.DEFAULTS[k], "0", k)                                            # network / second-screen features are opt-in
        for k in ("feat_shortcut_help", "feat_labels"):
            self.assertEqual(dbm.DEFAULTS[k], "1", k)

    def test_the_tables_are_in_place_after_an_upgrade(self):
        fresh()
        with dbm.db() as c:
            c.execute("DROP TABLE cloud_queue")
        dbm.init_db()
        self.assertEqual(count("cloud_queue"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
