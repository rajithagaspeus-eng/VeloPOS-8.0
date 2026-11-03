"""Headless tests for Phase 7.2 (developer support code: challenge-response password-reset override).
Run from the project root:   python -m unittest tests.test_phase7_2 -v"""
import base64, os, subprocess, sys, tempfile, time, unittest

os.environ.setdefault("VELOPOS_HOME", tempfile.mkdtemp(prefix="velopos_test72_"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cryptography.hazmat.primitives import serialization                         # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from tests.test_phase4 import fresh                                              # noqa: E402
from velopos import license as lic, services as svc, support                     # noqa: E402


def b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class SupportCode(unittest.TestCase):
    def setUp(self):
        fresh()
        support._used.clear()
        self.key = Ed25519PrivateKey.generate()
        self._old = lic.PUBLIC_KEY_B64
        lic.PUBLIC_KEY_B64 = b64(self.key.public_key().public_bytes_raw())
        self.mid, self.ch = lic.machine_id(), support.new_challenge()

    def tearDown(self):
        lic.PUBLIC_KEY_B64 = self._old

    def code(self, mid=None, ch=None, purpose="forgot-password", minutes=30, key=None):
        exp = int(time.time()) + minutes * 60
        return f"{exp}." + b64((key or self.key).sign(support.message(purpose, mid or self.mid, ch or self.ch, exp)))

    def test_valid_code_is_accepted_once(self):
        c = self.code()
        self.assertEqual(support.verify(c, self.ch, "forgot-password"), (True, "OK"))
        ok, msg = support.verify(c, self.ch, "forgot-password")
        self.assertFalse(ok); self.assertIn("already used", msg)

    def test_formatting_noise_is_tolerated(self):
        c = self.code()
        self.assertTrue(support.verify(" " + c[:20] + "\n" + c[20:] + " ", self.ch.lower(), "forgot-password")[0])

    def test_code_for_another_pc_is_refused(self):
        self.assertFalse(support.verify(self.code(mid="POS-AAAA-BBBB-CCCC"), self.ch, "forgot-password")[0])

    def test_code_for_another_challenge_is_refused(self):
        self.assertFalse(support.verify(self.code(ch="ZZZZ-9999"), self.ch, "forgot-password")[0])

    def test_code_for_another_purpose_is_refused(self):
        self.assertFalse(support.verify(self.code(purpose="factory-reset"), self.ch, "forgot-password")[0])

    def test_expired_and_far_future_codes_are_refused(self):
        ok, msg = support.verify(self.code(minutes=-1), self.ch, "forgot-password")
        self.assertFalse(ok); self.assertIn("expired", msg)
        self.assertFalse(support.verify(self.code(minutes=60 * 48), self.ch, "forgot-password")[0])

    def test_code_signed_by_someone_else_is_refused(self):
        self.assertFalse(support.verify(self.code(key=Ed25519PrivateKey.generate()), self.ch, "forgot-password")[0])

    def test_garbage_never_raises(self):
        for bad in ("", "abc", "1.2.3", "x.y", "99999999999.AAAA", None, "\x00"):
            self.assertFalse(support.verify(bad, self.ch, "forgot-password")[0], repr(bad))

    def test_no_public_key_means_nothing_works(self):
        lic.PUBLIC_KEY_B64 = ""
        self.assertFalse(support.verify(self.code(), self.ch, "forgot-password")[0])

    def test_challenges_are_random_and_well_formed(self):
        seen = {support.new_challenge() for _ in range(200)}
        self.assertGreater(len(seen), 190)
        self.assertTrue(all(len(c) == 9 and c[4] == "-" for c in seen))

    def test_support_code_resets_the_admin_password(self):
        svc.save_user("boss", "oldpass1", "Admin", "test")
        self.assertTrue(svc.verify_admin_password("boss", "oldpass1"))
        self.assertTrue(support.verify(self.code(), self.ch, "forgot-password")[0])
        svc.reset_password("boss", "newpass99", "Support code")
        self.assertTrue(svc.verify_admin_password("boss", "newpass99"))
        self.assertFalse(svc.verify_admin_password("boss", "oldpass1"))

    def test_developer_tool_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            pem = os.path.join(d, "k.pem")
            with open(pem, "wb") as f:
                f.write(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "support_code.py"), self.mid, self.ch, "--key", pem,
                                "--log", os.path.join(d, "log.csv"), "--customer", "Test Shop"], capture_output=True, text=True, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            code = [ln.strip() for ln in r.stdout.splitlines() if ln.strip() and "." in ln and ln.strip()[0].isdigit()][-1]
            self.assertTrue(support.verify(code, self.ch, "forgot-password")[0])
            with open(os.path.join(d, "log.csv"), encoding="utf-8") as f:
                self.assertIn("Test Shop", f.read())
            bad = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "support_code.py"), "WRONG", self.ch, "--key", pem], capture_output=True, text=True, cwd=d)
            self.assertNotEqual(bad.returncode, 0)



