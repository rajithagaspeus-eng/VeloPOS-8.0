"""First-run Setup Wizard: shop info -> bank -> printer -> owner contact/e-mail -> feature toggles."""
from tkinter import messagebox

import customtkinter as ctk

from .. import database as dbm, otp, printing as P, services as svc
from ..dialogs import run_bg
from ..theme import C

STEPS = [
    ("1 / 5   Shop information", "These appear on every receipt and invoice.",
     [("entry", "shop_name", "Shop name"), ("entry", "phone", "Phone"), ("entry", "address", "Address"),
      ("entry", "currency", "Currency symbol")]),
    ("2 / 5   Bank details (optional)", "Printed on A4 / A5 invoices. Leave blank to skip.",
     [("entry", "bank_name", "Bank name"), ("entry", "bank_branch", "Branch"),
      ("entry", "bank_acc", "Account number"), ("entry", "bank_holder", "Account holder")]),
    ("3 / 5   Receipt printer", "Pick your printer, then press 'Test receipt'. You can fine-tune later in Settings -> 3b.",
     [("menu", "printer_brand", "Printer brand", P.BRANDS), ("menu", "print_mode", "Connection", P.MODES),
      ("menu", "printer", "Windows printer", None), ("menu", "paper_size", "Paper size", ["80mm", "58mm", "A5", "A4"]),
      ("entry", "lan_ip", "LAN printer IP (LAN mode only)"), ("entry", "com_port", "COM port (Bluetooth/serial only)"),
      ("check", "feat_cash_drawer", "A cash drawer is connected to this printer")]),
    ("4 / 5   Owner contact & e-mail codes (optional)",
     "Used for security codes (Factory Reset, forgot password). For e-mail you need a Gmail address and an App Password "
     "(Google Account -> Security -> 2-Step Verification -> App passwords). It is stored encrypted on this PC only.",
     [("entry", "owner_email", "Owner e-mail (receives codes)"), ("entry", "owner_whatsapp", "Owner WhatsApp (e.g. 0771234567)"),
      ("entry", "smtp_user", "Gmail address (sender)"), ("entry", "smtp_host", "SMTP server"), ("entry", "smtp_port", "SMTP port"),
      ("password", "_smtp_pass", "Gmail App Password")]),
    ("5 / 5   Features", "Switch features on or off. You can change any of these later in Settings.", "FEATURES"),
]


