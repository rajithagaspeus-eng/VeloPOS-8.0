import os
import time
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .. import cloudsync as cs, database as dbm, otp, printing as P, security, services as svc
from .. import assistant_i18n as I, voice
from ..dialogs import FactoryResetDialog, ask_password, run_bg
from .. import thumbs
from .categories import open_manage_categories
from ..theme import ACCENTS, C
from . import Screen


class SettingsScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.w = {}
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent"); sc.pack(fill="both", expand=True)
        self.heading(sc, "Settings").pack(anchor="w", pady=(4, 8))

        # --- shop
        f = self.section(sc, "1. Shop profile & bank details")
        self.entry(f, 1, 0, "Shop name", "shop_name"); self.entry(f, 1, 2, "Phone", "phone")
        self.entry(f, 2, 0, "Address", "address"); self.entry(f, 2, 2, "Currency symbol", "currency")
        self.entry(f, 3, 0, "Bank name", "bank_name"); self.entry(f, 3, 2, "Branch", "bank_branch")
        self.entry(f, 4, 0, "Account number", "bank_acc"); self.entry(f, 4, 2, "Account holder", "bank_holder")

        # --- look
        f = self.section(sc, "2. Appearance")
        self.menu(f, 1, 0, "Theme", "theme", ["light", "dark", "system"])
        self.menu(f, 1, 2, "Accent colour", "accent", list(ACCENTS))
        self.menu(f, 2, 0, "Font", "font_family", ["Segoe UI", "Iskoola Pota", "Nirmala UI", "Arial", "Calibri"])
        self.menu(f, 2, 2, "Font size", "font_size", ["13", "14", "15", "16", "18", "20", "22"])

        # --- printing
        f = self.section(sc, "3. Language & WhatsApp")
        self.menu(f, 1, 0, "WhatsApp open mode", "whatsapp_mode", ["Desktop App", "Web Browser"])
        self.menu(f, 1, 2, "Second language", "second_lang", ["English Only", "Sinhala", "Tamil", "Arabic", "Hindi", "Spanish", "French"])

        f = self.section(sc, "3b. Printer, receipt & cash drawer")
        self.menu(f, 1, 0, "Printer brand", "printer_brand", P.BRANDS)
        self.menu(f, 1, 2, "Connection", "print_mode", P.MODES)
        self.menu(f, 2, 0, "Windows printer", "printer", svc.list_printers())
        self.menu(f, 2, 2, "Paper size", "paper_size", ["80mm", "58mm", "A5", "A4"])
        self.entry(f, 3, 0, "LAN printer IP", "lan_ip"); self.entry(f, 3, 2, "LAN port", "lan_port")
        self.entry(f, 4, 0, "COM port (Bluetooth)", "com_port"); self.entry(f, 4, 2, "COM baud rate", "com_baud")
        self.entry(f, 5, 0, "Print width dots (0=auto)", "print_width_dots"); self.entry(f, 5, 2, "Copies per bill", "print_copies")
        self.menu(f, 6, 0, "Receipt font", "receipt_font", P.RECEIPT_FONTS); self.menu(f, 6, 2, "Cut command", "cut_cmd", list(P.CUTS))
        self.entry(f, 7, 0, "Receipt footer text", "receipt_footer"); self.entry(f, 7, 2, "Bottom feed before cut (lines, 0 = tightest)", "print_bottom_feed")
        for i, (k, label) in enumerate((("feat_auto_print", "Print the receipt automatically after every bill"),
                                        ("feat_cut", "Auto-cut paper after printing"),
                                        ("feat_print_logo", "Print shop logo on the receipt (upload below)"))):
            cb = ctk.CTkCheckBox(f, text=label, text_color=C["text"], font=a.f(0)); cb.grid(row=8 + i, column=0, columnspan=4, padx=16, pady=3, sticky="w")
            if a.s.bool(k):
                cb.select()
            self.w[k] = cb
        ctk.CTkLabel(f, text="CASH DRAWER", font=a.f(1, "bold"), text_color=C["warning"]).grid(row=11, column=0, columnspan=4, padx=16, pady=(12, 2), sticky="w")
        cb = ctk.CTkCheckBox(f, text="Cash drawer is connected to my receipt printer (switch OFF if you have no drawer)", text_color=C["text"], font=a.f(0, "bold"))
        cb.grid(row=12, column=0, columnspan=4, padx=16, pady=3, sticky="w")
        if a.s.bool("feat_cash_drawer"):
            cb.select()
        self.w["feat_cash_drawer"] = cb
        self.menu(f, 13, 0, "Drawer connector", "drawer_pin", ["Pin 2", "Pin 5"]); self.menu(f, 13, 2, "Open drawer", "drawer_open_on", P.DRAWER_WHEN)
        self.entry(f, 14, 0, "Shift content LEFT (dots, 0-40)", "print_shift_left"); self.entry(f, 14, 2, "Print darkness (100-240, higher = bolder)", "print_threshold")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=15, column=0, columnspan=4, padx=16, pady=10, sticky="w")
        a.btn(row, "Test receipt", "accent", lambda: self.test("sample"), width=140).pack(side="left", padx=4)
        a.btn(row, "Width calibration", "purple", lambda: self.test("calibration"), width=170).pack(side="left", padx=4)
        a.btn(row, "Test cash drawer", "amber", lambda: self.test("drawer"), width=160).pack(side="left", padx=4)
        a.btn(row, "Upload shop logo", "gray", self.pick_logo, width=160).pack(side="left", padx=4)
        ctk.CTkLabel(f, text=P.shaping_status() + "   |   Tests use the values above (no need to save first).", font=a.f(-2), text_color=C["muted"]).grid(row=16, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        # --- feature toggles
        f = self.section(sc, "4. Smart features  (every feature can be switched on / off)")
        for i, (k, label) in enumerate(dbm.FEATURES):
            cb = ctk.CTkCheckBox(f, text=label, text_color=C["text"], font=a.f(0))
            cb.grid(row=i + 1, column=0, columnspan=4, padx=16, pady=4, sticky="w")
            if a.s.bool(k):
                cb.select()
            self.w[k] = cb

        f = self.section(sc, "4b. Cashier permissions  (Admin can always do everything)")
        for i, (k, label) in enumerate(dbm.PERMS):
            cb = ctk.CTkCheckBox(f, text=label, text_color=C["text"], font=a.f(0))
            cb.grid(row=i + 1, column=0, columnspan=4, padx=16, pady=4, sticky="w")
            if a.s.bool(k):
                cb.select()
            self.w[k] = cb

        f = self.section(sc, "4c. Owner contact, e-mail codes (OTP) & recovery")
        self.entry(f, 1, 0, "Owner e-mail (receives codes)", "owner_email"); self.entry(f, 1, 2, "Owner WhatsApp (0771234567)", "owner_whatsapp")
        self.entry(f, 2, 0, "SMTP server", "smtp_host"); self.entry(f, 2, 2, "SMTP port (465 SSL / 587)", "smtp_port")
        self.entry(f, 3, 0, "Gmail address (sender)", "smtp_user")
        ctk.CTkLabel(f, text="Gmail App Password:", text_color=C["text"]).grid(row=3, column=2, padx=16, pady=5, sticky="w")
        self.smtp_pass = ctk.CTkEntry(f, width=260, show="*", placeholder_text="(saved, encrypted)" if otp.has_smtp_password() else "16-character App Password")
        self.smtp_pass.grid(row=3, column=3, padx=8, pady=5)
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=4, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        self.lbl_mail = ctk.CTkLabel(f, text="", font=a.f(-1, "bold"), text_color=C["muted"], wraplength=900, justify="left")
        a.btn(row, "Send test e-mail", "accent", self.test_email, width=170).pack(side="left", padx=4)
        a.btn(row, "Forget saved password", "gray", self.forget_smtp, width=190).pack(side="left", padx=4)
        a.btn(row, "New recovery code", "amber", self.new_recovery, width=170).pack(side="left", padx=4)
        a.btn(row, "Run setup wizard", "teal", self.run_wizard, width=170).pack(side="left", padx=4)
        self.lbl_mail.grid(row=5, column=0, columnspan=4, padx=16, pady=(0, 4), sticky="w")
        ctk.CTkLabel(f, text="Security notes: the App Password is stored ENCRYPTED with a key tied to this computer, so a copied database or backup "
                             "cannot reveal it - but anyone already logged in to this Windows account could still use it. WhatsApp codes are only a "
                             "convenience link (the code is visible on this PC); Email OTP or the Recovery Code is safer. Save the settings below "
                             "before testing e-mail.", font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(
            row=6, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        f = self.section(sc, "4d. Smart assistant, voice & daily summary")
        self.menu(f, 1, 0, "Assistant answer language", "assistant_lang", [I.AUTO_LABEL] + list(I.LANGS.values()))
        self.menu(f, 1, 2, "Floating button position", "assistant_fab_pos", ["Top-right", "Bottom-right", "Top-left", "Bottom-left"])
        self.entry(f, 2, 0, "Low-stock level (items at or below)", "low_stock_level")
        self.menu(f, 2, 2, "Send daily summary by", "summary_channel", ["WhatsApp", "Email"])
        self.entry(f, 3, 0, "Day-end summary time (HH:MM, 24h)", "summary_time")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=4, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        self.lbl_voice = ctk.CTkLabel(f, text="", font=a.f(-1, "bold"), text_color=C["muted"], wraplength=900, justify="left")
        a.btn(row, "Check installed voices", "accent", self.check_voices, width=190).pack(side="left", padx=4)
        a.btn(row, "Test voice", "teal", self.test_voice, width=130).pack(side="left", padx=4)
        a.btn(row, "Send daily summary now", "green", lambda: a.daily_summary_now("manual"), width=210).pack(side="left", padx=4)
        self.lbl_voice.grid(row=5, column=0, columnspan=4, padx=16, pady=(0, 4), sticky="w")
        ctk.CTkLabel(f, text="Voice output uses Windows' own voices and works offline; it only speaks a language if a Windows voice for it is installed "
                             "(use 'Check installed voices'). Voice INPUT (microphone) is optional and ONLINE: audio is sent to Google, and it needs "
                             "'pip install SpeechRecognition pyaudio'. The assistant's translations were written by the developer assistant, not a "
                             "professional translator - please have a native speaker check them. E-mail summaries go to the owner e-mail in 4c.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=6, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        f = self.section(sc, "4e. Catalogue: categories, item grid & price tools")
        self.menu(f, 1, 0, "Item grid: items per page", "grid_page_size", ["8", "12", "18", "24", "36"])
        self.menu(f, 1, 2, "Item grid: columns", "grid_cols", ["2", "3", "4"])
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=2, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        self.lbl_cat = ctk.CTkLabel(f, text="", font=a.f(-1, "bold"), text_color=C["muted"])
        a.btn(row, "Manage categories", "teal", lambda: open_manage_categories(a), width=180).pack(side="left", padx=4)
        a.btn(row, "Clear picture cache", "gray", self.clear_thumbs, width=180).pack(side="left", padx=4)
        self.lbl_cat.grid(row=3, column=0, columnspan=4, padx=16, pady=(0, 4), sticky="w")
        ctk.CTkLabel(f, text="Pictures are shrunk once and cached, so the item grid stays fast even with large photos. Add a picture to an item in "
                             "Inventory -> Picture -> Choose. The grid is OFF by default (toggle above) - turn it on, or use the 'Item grid' button on the Billing screen.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=4, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        f = self.section(sc, "4f. Buying & money rules: VAT, service charge, purchases, credit reminders")
        self.menu(f, 1, 0, "VAT mode", "vat_mode", ["Exclusive", "Inclusive"]); self.entry(f, 1, 2, "VAT percent", "vat_percent")
        self.entry(f, 2, 0, "VAT registration number (printed)", "vat_number"); self.entry(f, 2, 2, "Service charge percent", "service_percent")
        self.menu(f, 3, 0, "Purchase cost policy", "purchase_cost_policy", ["Last cost", "Weighted average"])
        self.entry(f, 3, 2, "Overdue after (days)", "overdue_days")
        self.entry(f, 4, 0, "Reminder cool-down (days)", "reminder_cooldown_days")
        ctk.CTkLabel(f, text="Reminder message ({name} {amount} {days} {shop}):", text_color=C["text"]).grid(row=5, column=0, columnspan=2, padx=16, pady=(8, 0), sticky="w")
        self.reminder_box = ctk.CTkEntry(f, width=820); self.reminder_box.grid(row=6, column=0, columnspan=4, padx=16, pady=4, sticky="w")
        self.reminder_box.insert(0, a.s.get("reminder_template"))
        self.w["reminder_template"] = self.reminder_box
        ctk.CTkLabel(f, text="The on/off switches for VAT, service charge, credit limit and reminders are in the feature list above. VAT rules: discounts are spread over all "
                             "items; Exclusive = VAT is ADDED to the bill, Inclusive = prices already contain VAT (it is only shown); service charge is not taxed unless "
                             "you tick 'VAT also applies to the service charge' above; items can be marked non-taxable in Inventory. Rates are YOUR responsibility - check the current legal VAT rate. "
                             "Totals are rounded per bill to 2 decimals. Returns reverse VAT/service in proportion.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=7, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        f = self.section(sc, "4g. Customer display & updates")
        self.entry(f, 1, 0, "Display window X (px)", "pole_x"); self.entry(f, 1, 2, "Display window Y (px)", "pole_y")
        self.entry(f, 2, 0, "Display width", "pole_w"); self.entry(f, 2, 2, "Display height", "pole_h")
        self.entry(f, 3, 0, "Display font size", "pole_font"); self.entry(f, 3, 2, "Idle screen message", "pole_promo")
        self.entry(f, 4, 0, "Update link (https://... version.json)", "update_url")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=5, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        a.btn(row, "Open customer display now", "accent", a.open_pole, width=220).pack(side="left", padx=4)
        a.btn(row, "Check for updates now", "teal", lambda: a.start_update_check(force=True), width=200).pack(side="left", padx=4)
        ctk.CTkLabel(f, text="Customer display: switch it on in the feature list, save, then press 'Open customer display now'. Drag the window to the second screen (or set X/Y, "
                             "e.g. X = your first screen's width) and tick full-screen. Update check: you host a small JSON file ({\"version\": \"6.5.0\", \"notes\": \"...\", "
                             "\"download\": \"https://...\"}) on any HTTPS link; VeloPOS checks at most once a day, only tells you, and never downloads or installs anything.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=6, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        f = self.section(sc, "4h. Owner phone dashboard (see sales & profit from the owner's phone)")
        self.entry(f, 1, 0, "Dashboard address (https://...workers.dev)", "dash_url"); self.entry(f, 1, 2, "Invite / renewal code (from your VeloPOS provider)", "dash_invite")
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=2, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        self.lbl_dash = ctk.CTkLabel(f, text=self.dash_status_text(), font=a.f(-1, "bold"), text_color=C["muted"], wraplength=900, justify="left")
        a.btn(row, "Upload now (test)", "accent", self.dash_test, width=170).pack(side="left", padx=4)
        a.btn(row, "Show / copy phone link", "teal", self.dash_link, width=200).pack(side="left", padx=4)
        a.btn(row, "Send link to owner WhatsApp", "green", self.dash_whatsapp, width=230).pack(side="left", padx=4)
        a.btn(row, "New link (old one stops)", "amber", self.dash_rotate, width=210).pack(side="left", padx=4)
        self.lbl_dash.grid(row=3, column=0, columnspan=4, padx=16, pady=(0, 4), sticky="w")
        ctk.CTkLabel(f, text="Switch it on in the feature list above. Only a SUMMARY is uploaded (today's totals, last 30 days, top items, low stock, total credit owed) - "
                             "never customer names, phone numbers, bills or cost prices. Billing never waits for the internet; if it is down the POS retries by itself. "
                             "Anyone who has the phone link can see the summary, so share it only with the owner ('New link' makes the old one stop working). "
                             "Enter the dashboard address and invite code, press 'Upload now (test)' and then open the phone link.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=4, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")

        a.btn(sc, "SAVE ALL SETTINGS & APPLY", "green", self.save, height=46).pack(fill="x", pady=10)

        # --- users
        f = a.card(sc); f.pack(fill="x", pady=8)
        ctk.CTkLabel(f, text="5. Staff accounts", font=a.f(2, "bold"), text_color=C["warning"]).pack(anchor="w", padx=16, pady=8)
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", padx=16, pady=4)
        self.u_name = ctk.CTkEntry(row, width=150, placeholder_text="Username"); self.u_name.pack(side="left", padx=4)
        self.u_pass = ctk.CTkEntry(row, width=150, placeholder_text="New password", show="*"); self.u_pass.pack(side="left", padx=4)
        self.u_role = ctk.CTkOptionMenu(row, values=["Cashier", "Admin"], width=110); self.u_role.pack(side="left", padx=4)
        a.btn(row, "Add / Update", "accent", self.save_user, width=120).pack(side="left", padx=4)
        a.btn(row, "Delete", "red", self.delete_user, width=90).pack(side="left", padx=4)
        self.utree = ttk.Treeview(f, columns=("u", "r", "c"), show="headings", height=4)
        for c, t in (("u", "Username"), ("r", "Role"), ("c", "Created")):
            self.utree.heading(c, text=t); self.utree.column(c, width=200, anchor="center")
        self.utree.pack(fill="x", padx=16, pady=8)
        self.utree.bind("<<TreeviewSelect>>", self.pick_user)
        self.load_users()

        # --- data
        f = a.card(sc); f.pack(fill="x", pady=8)
        ctk.CTkLabel(f, text="6. Data", font=a.f(2, "bold"), text_color=C["warning"]).pack(anchor="w", padx=16, pady=8)
        row = ctk.CTkFrame(f, fg_color="transparent"); row.pack(fill="x", padx=16, pady=(0, 12))
        a.btn(row, "Backup now", "green", a.backup, width=140).pack(side="left", padx=4)
        a.btn(row, "Open backup folder", "gray", lambda: os.startfile(dbm.p("Backups")) if os.name == "nt" else None, width=170).pack(side="left", padx=4)
        a.btn(row, "Backup & Restore...", "blue", lambda: a.navigate("backup"), width=170).pack(side="left", padx=4)
        a.btn(row, "Factory Reset...", "red", lambda: FactoryResetDialog(a), width=170).pack(side="right", padx=4)

    # ----------------------------------------------------------- builders
    def section(self, parent, title):
        f = self.app.card(parent); f.pack(fill="x", pady=6)
        ctk.CTkLabel(f, text=title, font=self.app.f(2, "bold"), text_color=self.app.accent).grid(row=0, column=0, columnspan=4, padx=16, pady=8, sticky="w")
        return f

    def entry(self, f, r, c, label, key):
        ctk.CTkLabel(f, text=label + ":", text_color=C["text"]).grid(row=r, column=c, padx=16, pady=5, sticky="w")
        e = ctk.CTkEntry(f, width=260); e.grid(row=r, column=c + 1, padx=8, pady=5); e.insert(0, self.app.s.get(key))
        self.w[key] = e

    def menu(self, f, r, c, label, key, values):
        ctk.CTkLabel(f, text=label + ":", text_color=C["text"]).grid(row=r, column=c, padx=16, pady=5, sticky="w")
        cur = self.app.s.get(key)
        if cur not in values:
            values = [cur] + list(values)
        m = ctk.CTkOptionMenu(f, values=list(values), width=260); m.grid(row=r, column=c + 1, padx=8, pady=5); m.set(cur)
        self.w[key] = m

    def values(self):
        out = {}
        for k, w in self.w.items():
            out[k] = ("1" if w.get() else "0") if isinstance(w, ctk.CTkCheckBox) else w.get().strip()
        return out

    def test(self, kind):
        P.run_test(self.app, P.Cfg(self.values()), kind)

    def pick_logo(self):
        from PIL import Image
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp")])
        if p:
            Image.open(p).convert("RGBA").save(dbm.p("Assets", "shop_logo.png"))
            messagebox.showinfo("Logo", "Logo saved. Tick 'Print shop logo' and press Test receipt.")

    def save(self):
        was_batches = dbm.settings.bool("feat_batches")
        out = self.values()
        dbm.settings.set_many(out)
        if dbm.settings.bool("feat_batches") and not was_batches:          # batch tracking just switched ON: build the starting batches
            r = svc.enable_batches(self.app.user)
            messagebox.showinfo("Batch tracking", f"Batch tracking is ON.\n{r['created']} item(s) got an opening batch from their current stock "
                                f"and expiry date; {r['trimmed']} batch(es) were trimmed to match the stock.")
        if self.smtp_pass.get():
            otp.set_smtp_password(self.smtp_pass.get())      # encrypted; never goes through the plain settings loop
        dbm.audit(self.app.user, "SETTINGS_SAVED")
        self.app.build_shell("settings")
        messagebox.showinfo("Saved", "Settings applied.")

    # ----------------------------------------------------------- owner phone dashboard (Phase 7.1)
    def dash_status_text(self):
        s = self.app.s
        if not s.get("dash_last_msg"):
            return "Not uploaded yet."
        return f"Last result: {s.get('dash_last_msg')}" + (f"   (last successful upload: {s.get('dash_last_ok')})" if s.get("dash_last_ok") else "")

    def dash_store_fields(self):
        """Takes the address / code typed above (no need to press SAVE first)."""
        v = self.values()
        dbm.settings.set_many({"dash_url": v.get("dash_url", "").strip(), "dash_invite": v.get("dash_invite", "").strip()})

    def dash_test(self):
        self.dash_store_fields()
        if not cs.normalize_url(dbm.settings.get("dash_url")):
            return self.lbl_dash.configure(text="Enter the dashboard address first (it must start with https://).", text_color=C["danger"])
        self.lbl_dash.configure(text="Uploading...", text_color=C["muted"])

        def done(res, err):
            ok, msg = res if res else (False, str(err))
            dbm.settings.set_many({"dash_last_msg": msg, **({"dash_last_ok": time.strftime("%Y-%m-%d %H:%M")} if ok else {})})
            self.lbl_dash.configure(text=msg + ("  Now press 'Show / copy phone link'." if ok else ""), text_color=C["success"] if ok else C["danger"])
        run_bg(self, lambda: cs.push_snapshot(dbm.settings), done)

    def dash_link(self):
        self.dash_store_fields()
        cs.ensure_identity()
        url = cs.view_url()
        if not url:
            return self.lbl_dash.configure(text="Enter the dashboard address first (https://...).", text_color=C["danger"])
        try:
            self.clipboard_clear(); self.clipboard_append(url)
        except Exception:
            pass
        messagebox.showinfo("Owner phone link", "The link was copied. Open it on the owner's phone and use 'Add to Home screen'.\n\n"
                            "Keep it private: anyone with this link can see the summary.\n\n" + url)

    def dash_whatsapp(self):
        self.dash_store_fields()
        cs.ensure_identity()
        url = cs.view_url()
        phone = self.w["owner_whatsapp"].get().strip() if "owner_whatsapp" in self.w else dbm.settings.get("owner_whatsapp")
        try:
            svc.open_url(otp.whatsapp_link(phone, f"{dbm.settings.get('shop_name')} - VeloPOS dashboard (private link): {url}"), prefer_desktop=True)
        except ValueError as e:
            self.lbl_dash.configure(text=str(e), text_color=C["danger"])

    def dash_rotate(self):
        if messagebox.askyesno("New link", "Create a new phone link? The old link will stop working after the next upload."):
            cs.rotate_view_token()
            dbm.audit(self.app.user, "DASHBOARD_LINK_ROTATED")
            self.dash_test()

    # ----------------------------------------------------------- users
    def load_users(self):
        for i in self.utree.get_children():
            self.utree.delete(i)
        with dbm.db() as c:
            for r in c.execute("SELECT username, role, created FROM users ORDER BY role, username"):
                self.utree.insert("", "end", values=(r["username"], r["role"], r["created"] or ""))

    def pick_user(self, ev=None):
        sel = self.utree.selection()
        if sel:
            u, r, _ = self.utree.item(sel[0], "values")
            self.u_name.delete(0, "end"); self.u_name.insert(0, u); self.u_role.set(r)

    def save_user(self):
        u, p, r = self.u_name.get().strip().lower(), self.u_pass.get(), self.u_role.get()
        if not u:
            return messagebox.showwarning("Required", "Enter a username.")
        try:
            svc.save_user(u, p, r, self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("User", str(ex))
        self.u_pass.delete(0, "end"); self.load_users()

    def delete_user(self):
        u = self.u_name.get().strip().lower()
        if not u:
            return
        if not messagebox.askyesno("Delete", f"Delete user '{u}'?"):
            return
        try:
            svc.delete_user(u, self.app.user)
        except ValueError as ex:
            return messagebox.showerror("Blocked", str(ex))
        self.load_users()

    # ----------------------------------------------------------- security helpers
    def test_email(self):
        v = self.values()
        try:
            conf = dict(host=v["smtp_host"], port=int(v["smtp_port"] or 465), user=v["smtp_user"],
                        password=self.smtp_pass.get() or otp.smtp_config()["password"])
        except ValueError:
            return self.lbl_mail.configure(text="SMTP port must be a number (465 or 587).", text_color=C["danger"])
        to = v["owner_email"]
        self.lbl_mail.configure(text="Sending test e-mail...", text_color=C["muted"])

        def done(res, err):
            self.lbl_mail.configure(text=str(err) if err else f"Test e-mail sent to {to}. Check the inbox (and Spam).",
                                    text_color=C["danger"] if err else C["success"])
        run_bg(self, lambda: otp.send_email(to, "VeloPOS test e-mail", "Your VeloPOS e-mail settings work.", conf), done)

    def forget_smtp(self):
        if messagebox.askyesno("Forget password", "Remove the saved Gmail App Password from this computer?"):
            otp.set_smtp_password("")
            dbm.audit(self.app.user, "SMTP_PASSWORD_REMOVED")
            self.smtp_pass.configure(placeholder_text="16-character App Password")

    def new_recovery(self):
        pw = ask_password(self.app, "New recovery code", "Enter your Admin password to create a NEW recovery code.\nThe old code stops working.")
        if pw is None:
            return
        if not svc.verify_admin_password(self.app.user, pw):
            return messagebox.showerror("Denied", "Incorrect password.")
        code = svc.regenerate_recovery_code(self.app.user)
        self.clipboard_clear(); self.clipboard_append(code)
        messagebox.showinfo("SAVE YOUR NEW RECOVERY CODE", f"New recovery code (copied to clipboard):\n\n{code}\n\nWrite it down and keep it safe. "
                            "The old code no longer works and this one will NOT be shown again.")

    def check_voices(self):
        self.lbl_voice.configure(text="Checking Windows voices...", text_color=C["muted"])

        def done(res, err):
            ok, data = res if res else (False, str(err))
            if not ok:
                return self.lbl_voice.configure(text=str(data), text_color=C["danger"])
            lines = [f"{name}: " + (", ".join(data[code]) if code in data else "NO voice installed")
                     for code, name in I.LANGS.items()]
            self.lbl_voice.configure(text="\n".join(lines), text_color=C["text"])
        run_bg(self, voice.installed_voices, done)

    def test_voice(self):
        code = I.LANG_LABELS.get(self.w["assistant_lang"].get(), "auto")
        code = code if code in I.LANGS else "en"
        sample = {"en": "Voice test. VeloPOS is ready.", "es": "Prueba de voz. VeloPOS está listo."}.get(code, I.STR[code]["thanks"])

        def done(st):
            msg = {"ok": "Spoken.", "novoice": f"No Windows voice for {I.LANGS[code]} is installed.", "error": "Speaking failed."}[st]
            self.after(0, lambda: self.lbl_voice.configure(text=msg, text_color=C["text"] if st == "ok" else C["danger"]))
        voice.speak(sample, code, True, done)

    def clear_thumbs(self):
        thumbs.CACHE.clear()
        n = thumbs.clear_disk()
        self.lbl_cat.configure(text=f"Picture cache cleared ({n} files). It rebuilds automatically.", text_color=C["text"])

    def run_wizard(self):
        if messagebox.askyesno("Setup wizard", "Open the setup wizard? Your current values are pre-filled."):
            self.app.show_wizard()
