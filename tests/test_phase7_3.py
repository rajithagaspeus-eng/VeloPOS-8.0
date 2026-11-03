"""Headless tests for Phase 7.3 (review fixes). Run from the project root:   python -m unittest tests.test_phase7_3 -v"""
import os, sys, tempfile, unittest

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test73_"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_phase4 import fresh                                   # noqa: E402
from velopos import database as dbm, services as svc                  # noqa: E402


def one(sql, args=()):
    with dbm.db() as c:
        r = c.execute(sql, args).fetchone()
    return r[0] if r else None


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        svc.save_product("A", "Soap", "admin", cost=20, sell=33.33, stock=100)
        svc.save_product("Z", "Zero", "admin", cost=1, sell=10, stock=0)
        self.cid = svc.add_customer("Kamal", "0771234567", "admin")
        self.sid = svc.open_shift("admin", 1000)

    def sale(self, items, paid, method="Cash", cid=None):
        cart = [dict(barcode=b, name="x", qty=q, price=p) for b, q, p in items]
        return svc.create_sale(cart, 0, 0, paid, method, "", cid, "admin", self.sid)


class Rounding(Base):
    def test_subtotal_equals_sum_of_printed_lines(self):
        r = self.sale([("A", 1, 0.335)] * 3, 5)
        self.assertAlmostEqual(r["sub"], round(sum(l[3] for l in r["items"]), 2), places=2)
        self.assertEqual(r["sub"], 1.02)


class CreditOverpay(Base):
    def test_credit_sale_never_records_more_than_the_bill(self):
        r = self.sale([("A", 1, 33.33)], 100, "Credit", self.cid)
        self.assertEqual(r["paid"], 33.33)
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 0.0)
        self.assertEqual(svc.shift_summary(self.sid)["cash_sales"], 33.33)     # no phantom cash in the Z-report

    def test_loyalty_points_only_on_the_paid_part(self):
        self.sale([("A", 10, 100)], 0, "Credit", self.cid)                     # nothing paid
        self.assertEqual(one("SELECT loyalty_points FROM customers WHERE id=?", (self.cid,)), 0.0)
        self.sale([("A", 1, 100)], 100, "Cash", self.cid)
        self.assertEqual(one("SELECT loyalty_points FROM customers WHERE id=?", (self.cid,)), 1.0)

    def test_void_of_credit_sale_keeps_points_consistent(self):
        r = self.sale([("A", 2, 100)], 50, "Credit", self.cid)                 # earns 0.5, owes 150
        svc.void_sale(r["invoice"], "admin")
        self.assertEqual(one("SELECT loyalty_points FROM customers WHERE id=?", (self.cid,)), 0.0)
        self.assertEqual(one("SELECT credit_balance FROM customers WHERE id=?", (self.cid,)), 0.0)


class Oversell(Base):
    def test_blocked_by_default(self):
        with self.assertRaises(ValueError):
            self.sale([("Z", 1, 10)], 10)
        self.assertEqual(one("SELECT COUNT(*) FROM sales"), 0)

    def test_allowed_when_switched_on_and_stock_goes_negative(self):
        dbm.settings.set_many({"feat_allow_oversell": "1"})
        try:
            r = self.sale([("Z", 3, 10)], 30)
            self.assertEqual(one("SELECT stock_qty FROM products WHERE barcode='Z'"), -3)
            svc.void_sale(r["invoice"], "admin")                               # void puts it back to 0
            self.assertEqual(one("SELECT stock_qty FROM products WHERE barcode='Z'"), 0)
        finally:
            dbm.settings.set_many({"feat_allow_oversell": "0"})

    def test_allowed_with_batch_tracking_on(self):
        dbm.settings.set_many({"feat_allow_oversell": "1"})
        try:
            svc.enable_batches("admin")
            self.sale([("A", 150, 1)], 150)                                    # only 100 in stock
            self.assertEqual(one("SELECT stock_qty FROM products WHERE barcode='A'"), -50)
        finally:
            dbm.settings.set_many({"feat_allow_oversell": "0", "feat_batches": "0"})


class OptionalPhone(Base):
    def test_customers_without_phone(self):
        a = svc.add_customer("Walk A", "", "admin")
        b = svc.add_customer("Walk B", "", "admin")                            # a second blank phone must not clash
        self.assertNotEqual(a, b)
        self.assertIsNone(one("SELECT phone FROM customers WHERE id=?", (a,)))
        svc.update_customer(a, "Walk A2", "", "admin")

    def test_typed_phone_is_still_checked(self):
        with self.assertRaises(ValueError):
            svc.add_customer("Bad", "12", "admin")
        with self.assertRaises(ValueError):
            svc.add_customer("Dup", "+94771234567", "admin")


