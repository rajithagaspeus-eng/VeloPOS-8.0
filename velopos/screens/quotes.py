from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import printing, services as svc
from ..theme import C
from . import Screen


class QuotesScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew")
        self.heading(top, "Quotations / Estimate Bills").pack(side="left")
        a.btn(top, "Delete", "red", self.delete, width=90).pack(side="right", padx=3)
        a.btn(top, "Convert to bill", "green", self.convert, width=150).pack(side="right", padx=3)
        a.btn(top, "View / Print", "accent", self.view, width=130).pack(side="right", padx=3)
        self.q = ctk.CTkEntry(self, width=320, placeholder_text="Search quotation no / customer / phone..."); self.q.grid(row=1, column=0, sticky="w", pady=6)
        self.q.bind("<KeyRelease>", lambda e: self.load())
        cols = ("Quotation", "Date", "Valid until", "Customer", "Phone", f"Total ({a.cur})", "Status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (160, 100, 100, 200, 120, 120, 100)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda e: self.view())
        ctk.CTkLabel(self, text="Create quotations from the Billing screen: add items, then press the blue 'Quote' button.", font=a.f(-2, "bold"), text_color=C["muted"]).grid(row=3, column=0, sticky="w", pady=4)
        self.load()

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in svc.list_quotes(self.q.get().strip()):
            self.tree.insert("", "end", iid=r["quote_no"], values=(r["quote_no"], r["date"], r["valid_until"], r["customer_name"], r["phone"], f"{r['total']:,.2f}", r["status"]))

    def selected(self):
        sel = self.tree.selection()
        return svc.load_quote(sel[0]) if sel else None

    def view(self):
        q = self.selected()
        if not q:
            return messagebox.showinfo("Select", "Select a quotation first.")
        a = self.app
        width = 32 if a.s.get("paper_size") == "58mm" else 42
        shop = {"name": a.s.get("shop_name")}
        self.show_text(q["quote_no"], svc.quote_text(q, shop, width, a.cur), on_print=lambda: printing.print_quote(a, q))

    def convert(self):
        q = self.selected()
        if not q:
            return messagebox.showinfo("Select", "Select a quotation first.")
        if q["status"] != "OPEN":
            return messagebox.showinfo("Quotation", f"This quotation is already {q['status']}.")
        if q["valid_until"] < datetime.now().strftime("%Y-%m-%d") and not messagebox.askyesno("Expired", "This quotation has expired. Convert anyway?"):
            return
        self.app.pending_cart = q["raw"]
        svc.set_quote_status(q["quote_no"], "CONVERTED", self.app.user)
        self.app.navigate("billing")

    def delete(self):
        q = self.selected()
        if q and self.app.require_admin() and messagebox.askyesno("Delete", f"Delete {q['quote_no']}?"):
            svc.delete_quote(q["quote_no"], self.app.user)
            self.load()
