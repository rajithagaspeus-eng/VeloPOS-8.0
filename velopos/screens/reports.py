import csv
import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import database as dbm, printing, services as svc, theme
from ..theme import C
from . import Screen


class ReportsScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.rows = []
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(5, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew")
        self.heading(top, "Reports, Charts & Insights").pack(side="left")
        a.btn(top, "Export CSV", "green", self.export, width=110).pack(side="right", padx=3)
        a.btn(top, "Business insights", "purple", self.insights, width=150).pack(side="right", padx=3)

        fb = a.card(self); fb.grid(row=1, column=0, sticky="ew", pady=4)
        for lab, md in (("Today", "today"), ("This month", "month"), ("This year", "year"), ("All time", "all")):
            a.btn(fb, lab, "accent", lambda m=md: self.period(m), width=110, height=32).pack(side="left", padx=4, pady=8)
        a.btn(fb, "Search", "gray", self.load, width=80, height=32).pack(side="right", padx=6)
        self.e_to = ctk.CTkEntry(fb, width=105); self.e_to.pack(side="right", padx=3)
        ctk.CTkLabel(fb, text="To:", text_color=C["text"]).pack(side="right")
        self.e_from = ctk.CTkEntry(fb, width=105); self.e_from.pack(side="right", padx=3)
        ctk.CTkLabel(fb, text="From:", text_color=C["text"]).pack(side="right")

        self.cards = {}
        for r, (names, cols) in enumerate((((("bills", "Bills", "#475569"), ("revenue", "Net revenue", "#2563EB"), ("expenses", "Expenses", "#B45309"), ("profit", "Net profit", "#15803D")), 38),
                                          ((("Cash", "Cash", "#0F766E"), ("Card", "Card", "#334155"), ("QR", "QR", "#7C3AED"), ("Credit", "Credit", "#B91C1C")), 34))):
            fr = ctk.CTkFrame(self, fg_color="transparent"); fr.grid(row=2 + r, column=0, sticky="ew", pady=2); fr.grid_columnconfigure((0, 1, 2, 3), weight=1)
            for i, (k, lab, col) in enumerate(names):
                l = ctk.CTkLabel(fr, text=lab, font=a.f(0, "bold"), fg_color=col, text_color="white", corner_radius=8, height=cols)
                l.grid(row=0, column=i, padx=3, sticky="ew"); self.cards[k] = (l, lab)

        self.cv = tk.Canvas(self, height=130, highlightthickness=1, highlightbackground=a.accent)
        self.cv.grid(row=4, column=0, sticky="ew", pady=4)
        cols = ("Invoice", "Date", "Time", "Customer", f"Net ({a.cur})", "Method", f"Profit ({a.cur})", "Cashier", "Status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (150, 90, 80, 150, 110, 80, 100, 90, 70)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="center")
        theme.style_tree_tags(self.tree)
        self.tree.grid(row=5, column=0, sticky="nsew", pady=4)
        self.tree.bind("<Double-1>", self.detail)
        ctk.CTkLabel(self, text="Double-click an invoice to view, reprint or void it.", font=a.f(-3, "bold"), text_color=C["muted"]).grid(row=6, column=0)
        self.period("today")

    def period(self, m):
        now = datetime.now(); to = now.strftime("%Y-%m-%d")
        fr = {"today": to, "month": now.strftime("%Y-%m-01"), "year": now.strftime("%Y-01-01"), "all": "2000-01-01"}[m]
        self.e_from.delete(0, "end"); self.e_from.insert(0, fr); self.e_to.delete(0, "end"); self.e_to.insert(0, to)
        self.load()

    def load(self):
        a = self.app
        d = svc.report_data(self.e_from.get().strip(), self.e_to.get().strip())
        self.rows = d["rows"]
        vals = {"bills": f"Bills: {d['bills']}", "revenue": f"Net revenue: {a.cur} {d['revenue']:,.2f}", "expenses": f"Expenses: {a.cur} {d['expenses']:,.2f}",
                "profit": f"Net profit: {a.cur} {d['profit']:,.2f}"}
        if a.s.bool("feat_vat") or a.s.bool("feat_service_charge"):
            vals["revenue"] += f"  (incl. VAT {d['vat']:,.2f}" + (f", service {d['service']:,.2f}" if a.s.bool("feat_service_charge") else "") + ")"
        for m in ("Cash", "Card", "QR", "Credit"):
            vals[m] = f"{m}: {a.cur} {d['methods'].get(m, 0):,.2f}"
        for k, (lbl, _) in self.cards.items():
            lbl.configure(text=vals[k])
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in d["rows"]:
            self.tree.insert("", "end", iid=r["invoice_no"], tags=("danger",) if r["status"] != "OK" else (),
                             values=(r["invoice_no"], r["date"], r["time"], r["customer_name"], f"{r['total_amount']:,.2f}", r["payment_method"], f"{r['profit']:,.2f}", r["cashier"], r["status"]))
        self.chart(d)

    def chart(self, d):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#111A2E", "#F1F5F9") if dark else ("#FFFFFF", "#0F172A")
        cv = self.cv
        cv.delete("all"); cv.configure(bg=bg)
        cv.create_text(16, 14, text="INCOME vs EXPENSES vs PROFIT", anchor="w", fill=fg, font=("Segoe UI", 10, "bold"))
        cv.create_text(560, 14, text="PAYMENT CHANNELS", anchor="w", fill=fg, font=("Segoe UI", 10, "bold"))

        def bars(items, x0, y0, step, h, scale_w, lab_w):
            mx = max([abs(v) for _, v, _ in items] + [1.0])
            for i, (lab, v, col) in enumerate(items):
                y = y0 + i * step
                w = max(4, int(abs(v) / mx * scale_w))
                cv.create_text(x0, y + h / 2, text=lab, anchor="w", fill=fg, font=("Segoe UI", 9, "bold"))
                cv.create_rectangle(x0 + lab_w, y, x0 + lab_w + w, y + h, fill=col, outline="")
                cv.create_text(x0 + lab_w + w + 8, y + h / 2, text=f"{self.app.cur} {v:,.0f}", anchor="w", fill=fg, font=("Segoe UI", 9))
        bars([("Revenue", d["revenue"], "#3b82f6"), ("Expenses", d["expenses"], "#f97316"), ("Net profit", d["profit"], "#10b981" if d["profit"] >= 0 else "#ef4444")], 16, 30, 32, 20, 260, 90)
        bars([(m, d["methods"].get(m, 0), c) for m, c in (("Cash", "#14b8a6"), ("Card", "#6366f1"), ("QR", "#a855f7"), ("Credit", "#ef4444"))], 560, 28, 24, 16, 220, 70)

    # ------------------------------------------------------------- invoice detail / void / reprint
    def detail(self, ev=None):
        sel = self.tree.selection()
        if not sel:
            return
        a = self.app
        sale = svc.load_sale(sel[0])
        if not sale:
            return
        d = self.dialog(f"Invoice {sale['invoice']}", 700, 520)
        st = "" if sale["status"] == "OK" else "   [VOIDED]"
        ctk.CTkLabel(d, text=f"{sale['invoice']}{st}", font=a.f(4, "bold"), text_color=C["danger"] if st else C["text"]).pack(pady=(12, 2))
        ctk.CTkLabel(d, text=f"{sale['date']} {sale['time']}  |  {sale['customer']}  |  {sale['method']}  |  cashier {sale['cashier']}  |  net {a.cur} {sale['net']:,.2f}", font=a.f(-1), text_color=C["muted"]).pack()
        cols = ("Item", "Qty", "Price", "Total", "Serial / Warranty")
        tv = ttk.Treeview(d, columns=cols, show="headings", height=9)
        for c, w in zip(cols, (260, 60, 90, 100, 150)):
            tv.heading(c, text=c); tv.column(c, width=w)
        for n, q, p, l, s, w in sale["items"]:
            tv.insert("", "end", values=(n, f"{q:g}", f"{p:,.2f}", f"{l:,.2f}", f"{s} {w}".strip()))
        tv.pack(fill="both", expand=True, padx=14, pady=10)

        def reprint():
            width = 32 if a.s.get("paper_size") == "58mm" else 42
            shop = {"name": a.s.get("shop_name"), "address": a.s.get("address"), "phone": a.s.get("phone")}
            self.show_text(sale["invoice"], svc.receipt_text(sale, shop, width, a.cur),
                           on_print=lambda: printing.print_sale(a, sale, reprint=True))
            dbm.audit(a.user, "REPRINT", sale["invoice"])

        def void():
            if not a.require_admin():
                return
            from tkinter import simpledialog
            reason = simpledialog.askstring("Void bill", "Reason for voiding (required):", parent=d)
            if not reason:
                return
            try:
                svc.void_sale(sale["invoice"], a.user, reason)
            except ValueError as ex:
                return messagebox.showwarning("Cannot void", str(ex), parent=d)
            d.destroy(); self.load()
            messagebox.showinfo("Voided", "Bill voided. Stock, credit and points were restored.")
        row = ctk.CTkFrame(d, fg_color="transparent"); row.pack(pady=10)
        a.btn(row, "Reprint receipt", "accent", reprint, width=150).pack(side="left", padx=5)
        if sale["status"] == "OK" and a.is_admin:
            a.btn(row, "Void bill (Admin)", "red", void, width=170).pack(side="left", padx=5)
        a.btn(row, "Close", "gray", d.destroy, width=100).pack(side="left", padx=5)

    def insights(self):
        a = self.app
        top, low, dead = svc.insights()
        out = ["TOP 5 PRODUCTS (by revenue)"]
        out += [f"  {i}. {r['item_name']} - {r['q']:g} sold - {a.cur} {r['t']:,.2f}" for i, r in enumerate(top, 1)] or ["  no sales yet"]
        out += ["", f"REORDER NOW (stock <= {svc.low_stock_level():g})"]
        out += [f"  [{r['barcode']}] {r['name_en']} - {r['stock_qty']:g} left" for r in low] or ["  all stock is healthy"]
        out += ["", "DEAD STOCK (never sold)"]
        out += [f"  [{r['barcode']}] {r['name_en']} - {r['stock_qty']:g} units @ {a.cur} {r['selling_price']:,.2f}" for r in dead] or ["  none"]
        self.show_text("Business insights", "\n".join(out))

    def export(self):
        if not self.rows:
            return
        fn = dbm.p("Exports", f"Report_{datetime.now():%Y%m%d_%H%M%S}.csv")
        with open(fn, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Invoice", "Date", "Time", "Customer", "Net", "Method", "Profit", "Cashier", "Status"])
            w.writerows([tuple(svc.csv_safe(x) for x in r) for r in self.rows])
        messagebox.showinfo("Exported", f"Saved:\n{fn}")
