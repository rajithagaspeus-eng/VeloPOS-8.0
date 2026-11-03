from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk

from .. import database as dbm, services as svc
from ..theme import C
from . import Screen


class CustomersScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew")
        self.heading(top, "Customer Credit Book & Loyalty").pack(side="left")
        self.lbl_due = ctk.CTkLabel(top, text="", font=a.f(3, "bold"), text_color=C["danger"]); self.lbl_due.pack(side="right", padx=10)

        f = a.card(self); f.grid(row=1, column=0, sticky="ew", pady=6)
        self.e_name = ctk.CTkEntry(f, width=200, placeholder_text="Customer name"); self.e_name.pack(side="left", padx=6, pady=10)
        self.e_phone = ctk.CTkEntry(f, width=170, placeholder_text="Phone / WhatsApp"); self.e_phone.pack(side="left", padx=6)
        a.btn(f, "Add customer", "green", self.add, width=130).pack(side="left", padx=6)
        a.btn(f, "Edit", "gray", self.edit, width=70).pack(side="left", padx=6)
        a.btn(f, "Delete", "red", self.delete, width=80).pack(side="left", padx=6)
        a.btn(f, "Settle credit", "accent", self.settle, width=130).pack(side="left", padx=6)
        self.use_limit, self.use_rem = a.s.bool("feat_credit_limit"), a.s.bool("feat_overdue_reminders")
        if self.use_limit:
            a.btn(f, "Set credit limit", "amber", self.set_limit, width=140).pack(side="left", padx=6)
        self.cb_over = None
        if self.use_rem:
            self.cb_over = ctk.CTkCheckBox(f, text="Overdue only", text_color=C["text"], command=self.load)
            self.cb_over.pack(side="left", padx=8)
            a.btn(f, "Remind via WhatsApp", "green", self.remind, width=170).pack(side="left", padx=6)

        split = ctk.CTkFrame(self, fg_color="transparent"); split.grid(row=2, column=0, sticky="nsew", pady=6)
        split.grid_rowconfigure(0, weight=1); split.grid_columnconfigure(0, weight=3); split.grid_columnconfigure(1, weight=2)
        cols = ("ID", "Name", "Phone", f"Due ({a.cur})", "Points") + (("Limit",) if self.use_limit else ()) + (("Overdue", "Days") if self.use_rem else ())
        self.tree = ttk.Treeview(split, columns=cols, show="headings")
        for c, w in zip(cols, (50, 200, 130, 110, 80, 90, 100, 60)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.ledger)
        lc = ("Date", "Description", "Type", f"Amount ({a.cur})")
        self.led = ttk.Treeview(split, columns=lc, show="headings")
        for c, w in zip(lc, (90, 150, 110, 100)):
            self.led.heading(c, text=c); self.led.column(c, width=w)
        self.led.grid(row=0, column=1, sticky="nsew")
        self.load()

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        with dbm.db() as c:
            tot = c.execute("SELECT COALESCE(SUM(credit_balance),0) FROM customers").fetchone()[0]
            rows = c.execute("SELECT * FROM customers ORDER BY credit_balance DESC").fetchall()
        od = {r["id"]: r for r in svc.overdue_customers(only_overdue=False)} if self.use_rem else {}
        only = self.use_rem and self.cb_over is not None and bool(self.cb_over.get())
        self.lbl_due.configure(text=f"Total credit due: {self.app.cur} {tot:,.2f}" + (f"   Overdue: {self.app.cur} {sum(r['overdue'] for r in od.values()):,.2f}" if self.use_rem else ""))
        for r in rows:
            o = od.get(r["id"])
            if only and not (o and o["overdue"] > 0.004):
                continue
            vals = [r["id"], r["name"], r["phone"] or "", f"{r['credit_balance']:.2f}", f"{r['loyalty_points']:.1f}"]
            if self.use_limit:
                vals.append(f"{r['credit_limit']:,.2f}" if (r["credit_limit"] or 0) > 0 else "no limit")
            if self.use_rem:
                vals += [f"{o['overdue']:,.2f}" if o else "0.00", o["oldest_days"] if o else 0]
            over_limit = self.use_limit and (r["credit_limit"] or 0) > 0 and r["credit_balance"] > r["credit_limit"] + 1e-9
            self.tree.insert("", "end", iid=str(r["id"]), values=vals, tags=("danger",) if (o and o["overdue"] > 0.004) or over_limit else ())

    def ledger(self, ev=None):
        for i in self.led.get_children():
            self.led.delete(i)
        sel = self.tree.selection()
        if not sel:
            return
        with dbm.db() as c:
            for r in c.execute("SELECT date, description, type, amount FROM credit_logs WHERE customer_id=? ORDER BY id DESC", (sel[0],)):
                self.led.insert("", "end", values=(r["date"], r["description"], r["type"], f"{r['amount']:.2f}"))

    def set_limit(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select", "Select a customer first.")
        if not self.app.require_admin():
            return
        v = self.tree.item(sel[0], "values")
        s = simpledialog.askstring("Credit limit", f"{v[1]}\nCredit limit ({self.app.cur}); 0 = no limit:")
        if s is None:
            return
        try:
            svc.set_credit_limit(int(sel[0]), s, self.app.user)
        except ValueError as ex:
            return messagebox.showerror("Invalid", str(ex))
        self.load()

    def remind(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select", "Select a customer first.")
        try:
            r = svc.create_reminder(int(sel[0]), self.app.user)
        except svc.ReminderCooldown as ex:
            if not messagebox.askyesno("Reminder", f"{ex}\n\nPrepare it anyway?"):
                return
            r = svc.create_reminder(int(sel[0]), self.app.user, force=True)
        except ValueError as ex:
            return messagebox.showinfo("Reminder", str(ex))
        svc.open_url(r["url"], self.app.s.get("whatsapp_mode") == "Desktop App")
        self.load()

    def add(self):
        n, p = self.e_name.get().strip(), self.e_phone.get().strip()
        if not n:
            return messagebox.showwarning("Required", "Enter the customer's name (phone number is optional).")
        try:
            svc.add_customer(n, p, self.app.user)
        except ValueError as ex:
            return messagebox.showerror("Customer", str(ex))
        self.e_name.delete(0, "end"); self.e_phone.delete(0, "end"); self.load()

    def edit(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select", "Select a customer first.")
        cid = int(sel[0])
        with dbm.db() as c:
            row = c.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
        if row is None:
            return self.load()
        name = simpledialog.askstring("Edit customer", "Name:", initialvalue=row["name"])
        if name is None:
            return
        phone = simpledialog.askstring("Edit customer", "Phone / WhatsApp:", initialvalue=row["phone"] or "")
        if phone is None:
            return
        addr = simpledialog.askstring("Edit customer", "Address (optional):", initialvalue=row["address"] or "")
        try:
            svc.update_customer(cid, name, phone, self.app.user, addr or "")
        except ValueError as ex:
            return messagebox.showerror("Customer", str(ex))
        self.load()

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select", "Select a customer first.")
        if not self.app.require_admin():
            return
        v = self.tree.item(sel[0], "values")
        if not messagebox.askyesno("Delete customer", f"Delete {v[1]}?\nTheir loyalty points and credit history are removed. Old bills keep the name."):
            return
        try:
            svc.delete_customer(int(sel[0]), self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("Customer", str(ex))
        self.led.delete(*self.led.get_children()); self.load()

    def settle(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select", "Select a customer first.")
        cid = sel[0]
        v = self.tree.item(cid, "values")
        due = float(v[3])
        if due <= 0:
            return messagebox.showinfo("No due", f"{v[1]} has no credit balance.")
        s = simpledialog.askstring("Settle credit", f"{v[1]}  due {self.app.cur} {due:.2f}\nAmount paid:", initialvalue=f"{due:.2f}")
        if s:
            shift = svc.current_shift(self.app.user) if self.app.s.bool("feat_shift") else None
            if self.app.s.bool("feat_shift") and not shift:
                return messagebox.showwarning("Shift", "Open your shift first so this cash is recorded in the drawer.")
            try:
                amt = svc.settle_credit(int(cid), s, self.app.user, shift["id"] if shift else None)
            except ValueError as ex:
                return messagebox.showerror("Invalid", str(ex))
            self.load(); self.ledger()
            messagebox.showinfo("Recorded", f"Payment of {self.app.cur} {amt:,.2f} recorded.")