import json, shutil, urllib.request                                              # noqa: E402
from datetime import date, timedelta                                             # noqa: E402
from velopos import branding, database as dbm                                    # noqa: E402


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for the end-to-end Worker test")
class OnlineTrial(unittest.TestCase):
    """Deleting the local trial files must not give a new 30 days while the PC can reach the developer's server."""
    n = 0

    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(["node", "--no-warnings", os.path.join(ROOT, "tests", "worker_harness.mjs")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = cls.proc.stdout.readline().strip()
        if not line.startswith("PORT"):
            raise unittest.SkipTest("Worker harness did not start")
        cls.base = f"http://127.0.0.1:{line.split()[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.stdout.close(); cls.proc.stderr.close()

    def setUp(self):
        fresh()
        OnlineTrial.n += 1                            # every test gets its own PC: the Worker's database lives for the whole class
        self.mid = f"POS-1111-2222-{OnlineTrial.n:04X}"
        self.hw = f"{OnlineTrial.n:02x}" * 16
        self._m, self._h, self._url = lic.machine_id, lic.hw_id, branding.TRIAL_SERVER_URL
        lic.machine_id = lambda: self.mid
        lic.hw_id = lambda: self.hw
        branding.TRIAL_SERVER_URL = self.base
        lic._remote.update(tried=False, date=None)
        self._wipe()

    def tearDown(self):
        lic.machine_id, lic.hw_id, branding.TRIAL_SERVER_URL = self._m, self._h, self._url
        lic._remote.update(tried=False, date=None)

    def _wipe(self):
        with dbm.db() as c:
            c.execute("DELETE FROM license_state")
        for f in (os.path.join(lic._cache_dir(), "sys.dat"),):
            if os.path.exists(f):
                os.remove(f)

    def seed(self, key, days_ago):
        ts = int(time.time()) - days_ago * 86400
        req = urllib.request.Request(self.base + "/__seed", data=json.dumps({"key": key, "first_seen": ts}).encode(), method="POST")
        urllib.request.urlopen(req, timeout=5).read()

    def again(self):                      # a new program start
        lic._remote.update(tried=False, date=None)
        return lic.check_status()

    def test_first_run_is_registered_and_wipe_does_not_reset_it(self):
        self.assertEqual(self.again()[0:2], ("TRIAL", 30))
        self.seed(self.mid, 40)                       # pretend the server first saw this PC 40 days ago
        self._wipe()
        self.assertEqual(self.again()[0], "EXPIRED")

    def test_reinstall_new_machine_id_but_same_hardware_is_still_expired(self):
        self.seed("hw:" + self.hw, 45)
        self.assertEqual(self.again()[0], "EXPIRED")

    def test_offline_falls_back_to_local_rules(self):
        branding.TRIAL_SERVER_URL = "http://127.0.0.1:9"
        self.assertEqual(self.again()[0:2], ("TRIAL", 30))

    def test_no_server_configured_means_old_behaviour(self):
        branding.TRIAL_SERVER_URL = ""
        self.assertEqual(self.again()[0:2], ("TRIAL", 30))

    def test_server_cannot_extend_a_trial(self):
        self.assertEqual(self.again()[0:2], ("TRIAL", 30))
        with dbm.db() as c:
            c.execute("DELETE FROM license_state")
        self.assertEqual(self.again()[1], 30)         # same day -> still 30, never more


if __name__ == "__main__":
    unittest.main()
