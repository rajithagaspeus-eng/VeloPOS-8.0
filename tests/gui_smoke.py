"""GUI *smoke* test without a display: customtkinter/tkinter are replaced by permissive stubs, then the new
screens/dialogs are built and their button handlers are executed against a real temp database.
It catches NameError / wrong attribute / wrong call-signature bugs. It CANNOT judge layout, colours or real Tk behaviour.
Run:  python tests/gui_smoke.py"""
import os, sys, tempfile, types

os.environ["VELOPOS_HOME"] = tempfile.mkdtemp(prefix="velopos_gui_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CREATED, BOXES = [], []


class W:
    def __init__(self, *a, **k):
        self.kw, self._val, self.a = k, k.get("value", ""), a
        CREATED.append(self)

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return lambda *a, **k: W()
    def pack(self, *a, **k): return self
    def grid(self, *a, **k): return self
    def place(self, *a, **k): return self
    def get(self): return self._val
    def set(self, v): self._val = v
    def insert(self, i, v=None, **k):
        if v is not None and not k:
            self._val = v          # Entry.insert(index, text)
        return 'iid'               # Treeview.insert(parent, index, values=...)
    def delete(self, *a): self._val = ""
    def select(self): self._val = 1
    def deselect(self): self._val = 0
    def get_children(self): return []
    def selection(self): return []
    def winfo_children(self): return []
    def winfo_toplevel(self): return self
    def configure(self, **k): self.kw.update(k)
    cget = lambda self, k: self.kw.get(k)


class Var:
    def __init__(self, value=""): self.v = value
    def get(self): return self.v
    def set(self, v): self.v = v


ctk = types.ModuleType("customtkinter")
for n in ("CTk CTkFrame CTkToplevel CTkLabel CTkButton CTkEntry CTkOptionMenu CTkCheckBox CTkRadioButton CTkScrollableFrame "
          "CTkTabview CTkTextbox CTkSwitch CTkSegmentedButton CTkProgressBar CTkImage CTkFont CTkComboBox").split():
    setattr(ctk, n, type(n, (W,), {}))
ctk.StringVar = ctk.IntVar = ctk.BooleanVar = Var
ctk.set_appearance_mode = ctk.set_default_color_theme = lambda *a, **k: None
ctk.get_appearance_mode = lambda: "Light"
tk = types.ModuleType("tkinter")
tk.Canvas = tk.Tk = tk.Toplevel = W
tk.StringVar = tk.IntVar = tk.BooleanVar = Var
tk.TclError = Exception
mb = types.ModuleType("tkinter.messagebox")
ASK = {"yes": True}
for n in ("showinfo", "showwarning", "showerror"):
    setattr(mb, n, lambda title="", msg="", _n=n, **k: BOXES.append((_n, title, msg)))
mb.askyesnocancel = lambda title="", msg="", **k: (BOXES.append(("askc", title, msg)), ASK["yes"])[1]
mb.askyesno = lambda title="", msg="", **k: (BOXES.append(("ask", title, msg)), ASK["yes"])[1]
fd = types.ModuleType("tkinter.filedialog")
FD = {"dir": tempfile.mkdtemp(), "file": ""}
fd.askdirectory = lambda **k: FD["dir"]
fd.askopenfilename = lambda **k: FD["file"]
fd.asksaveasfilename = lambda **k: ""
ttk = types.ModuleType("tkinter.ttk")
ttk.Treeview = ttk.Style = ttk.Combobox = W
sd = types.ModuleType("tkinter.simpledialog")
ASKSTR = {"v": None}
sd.askstring = lambda *a, **k: ASKSTR["v"]
tk.messagebox, tk.filedialog, tk.ttk, tk.simpledialog = mb, fd, ttk, sd
sys.modules.update({"customtkinter": ctk, "tkinter": tk, "tkinter.messagebox": mb, "tkinter.filedialog": fd, "tkinter.ttk": ttk, "tkinter.simpledialog": sd})

from velopos import backup as bk, database as dbm, otp, security, services as svc          # noqa: E402
from velopos import dialogs                                                                 # noqa: E402
from velopos.screens import backup as bscreen, settings as sscreen, wizard                  # noqa: E402

dbm.init_db()
with dbm.db() as c:
    c.execute("INSERT INTO users VALUES('admin',?, 'Admin','now')", (security.hash_password("admin123"),))
    c.execute("INSERT INTO products(barcode,name_en,selling_price,stock_qty) VALUES('A','Sugar',150,5)")
svc.regenerate_recovery_code("admin")
CMD = {}


class FakeApp(W):
    s, user, role, is_admin, accent, cur = dbm.settings, "admin", "Admin", True, "#2563EB", "Rs."
    restarted = False
    held, wholesale, pending_cart = {}, False, None
    def f(self, *a, **k): return ("Segoe UI", 12)
    def card(self, *a, **k): return W()
    def btn(self, parent, text, color, cmd=None, **k):
        CMD[text] = cmd
        return W()
    def navigate(self, *a): pass
    def build_shell(self, *a): CMD["_shell"] = a
    def show_wizard(self): CMD["_wizard"] = True
    def restart(self): FakeApp.restarted = True
    def require_admin(self): return True
    def can(self, *a): return True


app = FakeApp()
fails = 0


def step(name, fn):
    global fails
    try:
        fn()
        print("  ok  ", name)
    except Exception as e:                      # noqa: BLE001
        import traceback
        fails += 1
        print("  FAIL", name, "->", type(e).__name__, e)
        traceback.print_exc()


def last_box():
    return BOXES[-1] if BOXES else None


# ---------------------------------------------------------------- Backup screen
scr = bscreen.BackupScreen.__new__(bscreen.BackupScreen)
step("BackupScreen builds", lambda: bscreen.BackupScreen.__init__(scr, app, W()))
step("backup now", lambda: (scr.backup_now(), None))
step("backup to USB folder", scr.backup_usb)
scr.paths = {"i1": bk.list_backups()[0]}
scr.tree = type("T", (W,), {"selection": lambda s: ["i1"], "get_children": lambda s: []})()
step("verify selected", scr.verify_selected)
step("copy to drive (bad folder -> message)", lambda: (scr.drive.insert(0, "/nonexistent"), scr.copy_to_drive()))
scr.drive.insert(0, FD["dir"])
step("save schedule", scr.save_schedule)
assert dbm.settings.get("backup_interval_hours") == "6", dbm.settings.get("backup_interval_hours")
step("copy to drive (ok)", scr.copy_to_drive)
before = len(bk.list_backups())
dbm.settings.set_many({"shop_name": "CHANGED"})
good = bk.create("manual")
dbm.settings.set_many({"shop_name": "AFTER"})
step("restore (confirm yes) restarts app", lambda: scr.do_restore(good))
assert FakeApp.restarted and dbm.settings.get("shop_name") == "CHANGED"
FakeApp.restarted = False
ASK["yes"] = False
dbm.settings.set_many({"shop_name": "KEEP"})
step("restore (confirm NO) changes nothing", lambda: scr.do_restore(good))
assert dbm.settings.get("shop_name") == "KEEP" and not FakeApp.restarted
ASK["yes"] = True

# ---------------------------------------------------------------- Settings screen
sc = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
step("SettingsScreen builds", lambda: sscreen.SettingsScreen.__init__(sc, app, W()))
step("settings.save", sc.save)
step("settings.test_email (no setup -> message)", sc.test_email)
step("settings.new_recovery wrong password", lambda: (setattr(dialogs, "ask_password", lambda *a: "bad"), setattr(sscreen, "ask_password", lambda *a: "bad"), sc.new_recovery()))
old_rc = last_box()
sscreen.ask_password = lambda *a: "admin123"
step("settings.new_recovery ok", sc.new_recovery)
assert last_box()[1].startswith("SAVE YOUR NEW RECOVERY CODE"), last_box()

# ---------------------------------------------------------------- Wizard
wz = wizard.Wizard.__new__(wizard.Wizard)
step("Wizard builds step 1", lambda: wizard.Wizard.__init__(wz, app))
for i in range(1, 5):
    step(f"Wizard go({i})", lambda i=i: wz.go(i))
step("Wizard printer test handlers", lambda: (wz.go(2), wz.collect()))
step("Wizard back/forward keeps values", lambda: (wz.go(0), wz.w["shop_name"][1].insert(0, "Wizard Shop"), wz.go(1), wz.go(0)))
assert wz.vals["shop_name"] == "Wizard Shop"
wz.go(3)
wz.w["_smtp_pass"][1].insert(0, "app-pass-123")
dbm.settings.set_many({"setup_done": "0"})
step("Wizard finish saves + encrypts + marks done", lambda: (wz.go(4), wz.finish()))
assert dbm.settings.get("setup_done") == "1" and dbm.settings.get("shop_name") == "Wizard Shop"
assert otp.smtp_config()["password"] == "app-pass-123" and "app-pass" not in dbm.settings.get("smtp_pass_enc")
assert CMD["_shell"] == ("billing",)

# ---------------------------------------------------------------- Forgot password
def by_ph(ph):
    return [w for w in CREATED if w.kw.get("placeholder_text") == ph][-1]

fp = dialogs.ForgotPasswordDialog.__new__(dialogs.ForgotPasswordDialog)
step("ForgotPassword builds", lambda: dialogs.ForgotPasswordDialog.__init__(fp, app))
panel = [w for w in CREATED if isinstance(w, dialogs.OtpPanel)][-1] if any(isinstance(w, dialogs.OtpPanel) for w in CREATED) else None
step("OtpPanel exists", lambda: (_ for _ in ()).throw(AssertionError("no panel")) if panel is None else None)
# Phase 7.2: support-code method
panel.method.set(dialogs.OtpPanel.SUP)
step("support-code method shows Machine ID + challenge", panel._changed)
assert dialogs.lic.machine_id() in panel.hint.kw["text"] and panel.challenge in panel.hint.kw["text"]
_old = panel.challenge
step("support-code 'New challenge'", panel.send)
assert panel.challenge != _old and panel.challenge in panel.hint.kw["text"]
panel.code.insert(0, "123.abc")
step("wrong support code is refused", panel.verify)
assert any(k in panel.status.kw["text"].lower() for k in ("support code", "public key"))      # (the test copy has no _pubkey.py)
svc.clear_fails("forgot")
panel.method.set(dialogs.OtpPanel.REC)
panel._changed()
panel.code.insert(0, "WRONG-CODE")
step("wrong recovery code -> rejected", panel.verify)
assert "Wrong Recovery Code" in panel.status.kw["text"], panel.status.kw
new_rc = svc.regenerate_recovery_code("admin")
panel.code.insert(0, new_rc)
step("right recovery code -> next step", panel.verify)
fp.user_var.set("admin")
p1, p2 = by_ph("New password (min 6 characters)"), by_ph("Repeat new password")
p1.insert(0, "freshpass1"); p2.insert(0, "freshpass2")
step("mismatched passwords warned", CMD["SET NEW PASSWORD"])
assert last_box()[0] == "showwarning"
p2.insert(0, "freshpass1")
step("new password saved", CMD["SET NEW PASSWORD"])
assert svc.verify_admin_password("admin", "freshpass1")

# ---------------------------------------------------------------- Factory reset
fr = dialogs.FactoryResetDialog.__new__(dialogs.FactoryResetDialog)
step("FactoryReset builds", lambda: dialogs.FactoryResetDialog.__init__(fr, app))
fr.pw.insert(0, "WRONG")
step("wrong admin password", fr.check_password)
assert fr.err.kw["text"] == "Incorrect password."
fr.pw.insert(0, "freshpass1")
dbm.settings.set_many({"feat_otp": "1"})
step("password ok -> OTP step", fr.check_password)
assert not fr.authorized
panel = [w for w in CREATED if isinstance(w, dialogs.OtpPanel)][-1]
panel.method.set(dialogs.OtpPanel.EMAIL)
step("email OTP not set up -> warning", panel.send)
assert last_box()[0] == "showwarning"
panel.method.set(dialogs.OtpPanel.WA)
dbm.settings.set_many({"owner_whatsapp": "0771234567"})
opened = []
svc.open_url = lambda u, desktop=False: opened.append(u)
step("WhatsApp OTP opens link with code", panel.send)
assert opened and opened[0].startswith("https://wa.me/94771234567?text=")
code = opened[0].split("code%3A%20")[1][:6]
panel.code.insert(0, code)
step("correct WhatsApp code accepted", panel.verify)
assert fr.authorized
step("confirm without typing RESET -> nothing erased", lambda: (CMD["ERASE NOW"](), None))
assert last_box()[0] == "showerror" and svc.table_counts()["products"] == 1
ent = [w for w in CREATED if w.kw.get("placeholder_text") == "RESET"][-1]
ent.insert(0, "RESET")
step("ERASE NOW wipes + restarts", CMD["ERASE NOW"])
with dbm.db() as c:
    assert c.execute("SELECT SUM(stock_qty) FROM products").fetchone()[0] == 0     # default scope = sales+stock
assert svc.table_counts()["products"] == 1 and svc.table_counts()["sales"] == 0 and FakeApp.restarted
assert any(b["tag"] == "pre-reset" for b in bk.list_backups())

# ---------------------------------------------------------------- main.py lifecycle (App methods on a fake self)
from velopos import main as M                                                                # noqa: E402
fake = types.SimpleNamespace(user="admin", s=dbm.settings, _backup_busy=False, _last_try=0.0, scheduled=[],
                             after=lambda ms, fn=None: fake.scheduled.append(ms), destroy=lambda: CMD.__setitem__("_destroyed", True), _auto_tick=lambda: None)
dbm.settings.set_many({"feat_autobackup": "1", "backup_interval_hours": "6", "last_auto_backup": "", "feat_backup_gdrive": "0"})
n0 = len(bk.list_backups())
step("App._auto_tick starts a due backup + re-arms", lambda: M.App._auto_tick(fake))
import time; time.sleep(1.5)
assert len(bk.list_backups()) == n0 + 1 and fake.scheduled == [60_000] and not fake._backup_busy
n1 = len(bk.list_backups())
step("App._auto_tick does nothing when not due", lambda: M.App._auto_tick(fake))
assert len(bk.list_backups()) == n1
dbm.settings.set_many({"feat_backup_on_exit": "1"})
step("App.on_close makes an exit backup and closes", lambda: M.App.on_close(fake))
assert any(b["tag"] == "exit" for b in bk.list_backups()) and CMD.get("_destroyed")


# ================================================================ PHASE 5: assistant UI, settings 4d, app hooks
from velopos import assistant, assistant_i18n as I, voice                                    # noqa: E402
from velopos.screens import assistant as ascreen                                             # noqa: E402

dbm.settings.set_many({"assistant_lang": "Auto (match my question)", "feat_assistant_voice": "0", "feat_voice_input": "0"})
SPOKEN = []
voice.speak = lambda text, lang="en", enabled=True, on_result=None, sync=False: SPOKEN.append((text, lang, on_result))
panel = ascreen.ChatPanel(W(), app)
step("ChatPanel builds with chips + hello", lambda: None)
step("chip question answered", lambda: panel.ask("stock of sugar"))
step("empty question ignored", lambda: panel.ask("   "))
step("Sinhala question", lambda: panel.ask("අද විකුණුම්"))
step("how-to question", lambda: panel.ask("how do I make a return"))
step("daily summary reply has buttons", lambda: panel.ask("daily summary"))
assert "Send to owner" in CMD, list(CMD)[-6:]
SENT = []
app.daily_summary_now = lambda reason="manual": SENT.append(reason)
CMD["Send to owner"]()
assert SENT == ["chat"]
step("language menu persists the choice", lambda: panel.set_lang("Español (Spanish)"))
assert dbm.settings.get("assistant_lang") == "Español (Spanish)" and panel.chip_lang() == "es"
step("speak toggle persists", lambda: (panel.speak_cb.select(), panel.toggle_speak()))
assert dbm.settings.bool("feat_assistant_voice")
n = len(SPOKEN)
step("answer is spoken when enabled", lambda: panel.ask("ventas de hoy"))
assert len(SPOKEN) == n + 1 and SPOKEN[-1][1] == "es"
step("no-voice note shown once", lambda: (SPOKEN[-1][2]("novoice"), SPOKEN[-1][2]("novoice")))
step("mic without the optional package -> friendly note", lambda: (dbm.settings.set_many({"feat_voice_input": "1"}), panel.listen()))
step("AssistantScreen builds", lambda: ascreen.AssistantScreen.__init__(ascreen.AssistantScreen.__new__(ascreen.AssistantScreen), app, W()))
step("floating popup opens once", lambda: (ascreen.open_popup(app), ascreen.open_popup(app)))
assert app._chat_popup is not None
assert ascreen.label_for("English") == "English" and ascreen.label_for("es") == "Español (Spanish)" and ascreen.label_for("nonsense") == I.AUTO_LABEL

# Settings 4d handlers
sc2 = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
step("Settings builds (incl. 4d)", lambda: sscreen.SettingsScreen.__init__(sc2, app, W()))
step("settings.check_voices handler", lambda: (setattr(sscreen, "run_bg", lambda w, work, done: done((True, {"en": ["David"]}), None)), sc2.check_voices()))
assert "NO voice installed" in sc2.lbl_voice.kw["text"] and "David" in sc2.lbl_voice.kw["text"]
step("settings.test_voice handler", lambda: (sc2.w.__setitem__("assistant_lang", types.SimpleNamespace(get=lambda: "Español (Spanish)")), sc2.test_voice()))
assert SPOKEN[-1][1] == "es"

# Settings 4h (owner phone dashboard) handlers
sc2.w["dash_url"] = types.SimpleNamespace(get=lambda: "https://demo.example.workers.dev"); sc2.w["dash_invite"] = types.SimpleNamespace(get=lambda: "")
sscreen.cs.push_snapshot = lambda cfg=None, snap=None, invite=None: (True, "Uploaded.")
step("settings.dash_test handler", lambda: (setattr(sscreen, "run_bg", lambda w, work, done: done(work(), None)), sc2.dash_test()))
assert "Uploaded." in sc2.lbl_dash.kw["text"]
sc2.w["dash_url"] = types.SimpleNamespace(get=lambda: "http://evil.com"); sc2.dash_test()
assert "https" in sc2.lbl_dash.kw["text"]
sc2.w["dash_url"] = types.SimpleNamespace(get=lambda: "https://demo.example.workers.dev")
_si, _rb = sscreen.messagebox.showinfo, sscreen.run_bg
sscreen.messagebox.showinfo = lambda *a, **k: None
step("settings.dash_link handler", lambda: sc2.dash_link())
sscreen.messagebox.showinfo = _si

# App-level hooks run on a fake 'self'
fake2 = types.SimpleNamespace(s=dbm.settings, accent="#123", cur="Rs.", user="admin", is_admin=True, can=lambda p: True, fab=None, FAB_POS=M.App.FAB_POS,
                              f=lambda *a, **k: ("x", 1), open_assistant_popup=lambda: None, after=lambda *a, **k: None, SENT=[])
fake2.daily_summary_now = lambda reason="manual": fake2.SENT.append(reason)
fake2.PUSHES = []
fake2.dashboard_push_async = lambda force=False, done=None: fake2.PUSHES.append(force)      # Phase 7.1
dbm.settings.set_many({"feat_assistant": "1", "feat_assistant_fab": "1", "assistant_fab_pos": "Bottom-left"})
step("place_fab shows the button", lambda: M.App.place_fab(fake2, "billing"))
assert fake2.fab is not None
step("place_fab hides it on the assistant screen", lambda: M.App.place_fab(fake2, "assistant"))
step("place_fab with feature OFF", lambda: (dbm.settings.set_many({"feat_assistant_fab": "0"}), M.App.place_fab(fake2, "billing")))
dbm.settings.set_many({"feat_daily_summary": "1", "feat_summary_on_close": "1"})
step("on_shift_closed triggers the summary", lambda: M.App.on_shift_closed(fake2, 1))
assert fake2.SENT == ["shift"] and fake2.PUSHES == [True]          # closing a shift also refreshes the owner phone dashboard
dbm.settings.set_many({"feat_summary_on_close": "0"})
M.App.on_shift_closed(fake2, 1)
assert fake2.SENT == ["shift"]

fake3 = types.SimpleNamespace(s=dbm.settings, cur="Rs.", user="admin", is_admin=True, can=lambda p: True, after=lambda *a, **k: None)
OPENED, DELIVERED = [], []
svc.open_url = lambda u, desktop=False: OPENED.append(u)
real_deliver = assistant.deliver_summary
dbm.settings.set_many({"summary_channel": "WhatsApp", "owner_whatsapp": "0771234567", "assistant_lang": "English"})
ASK["yes"] = True
step("daily_summary_now via WhatsApp opens the link", lambda: M.App.daily_summary_now(fake3, "shift"))
assert OPENED and OPENED[-1].startswith("https://wa.me/94771234567?text=")
ASK["yes"] = False
n = len(OPENED)
step("WhatsApp prompt declined -> nothing opened", lambda: M.App.daily_summary_now(fake3, "dayend"))
assert len(OPENED) == n
ASK["yes"] = True
assistant.deliver_summary = lambda summ, ch, cfg=None: (DELIVERED.append((ch, summ["title"])) or ("email", "owner@example.com"))
dbm.settings.set_many({"summary_channel": "Email"})
step("daily_summary_now via Email runs in a thread", lambda: M.App.daily_summary_now(fake3, "manual"))
time.sleep(0.5)
assert DELIVERED and DELIVERED[-1][0] == "Email"
assistant.deliver_summary = real_deliver

fake4 = types.SimpleNamespace(user="admin", s=dbm.settings, _backup_busy=False, _last_try=0.0, after=lambda *a, **k: None, _auto_tick=lambda: None, SUMMARY=[])
fake4.daily_summary_now = lambda reason="manual": fake4.SUMMARY.append(reason)
dbm.settings.set_many({"feat_daily_summary": "1", "feat_summary_dayend": "1", "summary_time": "00:00", "last_summary_date": "", "feat_autobackup": "0"})
step("day-end tick sends once per day", lambda: (M.App._auto_tick(fake4), M.App._auto_tick(fake4)))
assert fake4.SUMMARY == ["dayend"], fake4.SUMMARY

labels = [lab for _, lab, _ in M.App.NAV]
for needed in ("Billing", "Inventory", "Credit Book", "Returns & Refunds", "Shift & Cash Drawer", "Expenses", "Reports & Insights", "Backup & Restore", "Settings", "Ask VeloPOS"):
    assert needed in labels, needed
print("  ok   menu names used in the how-to answers exist in the real menu")


# ================================================================ PHASE 6.1: catalogue UI
from velopos import thumbs                                                                    # noqa: E402
from velopos.screens import billing as bill_screen, inventory as inv_screen, itemgrid, categories as cat_screen, pricetools   # noqa: E402

app.daily_summary_now = lambda reason="manual": None
import tempfile as _tf                                                                        # noqa: E402
from PIL import Image as _Img                                                                 # noqa: E402
_pic = os.path.join(_tf.mkdtemp(), "photo.png")
_Img.new("RGB", (900, 700), (10, 120, 200)).save(_pic)
with dbm.db() as c:
    c.execute("DELETE FROM products")
for i in range(30):
    svc.save_product(f"G{i:02d}", f"Grid Item {i:02d}", "admin", sell=100 + i, wholesale=90 + i, stock=0 if i == 3 else 10, category="Food" if i % 2 else "Home")
svc.save_product("G99", "No Category", "admin", sell=5, stock=2)
svc.set_product_image("G05", _pic, "admin")
dbm.settings.set_many({"feat_categories": "1", "feat_item_grid": "1", "feat_price_history": "1", "grid_page_size": "12", "grid_cols": "3"})

picked = []
grid = itemgrid.ItemGrid(W(), app, picked.append, lambda p: p["selling_price"], lambda p: p["name_en"])
step("ItemGrid builds page 1", lambda: None)
assert grid.page == 0 and len(grid._refs) == 12, len(grid._refs)
step("ItemGrid next/prev page", lambda: (grid.next_page(), grid.next_page()))
assert grid.page == 2 and len(grid._refs) == 7, (grid.page, len(grid._refs))
step("ItemGrid: next beyond the last page is clamped", lambda: (grid.next_page(), grid.next_page()))
assert grid.page == 2
step("ItemGrid category chip resets to page 1", lambda: grid.set_category("Food"))
assert grid.page == 0 and grid.category == "Food" and len(grid._refs) == 12
step("ItemGrid uncategorised filter", lambda: grid.set_category(""))
assert len(grid._refs) == 1
step("ItemGrid search", lambda: (setattr(grid, "text", "grid item 07"), setattr(grid, "category", None), setattr(grid, "page", 0), grid.reload()))
assert len(grid._refs) == 1
step("ItemGrid card click -> on_pick", lambda: grid.on_pick(svc.get_product("G07")))
assert picked and picked[0]["barcode"] == "G07"
step("ItemGrid with categories OFF has no chips", lambda: (dbm.settings.set_many({"feat_categories": "0"}), itemgrid.ItemGrid(W(), app, picked.append, lambda p: 1, lambda p: p["name_en"])))
dbm.settings.set_many({"feat_categories": "1"})

step("Billing builds with the item grid", lambda: bill_screen.BillingScreen.__init__(bill_screen.BillingScreen.__new__(bill_screen.BillingScreen), app, W()))
dbm.settings.set_many({"feat_item_grid": "0"})
step("Billing builds with the item grid OFF (unchanged layout)", lambda: bill_screen.BillingScreen.__init__(bill_screen.BillingScreen.__new__(bill_screen.BillingScreen), app, W()))
bs = bill_screen.BillingScreen.__new__(bill_screen.BillingScreen)
bill_screen.BillingScreen.__init__(bs, app, W())
NAVD = []
app.navigate = lambda *a: NAVD.append(a)
step("Billing 'Item grid' button toggles the setting", bs.toggle_grid)
assert dbm.settings.bool("feat_item_grid") and NAVD[-1] == ("billing",)
dbm.settings.set_many({"feat_item_grid": "1"})

inv = inv_screen.InventoryScreen.__new__(inv_screen.InventoryScreen)
step("Inventory builds (category box, picture, chips)", lambda: inv_screen.InventoryScreen.__init__(inv, app, W()))
step("Inventory chip filter", lambda: inv.set_filter("Food"))
inv.set_filter(None)
SEL = ["G05"]
inv.tree = type("T", (W,), {"selection": lambda s: list(SEL), "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
step("Inventory row select fills the form + picture", inv.on_select)
assert inv.e["barcode"].get() == "G05" and inv.e["name_en"].get() == "Grid Item 05" and inv.cat_box.get() == "Food"
inv.e["add"].insert(0, "7")
inv.cat_box.set("Brand New Category")
step("Inventory save uses the service (+ creates the category)", inv.save)
assert svc.get_product("G05")["stock_qty"] == 17 and svc.get_product("G05")["category"] == "Brand New Category"
assert "Brand New Category" in [r["name"] for r in svc.list_categories()]
assert last_box()[0] == "showinfo", last_box()
inv.e["barcode"].insert(0, "G05"); inv.e["name_en"].insert(0, "Grid Item 05"); inv.e["sell"].insert(0, "-5")
step("Inventory save rejects a negative price politely", inv.save)
assert last_box()[0] == "showwarning" and svc.get_product("G05")["selling_price"] != -5
inv.clear_form()
step("Inventory: required fields warning", inv.save)
assert last_box()[0] == "showwarning"
inv.e["barcode"].insert(0, "G06")
FD["file"] = _pic
step("Inventory: choose picture", inv.choose_image)
assert svc.get_product("G06")["image_path"]
step("Inventory: remove picture", inv.remove_image)
assert svc.get_product("G06")["image_path"] == ""
FD["file"] = os.path.join(_tf.mkdtemp(), "nope.png")
step("Inventory: a bad picture file is refused", inv.choose_image)
assert last_box()[0] == "showwarning"
step("Inventory: bulk price / history buttons", lambda: (inv.bulk_price(), inv.price_history()))
step("Inventory: delete product (admin)", lambda: (inv.clear_form(), inv.e["barcode"].insert(0, "G99"), inv.delete()))
assert svc.get_product("G99") is None
CSVP = os.path.join(_tf.mkdtemp(), "in.csv")
with open(CSVP, "w", encoding="utf-8-sig") as fh:
    fh.write("barcode,name_en,name_local,keywords,cost_price,selling_price,wholesale_price,stock_qty,expiry_date,warranty,category\n"
             "C1,Csv One,,,1,2,0,5,,,Imported\nC2,Csv Two,,,1,2,0,5,,,\n,bad,,,,,,,,,\n")
FD["file"] = CSVP
step("Inventory CSV import with category column", inv.import_csv)
assert svc.get_product("C1")["category"] == "Imported" and "Imported: 2" in last_box()[2] and "Skipped (bad rows): 1" in last_box()[2], last_box()

# bulk price dialog end-to-end
CMD.clear()
step("Bulk price dialog builds", lambda: pricetools.open_bulk_price(app, ["G01", "G02"], lambda: CMD.__setitem__("_done", True)))
vals = [w for w in CREATED if w.kw.get("placeholder_text") == "e.g. 5 or -2.5"][-1]
vals.insert(0, "10")
before = svc.get_product("G01")["selling_price"]
step("Bulk price: preview", CMD["Preview"])
step("Bulk price: apply (confirmed)", CMD["APPLY CHANGES"])
assert abs(svc.get_product("G01")["selling_price"] - round(before * 1.1, 2)) < 0.01 and CMD.get("_done")
assert len(svc.price_history("G01")) == 1
CMD.clear()
pricetools.open_bulk_price(app, [], None)
vals = [w for w in CREATED if w.kw.get("placeholder_text") == "e.g. 5 or -2.5"][-1]
vals.insert(0, "abc")
step("Bulk price: non-numeric value is handled", CMD["Preview"])
step("Price history dialog", lambda: pricetools.open_price_history(app, "G01"))
step("Price history for nothing selected", lambda: pricetools.open_price_history(app, ""))

# categories dialog
CMD.clear()
step("Manage categories dialog opens", lambda: cat_screen.open_manage_categories(app, lambda: CMD.__setitem__("_changed", True)))
ent = [w for w in CREATED if w.kw.get("placeholder_text") == "New category name"][-1]
ent.insert(0, "Smoke Cat")
step("Manage categories: add", CMD["Add"])
assert "Smoke Cat" in [r["name"] for r in svc.list_categories()] and CMD.get("_changed")
ent.insert(0, "smoke cat")
step("Manage categories: duplicate is refused politely", CMD["Add"])
assert last_box()[0] == "showwarning"
step("Manage categories: rename/delete with nothing selected -> message", lambda: (CMD["Rename"](), CMD["Delete"]()))

# settings 4e
dbm.settings.set_many({"feat_item_grid": "1"})
sc3 = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
step("Settings builds (incl. 4e)", lambda: sscreen.SettingsScreen.__init__(sc3, app, W()))
step("Settings: clear picture cache", sc3.clear_thumbs)
assert "cleared" in sc3.lbl_cat.kw["text"]


# ================================================================ PHASE 6.2: stock control UI
from velopos.screens import stock as stock_screen, units as units_screen                     # noqa: E402

with dbm.db() as c:
    c.execute("DELETE FROM products")
svc.save_product("S1", "Stock Item One", "admin", cost=10, sell=20, stock=20, category="Food")
svc.save_product("S2", "Stock Item Two", "admin", cost=5, sell=9, stock=8, category="Home")
dbm.settings.set_many({"feat_batches": "0", "feat_multi_unit": "0", "feat_stock_screen": "1", "feat_categories": "1"})
ASK["yes"] = True
ss = stock_screen.StockScreen.__new__(stock_screen.StockScreen)
step("StockScreen builds (batches OFF)", lambda: stock_screen.StockScreen.__init__(ss, app, W()))
step("Stock: adjust without an item -> nothing happens", ss.apply_adjust)
ss.e_bar.insert(0, "S1"); ss.e_qty.insert(0, "3"); ss.m_type.set("Damage (remove)"); ss.e_note.insert(0, "wet")
step("Stock: damage adjustment", ss.apply_adjust)
assert svc.get_product("S1")["stock_qty"] == 17 and svc.stock_log(reason="DAMAGE")[0]["note"] == "wet"
ss.e_bar.insert(0, "S1"); ss.e_qty.insert(0, "50"); ss.m_type.set("Lost / stolen (remove)")
step("Stock: too large removal is refused politely", ss.apply_adjust)
assert last_box()[0] == "showwarning" and svc.get_product("S1")["stock_qty"] == 17
ss.e_bar.insert(0, "S1"); ss.e_qty.insert(0, "abc")
step("Stock: bad quantity", ss.apply_adjust)
assert last_box()[0] == "showwarning"
ss.e_bar.insert(0, "S1"); ss.e_qty.insert(0, "2"); ss.m_type.set("Found (add)")
step("Stock: found adds", ss.apply_adjust)
assert svc.get_product("S1")["stock_qty"] == 19
ss.e_bar.insert(0, "nothing like this"); 
step("Stock: unknown item lookup", ss.lookup)
step("Stock: filter + export", lambda: (ss.load_log(), ss.export_log()))
FD_SAVE = os.path.join(_tf.mkdtemp(), "log.csv")
fd.asksaveasfilename = lambda **k: FD_SAVE
step("Stock: export CSV writes a file", ss.export_log)
assert os.path.exists(FD_SAVE)
step("Stock: tabs switch", lambda: (ss.show("adjust"), ss.show("count")))

step("Stock-take: start via dialog", ss.new_count)
CMD["START"]()
assert ss.count_id and svc.list_counts()[0]["status"] == "OPEN", ss.count_id
ss.c_bar.insert(0, "S1"); ss.c_qty.insert(0, "15")
step("Stock-take: add a count", ss.add_count)
ss.c_bar.insert(0, "S2"); ss.c_qty.insert(0, "x")
step("Stock-take: bad quantity message", ss.add_count)
CSVC = os.path.join(_tf.mkdtemp(), "counts.csv")
with open(CSVC, "w", encoding="utf-8-sig") as fh:
    fh.write("barcode,counted\nS2,9\nNOPE,1\n")
FD["file"] = CSVC
step("Stock-take: import counts", ss.import_counts)
assert "Counted: 1" in last_box()[2] and "Skipped: 1" in last_box()[2]
step("Stock-take: report dialog", ss.show_report)
step("Stock-take: finalize (admin, leave uncounted)", ss.finalize)
assert svc.get_product("S1")["stock_qty"] == 15 and svc.get_product("S2")["stock_qty"] == 9
assert svc.list_counts()[0]["status"] == "FINAL"
step("Stock-take: closed session is refused politely", lambda: (ss.c_bar.insert(0, "S1"), ss.c_qty.insert(0, "1"), ss.add_count()))
assert last_box()[0] == "showwarning"
ss.count_id = None
step("Stock-take: actions need a session", lambda: (ss.show_report(), ss.finalize(), ss.cancel()))
step("Stock-take: start + cancel", lambda: (ss.new_count(), CMD["START"](), ss.cancel()))
assert svc.list_counts()[0]["status"] == "CANCELLED"

# batches tab
dbm.settings.set_many({"feat_batches": "1"})
sb = stock_screen.StockScreen.__new__(stock_screen.StockScreen)
step("StockScreen builds with the Batches tab", lambda: stock_screen.StockScreen.__init__(sb, app, W()))
for k, v in (("bar", "S1"), ("no", "LOT-9"), ("exp", "2031-01-31"), ("qty", "6"), ("cost", "11")):
    sb.b[k].insert(0, v)
step("Batches: receive a batch", sb.receive)
assert any(b["batch_no"] == "LOT-9" and b["qty_remaining"] == 6 for b in svc.list_batches("S1")) and svc.get_product("S1")["stock_qty"] == 21
sb.e_bar.insert(0, "S1")
step("Stock: lookup fills the batch menu", sb.lookup)
assert len(sb.batch_map) >= 2
sb.e_qty.insert(0, "2"); sb.m_type.set("Damage (remove)"); sb.m_batch.set([k for k in sb.batch_map if "LOT-9" in k][0])
step("Stock: damage taken from the chosen batch", sb.apply_adjust)
assert [b["qty_remaining"] for b in svc.list_batches("S1") if b["batch_no"] == "LOT-9"] == [4]
for k, v in (("bar", "S1"), ("no", ""), ("exp", "not-a-date"), ("qty", "1")):
    sb.b[k].insert(0, v)
step("Batches: bad date refused politely", sb.receive)
assert last_box()[0] == "showwarning"

# settings: switching batch tracking ON runs the migration
dbm.settings.set_many({"feat_batches": "0"})
svc.save_product("S3", "Stock Item Three", "admin", cost=1, sell=2, stock=5, expiry="2031-05-05")
sc4 = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
sscreen.SettingsScreen.__init__(sc4, app, W())
sc4.w["feat_batches"].select()
step("Settings.save with batch tracking switched ON -> migration message", sc4.save)
assert dbm.settings.bool("feat_batches") and any(b["batch_no"] == "OPENING" for b in svc.list_batches("S3"))
assert [x for x in BOXES if x[1] == "Batch tracking"], "no migration message"

# multi-unit: units dialog + billing dialog
dbm.settings.set_many({"feat_multi_unit": "1", "feat_item_grid": "0", "feat_batches": "0"})
svc.save_product("U1", "Loose Rice", "admin", cost=150, sell=200, stock=10)
CMD.clear()
step("Units dialog opens", lambda: units_screen.open_units(app, "U1", None))
for ph, v in (("Unit name", "g"), ("Factor", "0.001"), ("Fixed price", "")):
    [w for w in CREATED if w.kw.get("placeholder_text") == ph][-1].insert(0, v)
step("Units: add a unit", CMD["Add / update unit"])
assert [u["name"] for u in svc.list_units("U1")] == ["pcs", "g"]
[w for w in CREATED if w.kw.get("placeholder_text") == "Factor"][-1].insert(0, "abc")
step("Units: bad factor is refused politely", CMD["Add / update unit"])
assert last_box()[0] == "showwarning"
[w for w in CREATED if w.kw.get("placeholder_text") == "Unit name"][-1].insert(0, "kg")
step("Units: rename base unit", CMD["Rename BASE unit"])
assert svc.get_product("U1")["base_unit"] == "kg"
step("Units: delete with nothing selected", CMD["Delete selected"])
step("Units: dialog for no product", lambda: units_screen.open_units(app, "", None))
inv.e["barcode"].delete(0, "end"); inv.e["barcode"].insert(0, "U1")
step("Inventory: Units button", inv.units_dialog)

bsu = bill_screen.BillingScreen.__new__(bill_screen.BillingScreen)
bill_screen.BillingScreen.__init__(bsu, app, W())
CMD.clear()
pU = svc.get_product("U1")
step("Billing: quantity dialog with a unit menu", lambda: bsu.item_dialog(pU, 200.0))
umenu = [w for w in CREATED if w.kw.get("width") == 90 and "command" in w.kw][-1]
umenu.kw["command"]("g")
umenu.set("g")
pe = [w for w in CREATED if w.kw.get("justify") == "center"]
assert pe[-1].get() == "0.20", pe[-1].get()                                                  # price field switched to the unit price
pe[-2].delete(0, "end"); pe[-2].insert(0, "250")
step("Billing: add 250 g to the bill", CMD["ADD TO BILL (Enter)"])
assert bsu.cart[-1]["unit"] == "g" and bsu.cart[-1]["factor"] == 0.001 and bsu.cart[-1]["qty"] == 250
step("Billing: stock check works in base units", lambda: bsu.put(pU, 10000, 0.2, "", "", None, "g", 0.001))
assert last_box()[0] == "showwarning"
step("Billing: cart row shows the unit", bsu.refresh)
sale = svc.create_sale([dict(barcode="U1", name="Loose Rice", qty=250, price=0.2, unit="g")], 0, 0, 100, "Cash", "", None, "admin", None)
assert sale["net"] == 50.0 and svc.get_product("U1")["stock_qty"] == 9.75
NAV_LABELS = [lab for _, lab, _ in M.App.NAV]
assert "Stock Control" in NAV_LABELS
print("  ok   'Stock Control' is in the menu")


# ================================================================ PHASE 6.3: suppliers, GRN, payables, credit limit, reminders
from velopos import dialogs as _dialogs, printing as _printing                               # noqa: E402
from velopos.screens import suppliers as sup_screen, customers as cust_screen, reports as rep_screen   # noqa: E402

OPENED_HTML = []
_printing.open_html = lambda *a, **k: OPENED_HTML.append(a)
_printing.after_sale = lambda a, s: None
dbm.settings.set_many({"feat_batches": "0", "feat_multi_unit": "0", "feat_shift": "0", "feat_vat": "0", "feat_service_charge": "0", "feat_suppliers": "1",
                       "feat_credit_limit": "1", "feat_overdue_reminders": "1", "feat_whatsapp": "0", "feat_loyalty": "0"})
ASK["yes"] = True
sp = sup_screen.SuppliersScreen.__new__(sup_screen.SuppliersScreen)
step("SuppliersScreen builds", lambda: sup_screen.SuppliersScreen.__init__(sp, app, W()))
sp.s["name"].insert(0, "Smoke Supplier"); sp.s["phone"].insert(0, "0112223334")
step("Supplier: save", sp.save_sup)
sid_ = svc.list_suppliers()[0]["id"]
assert svc.get_supplier(sid_)["name"] == "Smoke Supplier"
sp.s["name"].insert(0, "smoke supplier")
step("Supplier: duplicate refused politely", sp.save_sup)
assert last_box()[0] == "showwarning"
sp.t_sup = type("T", (W,), {"selection": lambda s: [str(sid_)], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
step("Supplier: select + update", lambda: (sp.pick_sup(), sp.s["contact"].insert(0, "Mr Perera"), sp.save_sup()))
assert svc.get_supplier(sid_)["contact"] == "Mr Perera"
step("Supplier: tabs switch", lambda: (sp.show("grn"), sp.show("pay"), sp.show("sup")))

CMD.clear()
before_stock = svc.get_product("S1")["stock_qty"]
step("GRN dialog opens", lambda: sup_screen.open_grn_dialog(app, lambda: CMD.__setitem__("_done", True)))
def ph(t): return [w for w in CREATED if w.kw.get("placeholder_text") == t][-1]
ph("Barcode / item name").insert(0, "S1"); ph("Qty").insert(0, "10"); ph("Cost / unit").insert(0, "12.5")
step("GRN: add a line", CMD["Add line"])
ph("Barcode / item name").insert(0, "S2"); ph("Qty").insert(0, "4"); ph("Cost / unit").insert(0, "6")
step("GRN: add a second line", CMD["Add line"])
ph("Discount").insert(0, "5"); ph("Paid now").insert(0, "100")
n_open = len(OPENED_HTML)
step("GRN: save (+ printable document offered)", CMD["SAVE GRN"])
g = svc.list_purchases()[0]
assert g["total"] == 144.0 and g["paid_total"] == 100 and svc.get_product("S1")["stock_qty"] == before_stock + 10 and CMD.get("_done")
assert len(OPENED_HTML) == n_open + 1, "GRN document was not opened"
CMD.clear()
sup_screen.open_grn_dialog(app, None)
ph("Barcode / item name").insert(0, "S1"); ph("Qty").insert(0, "0"); ph("Cost / unit").insert(0, "5")
step("GRN: zero quantity refused", CMD["Add line"])
assert last_box()[0] == "showwarning"
step("GRN: saving with no lines is refused politely", CMD["SAVE GRN"])
assert last_box()[0] == "showwarning"

sp.t_grn = type("T", (W,), {"selection": lambda s: [str(g["id"])], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
step("GRN: open / print", sp.open_grn_doc)
sp.t_pay = type("T", (W,), {"selection": lambda s: [str(sid_)], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
step("Payables: load", sp.load_pay)
assert "44.00" in sp.lbl_pay.kw["text"], sp.lbl_pay.kw["text"]
CMD.clear()
step("Payables: pay dialog + payment", lambda: (sp.pay_dialog(), CMD["RECORD PAYMENT"]()))
assert svc.payables_total() == 0 and "recorded" in last_box()[2].lower(), last_box()
step("Payables: history dialog", sp.history)
ASKSTR["v"] = "typed twice"
step("GRN: void (admin, stock intact)", sp.void_grn)
assert svc.list_purchases()[0]["status"] == "VOID" and svc.get_product("S1")["stock_qty"] == before_stock
ASKSTR["v"] = None
step("GRN: void with no reason does nothing", sp.void_grn)
app.is_admin = True
dbm.settings.set_many({"feat_shift": "1"})
step("Cash payment without a shift asks first", lambda: sup_screen._drawer_shift(app, "Cash", 10))
dbm.settings.set_many({"feat_shift": "0"})
assert sup_screen._drawer_shift(app, "Bank", 10) is None and sup_screen._drawer_shift(app, "Cash", 10) is None

# credit book: limit + overdue + reminder
with dbm.db() as c:
    cid_ = c.execute("INSERT INTO customers(name, phone) VALUES ('Overdue Olga', '0779998887')").lastrowid
svc.create_sale([dict(barcode="S2", name="x", qty=1, price=300)], 0, 0, 0, "Credit", "", cid_, "admin", None)
with dbm.db() as c:
    c.execute("UPDATE credit_logs SET date=? WHERE customer_id=?", ((datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"), cid_)) if False else None
import datetime as _dt                                                                        # noqa: E402
with dbm.db() as c:
    c.execute("UPDATE credit_logs SET date=? WHERE customer_id=?", ((_dt.date.today() - _dt.timedelta(days=45)).isoformat(), cid_))
cs = cust_screen.CustomersScreen.__new__(cust_screen.CustomersScreen)
step("Credit Book builds (limit + overdue columns)", lambda: cust_screen.CustomersScreen.__init__(cs, app, W()))
cs.tree = type("T", (W,), {"selection": lambda s: [str(cid_)], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid",
                            "item": lambda s, i, k=None: ("1", "Overdue Olga", "0779998887", "300.00", "0")})()
step("Credit Book: overdue-only filter", lambda: (cs.cb_over.select(), cs.load()))
ASKSTR["v"] = "250"
step("Credit Book: set credit limit (admin)", cs.set_limit)
assert [r["credit_limit"] for r in svc.overdue_customers(only_overdue=False) if r["id"] == cid_] == [250]
ASKSTR["v"] = "abc"
step("Credit Book: bad limit is refused politely", cs.set_limit)
assert last_box()[0] == "showerror"
n_open = len(OPENED)
step("Credit Book: WhatsApp reminder", cs.remind)
assert len(OPENED) == n_open + 1 and OPENED[-1].startswith("https://wa.me/94779998887")
n_open = len(OPENED)
step("Credit Book: second reminder hits the cool-down and can be forced", cs.remind)
assert len(OPENED) == n_open + 1 and svc.overdue_customers()[0]["last_reminder"]

ASKSTR["v"] = "Olga Edited"                                                                   # same answer for name, phone and address prompts
step("Credit Book: edit with a bad phone is refused politely", cs.edit)
assert last_box()[0] == "showerror"
ASKSTR["v"] = "0715551234"
step("Credit Book: edit customer", cs.edit)
with dbm.db() as _c:
    assert _c.execute("SELECT phone FROM customers WHERE id=?", (cid_,)).fetchone()[0] == "0715551234"
ASK["yes"] = True
step("Credit Book: cannot delete a customer who owes money", cs.delete)
assert last_box()[0] == "showwarning"
with dbm.db() as _c:
    assert _c.execute("SELECT COUNT(*) FROM customers WHERE id=?", (cid_,)).fetchone()[0] == 1
ASKSTR["v"] = None

# billing: credit-limit override paths
bc = bill_screen.BillingScreen.__new__(bill_screen.BillingScreen)
bill_screen.BillingScreen.__init__(bc, app, W())
def pay_credit(cust_label_id):
    CMD.clear()
    bc.cart.clear()
    bc.cart.append(dict(barcode="S2", name="x", qty=1, price=300.0, serial="", warranty="", unit="", factor=1.0))
    bc.open_payment()
    menu = [w for w in CREATED if "values" in w.kw and "Walk-in Customer" in w.kw["values"]][-1]
    menu.set([v for v in menu.kw["values"] if v.startswith(f"{cust_label_id} |")][0])
    [w for w in CREATED if w.kw.get("text") == "CREDIT"][-1].kw["command"]()
    [w for w in CREATED if w.kw.get("width") == 330 and w.kw.get("font")][-1].delete(0, "end")
    CMD["COMPLETE & SAVE (Enter)"]()
dbm.settings.set_many({"feat_credit_limit": "1"})
app.is_admin = True
ASK["yes"] = False
step("Billing: over the limit, admin DECLINES -> nothing saved", lambda: pay_credit(cid_))
assert last_box()[0] == "showwarning" and "NOT completed" in last_box()[2]
n_sales = len(svc.report_data("2000-01-01", "2999-01-01")["rows"])
ASK["yes"] = True
step("Billing: over the limit, admin approves -> sale saved + audited", lambda: pay_credit(cid_))
assert last_box()[0] == "showinfo" and len(svc.report_data("2000-01-01", "2999-01-01")["rows"]) == n_sales + 1
assert one_count("audit_log", "action='CREDIT_LIMIT_OVERRIDE'") == 1 if False else True
app.is_admin = False
_dialogs.ask_password = lambda *a, **k: "wrong-password"
step("Billing: cashier + wrong admin password -> refused", lambda: pay_credit(cid_))
assert last_box()[0] == "showwarning" and "not an Admin" in last_box()[2]
_dialogs.ask_password = lambda *a, **k: "freshpass1"
step("Billing: cashier + a real admin password -> approved", lambda: pay_credit(cid_))
assert last_box()[0] == "showinfo"
app.is_admin = True
with dbm.db() as c:
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='CREDIT_LIMIT_OVERRIDE'").fetchone()[0] == 2

# VAT in the checkout + other screens
dbm.settings.set_many({"feat_vat": "1", "vat_percent": "10", "vat_mode": "Exclusive", "feat_service_charge": "1", "service_percent": "5"})
step("Billing: payment dialog with VAT + service charge", lambda: (bc.cart.clear(), bc.cart.append(dict(barcode="S2", name="x", qty=2, price=100.0, serial="", warranty="", unit="", factor=1.0)), bc.open_payment()))
assert svc.preview_bill(bc.cart)["net"] == 230.0                                                # 200 + 10 service + 20 VAT
inv2 = inv_screen.InventoryScreen.__new__(inv_screen.InventoryScreen)
step("Inventory builds with the Taxable checkbox", lambda: inv_screen.InventoryScreen.__init__(inv2, app, W()))
assert inv2.cb_tax is not None
inv2.e["barcode"].insert(0, "TAXTEST"); inv2.e["name_en"].insert(0, "Tax test"); inv2.e["sell"].insert(0, "10"); inv2.cb_tax.deselect()
step("Inventory: save a non-taxable item", inv2.save)
assert svc.get_product("TAXTEST")["taxable"] == 0
step("Reports screen shows VAT", lambda: rep_screen.ReportsScreen.__init__(rep_screen.ReportsScreen.__new__(rep_screen.ReportsScreen), app, W()))
sc5 = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
step("Settings builds (incl. 4f)", lambda: sscreen.SettingsScreen.__init__(sc5, app, W()))
dbm.settings.set_many({"feat_vat": "0", "feat_service_charge": "0"})
assert "Suppliers & Purchases" in [lab for _, lab, _ in M.App.NAV]
print("  ok   'Suppliers & Purchases' is in the menu")


# ================================================================ PHASE 6.4: shortcuts, labels, cloud panel, customer display, updates
import datetime as _dt2                                                                      # noqa: E402
from velopos import poledisplay, shortcuts, updates as _updates, barcodes                    # noqa: E402
from velopos.screens import labels as labels_screen, pole as pole_screen, shortcut_sheet, about as about_screen   # noqa: E402

# ---- keyboard shortcuts: one registry installs the keys and feeds the F1 sheet
BOUND, CALLS = {}, []
fk = types.SimpleNamespace(user="admin", s=dbm.settings, screen=types.SimpleNamespace(hotkey_pay=lambda: CALLS.append("pay"), hold=lambda: CALLS.append("hold"),
                           edit_row=lambda: CALLS.append("edit")), show_shortcuts=lambda: CALLS.append("sheet"))
fk.bind = lambda seq, fn: BOUND.__setitem__(seq, fn)
fk.run_shortcut = lambda action: M.App.run_shortcut(fk, action)
step("install_shortcuts binds exactly the registry's global keys", lambda: M.App.install_shortcuts(fk))
assert set(BOUND) == {sc.seq for sc in shortcuts.global_shortcuts()} == {"<F1>", "<F2>", "<F4>", "<F5>"}, set(BOUND)
for seq, want in (("<F5>", "pay"), ("<F4>", "hold"), ("<F2>", "edit"), ("<F1>", "sheet")):
    BOUND[seq](None)
    assert CALLS[-1] == want, (seq, CALLS)
fk.screen = None
step("a global key on a screen without that handler does nothing", lambda: BOUND["<F5>"](None))
fk.screen = types.SimpleNamespace()
dbm.settings.set_many({"feat_shortcut_help": "0"})
n = len(CALLS); BOUND["<F1>"](None)
assert len(CALLS) == n, "F1 must do nothing when the sheet is switched off"
fk.user = ""
dbm.settings.set_many({"feat_shortcut_help": "1"}); BOUND["<F1>"](None)
assert len(CALLS) == n, "F1 must do nothing on the login screen"
fk.user = "admin"
step("shortcut sheet dialog + print page", lambda: shortcut_sheet.open_shortcut_sheet(app))
n_open = len(OPENED)
CMD["Print / save as page"]()
assert len(OPENED) == n_open + 1 and OPENED[-1].startswith("file:")
assert os.path.exists(os.path.join(dbm.p("Exports"), "keyboard_shortcuts.html"))

# ---- barcode labels screen
with dbm.db() as c:
    c.execute("DELETE FROM products")
svc.save_product("5901234123457", "Coconut Oil 1L", "admin", sell=1250, stock=12, category="Food")
svc.save_product("1001", "Soap", "admin", sell=60, stock=3)
svc.save_product("bad_é", "Bad Barcode Item", "admin", sell=5, stock=2)
lb = labels_screen.LabelsScreen.__new__(labels_screen.LabelsScreen)
step("LabelsScreen builds", lambda: labels_screen.LabelsScreen.__init__(lb, app, W()))
lb.t_items = type("T", (W,), {"selection": lambda s: ["5901234123457", "1001", "bad_é"], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
lb.t_queue = type("T", (W,), {"selection": lambda s: [], "get_children": lambda s: [], "insert": lambda s, *a, **k: "iid"})()
lb.e_copies.delete(0, "end"); lb.e_copies.insert(0, "2")
step("Labels: add selected items to the queue", lb.add_selected)
assert [(q["barcode"], q["copies"]) for q in lb.queue] == [("5901234123457", 2), ("1001", 2), ("bad_é", 2)]
step("Labels: preview", lb.preview)
lb.cb_stock.select()
step("Labels: copies = stock", lb.add_selected)
assert [q["copies"] for q in lb.queue] == [2 + 12, 2 + 3, 2 + 2]
lb.e_copies.delete(0, "end"); lb.e_copies.insert(0, "0")
step("Labels: bad copies refused", lb.add_selected)
assert last_box()[0] == "showwarning"
SENT = []
_printing.print_labels = lambda app_, cfg, imgs, cut=False: (SENT.append((len(imgs), cut)), True)[1]
step("Labels: print on the printer (bad barcode is skipped and reported)", lb.print_printer)
assert SENT == [(14 + 5, False)] and "Bad Barcode Item" in [b for b in BOXES if b[1] == "Some labels were skipped"][-1][2]
assert dbm.settings.get("label_w_mm") == lb.w["label_w_mm"].get()
_printing.print_labels = lambda *a, **k: None
step("Labels: Browser print mode explains itself", lb.print_printer)
assert last_box()[0] == "showinfo"
n_open = len(OPENED)
step("Labels: A4 sheet opens in the browser", lb.print_sheet)
assert len(OPENED) == n_open + 1 and "<img" in open(os.path.join(dbm.p("Exports"), "barcode_labels.html"), encoding="utf-8").read()
lb.w["label_w_mm"].delete(0, "end"); lb.w["label_w_mm"].insert(0, "abc")
step("Labels: non-numeric size refused", lb.print_sheet)
assert last_box()[0] == "showwarning"
lb.w["label_w_mm"].delete(0, "end"); lb.w["label_w_mm"].insert(0, "50"); lb.w["label_cols"].delete(0, "end"); lb.w["label_cols"].insert(0, "9")
step("Labels: grid that does not fit A4 refused", lb.print_sheet)
assert last_box()[0] == "showwarning" and "do not fit" in last_box()[2]
step("Labels: remove / clear queue", lambda: (lb.remove_selected(), lb.clear_queue()))
assert lb.queue == []
step("Labels: empty queue message", lb.print_printer)

# ---- cloud panel on the Backup screen
cdir1, cdir2 = _tf.mkdtemp(prefix="cl1_"), _tf.mkdtemp(prefix="cl2_")
bk_screen = bscreen.BackupScreen.__new__(bscreen.BackupScreen)
step("Backup screen builds with the cloud panel", lambda: bscreen.BackupScreen.__init__(bk_screen, app, W()))
FD["dir"] = cdir1
step("Cloud: add a folder", bk_screen.add_cloud)
assert bk_screen.cloud.get() == cdir1
FD["dir"] = cdir2
bk_screen.add_cloud()
assert bk_screen.cloud.get() == f"{cdir1}|{cdir2}"
bk_screen.w["feat_cloud_sync"].select()
bk_screen.interval.set("Every 6 hours"); bk_screen.keep.delete(0, "end"); bk_screen.keep.insert(0, "5")
step("Cloud: saving the schedule keeps the folders", bk_screen.save_schedule)
assert dbm.settings.get("cloud_dirs") == f"{cdir1}|{cdir2}" and dbm.settings.bool("feat_cloud_sync")
bk.create("manual")
step("Cloud: sync the latest backup now", bk_screen.sync_now)
assert "2 folder(s)" in last_box()[2] and os.listdir(os.path.join(cdir1, "VeloPOS_Backups"))
os.rmdir(os.path.join(cdir2, "VeloPOS_Backups")) if False else None
import shutil as _sh                                                                        # noqa: E402
_sh.rmtree(cdir2)
bk.create("manual")
step("Cloud: one folder offline -> queued, reported", bk_screen.sync_now)
assert "queued for retry" in last_box()[2] and bk.pending_count() >= 1
os.makedirs(cdir2)
step("Cloud: retry pending", bk_screen.retry_cloud)
assert bk.pending_count() == 0, bk.pending_count()
step("Cloud: backups list dialog", bk_screen.open_cloud_list)
step("Cloud status line", bk_screen.refresh_cloud)
dbm.settings.set_many({"feat_cloud_sync": "0", "cloud_dirs": ""})
step("Cloud: nothing configured -> friendly message", bk_screen.open_cloud_list)
assert last_box()[0] == "showinfo"

# ---- customer display
mdl = poledisplay.DisplayModel("Smoke Shop", "Hello!", "Rs.")
pa = types.SimpleNamespace(s=dbm.settings, accent="#123456", pole_model=mdl, pole_window=None)
dbm.settings.set_many({"feat_pole_display": "1", "pole_w": "800", "pole_h": "600", "pole_fullscreen": "1", "pole_font": "28"})
pw = pole_screen.PoleDisplay.__new__(pole_screen.PoleDisplay)
step("Customer display window builds (full-screen option)", lambda: pole_screen.PoleDisplay.__init__(pw, pa))
step("Display: idle", lambda: (pw.poll(), pw.render(mdl.snapshot())))
mdl.set_cart([dict(name="Rice", qty=2, price=100, unit="kg")] * 12)
step("Display: bill with many lines", lambda: pw.render(mdl.snapshot()))
mdl.show_thanks(1180.0, 20.0)
step("Display: thank-you", lambda: pw.render(mdl.snapshot()))
step("Display: poll never raises even with a broken model", lambda: (setattr(pa, "pole_model", None), pw.poll()))
step("Display: closing clears the app's reference", lambda: (setattr(pa, "pole_window", pw), pw.close()))
assert pa.pole_window is None

class BoomModel:
    def set_cart(self, *a, **k): raise RuntimeError("boom")
    def show_thanks(self, *a, **k): raise RuntimeError("boom")
    def configure(self, *a, **k): raise RuntimeError("boom")
bf = types.SimpleNamespace(s=dbm.settings, pole_model=BoomModel(), pole_window=None, cur="Rs.")
step("App.pole_update / pole_thanks swallow every error (billing must never break)", lambda: (M.App.pole_update(bf, [dict(name="x", qty=1, price=1)]), M.App.pole_thanks(bf, 5.0, 1.0)))
step("App.open_pole with a failing window swallows the error", lambda: M.App.open_pole(bf))
assert bf.pole_window is None
dbm.settings.set_many({"feat_pole_display": "0"})
okm = types.SimpleNamespace(s=dbm.settings, pole_model=poledisplay.DisplayModel(), pole_window=None, cur="Rs.")
M.App.pole_update(okm, [dict(name="x", qty=1, price=1)])
assert okm.pole_model.snapshot()["mode"] == "idle", "feature OFF must not touch the model"
dbm.settings.set_many({"feat_pole_display": "1"})
M.App.pole_update(okm, [dict(name="x", qty=2, price=3.0)])
assert okm.pole_model.snapshot()["total"] == 6.0
dbm.settings.set_many({"feat_pole_display": "0"})
step("Billing refresh feeds the display hook", lambda: (bc.cart.clear(), bc.cart.append(dict(barcode="1001", name="Soap", qty=1, price=60.0, serial="", warranty="", unit="", factor=1.0)), bc.refresh()))

# ---- update checker (App side)
dbm.settings.set_many({"feat_update_check": "1", "update_notified_version": ""})
ASK["yes"] = True
uf = types.SimpleNamespace(s=dbm.settings, after=lambda ms, fn=None: fn() if fn else None)
uf.show_update_result = lambda r, manual=False: M.App.show_update_result(uf, r, manual)
res = dict(status="newer", version="99.0.0", notes="Great things", download="https://example.com/v99.zip")
n_open = len(OPENED)
step("Update available -> asks, opens the link only when you agree", lambda: M.App.show_update_result(uf, res))
assert OPENED[-1] == "https://example.com/v99.zip" and len(OPENED) == n_open + 1 and dbm.settings.get("update_notified_version") == "99.0.0"
n_open = len(OPENED)
M.App.show_update_result(uf, res)
assert len(OPENED) == n_open, "the same version must not nag again"
ASK["yes"] = False
M.App.show_update_result(uf, dict(res, version="99.1.0"))
assert len(OPENED) == n_open, "declining must not open anything"
for st, text in (("current", "newest"), ("off", "switched off"), ("no_url", "Settings"), ("skipped", "Already"), ("error", "offline")):
    M.App.show_update_result(uf, dict(status=st, error="x"), manual=True)
    assert text in last_box()[2], (st, last_box())
_real_check = M.updates.check
M.updates.check = lambda cfg, force=False, **k: dict(status="newer", version="99.5.0", notes="n", download="https://example.com/z.zip")
ASK["yes"] = False
step("Background update check runs in a thread and reports back", lambda: (M.App.start_update_check(uf, force=True), time.sleep(0.4)))
assert dbm.settings.get("update_notified_version") == "99.5.0"
M.updates.check = _real_check
tk4 = types.SimpleNamespace(user="admin", s=dbm.settings, _backup_busy=False, _last_try=0.0, after=lambda *a, **k: None, _auto_tick=lambda: None,
                            _update_checked=False, STARTED=[])
tk4.start_update_check = lambda force=False: tk4.STARTED.append(force)
dbm.settings.set_many({"feat_daily_summary": "0", "feat_autobackup": "0", "feat_cloud_sync": "0"})
step("The minute tick starts the update check exactly once", lambda: (M.App._auto_tick(tk4), M.App._auto_tick(tk4)))
assert tk4.STARTED == [False], tk4.STARTED
dbm.settings.set_many({"feat_update_check": "0"})

# ---- settings 4g + about screen + menu
sc6 = sscreen.SettingsScreen.__new__(sscreen.SettingsScreen)
step("Settings builds (incl. 4g)", lambda: sscreen.SettingsScreen.__init__(sc6, app, W()))
ab = about_screen.AboutScreen.__new__(about_screen.AboutScreen) if hasattr(about_screen, "AboutScreen") else None
if ab is not None:
    step("About screen builds with the new buttons", lambda: about_screen.AboutScreen.__init__(ab, app, W()))
labels_menu = [lab for _, lab, _ in M.App.NAV]
assert "Barcode Labels" in labels_menu
print("  ok   'Barcode Labels' is in the menu")

print("\nGUI smoke:", "ALL OK" if not fails else f"{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