class Wizard(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=C["bg"])
        self.app = app
        self.vals, self.w, self.i = {}, {}, 0
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.card = app.card(self)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.show(0)

    # ------------------------------------------------------------------ rendering
    def show(self, i):
        a = self.app
        self.i = i
        for ch in self.card.winfo_children():
            ch.destroy()
        self.w = {}
        title, hint, fields = STEPS[i]
        ctk.CTkLabel(self.card, text="VeloPOS Setup", font=a.f(1, "bold"), text_color=a.accent).pack(padx=40, pady=(22, 0))
        ctk.CTkLabel(self.card, text=title, font=a.f(6, "bold"), text_color=C["text"]).pack(padx=40, pady=(2, 2))
        ctk.CTkLabel(self.card, text=hint, font=a.f(-1), text_color=C["muted"], wraplength=640, justify="center").pack(padx=40, pady=(0, 10))
        form = ctk.CTkFrame(self.card, fg_color="transparent")
        form.pack(padx=40, pady=4)
        if fields == "FEATURES":
            for r, (k, label) in enumerate(dbm.FEATURES):
                cb = ctk.CTkCheckBox(form, text=label, text_color=C["text"], font=a.f(0))
                cb.grid(row=r % 13, column=r // 13, sticky="w", pady=3, padx=(0, 18))
                if self.cur(k) == "1":
                    cb.select()
                self.w[k] = ("check", cb)
        else:
            for r, f in enumerate(fields):
                kind, key, label = f[0], f[1], f[2]
                if kind == "check":
                    cb = ctk.CTkCheckBox(form, text=label, text_color=C["text"], font=a.f(0))
                    cb.grid(row=r, column=0, columnspan=2, sticky="w", pady=4)
                    if self.cur(key) == "1":
                        cb.select()
                    self.w[key] = ("check", cb)
                    continue
                ctk.CTkLabel(form, text=label + ":", text_color=C["text"], font=a.f(0)).grid(row=r, column=0, sticky="w", padx=(0, 14), pady=5)
                if kind == "menu":
                    values = f[3] or svc.list_printers()
                    cur = self.cur(key)
                    if cur not in values:
                        values = [cur] + list(values)
                    wd = ctk.CTkOptionMenu(form, values=list(values), width=320)
                    wd.set(cur)
                else:
                    wd = ctk.CTkEntry(form, width=320, show="*" if kind == "password" else None,
                                      placeholder_text="(saved - leave blank to keep)" if kind == "password" and otp.has_smtp_password() else "")
                    if kind == "entry":
                        wd.insert(0, self.cur(key))
                wd.grid(row=r, column=1, pady=5, sticky="w")
                self.w[key] = (kind, wd)
        extra = ctk.CTkFrame(self.card, fg_color="transparent")
        extra.pack(pady=(6, 0))
        self.msg = ctk.CTkLabel(self.card, text="", font=a.f(-1, "bold"), text_color=C["muted"], wraplength=620)
        if i == 2:
            a.btn(extra, "Test receipt", "accent", lambda: self.test("sample"), width=150).pack(side="left", padx=4)
            a.btn(extra, "Width calibration", "purple", lambda: self.test("calibration"), width=170).pack(side="left", padx=4)
        if i == 3:
            a.btn(extra, "Send test e-mail", "accent", self.test_email, width=180).pack(side="left", padx=4)
        self.msg.pack(pady=2)
        nav = ctk.CTkFrame(self.card, fg_color="transparent")
        nav.pack(pady=(10, 24))
        if i > 0:
            a.btn(nav, "Back", "gray", lambda: self.go(i - 1), width=110, height=42).pack(side="left", padx=5)
        last = i == len(STEPS) - 1
        a.btn(nav, "FINISH" if last else "Next", "green", self.finish if last else (lambda: self.go(i + 1)), width=150, height=42).pack(side="left", padx=5)
        a.btn(nav, "Skip setup", "amber", self.skip, width=130, height=42).pack(side="left", padx=5)

    def cur(self, key):
        return self.vals[key] if key in self.vals else self.app.s.get(key)

    def collect(self):
        for key, (kind, wd) in self.w.items():
            if kind == "check":
                self.vals[key] = "1" if wd.get() else "0"
            elif kind == "password":
                self.vals[key] = wd.get()
            else:
                self.vals[key] = wd.get().strip()

    def go(self, i):
        self.collect()
        self.show(i)

    # ------------------------------------------------------------------ tests
    def test(self, kind):
        self.collect()
        P.run_test(self.app, P.Cfg({k: v for k, v in self.vals.items() if not k.startswith("_")}), kind)

    def test_email(self):
        self.collect()
        v = self.vals
        pw = v.get("_smtp_pass") or otp.smtp_config()["password"]
        conf = dict(host=v.get("smtp_host", ""), port=int(v.get("smtp_port") or 465), user=v.get("smtp_user", ""), password=pw)
        to = v.get("owner_email", "")
        self.msg.configure(text="Sending test e-mail...", text_color=C["muted"])

        def done(res, err):
            self.msg.configure(text=str(err) if err else f"Test e-mail sent to {to}. Check the inbox.",
                               text_color=C["danger"] if err else C["success"])
        run_bg(self, lambda: otp.send_email(to, "VeloPOS test e-mail", "Your VeloPOS e-mail settings work.", conf), done)

    # ------------------------------------------------------------------ end
    def skip(self):
        if messagebox.askyesno("Skip setup", "Skip the setup wizard? You can change everything later in Settings."):
            dbm.settings.set_many({"setup_done": "1"})
            self.app.build_shell("billing")

    def finish(self):
        self.collect()
        pw = self.vals.pop("_smtp_pass", "")
        self.vals["setup_done"] = "1"
        dbm.settings.set_many(self.vals)
        if pw:
            otp.set_smtp_password(pw)
        dbm.audit(self.app.user, "SETUP_WIZARD_DONE")
        messagebox.showinfo("All set", "Setup complete. You can change any of this later in Settings.\n\n"
                                       "Tip: Backup & Restore (left menu) is where automatic backups are scheduled.")
        self.app.build_shell("billing")
