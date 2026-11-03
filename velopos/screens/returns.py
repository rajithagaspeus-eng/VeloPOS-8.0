from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk

from .. import database as dbm, services as svc
from ..theme import C
from . import Screen


class ReturnsScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.inv, self.qty = None, {}
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(3, weight=1)
        self.heading(self, "Sales Return & Refund").grid(row=0, column=0, sticky="w")
        bar = a.card(self); bar.grid(row=1, column=0, sticky="ew", pady=6)
        self.e = ctk.CTkEntry(bar, width=340, height=38, placeholder_text="Invoice number (or last digits) / customer name"); self.e.pack(side="left", padx=10, pady=10)
        self.e.bind("<Return>", lambda ev: self.find())
        a.btn(bar, "Find", "accent", self.find, width=90).pack(side="left", padx=4)
        cols = ("Invoice", "Date", "Customer", "Net", "Method")
        self.found = ttk.Treeview(self, columns=cols, show="headings", height=4)
        for c, w in zip(cols, (180, 100, 200, 110, 90)):
            self.found.heading(c, text=c); self.found.column(c, width=w)
        self.found.grid(row=2, column=0, sticky="ew", pady=4)
        self.found.bind("<<TreeviewSelect>>", self.pick)

        ic = ("ID", "Item", "Sold", "Returned", "Returnable", "Price", "Return qty")
        self.items = ttk.Treeview(self, columns=ic, show="headings")
        for c, w in zip(ic, (50, 300, 70, 80, 90, 100, 100)):
            self.items.heading(c, text=c); self.items.column(c, width=w, anchor="center")
        self.items.grid(row=3, column=0, sticky="nsew", pady=4)
        self.items.bind("<Double-1>", self.ask_qty)
        ctk.CTkLabel(self, text="Double-click an item row to set the return quantity.", font=a.f(-2, "bold"), text_color=C["muted"]).grid(row=4, column=0, sticky="w")

        f = a.card(self); f.grid(row=5, column=0, sticky="ew", pady=6)
        self.method = ctk.CTkOptionMenu(f, values=["Cash", "Credit Book", "Card/QR (manual)"], width=180); self.method.pack(side="left", padx=10, pady=10)
        self.reason = ctk.CTkEntry(f, width=300, placeholder_text="Reason (required)"); self.reason.pack(side="left", padx=6)
        self.lbl = ctk.CTkLabel(f, text="", font=a.f(2, "bold"), text_color=C["warning"]); self.lbl.pack(side="left", padx=14)
        a.btn(f, "PROCESS RETURN", "red", self.process, width=190, height=40).pack(side="right", padx=10)
        self.find()

    def find(self):
        for i in self.found.get_children():
            self.found.delete(i)
        q = f"%{self.e.get().strip()}%"
        with dbm.db() as c:
            for r in c.execute("SELECT invoice_no,date,customer_name,total_amount,payment_method FROM sales WHERE status='OK' AND "
                               "(invoice_no LIKE ? OR customer_name LIKE ?) ORDER BY id DESC LIMIT 30", (q, q)):
                self.found.insert("", "end", iid=r["invoice_no"], values=(r["invoice_no"], r["date"], r["customer_name"], f"{r['total_amount']:,.2f}", r["payment_method"]))

    def pick(self, ev=None):
        sel = self.found.selection()
        if sel:
            self.inv, self.qty = sel[0], {}
            self.fill()

    def fill(self):
        for i in self.items.get_children():
            self.items.delete(i)
        for iid, b, name, sold, done, price in svc.returnable_items(self.inv):
            self.items.insert("", "end", iid=str(iid), values=(iid, name, f"{sold:g}", f"{done:g}", f"{sold - done:g}", f"{price:,.2f}", f"{self.qty.get(iid, 0):g}"))
        g = sum(self.qty.get(i[0], 0) * i[5] for i in svc.returnable_items(self.inv))
        self.lbl.configure(text=f"Approx. refund: {self.app.cur} {g:,.2f} (before bill discount)")

    def ask_qty(self, ev=None):
        sel = self.items.selection()
        if not sel:
            return
        iid = int(sel[0])
        v = self.items.item(sel[0], "values")
        s = simpledialog.askstring("Return quantity", f"{v[1]}\nReturnable: {v[4]}\nQuantity to return:", initialvalue=v[4])
        if s is None:
            return
        try:
            q = svc.num(s)
            if q < 0 or q > float(v[4]) + 1e-9:
                raise ValueError
        except ValueError:
            return messagebox.showwarning("Invalid", f"Enter a number between 0 and {v[4]}.")
        self.qty[iid] = q
        self.fill()

    def process(self):
        a = self.app
        if not self.inv:
            return messagebox.showwarning("Select", "Find and select an invoice first.")
        shift = svc.current_shift(a.user)
        if self.method.get() == "Cash" and a.s.bool("feat_shift") and not shift:
            return messagebox.showwarning("Shift", "Open your shift first so the cash refund is recorded in the drawer.")
        try:
            r = svc.create_return(self.inv, list(self.qty.items()), self.method.get(), self.reason.get(), a.user, shift["id"] if shift else None)
        except ValueError as ex:
            return messagebox.showwarning("Cannot process", str(ex))
        except Exception as ex:
            return messagebox.showerror("Error", f"Nothing was changed:\n{ex}")
        split = (f"\nTaken off the customer's credit due: {a.cur} {r['credit_offset']:,.2f}\nPaid back in cash: {a.cur} {r['cash_out']:,.2f}"
                 if r["method"] == "Cash" and r["credit_offset"] > 0 else "")
        note = (f"CREDIT NOTE {r['return_no']}\nInvoice: {self.inv}\nRefund: {a.cur} {r['amount']:,.2f} ({r['method']}){split}\nReason: {self.reason.get().strip()}\nBy: {a.user}")
        self.inv, self.qty = None, {}
        self.reason.delete(0, "end"); self.fill_empty(); self.find()
        self.show_text(r["return_no"], note)

    def fill_empty(self):
        for i in self.items.get_children():
            self.items.delete(i)
        self.lbl.configure(text="")
