"""Phase 4 dialogs: password prompt, OTP panel, Forgot-password and Factory-Reset. UI only - the real work
(verification, wipe, backup) lives in services.py / otp.py / backup.py."""
import threading
from tkinter import messagebox

import customtkinter as ctk

from . import database as dbm, license as lic, otp, security, services as svc, support
from .theme import C


def run_bg(widget, work, done):
    """Run work() in a thread (e-mail can take seconds), then done(result, error) on the UI thread."""
    def target():
        try:
            res, err = work(), None
        except Exception as e:          # noqa: BLE001 - shown to the user
            res, err = None, e
        try:
            widget.after(0, lambda: done(res, err))
        except Exception:               # window was closed meanwhile
            pass
    threading.Thread(target=target, daemon=True).start()


class _Dialog(ctk.CTkToplevel):
    def __init__(self, app, title, w, h):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.geometry(f"{w}x{h}")
        self.configure(fg_color=C["bg"])
        self.transient(app)
        self.after(120, lambda: (self.grab_set(), self.lift(), self.focus_force()))
        self.body = None

    def clear(self):
        if self.body is not None:
            self.body.destroy()
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=22, pady=18)
        return self.body

    def text(self, parent, text, off=0, bold=False, color="text", wrap=470, pady=4):
        lb = ctk.CTkLabel(parent, text=text, font=self.app.f(off, "bold" if bold else "normal"),
                          text_color=C[color], wraplength=wrap, justify="left")
        lb.pack(anchor="w", pady=pady)
        return lb


def ask_password(app, title, prompt):
    """Modal password prompt. Returns the typed text, or None if cancelled."""
    d = _Dialog(app, title, 430, 230)
    res = {"v": None}
    b = d.clear()
    d.text(b, prompt, 0, False, "text", 380, 6)
    e = ctk.CTkEntry(b, show="*", width=320, height=40, font=app.f(1))
    e.pack(pady=6)
    d.after(250, e.focus_force)

    def ok(ev=None):
        res["v"] = e.get()
        d.destroy()
    e.bind("<Return>", ok)
    row = ctk.CTkFrame(b, fg_color="transparent")
    row.pack(pady=8)
    app.btn(row, "OK", "green", ok, width=110).pack(side="left", padx=5)
    app.btn(row, "Cancel", "gray", d.destroy, width=110).pack(side="left", padx=5)
    d.wait_window()
    return res["v"]