class Housekeeping(unittest.TestCase):
    def test_dead_module_removed_and_version(self):
        import velopos
        self.assertFalse(os.path.exists(os.path.join(ROOT, "velopos", "ownerview.py")))
        self.assertEqual(velopos.__version__, "7.2.0")


if __name__ == "__main__":
    unittest.main()


class UserAgent(unittest.TestCase):
    """Cloudflare answers 403 to 'Python-urllib/x'. Every request must carry a VeloPOS User-Agent."""

    def _server(self):
        import http.server, threading
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(self.headers.get("User-Agent"))
                self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            do_GET = do_POST

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, seen

    def test_dashboard_post_has_user_agent(self):
        from velopos import cloudsync as cs
        srv, seen = self._server()
        try:
            cs._post(f"http://127.0.0.1:{srv.server_port}/push", b"{}", {"Content-Type": "application/json"})
        finally:
            srv.shutdown()
        self.assertTrue(seen[0].startswith("VeloPOS/"), seen)

    def test_global_shim_covers_urlopen_with_context(self):
        import ssl, urllib.request
        from velopos import netua
        netua.install(); netua.install()                                       # twice is harmless
        srv, seen = self._server()
        try:                                                                   # same call shape as licence.py (context=...)
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/trial", data=b"{}", method="POST"),
                                   timeout=4, context=ssl.create_default_context()).read()
        finally:
            srv.shutdown()
        self.assertTrue(seen[0].startswith("VeloPOS/"), seen)


class Assets(unittest.TestCase):
    """The owner's own QR pictures and logo (qr_codes/, branding/)."""

    def setUp(self):
        from PIL import Image
        self.root = tempfile.mkdtemp(prefix="vp_assets_")
        for d in ("qr_codes", "branding"):
            os.makedirs(os.path.join(self.root, d))
        self.mk = lambda rel, size=(40, 20): Image.new("RGB", size, "white").save(os.path.join(self.root, rel), format="PNG")

    def test_qr_names_any_extension_and_doubled_extension(self):
        from velopos import assets
        self.mk("qr_codes/qr_bank.jpg"); self.mk("qr_codes/qr_binance.png.jpeg"); self.mk("qr_codes/QR_International.PNG")
        self.assertTrue(assets.qr_path("bank", self.root).endswith("qr_bank.jpg"))
        self.assertTrue(assets.qr_path("binance", self.root).endswith("qr_binance.png.jpeg"))
        self.assertTrue(assets.qr_path("international", self.root).lower().endswith("qr_international.png"))
        self.assertIsNone(assets.qr_path("whatsapp", self.root))              # missing -> the text QR is drawn instead
        open(os.path.join(self.root, "qr_codes", "qr_whatsapp.txt"), "w").write("x")
        self.assertIsNone(assets.qr_path("whatsapp", self.root))              # not a picture

    def test_about_falls_back_to_whatsapp(self):
        from velopos import assets
        self.mk("qr_codes/qr_whatsapp.jpg")
        self.assertTrue(assets.qr_path("about", self.root).endswith("qr_whatsapp.jpg"))
        self.mk("qr_codes/qr_about.png")
        self.assertTrue(assets.qr_path("about", self.root).endswith("qr_about.png"))

    def test_logo_order(self):
        from velopos import assets
        self.assertIsNone(assets.logo_path(self.root))
        open(os.path.join(self.root, "branding", "app_icon.ico"), "wb").write(b"ico")
        self.assertTrue(assets.logo_path(self.root).endswith("app_icon.ico"))
        self.assertTrue(assets.icon_path(self.root).endswith("app_icon.ico"))
        self.mk("branding/logo.png")
        self.assertTrue(assets.logo_path(self.root).endswith("logo.png"))
        self.mk("branding/dev_logo.png")
        self.assertTrue(assets.logo_path(self.root).endswith("dev_logo.png"))

    def test_fit_size_keeps_the_shape(self):
        from velopos import assets
        self.assertEqual(assets.fit_size(1024, 1024, target_h=150), (150, 150))
        self.assertEqual(assets.fit_size(400, 100, target_h=90, target_w=200), (200, 50))
        self.assertEqual(assets.fit_size(359, 360, target_h=150, target_w=150)[1], 150)

    def test_the_owners_real_pictures_are_in_the_package(self):
        from velopos import assets
        for k in ("international", "bank", "binance", "whatsapp", "about"):
            self.assertTrue(assets.qr_path(k, ROOT), k)
        self.assertTrue(assets.logo_path(ROOT).endswith("dev_logo.png"))
        self.assertTrue(assets.icon_path(ROOT))
