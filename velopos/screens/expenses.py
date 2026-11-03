from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import database as dbm, services as svc
from ..theme import C
from . import Screen


class ExpensesScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self.heading(self, "Shop Expenses & Petty Cash").grid(row=0, column=0, sticky="w")
        f = a.card(self); f.grid(row=1, column=0, sticky="ew", pady=6)
        self.cat = ctk.CTkOptionMenu(f, values=["Supplier Payment", "Electricity / Water", "Rent", "Salary", "Transport", "Staff Tea/Food", "Maintenance", "Other"], width=170); self.cat.pack(side="left", padx=6, pady=10)
        self.desc = ctk.CTkEntry(f, width=260, placeholder_text="Description"); self.desc.pack(side="left", padx=6)
        self.amt = ctk.CTkEntry(f, width=130, placeholder_text=f"Amount ({a.cur})"); self.amt.pack(side="left", padx=6)
        self.drawer = ctk.CTkCheckBox(f, text="Paid from cash drawer", text_color=C["text"]); self.drawer.pack(side="left", padx=8)
        if a.s.bool("feat_shift"):
            self.drawer.select()
        else:
            self.drawer.pack_forget()
        a.btn(f, "Add", "amber", self.add, width=80).pack(side="left", padx=6)
        a.btn(f, "Delete selected", "red", self.delete, width=130).pack(side="right", padx=6)
        cols = ("ID", "Date", "Category", "Description", f"Amount ({a.cur})", "Added by")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (50, 100, 160, 300, 110, 100)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w)
        self.tree.grid(row=2, column=0, sticky="nsew", pady=8)
        self.load()

    def add(self):
        a = self.app
        use_drawer = a.s.bool("feat_shift") and bool(self.drawer.get())
        shift = svc.current_shift(a.user) if use_drawer else None
        if use_drawer and not shift:
            return messagebox.showwarning("Shift", "Open your shift first, or untick 'Paid from cash drawer'.")
        try:                                  # expense + drawer cash-out + audit are ONE transaction inside the service
            svc.add_expense(self.cat.get(), self.desc.get(), self.amt.get(), a.user, shift["id"] if shift else None)
        except ValueError as ex:
            return messagebox.showwarning("Expense", str(ex))
        self.desc.delete(0, "end"); self.amt.delete(0, "end"); self.load()

    def delete(self):
        sel = self.tree.selection()
        if not sel or not self.app.require_admin():
            return
        if not messagebox.askyesno("Delete expense", "Delete the selected expense?\n(If it was paid from a cash drawer that is still open, the cash is put back.)"):
            return
        try:
            svc.delete_expense(int(sel[0]), self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("Expense", str(ex))
        self.load()

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        with dbm.db() as c:
            for r in c.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 500"):
                self.tree.insert("", "end", iid=str(r["id"]), values=(r["id"], r["date"], r["category"], r["description"], f"{r['amount']:,.2f}", r["added_by"]))
