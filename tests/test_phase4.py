"""Headless tests for Phase 4 (no GUI, no Windows APIs). Run from the project root:
    python -m unittest tests.test_phase4 -v
Everything happens in a throw-away temp folder (VELOPOS_HOME), never in your real data."""
import base64, glob, os, socketserver, sqlite3, sys, tempfile, threading, unittest
from datetime import datetime, timedelta

os.environ["VELOPOS_HOME"] = tempfile.mkdtemp(prefix="velopos_test_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image                                               # noqa: E402

from velopos import backup as bk, database as dbm, otp as otpmod, printing as P, security, services as svc  # noqa: E402


def wfile(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def fresh():
    for f in glob.glob(dbm.DB_PATH + "*"):
        os.remove(f)
    for f in glob.glob(os.path.join(bk.folder(), "*")):
        os.remove(f)
    dbm.settings._c = {}
    dbm.init_db()
    with dbm.db() as c:
        c.execute("INSERT INTO users VALUES('admin',?, 'Admin', 'now')", (security.hash_password("admin123"),))
        c.execute("INSERT INTO users VALUES('cash',?, 'Cashier', 'now')", (security.hash_password("cash123"),))


def seed():
    with dbm.db() as c:
        c.execute("INSERT INTO products(barcode,name_en,cost_price,selling_price,stock_qty) VALUES('A','Sugar',100,150,10)")
        c.execute("INSERT INTO products(barcode,name_en,cost_price,selling_price,stock_qty) VALUES('B','Rice',80,120,20)")
        c.execute("INSERT INTO customers(name,phone) VALUES('Kamal','0771')")
    sid = svc.open_shift("admin", 1000)
    s1 = svc.create_sale([dict(barcode="A", name="Sugar", qty=2, price=150)], 0, 0, 300, "Cash", "", None, "admin", sid)
    svc.create_sale([dict(barcode="B", name="Rice", qty=1, price=120)], 0, 0, 0, "Credit", "", 1, "admin", sid)
    it = svc.returnable_items(s1["invoice"])
    svc.create_return(s1["invoice"], [(it[0][0], 1)], "Cash", "test", "admin", sid)
    with dbm.db() as c:
        c.execute("INSERT INTO expenses(date,category,description,amount,added_by) VALUES('2026-10-19','x','y',50,'admin')")


def count(table):
    with dbm.db() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def set_license(key, blob):
    dbm.settings.set_many({"license_key": key})
    with dbm.db() as c:
        c.execute("INSERT INTO license_state(id, blob) VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET blob=excluded.blob", (blob,))


def get_license():
    with dbm.db() as c:
        k = c.execute("SELECT value FROM settings WHERE key='license_key'").fetchone()
        b = c.execute("SELECT blob FROM license_state WHERE id=1").fetchone()
    return (k[0] if k else None), (b[0] if b else None)


# ============================================================================ backup / restore
class BackupTests(unittest.TestCase):
    def setUp(self):
        fresh()
        seed()

    def test_create_verify_list_single_file(self):
        a, m = bk.create("auto"), bk.create("manual")
        self.assertTrue(bk.verify(a)[0] and bk.verify(m)[0])
        tags = {b["tag"] for b in bk.list_backups()}
        self.assertEqual(tags, {"auto", "manual"})
        self.assertFalse(glob.glob(os.path.join(bk.folder(), "*-wal")))
        c = sqlite3.connect(a)
        self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "delete")   # self-contained file
        c.close()

    def test_unique_names_in_same_second(self):
        names = {os.path.basename(bk.create("manual")) for _ in range(5)}
        self.assertEqual(len(names), 5)
        self.assertEqual(len(bk.list_backups()), 5)

    def test_verify_rejects_bad_files(self):
        d = tempfile.mkdtemp()
        junk = os.path.join(d, "junk.db")
        wfile(junk, b"this is not a database" * 100)
        empty = os.path.join(d, "empty.db")
        sqlite3.connect(empty).execute("CREATE TABLE x(a)").connection.close()
        self.assertFalse(bk.verify(junk)[0])
        ok, msg = bk.verify(empty)
        self.assertFalse(ok)
        self.assertIn("missing", msg)
        self.assertFalse(bk.verify(os.path.join(d, "nope.db"))[0])

    def test_prune_only_touches_rotating_backups(self):
        for _ in range(3):
            bk.create("auto")
        bk.create("exit")
        for t in ("manual", "manual", "pre-restore", "pre-reset", "usb"):
            bk.create(t)
        removed = bk.prune(2)
        self.assertEqual(len(removed), 2)                         # 4 rotating -> keep 2
        left = [b["tag"] for b in bk.list_backups()]
        self.assertEqual(left.count("manual"), 2)
        for t in ("pre-restore", "pre-reset", "usb"):
            self.assertIn(t, left)
        self.assertEqual(sum(t in ("auto", "exit") for t in left), 2)

    def test_restore_roundtrip(self):
        good = bk.create("manual")
        with dbm.db() as c:
            c.execute("DELETE FROM products WHERE barcode='A'")
            c.execute("INSERT INTO products(barcode,name_en) VALUES('NEW','Later item')")
        res = bk.restore(good, "admin")
        with dbm.db() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM products WHERE barcode='A'").fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM products WHERE barcode='NEW'").fetchone())
            self.assertEqual(c.execute("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()[0], "RESTORE")
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # the safety copy still holds the data as it was BEFORE the restore
        pre = sqlite3.connect(res["pre_backup"])
        self.assertIsNotNone(pre.execute("SELECT 1 FROM products WHERE barcode='NEW'").fetchone())
        pre.close()
        self.assertTrue(any(b["tag"] == "pre-restore" for b in bk.list_backups()))
        for ext in ("-wal", "-shm"):
            self.assertFalse(os.path.exists(dbm.DB_PATH + ext))

    def test_restore_keeps_current_licence(self):
        set_license("OLDKEY", "state-1")
        old = bk.create("manual")
        set_license("CURRENTKEY", "state-2")
        bk.restore(old, "admin")
        self.assertEqual(get_license(), ("CURRENTKEY", "state-2"))

    def test_restore_bad_file_changes_nothing(self):
        bad = os.path.join(tempfile.mkdtemp(), "bad.db")
        wfile(bad, b"garbage" * 500)
        before = count("sales")
        with self.assertRaises(ValueError):
            bk.restore(bad, "admin")
        self.assertEqual(count("sales"), before)
        self.assertFalse(any(b["tag"] == "pre-restore" for b in bk.list_backups()))

    def test_restore_removes_stale_wal_and_shm(self):
        good = bk.create("manual")
        wfile(dbm.DB_PATH + "-wal", os.urandom(4096))
        wfile(dbm.DB_PATH + "-shm", os.urandom(32768))
        bk.restore(good, "admin")
        for ext in ("-wal", "-shm"):
            self.assertFalse(os.path.exists(dbm.DB_PATH + ext))
        self.assertEqual(count("products"), 2)

    def test_due_and_run_auto(self):
        cfg = dbm.settings
        cfg.set_many({"feat_autobackup": "1", "backup_interval_hours": "6", "last_auto_backup": ""})
        self.assertTrue(bk.due(cfg))
        res = bk.run_auto(cfg, "auto")
        self.assertTrue(os.path.exists(res["path"]) and not res["errors"])
        self.assertFalse(bk.due(cfg))
        self.assertTrue(bk.due(cfg, datetime.now() + timedelta(hours=7)))
        self.assertFalse(bk.due(cfg, datetime.now() + timedelta(hours=5)))
        cfg.set_many({"backup_interval_hours": "0"})
        self.assertFalse(bk.due(cfg, datetime.now() + timedelta(days=9)))
        cfg.set_many({"backup_interval_hours": "6", "feat_autobackup": "0"})
        self.assertFalse(bk.due(cfg, datetime.now() + timedelta(days=9)))
        cfg.set_many({"feat_autobackup": "1"})

    def test_run_auto_prunes_and_copies_to_drive(self):
        drive = tempfile.mkdtemp()
        cfg = dbm.settings
        cfg.set_many({"backup_keep": "2", "feat_backup_gdrive": "1", "backup_gdrive_dir": drive})
        for _ in range(4):
            res = bk.run_auto(cfg, "auto")
        self.assertFalse(res["errors"])
        self.assertEqual(sum(b["tag"] == "auto" for b in bk.list_backups()), 2)
        copies = os.listdir(os.path.join(drive, "VeloPOS_Backups"))
        self.assertEqual(len(copies), 2)                                  # destination is pruned too
        self.assertTrue(bk.verify(os.path.join(drive, "VeloPOS_Backups", copies[0]))[0])
        cfg.set_many({"feat_backup_gdrive": "0"})

    def test_drive_missing_is_reported_but_backup_still_made(self):
        cfg = dbm.settings
        cfg.set_many({"feat_backup_gdrive": "1", "backup_gdrive_dir": os.path.join(tempfile.gettempdir(), "no_such_drive_xyz")})
        res = bk.run_auto(cfg, "exit")
        self.assertTrue(os.path.exists(res["path"]))
        self.assertTrue(any("Google Drive" in e for e in res["errors"]))
        self.assertIn("Google Drive", cfg.get("last_backup_msg"))
        cfg.set_many({"feat_backup_gdrive": "0"})
        with self.assertRaises(FileNotFoundError):
            bk.copy_to(res["path"], os.path.join(tempfile.gettempdir(), "no_such_drive_xyz"))

    def test_restart_command(self):
        cmd = bk.restart_command()
        self.assertEqual(cmd[0], sys.executable)


# ============================================================================ OTP, vault, e-mail
class OtpTests(unittest.TestCase):
    def setUp(self):
        fresh()
        self.m = otpmod.OtpManager()
        self._real = otpmod._now

    def tearDown(self):
        otpmod._now = self._real

    def test_code_format_and_single_use(self):
        code = self.m.issue("p")
        self.assertRegex(code, r"^\d{6}$")
        self.assertEqual(self.m.verify("p", code), (True, "OK"))
        self.assertFalse(self.m.verify("p", code)[0])

    def test_three_wrong_attempts_kill_the_code(self):
        code = self.m.issue("p")
        wrong = "000000" if code != "000000" else "111111"
        self.assertIn("2 attempt", self.m.verify("p", wrong)[1])
        self.assertIn("1 attempt", self.m.verify("p", wrong)[1])
        self.assertIn("No attempts left", self.m.verify("p", wrong)[1])
        self.assertFalse(self.m.verify("p", code)[0])              # even the right code is dead now

    def test_expiry_after_five_minutes(self):
        t = [1000.0]
        otpmod._now = lambda: t[0]
        code = self.m.issue("p")
        t[0] += 299
        self.assertTrue(self.m.pending("p"))
        t[0] += 2
        self.assertFalse(self.m.pending("p"))
        ok, msg = self.m.verify("p", code)
        self.assertFalse(ok)
        self.assertIn("expired", msg)

    def test_new_code_replaces_old_and_purposes_are_separate(self):
        a = self.m.issue("one")
        b = self.m.issue("one")
        other = self.m.issue("two")
        if a != b:
            self.assertFalse(self.m.verify("one", a)[0])
        self.assertTrue(self.m.verify("two", other)[0])

    def test_whatsapp_link_and_phone_normalising(self):
        self.assertEqual(otpmod.normalize_phone("077 123 4567"), "94771234567")
        self.assertEqual(otpmod.normalize_phone("+94 77 123 4567"), "94771234567")
        url = otpmod.whatsapp_otp_url("0771234567", "123456", "factory-reset", "Shop")
        self.assertTrue(url.startswith("https://wa.me/94771234567?text="))
        self.assertIn("123456", url)
        with self.assertRaises(ValueError):
            otpmod.whatsapp_otp_url("", "123456", "x")

    def test_mask_email(self):
        self.assertEqual(otpmod.mask_email("rajitha@gmail.com"), "r***@gmail.com")


class VaultTests(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_round_trip_and_no_plaintext(self):
        blob = security.vault_encrypt("abcd efgh ijkl mnop")
        self.assertTrue(blob.startswith("enc1:"))
        self.assertNotIn("abcd", blob)
        self.assertEqual(security.vault_decrypt(blob), "abcd efgh ijkl mnop")

    def test_tampered_or_foreign_blob_gives_empty(self):
        blob = security.vault_encrypt("secret")
        self.assertEqual(security.vault_decrypt(blob[:-4] + "AAAA"), "")
        self.assertEqual(security.vault_decrypt("plain-text"), "")
        self.assertEqual(security.vault_decrypt(""), "")

    def test_smtp_password_is_stored_encrypted_in_the_database(self):
        otpmod.set_smtp_password("my app password")
        with dbm.db() as c:
            raw = c.execute("SELECT value FROM settings WHERE key='smtp_pass_enc'").fetchone()[0]
        self.assertTrue(raw.startswith("enc1:"))
        self.assertNotIn("my app password", raw)
        self.assertEqual(otpmod.smtp_config()["password"], "my app password")
        self.assertTrue(otpmod.has_smtp_password())
        otpmod.set_smtp_password("")
        self.assertFalse(otpmod.has_smtp_password())

    def test_backup_file_never_contains_the_plain_password(self):
        otpmod.set_smtp_password("TOPSECRETPASSWORD123")
        seed_path = bk.create("manual")
        with open(seed_path, "rb") as fh:
            self.assertNotIn(b"TOPSECRETPASSWORD123", fh.read())


class _FakeSmtp(socketserver.StreamRequestHandler):
    """Tiny SMTP server: AUTH PLAIN password must be 'goodpass'. Stores the received messages."""
    def handle(self):
        w = lambda s: self.wfile.write((s + "\r\n").encode())            # noqa: E731
        w("220 fake ESMTP")
        data_mode, buf = False, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            t = line.decode(errors="replace").rstrip("\r\n")
            if data_mode:
                if t == ".":
                    self.server.messages.append("\n".join(buf))
                    data_mode, buf = False, []
                    w("250 queued")
                else:
                    buf.append(t)
                continue
            up = t.upper()
            if up.startswith("EHLO") or up.startswith("HELO"):
                w("250-fake"); w("250 AUTH PLAIN")
            elif up.startswith("AUTH PLAIN"):
                _, user, pw = base64.b64decode(t.split()[2]).decode().split("\0")
                w("235 ok" if pw == "goodpass" else "535 5.7.8 bad credentials")
            elif up.startswith(("MAIL", "RCPT")):
                w("250 ok")
            elif up == "DATA":
                w("354 go"); data_mode = True
            elif up == "QUIT":
                w("221 bye"); return
            else:
                w("250 ok")


class SmtpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _FakeSmtp)
        cls.srv.messages = []
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        fresh()
        dbm.settings.set_many({"smtp_host": "127.0.0.1", "smtp_port": str(self.port), "smtp_user": "shop@gmail.com",
                               "owner_email": "owner@example.com", "shop_name": "Test Shop"})
        otpmod.set_smtp_password("goodpass")
        self.srv.messages.clear()

    def test_otp_email_is_delivered_with_the_code(self):
        self.assertTrue(otpmod.email_ready())
        otpmod.send_otp_email("481516", "factory-reset")
        self.assertEqual(len(self.srv.messages), 1)
        m = self.srv.messages[0]
        self.assertIn("481516", m)
        self.assertIn("owner@example.com", m)
        self.assertIn("Test Shop", m)

    def test_wrong_password_gives_a_helpful_message(self):
        otpmod.set_smtp_password("wrongpass")
        with self.assertRaises(RuntimeError) as cm:
            otpmod.send_otp_email("111111", "x")
        self.assertIn("App Password", str(cm.exception))

    def test_unreachable_server_message(self):
        dbm.settings.set_many({"smtp_port": "1"})
        with self.assertRaises(RuntimeError) as cm:
            otpmod.send_otp_email("111111", "x")
        self.assertIn("Cannot reach", str(cm.exception))

    def test_refuses_plain_smtp_to_a_remote_host(self):
        with self.assertRaises(ValueError):
            otpmod.send_email("a@b.com", "s", "b", dict(host="mail.example.com", port=25, user="u", password="p"))

    def test_not_ready_without_setup(self):
        otpmod.set_smtp_password("")
        self.assertFalse(otpmod.email_ready())
        with self.assertRaises(ValueError):
            otpmod.send_otp_email("111111", "x")


# ============================================================================ services: reset / recovery
class ResetTests(unittest.TestCase):
    def setUp(self):
        fresh()
        seed()
        set_license("LICENCE-KEY", "trial-blob")
        dbm.settings.set_many({"shop_name": "Keep Me"})

    def kept(self):
        self.assertEqual(count("users"), 2)
        self.assertEqual(get_license(), ("LICENCE-KEY", "trial-blob"))
        self.assertEqual(dbm.settings.get("shop_name"), "Keep Me")
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()[0], "FACTORY_RESET")

    def test_sales_stock_scope(self):
        res = svc.factory_reset("sales_stock", "admin", "RESET")
        for t in ("sales", "sale_items", "returns", "return_items", "credit_logs", "shifts", "cash_moves", "expenses"):
            self.assertEqual(count(t), 0, t)
        self.assertEqual(count("products"), 2)
        self.assertEqual(count("customers"), 1)
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT SUM(stock_qty) FROM products").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT credit_balance FROM customers").fetchone()[0], 0)
        self.kept()
        pre = sqlite3.connect(res["backup"])                                  # the backup really holds the old data
        self.assertEqual(pre.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 2)
        pre.close()

    def test_products_only_scope(self):
        svc.factory_reset("products", "admin", "RESET")
        self.assertEqual(count("products"), 0)
        self.assertEqual(count("sales"), 2)
        self.assertEqual(count("customers"), 1)
        self.kept()

    def test_everything_scope_and_numbering_restarts(self):
        svc.factory_reset("everything", "admin", "RESET")
        for t in ("products", "customers", "sales", "returns", "expenses", "shifts", "quotations"):
            self.assertEqual(count(t), 0, t)
        self.kept()
        with dbm.db() as c:
            c.execute("INSERT INTO customers(name,phone) VALUES('New','1')")
            self.assertEqual(c.execute("SELECT id FROM customers").fetchone()[0], 1)

    def test_wrong_confirmation_text_does_nothing_and_makes_no_backup(self):
        for bad in ("reset", "", "RESET NOW"):
            with self.assertRaises(ValueError):
                svc.factory_reset("everything", "admin", bad)
        self.assertEqual(count("sales"), 2)
        self.assertFalse(any(b["tag"] == "pre-reset" for b in bk.list_backups()))
        with self.assertRaises(ValueError):
            svc.factory_reset("bogus", "admin", "RESET")

    def test_failed_backup_aborts_the_wipe(self):
        real = bk.create
        bk.create = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
        try:
            with self.assertRaises(RuntimeError):
                svc.factory_reset("everything", "admin", "RESET")
        finally:
            bk.create = real
        self.assertEqual(count("products"), 2)
        self.assertEqual(count("sales"), 2)

    def test_failure_midway_rolls_everything_back(self):
        with dbm.db() as c:
            c.execute("CREATE TRIGGER block_items BEFORE DELETE ON sale_items BEGIN SELECT RAISE(ABORT,'blocked'); END")
        before = {t: count(t) for t in ("return_items", "returns", "sale_items", "sales", "products", "customers")}
        with self.assertRaises(sqlite3.DatabaseError):
            svc.factory_reset("everything", "admin", "RESET")
        self.assertEqual({t: count(t) for t in before}, before)               # nothing half-wiped
        with dbm.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit_log WHERE action='FACTORY_RESET'").fetchone()[0], 0)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        fresh()

    def test_admin_password_check(self):
        self.assertTrue(svc.verify_admin_password("admin", "admin123"))
        self.assertFalse(svc.verify_admin_password("admin", "nope"))
        self.assertFalse(svc.verify_admin_password("cash", "cash123"))        # cashiers are not admins
        self.assertFalse(svc.verify_admin_password("ghost", "x"))

    def test_recovery_code_regenerate_and_verify(self):
        self.assertFalse(svc.verify_recovery_code("ABCD-EFGH-JKLM-NPQR"))     # none set yet
        old = svc.regenerate_recovery_code("admin")
        self.assertTrue(svc.verify_recovery_code(old))
        self.assertTrue(svc.verify_recovery_code(old.lower().replace("-", " ")))
        self.assertFalse(svc.verify_recovery_code("AAAA-BBBB-CCCC-DDDD"))
        self.assertFalse(svc.verify_recovery_code(""))
        new = svc.regenerate_recovery_code("admin")
        self.assertFalse(svc.verify_recovery_code(old))                       # the old code died
        self.assertTrue(svc.verify_recovery_code(new))

    def test_reset_password_rules(self):
        svc.reset_password("admin", "brandnew1", "Recovery Code")
        self.assertTrue(svc.verify_admin_password("admin", "brandnew1"))
        self.assertFalse(svc.verify_admin_password("admin", "admin123"))
        with dbm.db() as c:
            row = c.execute("SELECT action, detail FROM audit_log WHERE action='PASSWORD_RESET'").fetchone()
        self.assertIn("via=Recovery Code", row["detail"])
        with self.assertRaises(ValueError):
            svc.reset_password("admin", "short", "x")
        with self.assertRaises(ValueError):
            svc.reset_password("cash", "longenough", "x")                     # admins only
        with self.assertRaises(ValueError):
            svc.reset_password("ghost", "longenough", "x")
        self.assertEqual(svc.admin_usernames(), ["admin"])

    def test_persistent_lockout(self):
        for _ in range(4):
            self.assertFalse(svc.register_fail("forgot"))
        self.assertEqual(svc.lock_remaining("forgot"), 0)
        self.assertTrue(svc.register_fail("forgot"))                           # 5th wrong try locks
        self.assertGreater(svc.lock_remaining("forgot"), 800)
        self.assertEqual(svc.lock_remaining("reset"), 0)                       # other scopes unaffected
        svc.clear_fails("forgot")
        self.assertEqual(svc.lock_remaining("forgot"), 0)

    def test_defaults_protect_existing_installs(self):
        self.assertEqual(dbm.settings.get("setup_done"), "1")                  # upgrade never shows the wizard
        keys = {k for k, _ in dbm.FEATURES}
        for k in ("feat_autobackup", "feat_backup_on_exit", "feat_backup_gdrive", "feat_otp", "feat_forgot_pw"):
            self.assertIn(k, keys)
            self.assertIn(k, dbm.DEFAULTS)


