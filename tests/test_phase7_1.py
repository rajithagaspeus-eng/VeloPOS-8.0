"""Headless tests for Phase 7.1 (owner phone dashboard): snapshot content & privacy, signing, and an END-TO-END run against the real
cloud/worker.js (Node 22+, in-memory SQLite standing in for Cloudflare D1).
Run from the project root:   python -m unittest tests.test_phase7_1 -v"""
import json, os, shutil, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request
from datetime import date, timedelta

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test71_"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_phase4 import fresh                                   # noqa: E402
from velopos import cloudsync as cs, database as dbm, services as svc  # noqa: E402


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Base(unittest.TestCase):
    def setUp(self):
        fresh()
        cs.reset_state()
        svc.save_product("A", "Soap", "admin", cost=20, sell=50, stock=100)
        svc.save_product("B", "Rice", "admin", cost=10, sell=30, stock=2)         # low stock (level 5)
        self.cid = svc.add_customer("Kamal Perera", "0771234567", "admin")
        self.sid = svc.open_shift("admin", 1000)

    def sale(self, qty=2, barcode="A", price=50, method="Cash", paid=None, cid=None):
        paid = qty * price if paid is None else paid
        return svc.create_sale([dict(barcode=barcode, name="x", qty=qty, price=price)], 0, 0, paid, method, "", cid, "admin", self.sid)


