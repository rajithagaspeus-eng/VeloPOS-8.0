import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import assets, assistant, backup as bk, cloudsync as cs, poledisplay, updates, branding as B, database as dbm, license as lic, security, services as svc, theme
from .dialogs import ForgotPasswordDialog
from .theme import C, BTN


class App(ctk.CTk):
    # (key, label, permission)  permission: None = everyone, "admin" = Admin only, else cashier-permission name
    NAV = [("billing", "Billing", None), ("inventory", "Inventory", None), ("stock", "Stock Control", "stock"), ("suppliers", "Suppliers & Purchases", "stock"), ("labels", "Barcode Labels", "stock"), ("customers", "Credit Book", None),
           ("returns", "Returns & Refunds", "returns"), ("quotes", "Quotations", None), ("shift", "Shift & Cash Drawer", None),
           ("expenses", "Expenses", "expenses"), ("reports", "Reports & Insights", "reports"),
           ("assistant", "Ask VeloPOS", None), ("audit", "Audit Log", "admin"), ("backup", "Backup & Restore", "admin"), ("settings", "Settings", "admin"),
           ("about", "About & License", None)]

    def __init__(self):
        super().__init__()
        self.s = dbm.settings
        self.user, self.role = "", ""
        self.held, self.wholesale = {}, False
        self.pending_cart = None
        self.screen, self.nav_btns = None, {}
        self.geometry("1400x830")
        self.minsize(1100, 700)
        self.apply_look()
        self.lic_status, self.lic_days, self.machine_id = lic.check_status()
        self.install_shortcuts()
        self._backup_busy, self._last_try = False, 0.0
        self.pole_model, self.pole_window, self._update_checked = poledisplay.DisplayModel(), None, False
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(250, self.set_window_icon)          # CustomTkinter sets its own icon after start-up, so ours must come later
        self.after(20, self.start)

    # ---------------------------------------------------------------- look & helpers
    def apply_look(self):
        ctk.set_appearance_mode(self.s.get("theme"))
        self.accent = theme.ACCENTS.get(self.s.get("accent"), "#2563EB")
        self.cur = self.s.get("currency")
        self.title(f"{self.s.get('shop_name')} - VeloPOS")
        theme.apply_ttk(self.accent, self.s.get("font_family"), self.s.int("font_size", 15))

    def set_window_icon(self):
        """branding/app_icon.ico -> title bar + taskbar icon (Windows only; silently skipped when there is no file)."""
        p = assets.icon_path()
        if p and os.name == "nt":
            try:
                self.iconbitmap(p)
            except Exception:
                pass

    def logo(self, parent, where):
        """The owner's logo (branding/dev_logo.png ...) as a label, or None -> the screen keeps its text title."""
        p = assets.logo_path()
        if not p:
            return None
        r = assets.load_image(p, target_h=assets.LOGO_HEIGHT[where], target_w=520)
        return ctk.CTkLabel(parent, image=r[0], text="", fg_color="transparent") if r else None

    def f(self, off=0, weight="normal"):
        return ctk.CTkFont(family=self.s.get("font_family"),
                           size=max(11, self.s.int("font_size", 15) + off), weight=weight)

    @property
    def is_admin(self):
        return self.role == "Admin"

    def can(self, perm):
        """Admin can do everything; cashiers follow the permission matrix in Settings."""
        return self.is_admin or self.s.bool("cperm_" + perm)

    def allowed(self, key, perm):
        if perm == "admin":
            return self.is_admin
        if key == "shift" and not self.s.bool("feat_shift"):
            return False
        if key == "assistant" and not self.s.bool("feat_assistant"):
            return False
        if key == "stock" and not self.s.bool("feat_stock_screen"):
            return False
        if key == "suppliers" and not self.s.bool("feat_suppliers"):
            return False
        if key == "labels" and not self.s.bool("feat_labels"):
            return False
        return perm is None or self.can(perm)

    def clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.screen = None
        self.fab = None
        self._chat_popup = None
        self.pole_window = None

    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=C["surface"], border_color=C["border"],
                            border_width=1, corner_radius=12, **kw)

    def btn(self, parent, text, color="accent", command=None, width=0, height=36, **kw):
        col = self.accent if color == "accent" else BTN.get(color, color)
        return ctk.CTkButton(parent, text=text, fg_color=col, hover_color=col, text_color="white",
                             height=height, width=width or 100, font=self.f(0, "bold"),
                             command=command, **kw)

    def start(self):
        with dbm.db() as c:
            n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            self.show_setup()
        elif self.lic_status in ("EXPIRED", "TAMPERED"):
            self.show_activation(allow_back=False)
        else:
            self.show_login()

    def require_admin(self):
        if self.is_admin:
            return True
        messagebox.showwarning("Admin only", "This action needs an Admin account.")
        return False

    # ---------------------------------------------------------------- first-run setup
    def show_setup(self):
        self.clear()
        self.configure(fg_color=C["bg"])
        box = self.card(self)
        box.place(relx=0.5, rely=0.5, anchor="center")
        lg = self.logo(box, "setup")
        if lg:
            lg.pack(padx=50, pady=(26, 4))
        else:
            ctk.CTkLabel(box, text="Welcome to VeloPOS", font=self.f(10, "bold"), text_color=C["text"]).pack(padx=50, pady=(30, 4))
        ctk.CTkLabel(box, text="Create your Admin account (no default passwords!)", font=self.f(0), text_color=C["muted"]).pack(pady=(0, 14))
        e_shop = ctk.CTkEntry(box, width=320, height=40, placeholder_text="Shop name", font=self.f(1)); e_shop.pack(pady=5)
        e_user = ctk.CTkEntry(box, width=320, height=40, placeholder_text="Admin username", font=self.f(1)); e_user.pack(pady=5); e_user.insert(0, "admin")
        e_p1 = ctk.CTkEntry(box, width=320, height=40, placeholder_text="Password (min 6 characters)", show="*", font=self.f(1)); e_p1.pack(pady=5)
        e_p2 = ctk.CTkEntry(box, width=320, height=40, placeholder_text="Repeat password", show="*", font=self.f(1)); e_p2.pack(pady=5)

        def create(e=None):
            u, p1, p2 = e_user.get().strip().lower(), e_p1.get(), e_p2.get()
            if not u or len(p1) < 6:
                return messagebox.showwarning("Check", "Username required and password must be at least 6 characters.")
            if p1 != p2:
                return messagebox.showwarning("Check", "Passwords do not match.")
            code = security.new_recovery_code()
            with dbm.db() as c:
                c.execute("INSERT INTO users(username, pw_hash, role, created) VALUES (?,?,?,datetime('now'))",
                          (u, security.hash_password(p1), "Admin"))
            dbm.settings.set_many({"shop_name": e_shop.get().strip() or "MY STORE", "setup_done": "0",
                                   "recovery_hash": security.hash_password(security.normalize_code(code))})
            dbm.audit(u, "SETUP", "first run")
            self.clipboard_clear(); self.clipboard_append(code)
            messagebox.showinfo("SAVE YOUR RECOVERY CODE",
                                f"Recovery code (copied to clipboard):\n\n{code}\n\nWrite it down and keep it safe. "
                                "It is the only way to reset the Admin password if you forget it.\n"
                                "It will NOT be shown again.")
            self.apply_look()
            self.show_login()
        self.btn(box, "CREATE & CONTINUE", "green", create, width=320, height=44).pack(padx=50, pady=(14, 30))

    # ---------------------------------------------------------------- login
    def show_login(self):
        if self.lic_status != "ACTIVATED":                            # the trial may have ended while the program stayed open
            self.lic_status, self.lic_days, _ = lic.check_status()
            if self.lic_status in ("EXPIRED", "TAMPERED"):
                return self.show_activation(allow_back=False)
        self.clear()
        self.configure(fg_color=C["bg"])
        box = self.card(self)
        box.place(relx=0.5, rely=0.5, anchor="center")
        lg = self.logo(box, "login")
        if lg:
            lg.pack(padx=60, pady=(24, 0))
        else:
            ctk.CTkLabel(box, text="VeloPOS", font=self.f(18, "bold"), text_color=self.accent).pack(padx=60, pady=(28, 0))
        ctk.CTkLabel(box, text=self.s.get("shop_name"), font=self.f(5, "bold"), text_color=C["text"]).pack(pady=(2, 2))
        if self.lic_status == "ACTIVATED":
            ctk.CTkLabel(box, text="Licensed Full Version", font=self.f(-1, "bold"), text_color=C["success"]).pack(pady=(0, 12))
        else:
            ctk.CTkLabel(box, text=f"Free Trial: {self.lic_days} days remaining", font=self.f(-1, "bold"), text_color=C["warning"]).pack(pady=(0, 12))
        with dbm.db() as c:
            users = [f"{r['username']} ({r['role']})" for r in c.execute("SELECT username, role FROM users ORDER BY role, username")]
        opt = ctk.CTkOptionMenu(box, values=users, width=300, height=40, font=self.f(1), fg_color=self.accent, button_color=self.accent)
        opt.pack(pady=6, padx=40)
        pw = ctk.CTkEntry(box, width=300, height=40, show="*", placeholder_text="Password", font=self.f(1)); pw.pack(pady=8); pw.focus()

        def login(e=None):
            u = opt.get().split(" (")[0]
            wait = svc.login_locked_for(u)
            if wait:
                return messagebox.showerror("Locked", f"Too many wrong attempts. Try again in {wait} seconds.")
            with dbm.db() as c:
                r = c.execute("SELECT pw_hash, role FROM users WHERE username=?", (u,)).fetchone()
            if r and security.verify_password(pw.get(), r["pw_hash"]):
                svc.login_ok(u)
                self.user, self.role = u, r["role"]
                dbm.audit(u, "LOGIN")
                svc.speak(f"Welcome {u}", self.s.bool("feat_voice"))
                if self.is_admin and self.s.get("setup_done") == "0":
                    self.show_wizard()
                else:
                    self.build_shell("billing")
            else:
                svc.login_failed(u)
                dbm.audit(u, "LOGIN_FAILED")
                messagebox.showerror("Access denied", "Incorrect password.")
                pw.delete(0, "end")
        pw.bind("<Return>", login)
        self.btn(box, "LOGIN", "green", login, width=300, height=44).pack(pady=(14, 4))
        if self.s.bool("feat_forgot_pw"):
            ctk.CTkButton(box, text="Forgot password?", width=300, height=26, fg_color="transparent", hover_color=C["hover"],
                          text_color=self.accent, font=self.f(-1, "bold"),
                          command=lambda: ForgotPasswordDialog(self)).pack(pady=(0, 10))
        ctk.CTkLabel(box, text=B.DEV_COPYRIGHT, font=self.f(-3), text_color=C["muted"]).pack(pady=(4, 16))

    # ---------------------------------------------------------------- activation / purchase screen
    def show_activation(self, allow_back=True):
        self.clear()
        self.configure(fg_color=C["bg"])
        box = self.card(self)
        box.place(relx=0.5, rely=0.5, anchor="center")
        msgs = {"TAMPERED": ("SYSTEM CLOCK / TRIAL DATA TAMPERING DETECTED", "Restore the correct date, or enter your License Key."),
                "EXPIRED": ("30-DAY FREE TRIAL HAS ENDED", "All your data is safe. Buy a Lifetime License below to continue."),
                }
        title, sub = msgs.get(self.lic_status, (f"SOFTWARE ACTIVATION ({self.lic_days} trial days left)", "Buy a Lifetime License and send us your Machine ID."))
        lg = self.logo(box, "activate")
        if lg:
            lg.pack(padx=40, pady=(16, 0))
        else:
            ctk.CTkLabel(box, text=B.DEV_COMPANY, font=self.f(2, "bold"), text_color=self.accent).pack(padx=40, pady=(22, 0))
        ctk.CTkLabel(box, text=title, font=self.f(4, "bold"), text_color=C["danger"]).pack()
        ctk.CTkLabel(box, text=sub, font=self.f(-1), text_color=C["muted"], wraplength=700).pack(pady=(2, 4))
        ctk.CTkLabel(box, text=f"Lifetime License: {B.PRICE_LKR}  |  International: {B.PRICE_USD} (one-time)", font=self.f(1, "bold"), text_color=C["warning"]).pack(pady=4)

        tabs = ctk.CTkTabview(box, width=760, height=215)
        tabs.pack(padx=30, pady=6)
        wa_msg = f"Hello VeloPOS! I want to activate my license. Machine ID: {self.machine_id}"
        wa_url = f"https://wa.me/{B.DEV_WHATSAPP}?text=" + __import__("urllib.parse").parse.quote(wa_msg)
        for name, info, url, qr_data, col, kind in [
            ("International (Card)", f"Pay by Visa / MasterCard / Apple Pay via Gumroad ({B.PRICE_USD}).\nThen WhatsApp your receipt + Machine ID.", B.DEV_WEBSITE, B.DEV_WEBSITE, "pink", "international"),
            ("Local Bank", f"{B.DEV_BANK}\n\nTransfer {B.PRICE_LKR}, then WhatsApp the slip + Machine ID.", None, B.DEV_BANK, "blue", "bank"),
            ("Binance Pay", f"{B.DEV_BINANCE}\n\nPay, then WhatsApp the receipt + Machine ID.", None, B.DEV_BINANCE, "amber", "binance"),
            ("WhatsApp", f"Chat with us directly:\n{B.DEV_PHONE}", wa_url, wa_url, "green", "whatsapp")]:
            t = tabs.add(name)
            theme.qr_or_image(t, kind, qr_data, 150).pack(side="left", padx=20, pady=4)
            col_f = ctk.CTkFrame(t, fg_color="transparent"); col_f.pack(side="left", fill="both", expand=True)
            ctk.CTkLabel(col_f, text=info, font=self.f(-1), text_color=C["text"], justify="left", wraplength=480).pack(anchor="w", pady=6)
            if url:
                self.btn(col_f, "Open", col, lambda u=url: svc.open_url(u), width=160).pack(anchor="w")

        mf = ctk.CTkFrame(box, fg_color="transparent"); mf.pack(pady=4)
        ctk.CTkLabel(mf, text="Your Machine ID:", font=self.f(0, "bold"), text_color=C["text"]).pack(side="left", padx=6)
        me = ctk.CTkEntry(mf, width=190, font=self.f(2, "bold"), justify="center"); me.pack(side="left", padx=4)
        me.insert(0, self.machine_id); me.configure(state="readonly")
        self.btn(mf, "Copy", "gray", lambda: (self.clipboard_clear(), self.clipboard_append(self.machine_id)), width=70).pack(side="left", padx=4)

        ctk.CTkLabel(box, text="Paste your License Key:", font=self.f(-1), text_color=C["muted"]).pack()
        kt = ctk.CTkTextbox(box, width=640, height=70, font=("Consolas", 12)); kt.pack(pady=4)

        def activate():
            if lic.activate(kt.get("1.0", "end")):
                self.lic_status, self.lic_days, _ = lic.check_status()
                dbm.audit(self.user, "LICENSE_ACTIVATED")
                messagebox.showinfo("Activated", "Thank you! Lifetime license activated.")
                self.show_login() if not self.user else self.build_shell("about")
            else:
                messagebox.showerror("Invalid key", "This key is not valid for this computer.")
        row = ctk.CTkFrame(box, fg_color="transparent"); row.pack(pady=(6, 20))
        self.btn(row, "ACTIVATE LIFETIME LICENSE", "green", activate, width=290, height=42).pack(side="left", padx=6)
        if allow_back:
            self.btn(row, "Back", "gray", lambda: self.build_shell("about") if self.user else self.show_login(), width=120, height=42).pack(side="left", padx=6)

    # ---------------------------------------------------------------- shell
    def build_shell(self, start="billing"):
        self.clear()
        self.configure(fg_color=C["bg"])
        self.apply_look()
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(1, weight=1)
        side = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=C["surface"])
        side.grid(row=0, column=0, sticky="nsew"); side.grid_propagate(False)
        ctk.CTkLabel(side, text=self.s.get("shop_name"), font=self.f(3, "bold"), text_color=C["text"], wraplength=220).pack(padx=14, pady=(18, 2))
        ctk.CTkLabel(side, text=f"{self.user.upper()}  •  {self.role}", font=self.f(-2, "bold"), text_color="white",
                     fg_color=BTN["red"] if self.is_admin else self.accent, corner_radius=6, padx=10, pady=2).pack(pady=(0, 14))
        self.nav_btns = {}
        n = 0
        for key, label, perm in self.NAV:
            if not self.allowed(key, perm):
                continue
            n += 1
            b = ctk.CTkButton(side, text=f"{n}. {label}", anchor="w", height=34, font=self.f(0, "bold"), fg_color="transparent",
                              text_color=C["text"], hover_color=C["hover"], command=lambda k=key: self.navigate(k))
            b.pack(fill="x", padx=12, pady=1)
            self.nav_btns[key] = b
        bottom = ctk.CTkFrame(side, fg_color="transparent"); bottom.pack(side="bottom", fill="x", padx=12, pady=12)
        if self.lic_status != "ACTIVATED":
            self.btn(bottom, f"Trial: {self.lic_days}d left - Activate", "amber", lambda: self.show_activation(True), height=30).pack(fill="x", pady=3)
        self.lbl_clock = ctk.CTkLabel(bottom, text="", font=self.f(-2, "bold"), text_color=C["warning"]); self.lbl_clock.pack(pady=2)
        self.tick()
        self.btn(bottom, "Backup now", "green", self.backup, height=30).pack(fill="x", pady=3)
        self.btn(bottom, "Switch user / Logout", "red", lambda: (dbm.audit(self.user, "LOGOUT"), self.show_login()), height=30).pack(fill="x", pady=3)
        ctk.CTkLabel(bottom, text=f"Powered by {B.DEV_COMPANY}", font=self.f(-4), text_color=C["muted"]).pack()

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=14, pady=14)
        self.content.grid_rowconfigure(0, weight=1); self.content.grid_columnconfigure(0, weight=1)
        self.open_pole()
        if not getattr(self, "_tick_started", False):
            self._tick_started = True
            self.after(60_000, self._auto_tick)
        self.navigate(start)

    def tick(self):
        from datetime import datetime
        if hasattr(self, "lbl_clock") and self.lbl_clock.winfo_exists():
            self.lbl_clock.configure(text=datetime.now().strftime("%Y-%m-%d | %I:%M:%S %p"))
            self.after(1000, self.tick)

    def navigate(self, key):
        from .screens import (about, assistant as assistant_screen, audit, backup, billing, stock as stock_screen, suppliers as suppliers_screen, labels as labels_screen, customers, expenses, inventory,
                              quotes, reports, returns, settings, shift)
        classes = {"billing": billing.BillingScreen, "inventory": inventory.InventoryScreen,
                   "customers": customers.CustomersScreen, "returns": returns.ReturnsScreen, "quotes": quotes.QuotesScreen,
                   "shift": shift.ShiftScreen, "expenses": expenses.ExpensesScreen,
                   "reports": reports.ReportsScreen, "audit": audit.AuditScreen, "backup": backup.BackupScreen, "assistant": assistant_screen.AssistantScreen, "stock": stock_screen.StockScreen, "suppliers": suppliers_screen.SuppliersScreen, "labels": labels_screen.LabelsScreen,
                   "settings": settings.SettingsScreen, "about": about.AboutScreen}
        perm = next((p for k, _, p in self.NAV if k == key), None)
        if not self.allowed(key, perm):
            return
        for w in self.content.winfo_children():
            w.destroy()
        for k, b in self.nav_btns.items():
            on = k == key
            b.configure(fg_color=self.accent if on else "transparent", text_color="white" if on else C["text"])
        self.screen = classes[key](self, self.content)
        self.screen.grid(row=0, column=0, sticky="nsew")
        self.place_fab(key)

    # ---------------------------------------------------------------- Ask VeloPOS: floating button, daily summary
    FAB_POS = {"Top-right": dict(relx=1.0, rely=0.0, x=-18, y=12, anchor="ne"), "Top-left": dict(relx=0.0, rely=0.0, x=268, y=12, anchor="nw"),
               "Bottom-right": dict(relx=1.0, rely=1.0, x=-18, y=-14, anchor="se"), "Bottom-left": dict(relx=0.0, rely=1.0, x=268, y=-14, anchor="sw")}

    def place_fab(self, key=None):
        want = self.s.bool("feat_assistant") and self.s.bool("feat_assistant_fab") and key != "assistant"
        fab = getattr(self, "fab", None)
        if not want:
            if fab is not None:
                fab.place_forget()
            return
        if fab is None:
            fab = self.fab = ctk.CTkButton(self, text="Ask", width=52, height=52, corner_radius=26, fg_color=self.accent, hover_color=self.accent,
                                           text_color="white", font=self.f(0, "bold"), command=self.open_assistant_popup)
        fab.place(**self.FAB_POS.get(self.s.get("assistant_fab_pos"), self.FAB_POS["Top-right"]))
        fab.lift()

    def open_assistant_popup(self):
        from .screens.assistant import open_popup
        open_popup(self)

    def on_shift_closed(self, sid):
        self.dashboard_push_async(force=True)                      # owner phone dashboard (no-op unless switched on)
        if self.s.bool("feat_daily_summary") and self.s.bool("feat_summary_on_close"):
            self.daily_summary_now("shift")

    def daily_summary_now(self, reason="manual"):
        """Build today's summary and send it to the owner. E-mail: sent in the background (the owner gets the full report).
        WhatsApp: opens a pre-filled chat (the user presses Send); it is limited to what the logged-in user may see."""
        channel = self.s.get("summary_channel")
        email = channel.lower().startswith("email")
        ctx = assistant.Ctx(cur=self.cur, shop=self.s.get("shop_name"), user=self.user, is_admin=self.is_admin,
                            can=(lambda p: True) if email else self.can, lang=self.s.get("assistant_lang"), cfg=self.s)
        lang = assistant.resolve_lang(self.s.get("assistant_lang"), "")
        summ = assistant.build_daily_summary(ctx, lang)
        if email:
            def work():
                try:
                    kind, dest = assistant.deliver_summary(summ, channel, self.s)
                    dbm.audit(self.user, "SUMMARY_SENT", f"{reason} via {kind} to {dest}")
                    msg, ok = f"Daily summary e-mailed to {dest}.", True
                except Exception as e:
                    msg, ok = f"Could not e-mail the daily summary:\n{e}", False
                self.after(0, lambda: (messagebox.showinfo if ok else messagebox.showwarning)("Daily summary", msg))
            threading.Thread(target=work, daemon=True).start()
            return
        if reason in ("shift", "dayend") and not messagebox.askyesno("Daily summary", "Open WhatsApp to send today's summary to the owner?"):
            return
        try:
            kind, url = assistant.deliver_summary(summ, channel, self.s)
        except Exception as e:
            return messagebox.showwarning("Daily summary", str(e))
        dbm.audit(self.user, "SUMMARY_SENT", f"{reason} via {kind}")
        svc.open_url(url)

    def backup(self):
        try:
            path = bk.create("manual")
            dbm.audit(self.user, "BACKUP_MANUAL", os.path.basename(path))
            messagebox.showinfo("Backup", f"Saved and verified:\n{path}")
        except Exception as e:
            messagebox.showerror("Backup failed", str(e))

    # ---------------------------------------------------------------- customer display (never allowed to disturb billing)
    def open_pole(self):
        if not self.s.bool("feat_pole_display"):
            return
        try:
            self.pole_model.configure(self.s.get("shop_name"), self.s.get("pole_promo"), self.cur)
            if self.pole_window is None or not self.pole_window.winfo_exists():
                from .screens.pole import PoleDisplay
                self.pole_window = PoleDisplay(self)
        except Exception:
            self.pole_window = None

    def pole_update(self, cart):
        if not self.s.bool("feat_pole_display"):
            return
        try:
            try:
                total = svc.preview_bill(cart, 0, 0)["net"] if cart else None
            except Exception:
                total = None
            self.pole_model.set_cart(cart, total)
        except Exception:
            pass

    def pole_thanks(self, total, change=0.0):
        if self.s.bool("feat_pole_display"):
            try:
                self.pole_model.show_thanks(total, change)
            except Exception:
                pass

    # ---------------------------------------------------------------- update check (background, silent when offline, never installs anything)
    def start_update_check(self, force=False):
        def work():
            res = updates.check(self.s, force=force)
            if force or res["status"] == "newer":
                self.after(0, lambda: self.show_update_result(res, force))
        threading.Thread(target=work, daemon=True).start()

    def show_update_result(self, res, manual=False):
        st = res["status"]
        if st == "newer" and (manual or self.s.get("update_notified_version") != res["version"]):
            self.s.set_many({"update_notified_version": res["version"]})
            if messagebox.askyesno("Update available", f"VeloPOS {res['version']} is available (you have {__import__('velopos').__version__}).\n\n{res['notes'][:600]}\n\n"
                                   "Open the download page in your browser?\n(Nothing is downloaded or installed automatically.)"):
                svc.open_url(res["download"])
        elif manual:
            msg = {"current": "You already have the newest version.", "off": "Update checking is switched off in Settings.", "no_url": "Enter the update link in Settings first.",
                   "skipped": "Already checked today.", "error": f"Could not check for updates (offline?)\n{res.get('error', '')}"}.get(st, st)
            messagebox.showinfo("Update check", msg)

    # ---------------------------------------------------------------- keyboard shortcuts (one registry: shortcuts.py)
    def install_shortcuts(self):
        from . import shortcuts
        for sc in shortcuts.global_shortcuts():
            self.bind(sc.seq, lambda e, sc=sc: self.run_shortcut(sc.action))

    def run_shortcut(self, action):
        if action == "help":
            if self.user and self.s.bool("feat_shortcut_help"):
                self.show_shortcuts()
            return
        getattr(self.screen, action, lambda: None)()

    def show_shortcuts(self):
        from .screens.shortcut_sheet import open_shortcut_sheet
        open_shortcut_sheet(self)

    # ---------------------------------------------------------------- wizard / restart / auto-backup
    def show_wizard(self):
        from .screens.wizard import Wizard
        self.clear()
        self.configure(fg_color=C["bg"])
        Wizard(self)

    def restart(self):
        """Relaunch VeloPOS (after Restore / Factory Reset) without the exit backup."""
        try:
            subprocess.Popen(bk.restart_command(), cwd=os.getcwd())
        except Exception as e:
            messagebox.showwarning("Restart", f"Please close and open VeloPOS again.\n({e})")
        self._closing = True
        self.destroy()

    def _auto_tick(self):
        """Every minute: run the scheduled backup if it is due (in a background thread)."""
        try:
            if self.user and assistant.summary_due(self.s):
                self.s.set_many({"last_summary_date": time.strftime("%Y-%m-%d")})
                self.daily_summary_now("dayend")
            if self.user and not getattr(self, "_update_checked", True) and self.s.bool("feat_update_check"):
                self._update_checked = True
                self.start_update_check()
            if self.user and not getattr(self, "_dash_busy", False) and cs.due(self.s):
                self.dashboard_push_async()
            if self.user and not getattr(self, "_cloud_busy", False) and bk.cloud_targets(self.s) and bk.pending_count():
                self._cloud_busy = True

                def cloud_work():
                    try:
                        bk.process_queue(self.s)
                    finally:
                        self._cloud_busy = False
                threading.Thread(target=cloud_work, daemon=True).start()
            if (self.user and not self._backup_busy and time.time() - self._last_try > 900 and bk.due(self.s)):
                self._backup_busy, self._last_try = True, time.time()

                def work():
                    try:
                        bk.run_auto(self.s, "auto", "system")
                    finally:
                        self._backup_busy = False
                threading.Thread(target=work, daemon=True).start()
        finally:
            self.after(60_000, self._auto_tick)

    def dashboard_push_async(self, force=False, done=None):
        """Owner phone dashboard: upload the summary in a background thread (never blocks billing). done(ok, msg) runs on the UI thread."""
        if getattr(self, "_dash_busy", False) or not cs.enabled(self.s):
            return

        self._dash_busy = True

        def work():
            ok, msg = False, ""
            try:
                ok, msg = cs.run_push(self.s, force=force)
            finally:
                self._dash_busy = False
            if done:
                try:
                    self.after(0, lambda: done(ok, msg))
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def on_close(self):
        if not getattr(self, "_closing", False) and self.s.bool("feat_backup_on_exit"):
            try:
                with dbm.db() as c:
                    has_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0
                if has_users:
                    bk.run_auto(self.s, "exit", self.user or "system")
            except Exception:
                pass                       # never block closing the program
        self.destroy()


def run():
    from . import netua
    netua.install()                 # real User-Agent for every web request (Cloudflare blocks "Python-urllib")
    dbm.init_db()
    App().mainloop()