# ============================================================================ printing fixes
class PrintingTests(unittest.TestCase):
    def test_bottom_feed_is_configurable(self):
        img = Image.new("L", (64, 8), 255)                                      # blank -> no stray 1b 64 in raster
        one = P.build_job(P.Cfg({"print_bottom_feed": "1"}), img, cut=True)
        zero = P.build_job(P.Cfg({"print_bottom_feed": "0"}), img, cut=True)
        many = P.build_job(P.Cfg({"print_bottom_feed": "99"}), img, cut=False)
        self.assertEqual(one.count(b"\x1b\x64\x01"), 1)
        self.assertNotIn(b"\x1b\x64", zero)
        self.assertIn(b"\x1b\x64\x0a", many)                                    # clamped to 10
        self.assertTrue(one.endswith(P.CUTS["Partial cut (GS V 66)"]))
        self.assertFalse(many.endswith(P.CUTS["Partial cut (GS V 66)"]))

    def test_default_feed_is_tightest_and_no_cutter_keeps_tear_margin(self):
        img = Image.new("L", (64, 8), 255)
        self.assertNotIn(b"\x1b\x64", P.build_job(P.Cfg({}), img, cut=True))          # default 0 lines
        nocut = P.build_job(P.Cfg({"print_bottom_feed": "0"}), img, cut=False)
        self.assertIn(b"\x1b\x64\x04", nocut)                                         # min 4 lines to tear off

    def test_hyphen_is_always_a_solid_bar(self):
        R = P.PILText("Arial", 26)                         # falls back to a system font
        img = Image.new("L", (200, 50), 255)
        R.draw(img, 10, 5, "-", "n")
        bw = img.point(lambda v: 255 if v < 165 else 0)                                # the OLD threshold, worst case
        ink = [(x, y) for x in range(200) for y in range(50) if bw.getpixel((x, y))]
        rows = {y for _, y in ink}
        self.assertGreaterEqual(len(rows), 2)                                           # at least 2 px thick
        self.assertGreaterEqual(len(ink), 2 * 6)
        img2 = Image.new("L", (400, 50), 255)
        R.draw(img2, 5, 5, "INV20261020-0002 2026-10-20", "n")
        self.assertGreater(R.width("INV20261020-0002", "n"), 100)

    def test_logo_empty_border_is_cropped(self):
        os.makedirs(dbm.p("Assets"), exist_ok=True)
        art = Image.new("RGBA", (400, 300), (0, 0, 0, 0))                               # mostly transparent canvas
        for x in range(180, 220):
            for y in range(130, 170):
                art.putpixel((x, y), (0, 0, 0, 255))
        art.save(dbm.p("Assets", "shop_logo.png"))
        try:
            lg = P._logo(P.Cfg({"feat_print_logo": "1"}), 576)
            self.assertLessEqual(lg.size[0], 46)                                         # 40 px of ink + 2*3 pad
            self.assertLessEqual(lg.size[1], 46)
        finally:
            os.remove(dbm.p("Assets", "shop_logo.png"))

    def test_top_of_the_receipt_is_tight(self):
        cfg = P.Cfg({"shop_name": "Shop", "address": "", "phone": "", "feat_print_logo": "0"})
        img = P.render_doc(cfg, self._doc(1), 576)
        px = img.load()
        first = min(y for y in range(img.height) if any(px[x, y] < 128 for x in range(0, 576, 2)))
        self.assertLessEqual(first, 12)                                                  # was 10 + glyph ascent padding

    def test_threshold_keeps_thin_strokes(self):
        img = Image.new("L", (16, 2), 180)                                      # a light gray stroke (like a thin '-')
        self.assertEqual(set(P.raster_bytes(img, threshold=165)[8:]), {0})
        self.assertNotEqual(set(P.raster_bytes(img, threshold=190)[8:]), {0})
        job = P.build_job(P.Cfg({"print_threshold": "190"}), img, cut=False)
        self.assertNotEqual(set(job[2 + 8:]), {0, 0x1b, 0x64, 1})

    def test_margins_and_shift(self):
        self.assertEqual(P.margins(P.Cfg({"print_shift_left": "0"})), (14, 14))
        self.assertEqual(P.margins(P.Cfg({"print_shift_left": "16"})), (2, 30))
        self.assertEqual(P.margins(P.Cfg({"print_shift_left": "999"})), (2, 54))
        self.assertEqual(P.margins(P.Cfg({"print_shift_left": "-5"})), (14, 14))

    def _doc(self, n=12):
        items = [(f"Very long product name number {i} " * 6, 2, 123.45, 246.9, "S/N:ABC123 Warranty:1 Year") for i in range(n)]
        return dict(title="", meta=[("Invoice", "INV20261019-0007"), ("Date", "2026-10-19 14:22:18")], items=items,
                    totals=[("NET TOTAL", "Rs. 2,962.80", True)], footer="Thank you!", kind="INVOICE")

    def test_long_bills_are_never_cut_off(self):
        cfg = P.Cfg({"shop_name": "Shop", "address": "Addr", "phone": "011", "print_shift_left": "0"})
        img = P.render_doc(cfg, self._doc(), 576)
        self.assertEqual(img.width, 576)
        self.assertGreater(img.height, 2500)                                    # the old fixed estimate would have clipped this
        px = img.load()
        last = max(y for y in range(img.height) if any(px[x, y] < 128 for x in range(0, 576, 2)))
        self.assertTrue(8 <= img.height - last < 50, img.height - last)         # footer present, small bottom padding

    def test_content_stays_inside_the_margins(self):
        for shift, (ml, mr) in ((0, (14, 14)), (16, (2, 30))):
            cfg = P.Cfg({"shop_name": "Shop", "address": "Addr", "phone": "011", "print_shift_left": str(shift)})
            img = P.render_doc(cfg, self._doc(3), 576)
            px = img.load()
            dark_x = [x for x in range(576) for y in range(0, img.height, 2) if px[x, y] < 128]
            self.assertGreaterEqual(min(dark_x), ml)
            self.assertLess(max(dark_x), 576 - mr)

    def test_text_report_and_calibration_still_render(self):
        cfg = P.Cfg({})
        self.assertEqual(P.render_text(cfg, "Z REPORT\n" + "x" * 40, 576).width, 576)
        self.assertEqual(P.calibration_image(576).width, 576)


if __name__ == "__main__":
    unittest.main(verbosity=2)
