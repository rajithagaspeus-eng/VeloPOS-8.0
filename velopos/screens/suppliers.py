"""Suppliers, purchases (GRN) and supplier payables. UI only - the logic is in services.py (create_purchase, pay_supplier, ...)."""
from datetime import date
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import database as dbm, printing, services as svc, theme
from ..theme import C
from . import Screen


def _tree(parent, cols, widths, height=10):
    t = ttk.Treeview(parent, columns=[c for c, _ in cols], show="headings", height=height)
    for (c, title), w in zip(cols, widths):
        t.heading(c, text=title)
        t.column(c, width=w, anchor="w" if w >= 150 else "center")
    theme.style_tree_tags(t)
    return t


def _drawer_shift(app, method, amount):
    """Shift id when a CASH payment should leave the drawer; None when it should not (after asking). 'cancel' aborts."""
    if method != "Cash" or amount <= 0 or not app.s.bool("feat_shift"):
        return None
    sh = svc.current_shift(app.user)
    if sh:
        return sh["id"]
    return None if messagebox.askyesno("No shift open", "No shift is open, so this cash payment will NOT be recorded in the cash drawer.\nContinue anyway?") else "cancel"


class SuppliersScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self.heading(self, "Suppliers & Purchases").grid(row=0, column=0, sticky="w", pady=(4, 6))
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.grid(row=1, column=0, sticky="ew")
        self.frames = {}
        for key, label in (("sup", "Suppliers"), ("grn", "Purchases (GRN)"), ("pay", "Payables")):
            a.btn(bar, label, "accent", lambda k=key: self.show(k), width=160, height=34).pack(side="left", padx=4)
            fr = ctk.CTkFrame(self, fg_color="transparent"); fr.grid(row=2, column=0, sticky="nsew")
            self.frames[key] = fr
        self.sid = None
        self.build_sup(self.frames["sup"]); self.build_grn(self.frames["grn"]); self.build_pay(self.frames["pay"])
        self.show("sup")

    def show(self, key):
        for k, fr in self.frames.items():
            fr.grid() if k == key else fr.grid_remove()
        {"sup": self.load_sup, "grn": self.load_grn, "pay": self.load_pay}[key]()

    # ================================================================== suppliers
    def build_sup(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(1, weight=1)
        f = a.card(fr); f.grid(row=0, column=0, sticky="ew", pady=6)
        self.s = {}
        for i, (k, ph, w) in enumerate((("name", "Supplier name", 190), ("contact", "Contact person", 150), ("phone", "Phone", 120), ("whatsapp", "WhatsApp", 120),
                                        ("address", "Address", 200), ("notes", "Notes", 160))):
            self.s[k] = ctk.CTkEntry(f, width=w, placeholder_text=ph); self.s[k].grid(row=0, column=i, padx=4, pady=10)
        self.cb_active = ctk.CTkCheckBox(f, text="Active", text_color=C["text"]); self.cb_active.grid(row=0, column=6, padx=6); self.cb_active.select()
        a.btn(f, "Save", "green", self.save_sup, width=90, height=32).grid(row=0, column=7, padx=4)
        a.btn(f, "New", "gray", self.clear_sup, width=70, height=32).grid(row=0, column=8, padx=4)
        cols = [("n", "Supplier"), ("c", "Contact"), ("p", "Phone"), ("w", "WhatsApp"), ("a", "Active")]
        self.t_sup = _tree(fr, cols, [220, 160, 130, 130, 70], 14)
        self.t_sup.grid(row=1, column=0, sticky="nsew", pady=6)
        self.t_sup.bind("<<TreeviewSelect>>", self.pick_sup)

    def load_sup(self):
        for i in self.t_sup.get_children():
            self.t_sup.delete(i)
        for r in svc.list_suppliers():
            self.t_sup.insert("", "end", iid=str(r["id"]), values=(r["name"], r["contact"], r["phone"], r["whatsapp"], "yes" if r["active"] else "no"))

    def clear_sup(self):
        self.sid = None
        for e in self.s.values():
            e.delete(0, "end")
        self.cb_active.select()

    def pick_sup(self, ev=None):
        sel = self.t_sup.selection()
        r = svc.get_supplier(int(sel[0])) if sel else None
        if r is None:
            return
        self.clear_sup()
        self.sid = r["id"]
        for k, e in self.s.items():
            e.insert(0, r[k] or "")
        self.cb_active.select() if r["active"] else self.cb_active.deselect()

    def save_sup(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to edit suppliers.")
        v = {k: e.get().strip() for k, e in self.s.items()}
        try:
            if self.sid:
                svc.update_supplier(self.sid, self.app.user, v["name"], v["contact"], v["phone"], v["whatsapp"], v["address"], v["notes"], bool(self.cb_active.get()))
            else:
                svc.add_supplier(v["name"], self.app.user, v["contact"], v["phone"], v["whatsapp"], v["address"], v["notes"])
        except ValueError as ex:
            return messagebox.showwarning("Supplier", str(ex))
        self.clear_sup(); self.load_sup()

    # ================================================================== purchases (GRN)
    def build_grn(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(fr, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew", pady=6)
        a.btn(top, "New GRN...", "green", self.new_grn, width=130, height=32).pack(side="left", padx=3)
        a.btn(top, "Open / Print", "accent", self.open_grn_doc, width=120, height=32).pack(side="left", padx=3)
        a.btn(top, "Void (Admin)", "red", self.void_grn, width=120, height=32).pack(side="left", padx=3)
        cols = [("g", "GRN"), ("d", "Date"), ("s", "Supplier"), ("i", "Supplier invoice"), ("t", "Total"), ("p", "Paid"), ("st", "Status")]
        self.t_grn = _tree(fr, cols, [150, 100, 200, 140, 100, 100, 80], 14)
        self.t_grn.grid(row=1, column=0, sticky="nsew")

    def load_grn(self):
        for i in self.t_grn.get_children():
            self.t_grn.delete(i)
        for r in svc.list_purchases():
            self.t_grn.insert("", "end", iid=str(r["id"]), values=(r["grn_no"], r["date"], r["supplier"], r["supplier_invoice"], f"{r['total']:,.2f}", f"{r['paid_total']:,.2f}", r["status"]),
                              tags=("danger",) if r["status"] != "OK" else ())

    def _sel_grn(self):
        sel = self.t_grn.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a purchase first.")
            return None
        return int(sel[0])

    def new_grn(self):
        open_grn_dialog(self.app, self.load_grn)

    def open_grn_doc(self):
        pid = self._sel_grn()
        g = svc.get_purchase(pid) if pid else None
        if g:
            printing.open_html(dbm.settings, printing.grn_doc(dbm.settings, g), "A4", g["header"]["grn_no"])

    def void_grn(self):
        pid = self._sel_grn()
        if not pid or not self.app.require_admin():
            return
        from tkinter import simpledialog
        why = simpledialog.askstring("Void purchase", "Reason for voiding this GRN:")
        if not why:
            return
        try:
            svc.void_purchase(pid, self.app.user, why)
        except ValueError as ex:
            return messagebox.showwarning("Cannot void", str(ex))
        self.load_grn()

    # ================================================================== payables
    def build_pay(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(fr, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew", pady=6)
        a.btn(top, "Pay supplier...", "green", self.pay_dialog, width=140, height=32).pack(side="left", padx=3)
        a.btn(top, "Payment history", "accent", self.history, width=140, height=32).pack(side="left", padx=3)
        self.lbl_pay = ctk.CTkLabel(top, text="", font=a.f(2, "bold"), text_color=C["danger"]); self.lbl_pay.pack(side="left", padx=14)
        ctk.CTkLabel(fr, text="Ageing = how old the UNPAID purchases are (payments settle the oldest purchases first).", font=a.f(-2), text_color=C["muted"]).grid(row=1, column=0, sticky="w")
        cols = [("n", "Supplier"), ("0", "0-30 days"), ("1", "31-60"), ("2", "61-90"), ("3", "90+"), ("b", "Total owed")]
        self.t_pay = _tree(fr, cols, [240, 110, 110, 110, 110, 120], 14)
        self.t_pay.grid(row=2, column=0, sticky="nsew", pady=6)

    def load_pay(self):
        for i in self.t_pay.get_children():
            self.t_pay.delete(i)
        if not self.app.can("reports"):
            self.lbl_pay.configure(text="Totals need the 'View reports' permission.")
            return
        rows, tot = svc.payables_ageing()
        self.lbl_pay.configure(text=f"Total owed to suppliers: {self.app.cur} {tot['balance']:,.2f}")
        for r in rows:
            self.t_pay.insert("", "end", iid=str(r["id"]), values=(r["name"], f"{r['b0']:,.2f}", f"{r['b1']:,.2f}", f"{r['b2']:,.2f}", f"{r['b3']:,.2f}", f"{r['balance']:,.2f}"),
                              tags=("danger",) if r["b3"] > 0 else ())

    def _sel_supplier(self):
        sel = self.t_pay.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a supplier in the list first.")
            return None
        return int(sel[0])

    def pay_dialog(self):
        sid = self._sel_supplier()
        if not sid or not self.app.can("reports"):
            return
        sup = svc.get_supplier(sid)
        bal = next((r["balance"] for r in svc.supplier_balances() if r["id"] == sid), 0.0)
        d = ctk.CTkToplevel(self); d.title("Pay supplier"); d.geometry("420x380"); d.configure(fg_color=C["bg"]); d.transient(self.winfo_toplevel())
        d.after(120, lambda: (d.grab_set(), d.lift()))
        ctk.CTkLabel(d, text=f"{sup['name']}\nOwed: {self.app.cur} {bal:,.2f}", font=self.app.f(3, "bold"), text_color=C["text"]).pack(pady=12)
        e_amt = ctk.CTkEntry(d, width=240, placeholder_text="Amount"); e_amt.pack(pady=4); e_amt.insert(0, f"{max(bal, 0):.2f}")
        m = ctk.CTkOptionMenu(d, values=["Cash", "Bank", "Cheque"], width=240); m.pack(pady=4); m.set("Cash")
        e_ref = ctk.CTkEntry(d, width=240, placeholder_text="Reference / cheque no"); e_ref.pack(pady=4)
        e_note = ctk.CTkEntry(d, width=240, placeholder_text="Note"); e_note.pack(pady=4)

        def go():
            try:
                amt = svc.num(e_amt.get())
                shift = _drawer_shift(self.app, m.get(), amt)
                if shift == "cancel":
                    return
                left = svc.pay_supplier(sid, amt, m.get(), self.app.user, e_ref.get().strip(), e_note.get().strip(), shift)
            except ValueError as ex:
                return messagebox.showwarning("Payment", "Enter a valid amount." if "could not convert" in str(ex) else str(ex), parent=d)
            messagebox.showinfo("Recorded", f"Payment recorded. Balance now {self.app.cur} {left:,.2f}", parent=d)
            d.destroy(); self.load_pay()
        self.app.btn(d, "RECORD PAYMENT", "green", go, width=200, height=40).pack(pady=14)

    def history(self):
        sid = self._sel_supplier()
        if not sid:
            return
        d = ctk.CTkToplevel(self); d.title("Supplier payments"); d.geometry("700x420"); d.configure(fg_color=C["bg"]); d.transient(self.winfo_toplevel())
        t = _tree(d, [("d", "Date"), ("a", "Amount"), ("m", "Method"), ("r", "Reference"), ("n", "Note"), ("u", "User")], [100, 100, 90, 140, 160, 80], 14)
        t.pack(fill="both", expand=True, padx=12, pady=12)
        for p in svc.list_supplier_payments(sid):
            t.insert("", "end", values=(p["date"], f"{p['amount']:,.2f}", p["method"], p["ref"], p["note"], p["user"]))


# ====================================================================== New GRN dialog
def open_grn_dialog(app, on_done=None):
    a = app
    if not (a.can("stock") and a.can("see_cost")):
        return messagebox.showwarning("Not allowed", "Receiving goods needs the 'edit inventory' and 'see cost' permissions.")
    sups = svc.list_suppliers(True)
    if not sups:
        return messagebox.showinfo("Suppliers", "Add a supplier first (Suppliers tab).")
    d = ctk.CTkToplevel(a); d.title("New GRN - goods received"); d.geometry("1000x720"); d.configure(fg_color=C["bg"]); d.transient(a)
    d.after(120, lambda: (d.grab_set(), d.lift()))
    names = {s["name"]: s["id"] for s in sups}
    lines, cur = [], {"p": None}
    units_on, batches_on = a.s.bool("feat_multi_unit"), a.s.bool("feat_batches")
    head = a.card(d); head.pack(fill="x", padx=14, pady=8)
    m_sup = ctk.CTkOptionMenu(head, values=list(names), width=220); m_sup.grid(row=0, column=0, padx=8, pady=8)
    m_sup.set(list(names)[0])
    e_inv = ctk.CTkEntry(head, width=170, placeholder_text="Supplier invoice no"); e_inv.grid(row=0, column=1, padx=6)
    e_date = ctk.CTkEntry(head, width=120); e_date.grid(row=0, column=2, padx=6); e_date.insert(0, date.today().isoformat())
    e_note = ctk.CTkEntry(head, width=240, placeholder_text="Note"); e_note.grid(row=0, column=3, padx=6)
    ln = a.card(d); ln.pack(fill="x", padx=14, pady=4)
    e_bar = ctk.CTkEntry(ln, width=170, placeholder_text="Barcode / item name"); e_bar.grid(row=0, column=0, padx=6, pady=8)
    lbl_item = ctk.CTkLabel(ln, text="", text_color=C["muted"], width=200, anchor="w"); lbl_item.grid(row=0, column=1, padx=4)
    e_qty = ctk.CTkEntry(ln, width=80, placeholder_text="Qty"); e_qty.grid(row=0, column=2, padx=4)
    m_unit = ctk.CTkOptionMenu(ln, values=["-"], width=90, command=lambda v: fill_cost()); m_unit.grid(row=0, column=3, padx=4)
    e_cost = ctk.CTkEntry(ln, width=100, placeholder_text="Cost / unit"); e_cost.grid(row=0, column=4, padx=4)
    e_batch = ctk.CTkEntry(ln, width=110, placeholder_text="Batch no"); e_exp = ctk.CTkEntry(ln, width=130, placeholder_text="Expiry YYYY-MM-DD")
    if batches_on:
        e_batch.grid(row=0, column=5, padx=4)
    e_exp.grid(row=0, column=6, padx=4)
    units = {}

    def fill_cost():
        p = cur["p"]
        if p is None:
            return
        f = units.get(m_unit.get(), 1.0)
        e_cost.delete(0, "end"); e_cost.insert(0, f"{(p['cost_price'] or 0) * f:.2f}")

    def lookup(ev=None):
        q = e_bar.get().strip()
        p = svc.get_product(q) if q else None
        if p is None and q:
            f = svc.search_products(q, 1)
            p = f[0] if f else None
        cur["p"] = p
        if p is None:
            lbl_item.configure(text="Item not found", text_color=C["danger"])
            return
        e_bar.delete(0, "end"); e_bar.insert(0, p["barcode"])
        lbl_item.configure(text=p["name_en"][:30], text_color=C["text"])
        units.clear()
        if units_on:
            for u in svc.list_units(p["barcode"]):
                units[u["name"]] = u["factor"]
        m_unit.configure(values=list(units) or ["-"]); m_unit.set(next(iter(units), "-"))
        if not e_cost.get().strip():                      # never overwrite a cost the user already typed
            fill_cost()
        e_qty.focus_set()
    e_bar.bind("<Return>", lookup)
    tree = _tree(d, [("i", "Item"), ("q", "Qty"), ("u", "Unit"), ("c", "Cost"), ("t", "Total"), ("b", "Batch"), ("e", "Expiry")], [260, 80, 80, 100, 110, 110, 120], 9)
    tree.pack(fill="both", expand=True, padx=14, pady=6)
    lbl_tot = ctk.CTkLabel(d, text="", font=a.f(3, "bold"), text_color=C["success"]); lbl_tot.pack()

    def refresh():
        for i in tree.get_children():
            tree.delete(i)
        for k, x in enumerate(lines):
            tree.insert("", "end", iid=str(k), values=(x["name"], f"{x['qty']:g}", x["unit"], f"{x['cost']:,.2f}", f"{x['qty'] * x['cost']:,.2f}", x["batch_no"], x["expiry"]))
        lbl_tot.configure(text=f"Lines: {len(lines)}    Sub total: {a.cur} {sum(x['qty'] * x['cost'] for x in lines):,.2f}")

    def add_line():
        lookup()
        p = cur["p"]
        if p is None:
            return
        try:
            qty, cost = svc.num(e_qty.get()), svc.num(e_cost.get())
            if qty <= 0 or cost < 0:
                raise ValueError
        except ValueError:
            return messagebox.showwarning("Line", "Enter a quantity greater than zero and a cost.", parent=d)
        u = m_unit.get() if units and m_unit.get() != "-" and units.get(m_unit.get(), 1.0) != 1.0 else ""
        lines.append(dict(barcode=p["barcode"], name=p["name_en"], qty=qty, unit=u, cost=cost, batch_no=e_batch.get().strip(), expiry=e_exp.get().strip()))
        for e in (e_bar, e_qty, e_cost, e_batch, e_exp):
            e.delete(0, "end")
        cur["p"] = None; lbl_item.configure(text=""); refresh(); e_bar.focus_set()

    def remove_line():
        sel = tree.selection()
        if sel:
            del lines[int(sel[0])]
            refresh()
    a.btn(ln, "Add line", "green", add_line, width=90, height=30).grid(row=0, column=7, padx=6)
    a.btn(ln, "Remove selected", "gray", remove_line, width=130, height=30).grid(row=0, column=8, padx=4)
    pay = a.card(d); pay.pack(fill="x", padx=14, pady=6)
    e_disc = ctk.CTkEntry(pay, width=110, placeholder_text="Discount"); e_disc.grid(row=0, column=0, padx=8, pady=8)
    e_paid = ctk.CTkEntry(pay, width=130, placeholder_text="Paid now"); e_paid.grid(row=0, column=1, padx=6)
    m_pay = ctk.CTkOptionMenu(pay, values=["Cash", "Bank", "Cheque"], width=110); m_pay.grid(row=0, column=2, padx=6); m_pay.set("Cash")
    e_ref = ctk.CTkEntry(pay, width=170, placeholder_text="Payment reference"); e_ref.grid(row=0, column=3, padx=6)

    def save():
        try:
            disc, paid = svc.num(e_disc.get() or 0), svc.num(e_paid.get() or 0)
        except ValueError:
            return messagebox.showwarning("Check", "Discount and payment must be numbers.", parent=d)
        shift = _drawer_shift(a, m_pay.get(), paid)
        if shift == "cancel":
            return
        try:
            res = svc.create_purchase(names[m_sup.get()], [dict(barcode=x["barcode"], qty=x["qty"], cost=x["cost"], unit=x["unit"], batch_no=x["batch_no"], expiry=x["expiry"]) for x in lines],
                                      a.user, e_inv.get().strip(), e_date.get().strip(), disc, paid, m_pay.get(), e_ref.get().strip(), e_note.get().strip(), shift)
        except ValueError as ex:
            return messagebox.showwarning("GRN", "Check the date (YYYY-MM-DD) and the numbers." if "does not match format" in str(ex) else str(ex), parent=d)
        d.destroy()
        if on_done:
            on_done()
        if messagebox.askyesno("GRN saved", f"{res['grn_no']} saved. Total {a.cur} {res['total']:,.2f}, still owed {a.cur} {res['due']:,.2f}.\n\nOpen the printable GRN?"):
            printing.open_html(dbm.settings, printing.grn_doc(dbm.settings, svc.get_purchase(res["purchase_id"])), "A4", res["grn_no"])
    a.btn(pay, "SAVE GRN", "green", save, width=150, height=38).grid(row=0, column=4, padx=14)
    a.btn(pay, "Cancel", "gray", d.destroy, width=100, height=38).grid(row=0, column=5, padx=4)
    refresh()
    return d