class Snapshot(Base):
    def test_totals_series_top_low_credit(self):
        self.sale(qty=2)                                                   # 100 revenue, 60 profit
        self.sale(qty=1, method="Card")                                    # 50 revenue, 30 profit
        svc.add_expense("Tea", "tea", 20, "admin")
        s = cs.build_snapshot()
        self.assertEqual(s["today"]["expenses"], 20)
        self.assertEqual(s["today"]["profit"], 60 + 30 - 20)
        self.assertEqual(s["v"], 1)
        self.assertEqual(len(s["days"]), 30)
        self.assertEqual(s["days"][-1]["d"], date.today().isoformat())
        self.assertEqual(s["today"]["bills"], 2)
        self.assertEqual(s["today"]["revenue"], 150)
        self.assertEqual(s["today"]["methods"], {"Cash": 100, "Card": 50})
        self.assertEqual(s["top"][0]["n"], "x")
        self.assertEqual([x["n"] for x in s["low"]], ["Rice"])
        self.assertEqual(sum(d["bills"] for d in s["days"]), 2)

    def test_returns_and_voids_are_reflected(self):
        self.sale(qty=2)
        inv2 = self.sale(qty=1)
        svc.void_sale(inv2["invoice"], "admin", "mistake")
        s = cs.build_snapshot()
        self.assertEqual(s["today"]["bills"], 1)
        self.assertEqual(s["today"]["revenue"], 100)

    def test_credit_total(self):
        self.sale(qty=2, paid=0, method="Credit", cid=self.cid)
        s = cs.build_snapshot()
        self.assertEqual(s["credit"]["count"], 1)
        self.assertEqual(s["credit"]["total"], 100)

    def test_no_personal_data_in_snapshot(self):
        self.sale(qty=2, paid=0, method="Credit", cid=self.cid)
        blob = json.dumps(cs.build_snapshot())
        for secret in ("Kamal", "Perera", "0771234567", "cost_price", "pbkdf2", "smtp"):
            self.assertNotIn(secret, blob)
        self.assertNotIn(dbm.settings.get("dash_view_token"), blob)        # only the HASH of the view token is sent
        self.assertIn(cs.build_snapshot()["view_hash"], blob)

    def test_identity_is_created_once_and_key_survives(self):
        a = cs.ensure_identity()
        key1 = dbm.settings.get("dash_key_enc")
        self.assertEqual(len(a), 16)
        self.assertEqual(cs.ensure_identity(), a)
        self.assertEqual(dbm.settings.get("dash_key_enc"), key1)
        self.assertTrue(key1.startswith("enc1:"))                          # encrypted at rest, never plain

    def test_url_rules(self):
        self.assertEqual(cs.normalize_url(" https://x.example.workers.dev/ "), "https://x.example.workers.dev")
        for bad in ("", "http://evil.com", "ftp://a.b", "https://nodot", "javascript:alert(1)"):
            self.assertEqual(cs.normalize_url(bad), "", bad)
        self.assertEqual(cs.normalize_url("http://127.0.0.1:8787"), "http://127.0.0.1:8787")

    def test_due_logic(self):
        dbm.settings.set_many({"feat_dashboard": "1", "dash_url": "https://x.example.com"})
        self.assertTrue(cs.due())
        cs._state.update(last_try=time.time(), last_ok=time.time())
        self.assertFalse(cs.due())
        self.assertTrue(cs.due(now=time.time() + cs.PUSH_EVERY + 1))
        cs._state.update(last_try=time.time(), last_ok=0)                  # failed last time -> retry sooner
        self.assertTrue(cs.due(now=time.time() + cs.RETRY_EVERY + 1))
        dbm.settings.set_many({"feat_dashboard": "0"})
        self.assertFalse(cs.due())

    def test_offline_never_raises(self):
        dbm.settings.set_many({"feat_dashboard": "1", "dash_url": "http://127.0.0.1:9"})   # nothing listens there
        ok, msg = cs.run_push(force=True)
        self.assertFalse(ok)
        self.assertIn("internet", msg.lower())


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for the end-to-end Worker test")
class EndToEnd(Base):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(["node", "--no-warnings", os.path.join(ROOT, "tests", "worker_harness.mjs")],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = cls.proc.stdout.readline().strip()
        if not line.startswith("PORT"):
            raise unittest.SkipTest("Worker harness did not start: " + cls.proc.stderr.read()[:300])
        cls.base = f"http://127.0.0.1:{line.split()[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()

    def invite(self, days=30):
        st, body = http("POST", self.base + "/admin/invite", json.dumps({"days": days}).encode(),
                        {"Authorization": "Bearer test-admin-key", "Content-Type": "application/json"})
        self.assertEqual(st, 200)
        return json.loads(body)["code"]

    def setup_shop(self, invite=True):
        dbm.settings.set_many({"feat_dashboard": "1", "dash_url": self.base, "dash_invite": self.invite() if invite else ""})
        cs.ensure_identity()

    def api(self, token=None):
        t = dbm.settings.get("dash_view_token") if token is None else token
        return http("GET", f"{self.base}/api/snap/{dbm.settings.get('dash_shop_id')}?t={t}")

    def test_full_flow(self):
        self.sale(qty=2)
        self.setup_shop()
        ok, msg = cs.run_push(force=True)
        self.assertTrue(ok, msg)
        self.assertEqual(dbm.settings.get("dash_invite"), "")              # the one-time code is used up
        st, body = self.api()
        self.assertEqual(st, 200)
        j = json.loads(body)
        self.assertEqual(j["snap"]["today"]["revenue"], 100)
        self.assertEqual(j["snap"]["shop"], dbm.settings.get("shop_name"))
        # a later push (no invite) keeps working and updates the data
        self.sale(qty=1)
        self.assertTrue(cs.run_push(force=True)[0])
        self.assertEqual(json.loads(self.api()[1])["snap"]["today"]["revenue"], 150)

    def test_unchanged_data_is_not_uploaded_again(self):
        self.setup_shop()
        self.assertEqual(cs.run_push()[1], "Uploaded.")
        self.assertEqual(cs.run_push()[1], "No changes.")

    def test_first_push_needs_an_invite(self):
        self.setup_shop(invite=False)
        ok, msg = cs.run_push(force=True)
        self.assertFalse(ok)
        self.assertIn("invite", msg.lower())

    def test_invite_is_single_use_and_forged_invite_refused(self):
        code = self.invite()
        dbm.settings.set_many({"feat_dashboard": "1", "dash_url": self.base, "dash_invite": "AAAA-BBBB-CCCC"})
        cs.ensure_identity()
        self.assertFalse(cs.run_push(force=True)[0])                       # invented code
        dbm.settings.set_many({"dash_invite": code})
        self.assertTrue(cs.run_push(force=True)[0])
        # a second shop re-using the same code must fail
        dbm.settings.set_many({"dash_shop_id": "", "dash_key_enc": "", "dash_invite": code})
        cs.ensure_identity()
        cs.reset_state()
        self.assertFalse(cs.run_push(force=True)[0])

    def test_wrong_view_token_gets_nothing(self):
        self.setup_shop(); cs.run_push(force=True)
        self.assertEqual(self.api("wrong-token")[0], 404)
        self.assertEqual(self.api("")[0], 404)

    def test_rotating_the_link_kills_the_old_one(self):
        self.setup_shop(); cs.run_push(force=True)
        old = dbm.settings.get("dash_view_token")
        cs.rotate_view_token()
        self.assertTrue(cs.run_push(force=True)[0])
        self.assertEqual(self.api(old)[0], 404)
        self.assertEqual(self.api()[0], 200)

    def test_forged_and_replayed_requests_are_refused(self):
        self.setup_shop(); cs.run_push(force=True)
        snap = cs.build_snapshot(); body = json.dumps(snap).encode()
        good = cs._signed_headers(dbm.settings, body)
        # tampered body
        self.assertEqual(http("POST", self.base + "/push", body + b" ", good)[0], 401)
        # stale timestamp (replay)
        old = dict(good, **{"X-Ts": str(int(time.time()) - 3600)})
        self.assertEqual(http("POST", self.base + "/push", body, old)[0], 400)
        # attacker with their own key claims the same shop id without an invite
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        k = Ed25519PrivateKey.generate(); ts = str(int(time.time()))
        h = {"X-Shop": dbm.settings.get("dash_shop_id"), "X-Ts": ts, "X-Pub": cs._b64e(k.public_key().public_bytes_raw()),
             "X-Sig": cs._b64e(k.sign(ts.encode() + b"." + body))}
        self.assertEqual(http("POST", self.base + "/push", body, h)[0], 401)
        self.assertEqual(json.loads(self.api()[1])["snap"]["today"]["bills"], 0)

    def test_admin_endpoint_needs_the_key(self):
        self.assertEqual(http("POST", self.base + "/admin/invite", b"{}", {"Authorization": "Bearer nope"})[0], 403)
        self.assertEqual(http("POST", self.base + "/admin/invite", b"{}")[0], 403)

    def test_page_is_served_with_strict_headers(self):
        st, body = http("GET", f"{self.base}/d/0123456789abcdef?t=x")
        self.assertEqual(st, 200)
        self.assertIn(b"VeloPOS Dashboard", body)


if __name__ == "__main__":
    unittest.main()