# ====================================================================== OTP / Recovery-code panel
class OtpPanel(ctk.CTkFrame):
    EMAIL, WA, REC = "Email OTP", "WhatsApp OTP (convenience only)", "Recovery Code"
    SUP = "Support code (from your VeloPOS provider)"

    def __init__(self, parent, app, purpose, scope, methods, on_ok):
        super().__init__(parent, fg_color="transparent")
        self.app, self.purpose, self.scope, self.on_ok = app, purpose, scope, on_ok
        self.method = ctk.StringVar(value=methods[0])
        self.challenge = support.new_challenge()
        ctk.CTkLabel(self, text="Verify it is really you", font=app.f(2, "bold"), text_color=C["warning"]).pack(anchor="w", pady=(0, 6))
        ctk.CTkOptionMenu(self, values=methods, variable=self.method, command=lambda v: self._changed(),
                          width=340, height=36, font=app.f(0), fg_color=app.accent, button_color=app.accent).pack(anchor="w", pady=4)
        self.hint = ctk.CTkLabel(self, text="", font=app.f(-1), text_color=C["muted"], wraplength=450, justify="left")
        self.hint.pack(anchor="w", pady=4)
        self.send_btn = app.btn(self, "Send code", "accent", self.send, width=340)
        self.send_btn.pack(anchor="w", pady=4)
        self.code = ctk.CTkEntry(self, width=340, height=40, font=app.f(2))
        self.code.pack(anchor="w", pady=6)
        self.code.bind("<Return>", self.verify)
        app.btn(self, "VERIFY", "green", self.verify, width=340, height=42).pack(anchor="w", pady=4)
        self.status = ctk.CTkLabel(self, text="", font=app.f(-1, "bold"), text_color=C["muted"], wraplength=450, justify="left")
        self.status.pack(anchor="w", pady=4)
        self._changed()

    def _say(self, text, color="muted"):
        self.status.configure(text=text, text_color=C[color])

    def _changed(self):
        m, s = self.method.get(), self.app.s
        rec, sup = m == self.REC, m == self.SUP
        self.send_btn.configure(state="disabled" if rec else "normal", text="New challenge" if sup else "Send code")
        self.code.configure(placeholder_text="XXXX-XXXX-XXXX-XXXX" if rec else ("support code" if sup else "6-digit code"))
        if sup:
            self.hint.configure(text=f"Tell your VeloPOS provider this Machine ID and Challenge:\n\n   {lic.machine_id()}\n   {self.challenge}\n\n"
                                     "The provider types a one-time code on this screen. It works only on this PC, only for this challenge, "
                                     "and only for a short time.")
        elif rec:
            self.hint.configure(text="Type the Recovery Code you saved when VeloPOS was first set up. Works offline.")
        elif m == self.EMAIL:
            mail = otp.mask_email(s.get("owner_email")) if s.get("owner_email") else "(owner e-mail not set)"
            self.hint.configure(text=f"A 6-digit code is e-mailed to {mail}. Valid 5 minutes, 3 attempts.")
        else:
            self.hint.configure(text="Opens WhatsApp with the code typed in; you press Send yourself. This is only a convenience: "
                                     "the code is visible on this PC, so Email OTP or the Recovery Code is safer.")
        self._say("")

    def _locked(self):
        wait = svc.lock_remaining(self.scope)
        if wait:
            self._say(f"Too many wrong attempts. Try again in {wait // 60 + 1} minute(s).", "danger")
        return bool(wait)

    def send(self):
        if self._locked():
            return
        m, s = self.method.get(), self.app.s
        top = self.winfo_toplevel()
        if m == self.SUP:
            self.challenge = support.new_challenge()
            return self._changed()
        if m == self.EMAIL:
            if not otp.email_ready(s):
                return messagebox.showwarning("E-mail not set up", "Enter the owner e-mail, your Gmail address and App Password in "
                                              "Settings -> 4c first (or use the Recovery Code).", parent=top)
            code = otp.otp.issue(self.purpose)
            self.send_btn.configure(state="disabled")
            self._say("Sending e-mail...")

            def done(res, err):
                self.send_btn.configure(state="normal")
                if err:
                    otp.otp.cancel(self.purpose)
                    self._say(str(err), "danger")
                else:
                    self._say(f"Code sent to {otp.mask_email(s.get('owner_email'))}. Check the inbox (and Spam).", "success")
                    self.code.focus_set()
            run_bg(self, lambda: otp.send_otp_email(code, self.purpose, s), done)
        elif m == self.WA:
            code = otp.otp.issue(self.purpose)
            try:
                url = otp.whatsapp_otp_url(s.get("owner_whatsapp"), code, self.purpose, s.get("shop_name"))
            except ValueError as e:
                otp.otp.cancel(self.purpose)
                return self._say(str(e), "danger")
            svc.open_url(url)
            self._say("WhatsApp opened. Press Send there, read the code, and type it above.", "success")

    def verify(self, e=None):
        if self._locked():
            return
        m, code = self.method.get(), self.code.get().strip()
        if not code:
            return self._say("Enter the code first.", "danger")
        if m == self.REC:
            ok, msg = svc.verify_recovery_code(code), "Wrong Recovery Code."
        elif m == self.SUP:
            ok, msg = support.verify(code, self.challenge, self.purpose)
            if ok:
                dbm.audit(self.app.user or "-", "SUPPORT_CODE_USED", f"{self.purpose} challenge={self.challenge}")
                self.challenge = support.new_challenge()
        else:
            ok, msg = otp.otp.verify(self.purpose, code)
        who = self.app.user or "-"
        if ok:
            svc.clear_fails(self.scope)
            dbm.audit(who, "OTP_OK", f"{self.purpose} via {m}")
            self.on_ok(m)
        else:
            locked = svc.register_fail(self.scope)
            dbm.audit(who, "OTP_FAILED", f"{self.purpose} via {m}")
            self.code.delete(0, "end")
            self._say(msg + (" Locked for 15 minutes." if locked else ""), "danger")


# ====================================================================== forgot password (login screen)
class ForgotPasswordDialog(_Dialog):
    def __init__(self, app):
        super().__init__(app, "Forgot password", 540, 640)
        self.user_var = ctk.StringVar(value="")
        self.via = ""
        self.step_proof()

    def step_proof(self):
        a, b = self.app, self.clear()
        self.text(b, "Reset an Admin password", 4, True, "text")
        self.text(b, "Prove you are the owner with the Recovery Code you saved at setup, or with an e-mailed code. "
                     "Cashier passwords are reset by an Admin in Settings.", -1, False, "muted")
        admins = svc.admin_usernames() or ["(none)"]
        self.user_var.set(admins[0])
        ctk.CTkOptionMenu(b, values=admins, variable=self.user_var, width=340, height=36, font=a.f(0),
                          fg_color=a.accent, button_color=a.accent).pack(anchor="w", pady=(4, 10))
        methods = [OtpPanel.REC] + ([OtpPanel.EMAIL] if otp.email_ready(a.s) else []) + [OtpPanel.SUP]
        OtpPanel(b, a, "forgot-password", "forgot", methods, self.proved).pack(anchor="w", fill="x")

    def proved(self, method):
        self.via = method
        a, b = self.app, self.clear()
        self.text(b, "Choose a new password", 4, True, "text")
        self.text(b, f"Account: {self.user_var.get()}", 0, False, "muted")
        p1 = ctk.CTkEntry(b, width=340, height=40, show="*", placeholder_text="New password (min 6 characters)", font=a.f(1))
        p1.pack(anchor="w", pady=6)
        p2 = ctk.CTkEntry(b, width=340, height=40, show="*", placeholder_text="Repeat new password", font=a.f(1))
        p2.pack(anchor="w", pady=6)

        def save(e=None):
            if p1.get() != p2.get():
                return messagebox.showwarning("Check", "The two passwords do not match.", parent=self)
            try:
                svc.reset_password(self.user_var.get(), p1.get(), self.via)
            except ValueError as ex:
                return messagebox.showwarning("Check", str(ex), parent=self)
            messagebox.showinfo("Password changed", "Done. You can now log in with the new password.", parent=self)
            self.destroy()
        p2.bind("<Return>", save)
        a.btn(b, "SET NEW PASSWORD", "green", save, width=340, height=44).pack(anchor="w", pady=12)


