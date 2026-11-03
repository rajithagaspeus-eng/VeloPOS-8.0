from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import database as dbm, services as svc
from ..theme import C
from . import Screen


class ShiftScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self.heading(self, "Shift & Cash Drawer").grid(row=0, column=0, sticky="w")
        self.body = app.card(self); self.body.grid(row=1, column=0, sticky="ew", pady=8)
        box = ctk.CTkFrame(self, fg_color="transparent"); box.grid(row=2, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1); box.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(box, text="Shift history  (double-click to view / print the Z-Report)", font=app.f(0, "bold"), text_color=C["muted"]).grid(row=0, column=0, sticky="w")
        cols = ("#", "Cashier", "Opened", "Closed", "Opening", "Expected", "Counted", "Difference", "Status")
        self.tree = ttk.Treeview(box, columns=cols, show="headings")
        for c, w in zip(cols, (50, 100, 150, 150, 95, 95, 95, 95, 80)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=6)
        self.tree.bind("<Double-1>", self.open_z)
        self.render()

    def render(self):
        a = self.app
        for w in self.body.winfo_children():
            w.destroy()
        sh = svc.current_shift(a.user)
        if not sh:
            ctk.CTkLabel(self.body, text="No open shift for you", font=a.f(4, "bold"), text_color=C["warning"]).pack(padx=20, pady=(16, 4))
            ctk.CTkLabel(self.body, text="Count the cash in the drawer and enter it as the opening cash.", font=a.f(0), text_color=C["muted"]).pack()
            row = ctk.CTkFrame(self.body, fg_color="transparent"); row.pack(pady=14)
            e = ctk.CTkEntry(row, width=200, height=40, placeholder_text=f"Opening cash ({a.cur})", font=a.f(2)); e.pack(side="left", padx=6)
            e.insert(0, "0")

            def go(ev=None):
                try:
                    svc.open_shift(a.user, svc.num(e.get() or 0))
                except ValueError as ex:
                    return messagebox.showwarning("Shift", str(ex))
                self.render(); self.load()
            e.bind("<Return>", go)
            a.btn(row, "OPEN SHIFT", "green", go, width=160, height=40).pack(side="left", padx=6)
        else:
            sm = svc.shift_summary(sh["id"])
            ctk.CTkLabel(self.body, text=f"Shift #{sh['id']} OPEN since {sh['opened_at'].replace('T', ' ')}  -  {a.user.upper()}", font=a.f(3, "bold"), text_color=C["success"]).pack(padx=20, pady=(14, 6), anchor="w")
            g = ctk.CTkFrame(self.body, fg_color="transparent"); g.pack(fill="x", padx=20)
            lines = [("Opening cash", sm["shift"]["opening_cash"])]
            lines += [(f"{m} sales ({n})", t) for m, (n, t) in sorted(sm["by"].items())]
            lines += [("Cash from sales (incl. credit advances)", sm["cash_sales"]), ("Cash in", sm["ins"]), ("Cash out (incl. refunds)", sm["outs"])]
            for i, (lab, val) in enumerate(lines):
                ctk.CTkLabel(g, text=lab, font=a.f(0), text_color=C["text"]).grid(row=i, column=0, sticky="w", pady=1)
                ctk.CTkLabel(g, text=f"{a.cur} {val:,.2f}", font=a.f(0, "bold"), text_color=C["text"]).grid(row=i, column=1, sticky="e", padx=30)
            ctk.CTkLabel(self.body, text=f"EXPECTED CASH IN DRAWER:  {a.cur} {sm['expected']:,.2f}", font=a.f(5, "bold"), text_color=C["warning"]).pack(pady=10)
            row = ctk.CTkFrame(self.body, fg_color="transparent"); row.pack(pady=(0, 14))
            a.btn(row, "Cash IN", "teal", lambda: self.move("IN", sh["id"]), width=120).pack(side="left", padx=5)
            a.btn(row, "Cash OUT", "amber", lambda: self.move("OUT", sh["id"]), width=120).pack(side="left", padx=5)
            a.btn(row, "Refresh", "gray", self.render, width=100).pack(side="left", padx=5)
            a.btn(row, "CLOSE SHIFT / Z-REPORT", "red", lambda: self.close(sh["id"]), width=230).pack(side="left", padx=5)
        self.load()

    def move(self, kind, sid):
        a = self.app
        d = self.dialog(f"Cash {kind}", 420, 280)
        ctk.CTkLabel(d, text="Cash IN (add to drawer)" if kind == "IN" else "Cash OUT (take from drawer)", font=a.f(3, "bold"), text_color=C["text"]).pack(pady=(18, 8))
        e_a = ctk.CTkEntry(d, width=280, height=40, placeholder_text=f"Amount ({a.cur})"); e_a.pack(pady=5)
        e_r = ctk.CTkEntry(d, width=280, height=40, placeholder_text="Reason (e.g. bought tea, bank deposit)"); e_r.pack(pady=5)

        def ok(ev=None):
            try:
                svc.cash_move(sid, kind, svc.num(e_a.get()), e_r.get(), a.user)
            except ValueError as ex:
                return messagebox.showwarning("Cash move", str(ex), parent=d)
            d.destroy(); self.render()
        e_r.bind("<Return>", ok)
        a.btn(d, "SAVE", "green", ok, width=280, height=42).pack(pady=12)

    def close(self, sid):
        a = self.app
        sm = svc.shift_summary(sid)
        d = self.dialog("Close shift", 440, 360)
        ctk.CTkLabel(d, text="Count the cash in the drawer", font=a.f(3, "bold"), text_color=C["text"]).pack(pady=(18, 4))
        ctk.CTkLabel(d, text=f"Expected: {a.cur} {sm['expected']:,.2f}", font=a.f(1), text_color=C["muted"]).pack()
        e_c = ctk.CTkEntry(d, width=280, height=42, font=a.f(3, "bold"), justify="center", placeholder_text="Counted cash"); e_c.pack(pady=10)
        e_n = ctk.CTkEntry(d, width=280, height=38, placeholder_text="Note (optional)"); e_n.pack(pady=4)

        def ok():
            try:
                counted = svc.num(e_c.get())
            except ValueError:
                return messagebox.showwarning("Check", "Enter the counted cash.", parent=d)
            diff = svc.close_shift(sid, counted, e_n.get().strip(), a.user)
            d.destroy(); self.render()
            self.show_text("Z-Report", svc.z_report_text(sid, 42, a.cur, a.s.get("shop_name")))
            if diff:
                messagebox.showwarning("Cash difference", f"Drawer is {'OVER' if diff > 0 else 'SHORT'} by {a.cur} {abs(diff):,.2f}")
            a.on_shift_closed(sid)
        a.btn(d, "CLOSE SHIFT", "red", ok, width=280, height=44).pack(pady=14)
        d.after(200, e_c.focus_force)

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        q, args = "SELECT * FROM shifts", ()
        if not self.app.is_admin:
            q, args = q + " WHERE cashier=?", (self.app.user,)
        with dbm.db() as c:
            for r in c.execute(q + " ORDER BY id DESC LIMIT 60", args):
                f = lambda v: "-" if v is None else f"{v:,.2f}"
                self.tree.insert("", "end", iid=str(r["id"]), values=(r["id"], r["cashier"], r["opened_at"].replace("T", " "), (r["closed_at"] or "-").replace("T", " "),
                                 f(r["opening_cash"]), f(r["expected_cash"]), f(r["counted_cash"]), f(r["difference"]), r["status"]))

    def open_z(self, ev=None):
        sel = self.tree.selection()
        if sel:
            self.show_text(f"Z-Report #{sel[0]}", svc.z_report_text(int(sel[0]), 42, self.app.cur, self.app.s.get("shop_name")))