# ====================================================================== factory reset (Settings)
class FactoryResetDialog(_Dialog):
    SCOPE_LABEL = {"sales_stock": "Sales + stock only", "products": "Products only", "everything": "EVERYTHING"}

    def __init__(self, app):
        super().__init__(app, "Factory Reset", 600, 760)
        self.scope = ctk.StringVar(value="sales_stock")
        self.authorized = False
        self.step_scope()

    def step_scope(self):
        a, b = self.app, self.clear()
        self.text(b, "Factory Reset", 6, True, "danger")
        self.text(b, "Choose what to erase. A full backup is made automatically first, and your user accounts, licence, "
                     "settings and audit log are always kept.", -1, False, "muted")
        n = svc.table_counts()
        self.text(b, f"Right now: {n['products']} products, {n['customers']} customers, {n['sales']} bills, "
                     f"{n['returns']} returns, {n['expenses']} expenses.", -1, True, "text")
        for key in ("sales_stock", "products", "everything"):
            ctk.CTkRadioButton(b, text=self.SCOPE_LABEL[key], variable=self.scope, value=key, font=a.f(1, "bold"),
                               text_color=C["text"]).pack(anchor="w", pady=(10, 0))
            self.text(b, svc.RESET_SCOPES[key], -2, False, "muted", 500, 0)
        self.text(b, "Step 1: enter YOUR Admin password", 0, True, "warning", pady=(14, 2))
        self.pw = ctk.CTkEntry(b, show="*", width=340, height=40, font=a.f(1))
        self.pw.pack(anchor="w", pady=4)
        self.pw.bind("<Return>", lambda e: self.check_password())
        self.err = self.text(b, "", -1, True, "danger")
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.pack(anchor="w", pady=8)
        a.btn(row, "NEXT", "red", self.check_password, width=150, height=42).pack(side="left", padx=(0, 8))
        a.btn(row, "Cancel", "gray", self.destroy, width=120, height=42).pack(side="left")

    def check_password(self):
        a, u = self.app, self.app.user
        wait = svc.lock_remaining("pwcheck:" + u)
        if wait:
            return self.err.configure(text=f"Too many wrong attempts. Wait {wait} seconds.")
        if not svc.verify_admin_password(u, self.pw.get()):
            svc.register_fail("pwcheck:" + u, 5, 60)
            dbm.audit(u, "RESET_PASSWORD_WRONG")
            self.pw.delete(0, "end")
            return self.err.configure(text="Incorrect password.")
        svc.clear_fails("pwcheck:" + u)
        if a.s.bool("feat_otp"):
            self.step_otp()
        else:
            self.authorized = True
            self.step_confirm()

    def step_otp(self):
        a, b = self.app, self.clear()
        self.text(b, "Step 2: one-time code", 4, True, "warning")
        OtpPanel(b, a, "factory-reset", "reset", [OtpPanel.REC, OtpPanel.EMAIL, OtpPanel.WA], self.otp_ok).pack(anchor="w", fill="x")

    def otp_ok(self, method):
        self.authorized = True
        self.step_confirm()

    def step_confirm(self):
        a, b = self.app, self.clear()
        scope = self.scope.get()
        self.text(b, "Step 3: final confirmation", 4, True, "danger")
        self.text(b, f"You are about to erase:\n{svc.RESET_SCOPES[scope]}", 0, False, "text")
        self.text(b, "Type  RESET  (capital letters) below. VeloPOS will back up first, wipe, then restart.", -1, False, "muted")
        e = ctk.CTkEntry(b, width=340, height=42, font=a.f(2, "bold"), placeholder_text="RESET")
        e.pack(anchor="w", pady=8)

        def go(ev=None):
            if not self.authorized:
                return
            try:
                res = svc.factory_reset(scope, a.user, e.get())
            except Exception as ex:             # noqa: BLE001
                return messagebox.showerror("Factory Reset", f"Nothing was erased.\n\n{ex}", parent=self)
            messagebox.showinfo("Factory Reset done", f"Data erased ({self.SCOPE_LABEL[scope]}).\n\nBackup of your old data:\n"
                                f"{res['backup']}\n\nVeloPOS will now restart.", parent=self)
            self.destroy()
            a.restart()
        e.bind("<Return>", go)
        a.btn(b, "ERASE NOW", "red", go, width=340, height=46).pack(anchor="w", pady=10)
        a.btn(b, "Cancel", "gray", self.destroy, width=340, height=36).pack(anchor="w")
