import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import database as dbm, printing, services as svc, theme
from ..theme import C
from . import Screen
from .itemgrid import ItemGrid


class BillingScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.cart = []
        self._rows = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        a = app

        top = ctk.CTkFrame(self, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.heading(top, "Cashier Billing Desk").pack(side="left")
        a.btn(top, "Clear", "red", self.clear_cart, width=70).pack(side="right", padx=3)
        a.btn(top, "Quote", "blue", self.make_quote, width=70).pack(side="right", padx=3)
        if a.s.bool("feat_cash_drawer"):
            a.btn(top, "Open drawer", "gray", lambda: printing.open_drawer(a), width=110).pack(side="right", padx=3)
        a.btn(top, "Item grid: ON" if a.s.bool("feat_item_grid") else "Item grid: OFF", "teal" if a.s.bool("feat_item_grid") else "gray",
              self.toggle_grid, width=120).pack(side="right", padx=3)
        a.btn(top, "Remove", "amber", self.remove_row, width=80).pack(side="right", padx=3)
        a.btn(top, f"Recall ({len(a.held)})", "teal", self.recall, width=100).pack(side="right", padx=3)
        a.btn(top, "Hold (F4)", "purple", self.hold, width=90).pack(side="right", padx=3)
        a.btn(top, "Edit (F2)", "accent", self.edit_row, width=90).pack(side="right", padx=3)
        if a.s.bool("feat_wholesale"):
            a.btn(top, "WHOLESALE" if a.wholesale else "RETAIL", "amber" if a.wholesale else "green",
                  self.toggle_wholesale, width=110).pack(side="right", padx=8)

        bar = a.card(self); bar.grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(bar, text="Scan barcode / search item:", font=a.f(1, "bold"), text_color=C["text"]).pack(side="left", padx=12, pady=10)
        self.entry = ctk.CTkEntry(bar, width=460, height=40, font=a.f(1), placeholder_text="Scan, or type name / first letters...")
        self.entry.pack(side="left", padx=6, pady=10)
        self.entry.bind("<KeyRelease>", self.on_key)
        self.entry.bind("<Return>", self.on_enter)
        self.entry.bind("<Down>", lambda e: self._focus_results())
        self.entry.bind("<Escape>", lambda e: self.hide_results())

        self.res_frame = a.card(self)
        self.res = ttk.Treeview(self.res_frame, columns=("b", "n", "p", "s"), show="headings", height=5)
        for c, t, w in (("b", "Barcode", 110), ("n", "Item", 380), ("p", "Price", 100), ("s", "Stock", 80)):
            self.res.heading(c, text=t); self.res.column(c, width=w)
        theme.style_tree_tags(self.res)
        self.res.pack(fill="x", padx=4, pady=4)
        self.res.bind("<Double-1>", lambda e: self.add_selected_result())
        self.res.bind("<Return>", lambda e: self.add_selected_result())

        cols = ("Barcode", "Item", f"Price ({a.cur})", "Qty", f"Total ({a.cur})", "Serial / Warranty")
        mid = ctk.CTkFrame(self, fg_color="transparent"); mid.grid(row=3, column=0, sticky="nsew", pady=6)
        mid.grid_rowconfigure(0, weight=1); mid.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(mid, columns=cols, show="headings")
        for c, w, an in zip(cols, (110, 380, 110, 70, 120, 170), ("center", "w", "e", "center", "e", "center")):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor=an)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda e: self.edit_row())
        self.item_grid = None
        if a.s.bool("feat_item_grid"):
            self.item_grid = ItemGrid(mid, a, self.add_from_grid, self.price_of, self.pname)
            self.item_grid.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        bot = a.card(self); bot.grid(row=4, column=0, sticky="ew", pady=4)
        self.lbl_count = ctk.CTkLabel(bot, text="Items: 0", font=a.f(4, "bold"), text_color=C["text"]); self.lbl_count.pack(side="left", padx=24, pady=14)
        self.lbl_total = ctk.CTkLabel(bot, text=f"Total: {a.cur} 0.00", font=a.f(14, "bold"), text_color=C["success"]); self.lbl_total.pack(side="left", padx=30)
        a.btn(bot, f"PAY & PRINT ({a.s.get('paper_size')})  F5", "green", self.open_payment, width=290, height=54).pack(side="right", padx=18, pady=10)
        self.load_pending()
        self.entry.focus_set()

    # ------------------------------------------------------------- search
    def on_key(self, e):
        if e.keysym in ("Return", "Up", "Down", "Escape", "Tab"):
            return
        q = self.entry.get().strip()
        if not q:
            return self.hide_results()
        rows = svc.search_products(q)
        if not rows:
            return self.hide_results()
        self._rows = {r["barcode"]: r for r in rows}
        for i in self.res.get_children():
            self.res.delete(i)
        for r in rows:
            exp, _ = svc.expiry_state(r["expiry_date"])
            tag = ("danger",) if (r["stock_qty"] <= svc.low_stock_level() or exp != "OK") else ()
            self.res.insert("", "end", iid=r["barcode"], tags=tag,
                            values=(r["barcode"], self.pname(r), f"{self.price_of(r):,.2f}", f"{r['stock_qty']:g}"))
        self.res.configure(height=min(len(rows), 5))
        self.res_frame.grid(row=2, column=0, sticky="ew")

    def toggle_grid(self):
        self.app.s.set_many({"feat_item_grid": "0" if self.app.s.bool("feat_item_grid") else "1"})
        self.app.navigate("billing")

    def add_from_grid(self, p):
        self.add_product(p)
        self.entry.focus_set()

    def hide_results(self):
        self.res_frame.grid_remove()

    def _focus_results(self):
        ch = self.res.get_children()
        if ch:
            self.res.focus_set(); self.res.selection_set(ch[0]); self.res.focus(ch[0])

    def add_selected_result(self):
        sel = self.res.selection()
        if sel:
            self.hide_results(); self.entry.delete(0, "end")
            self.add_product(self._rows[sel[0]])

    def on_enter(self, e=None):
        q = self.entry.get().strip()
        if not q:
            return
        p = svc.get_product(q)                      # exact barcode (scanner) first
        if not p:
            rows = svc.search_products(q, 1)
            p = rows[0] if rows else None
        self.hide_results(); self.entry.delete(0, "end")
        if p:
            self.add_product(p)
        else:
            messagebox.showwarning("Not found", f"No product found for '{q}'.")
            self.entry.focus_set()

    # ------------------------------------------------------------- cart
    def pname(self, p):
        if self.app.s.bool("feat_dual_lang") and p["name_local"]:
            return f"{p['name_en']} ({p['name_local']})"
        return p["name_en"]

    def price_of(self, p):
        return p["wholesale_price"] if (self.app.wholesale and p["wholesale_price"] and p["wholesale_price"] > 0) else p["selling_price"]

    def add_product(self, p):
        if p["stock_qty"] <= 0 and not self.app.s.bool("feat_allow_oversell"):
            messagebox.showwarning("Out of stock", f"'{p['name_en']}' is out of stock!")
            return self.entry.focus_set()
        if self.app.s.bool("feat_qty_popup"):
            self.item_dialog(p, self.price_of(p))
        else:
            self.put(p, 1.0, self.price_of(p), "", p["warranty"] or "")
            svc.speak(p["name_en"], self.app.s.bool("feat_voice"))

    def in_cart(self, barcode, skip=None):
        return sum(i["qty"] * i.get("factor", 1.0) for k, i in enumerate(self.cart) if i["barcode"] == barcode and k != skip)

    def put(self, p, qty, price, serial, war, idx=None, unit="", factor=1.0):
        if self.in_cart(p["barcode"], idx) + qty * factor > p["stock_qty"] + 1e-9 and not self.app.s.bool("feat_allow_oversell"):
            ut = f" {p['base_unit'] or 'pcs'}" if self.app.s.bool("feat_multi_unit") else ""
            messagebox.showwarning("Stock limit", f"Only {p['stock_qty']:g}{ut} in stock (cart already has {self.in_cart(p['barcode'], idx):g}{ut}).")
            return False
        item = dict(barcode=p["barcode"], name=self.pname(p), qty=qty, price=price, serial=serial, warranty=war, unit=unit, factor=factor)
        if idx is not None:
            self.cart[idx] = item
        else:
            for it in self.cart:
                if not serial and not it["serial"] and it["barcode"] == item["barcode"] and abs(it["price"] - price) < 0.005 and it["warranty"] == war and it.get("unit", "") == unit:
                    it["qty"] += qty
                    break
            else:
                self.cart.append(item)
        self.refresh(f"{item['name']}")
        self.entry.focus_set()
        return True

    def refresh(self, last=""):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for k, it in enumerate(self.cart):
            sw = " | ".join(x for x in (it["serial"], it["warranty"]) if x)
            self.tree.insert("", "end", iid=str(k), values=(it["barcode"], it["name"], f"{it['price']:,.2f}", f"{it['qty']:g}" + (f" {it['unit']}" if it.get("unit") else ""), f"{it['qty'] * it['price']:,.2f}", sw))
        self.lbl_count.configure(text=f"Items: {len(self.cart)}")
        self.lbl_total.configure(text=f"Total: {self.app.cur} {self.subtotal():,.2f}")
        self.app.pole_update(self.cart)                        # customer display (no-op when the feature is OFF; errors are swallowed)

    def subtotal(self):
        return round(sum(i["qty"] * i["price"] for i in self.cart), 2)

    def selected_idx(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def remove_row(self):
        i = self.selected_idx()
        if i is not None:
            del self.cart[i]; self.refresh()
        self.entry.focus_set()

    def clear_cart(self):
        self.cart.clear(); self.refresh(); self.entry.focus_set()

    def toggle_wholesale(self):
        self.app.wholesale = not self.app.wholesale
        self.app.navigate("billing")

    def hold(self):
        if not self.cart:
            return
        from tkinter import simpledialog
        ref = simpledialog.askstring("Hold bill", "Customer name / reference:")
        if ref:
            self.app.held[ref] = list(self.cart); self.clear_cart(); self.app.navigate("billing")

    def recall(self):
        if not self.app.held:
            return messagebox.showinfo("Hold", "No held bills.")
        from tkinter import simpledialog
        ref = simpledialog.askstring("Recall", "Held bills:\n" + "\n".join(self.app.held) + "\n\nEnter name:")
        if ref in self.app.held:
            for it in self.app.held.pop(ref):
                p = svc.get_product(it["barcode"])           # re-validate against current stock
                if p and (self.app.s.bool("feat_allow_oversell") or p["stock_qty"] >= it["qty"] + self.in_cart(it["barcode"])):
                    self.cart.append(it)
                else:
                    messagebox.showwarning("Skipped", f"'{it['name']}' skipped - not enough stock now.")
            self.app.navigate("billing")

    def load_pending(self):
        """Items sent here by 'Convert quotation to bill'."""
        pc, self.app.pending_cart = self.app.pending_cart, None
        if not pc:
            return
        skipped = []
        for it in pc:
            p = svc.get_product(it["barcode"])
            if p and (self.app.s.bool("feat_allow_oversell") or p["stock_qty"] >= it["qty"] + self.in_cart(it["barcode"])):
                self.cart.append(dict(it))
            else:
                skipped.append(it["name"])
        self.refresh()
        if skipped:
            messagebox.showwarning("Not added", "Not enough stock / item missing:\n" + "\n".join(skipped))

    def make_quote(self):
        a = self.app
        if not self.cart:
            return messagebox.showinfo("Quotation", "Add items to the bill first, then press Quote.")
        d = self.dialog("Create quotation", 440, 440)
        ctk.CTkLabel(d, text="Create quotation / estimate", font=a.f(3, "bold"), text_color=C["text"]).pack(pady=(16, 6))
        e_n = ctk.CTkEntry(d, width=330, height=38, placeholder_text="Customer name"); e_n.pack(pady=4)
        e_p = ctk.CTkEntry(d, width=330, height=38, placeholder_text="Phone"); e_p.pack(pady=4)
        e_v = ctk.CTkEntry(d, width=330, height=38, placeholder_text="Valid for (days)"); e_v.pack(pady=4); e_v.insert(0, "7")
        e_d = ctk.CTkEntry(d, width=330, height=38, placeholder_text=f"Discount ({a.cur})"); e_d.pack(pady=4); e_d.insert(0, "0")
        e_t = ctk.CTkEntry(d, width=330, height=38, placeholder_text="Note (delivery, terms...)"); e_t.pack(pady=4)

        def ok():
            try:
                q = svc.create_quote(self.cart, e_n.get().strip(), e_p.get().strip(), e_v.get() or 7, e_d.get() or 0, e_t.get().strip(), a.user)
            except ValueError as ex:
                return messagebox.showwarning("Quotation", str(ex), parent=d)
            d.destroy()
            width = 32 if a.s.get("paper_size") == "58mm" else 42
            self.show_text(q["quote_no"], svc.quote_text(q, {"name": a.s.get("shop_name")}, width, a.cur), on_print=lambda: printing.print_quote(a, q))
        a.btn(d, "SAVE QUOTATION", "green", ok, width=330, height=44).pack(pady=14)

    # ------------------------------------------------------------- qty / price dialog
    def edit_row(self):
        i = self.selected_idx()
        if i is None:
            return
        it = self.cart[i]
        p = svc.get_product(it["barcode"])
        if p:
            self.item_dialog(p, it["price"], idx=i, qty=it["qty"], serial=it["serial"], war=it["warranty"], unit=it.get("unit", ""))

    def item_dialog(self, p, price, idx=None, qty=1, serial="", war=None, unit=""):
        a = self.app
        war = p["warranty"] if war is None else war
        dlg = ctk.CTkToplevel(self); dlg.title("Quantity & Price"); dlg.geometry("470x470" if a.s.bool("feat_warranty") else "470x340")
        dlg.transient(self.winfo_toplevel())
        ctk.CTkLabel(dlg, text=self.pname(p), font=a.f(3, "bold"), text_color=C["text"], wraplength=420).pack(pady=(14, 4))
        exp, _ = svc.expiry_state(p["expiry_date"])
        warn = p["stock_qty"] <= svc.low_stock_level() or exp != "OK"
        ut = f" {p['base_unit'] or 'pcs'}" if a.s.bool("feat_multi_unit") else ""
        ctk.CTkLabel(dlg, text=f"Stock: {p['stock_qty']:g}{ut}" + (f"   Expiry: {p['expiry_date']} ({exp})" if p["expiry_date"] else ""),
                     font=a.f(-1, "bold"), text_color=C["danger"] if warn else C["muted"]).pack()
        form = a.card(dlg); form.pack(padx=24, pady=10, fill="x")
        ctk.CTkLabel(form, text="Quantity:", font=a.f(1, "bold"), text_color=C["text"]).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        e_q = ctk.CTkEntry(form, width=170, height=38, font=a.f(3, "bold"), justify="center"); e_q.grid(row=0, column=1, padx=12); e_q.insert(0, f"{qty:g}")
        ctk.CTkLabel(form, text=f"Unit price ({a.cur}):", font=a.f(1, "bold"), text_color=C["text"]).grid(row=1, column=0, padx=12, pady=10, sticky="w")
        e_p = ctk.CTkEntry(form, width=170, height=38, font=a.f(3, "bold"), justify="center"); e_p.grid(row=1, column=1, padx=12); e_p.insert(0, f"{price:.2f}")
        e_s = e_w = None
        if a.s.bool("feat_warranty"):
            ctk.CTkLabel(form, text="Serial / IMEI:", font=a.f(0), text_color=C["text"]).grid(row=2, column=0, padx=12, pady=6, sticky="w")
            e_s = ctk.CTkEntry(form, width=170); e_s.grid(row=2, column=1, padx=12); e_s.insert(0, serial)
            ctk.CTkLabel(form, text="Warranty:", font=a.f(0), text_color=C["text"]).grid(row=3, column=0, padx=12, pady=6, sticky="w")
            e_w = ctk.CTkComboBox(form, values=["", "No Warranty", "3 Months", "6 Months", "1 Year", "2 Years", "Lifetime"], width=170)
            e_w.grid(row=3, column=1, padx=12); e_w.set(war or "")
        units = svc.list_units(p["barcode"]) if a.s.bool("feat_multi_unit") else []
        ufac, unit_menu, base_price = {u["name"]: u for u in units}, None, self.price_of(p)

        def on_unit(name):
            u = ufac[name]
            e_p.delete(0, "end"); e_p.insert(0, f"{svc.unit_price(base_price, u['factor'], u['price']):.2f}")
            preview()
        if len(units) > 1:
            unit_menu = ctk.CTkOptionMenu(form, values=[u["name"] for u in units], width=90, command=on_unit)
            unit_menu.grid(row=0, column=2, padx=6)
            unit_menu.set(unit if unit in ufac else units[0]["name"])
        lbl = ctk.CTkLabel(dlg, text="", font=a.f(3, "bold"), text_color=C["warning"]); lbl.pack(pady=4)

        def preview(e=None):
            try:
                lbl.configure(text=f"Line total: {a.cur} {float(e_q.get() or 0) * float(e_p.get() or 0):,.2f}")
            except ValueError:
                pass
        e_q.bind("<KeyRelease>", preview); e_p.bind("<KeyRelease>", preview); preview()

        def ok(e=None):
            try:
                q, pr = svc.num(e_q.get(), "Quantity"), svc.num(e_p.get(), "Price", minimum=0)
            except ValueError as ex:
                return messagebox.showerror("Invalid", str(ex), parent=dlg)
            if q <= 0:
                if idx is not None:
                    del self.cart[idx]; self.refresh()
                return dlg.destroy()
            uname, fac = "", 1.0
            if unit_menu is not None and not ufac[unit_menu.get()]["base"]:
                uname, fac = unit_menu.get(), ufac[unit_menu.get()]["factor"]
            if units:
                q = round(q, 3)                                  # at most 3 decimals (kg/g, litres...)
            if self.put(p, q, pr, e_s.get().strip() if e_s else "", e_w.get().strip() if e_w else "", idx, uname, fac):
                svc.speak(p["name_en"], a.s.bool("feat_voice"))
                dlg.destroy()
        e_q.bind("<Return>", lambda e: (e_p.focus_force(), e_p.select_range(0, "end"), "break")[-1])
        e_p.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        a.btn(dlg, "ADD TO BILL (Enter)", "green", ok, height=44).pack(fill="x", padx=24, pady=8)
        dlg.after(120, lambda: (dlg.grab_set(), dlg.lift(), e_q.focus_force(), e_q.select_range(0, "end")))

    # ------------------------------------------------------------- payment
    def hotkey_pay(self):
        self.open_payment()

    def open_payment(self):
        if not self.cart:
            return
        a = self.app
        shift = svc.current_shift(a.user) if a.s.bool("feat_shift") else None
        if a.s.bool("feat_shift") and not shift:
            if messagebox.askyesno("No open shift", "Open your cash drawer shift before billing?\n\nYES = go to the Shift screen"):
                a.navigate("shift")
            return
        sub = self.subtotal()
        svc.speak(f"Sub total is {int(sub)}", a.s.bool("feat_voice"))
        with dbm.db() as c:
            custs = c.execute("SELECT id, name, phone, credit_balance, loyalty_points FROM customers ORDER BY name").fetchall()
        lim = a.s.bool("feat_credit_limit")
        with dbm.db() as c:
            limits = {r["id"]: (r["credit_limit"] or 0) for r in c.execute("SELECT id, credit_limit FROM customers")} if lim else {}
        opts = ["Walk-in Customer"] + [f"{r['id']} | {r['name']} | {r['phone']} | Pts {r['loyalty_points']:.0f} | Due {r['credit_balance']:.0f}"
                                       + (f" / Limit {limits[r['id']]:.0f}" if lim and limits.get(r["id"]) else "") for r in custs]
        pts_of = {str(r["id"]): r["loyalty_points"] for r in custs}

        m = ctk.CTkToplevel(self); m.title("Checkout & Payment"); m.geometry("660x790"); m.transient(self.winfo_toplevel())
        mode = {"v": "Cash"}
        ctk.CTkLabel(m, text=f"Sub Total: {a.cur} {sub:,.2f}", font=a.f(5, "bold"), text_color=C["text"]).pack(pady=(12, 4))
        mf = ctk.CTkFrame(m, fg_color="transparent"); mf.pack(fill="x", padx=20); mf.grid_columnconfigure((0, 1, 2, 3), weight=1)
        mbtn = {}
        for i, (k, lab) in enumerate((("Cash", "CASH"), ("Card", "CARD"), ("QR", "QR PAY"), ("Credit", "CREDIT"))):
            mbtn[k] = ctk.CTkButton(mf, text=lab, height=42, font=a.f(1, "bold"), text_color="white")
            mbtn[k].grid(row=0, column=i, padx=3, sticky="ew")

        f = a.card(m); f.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(f, text="Customer:", text_color=C["text"]).grid(row=0, column=0, padx=10, pady=6, sticky="w")
        opt = ctk.CTkOptionMenu(f, values=opts, width=330); opt.grid(row=0, column=1, padx=10, pady=6)
        ctk.CTkLabel(f, text=f"Discount ({a.cur} or %):", text_color=C["text"]).grid(row=1, column=0, padx=10, pady=6, sticky="w")
        e_disc = ctk.CTkEntry(f, width=330); e_disc.grid(row=1, column=1, padx=10); e_disc.insert(0, "0")
        if not a.can("discount"):
            e_disc.configure(state="disabled")
        e_red = None
        if a.s.bool("feat_loyalty"):
            ctk.CTkLabel(f, text="Redeem points (1 pt = 1):", text_color=C["text"]).grid(row=2, column=0, padx=10, pady=6, sticky="w")
            e_red = ctk.CTkEntry(f, width=330); e_red.grid(row=2, column=1, padx=10); e_red.insert(0, "0")
        lbl_paid = ctk.CTkLabel(f, text="Cash tendered:", text_color=C["text"]); lbl_paid.grid(row=3, column=0, padx=10, pady=6, sticky="w")
        e_paid = ctk.CTkEntry(f, width=330, font=a.f(3, "bold")); e_paid.grid(row=3, column=1, padx=10); e_paid.insert(0, f"{svc.preview_bill(self.cart, 0, 0)['net']:.2f}")      # includes VAT / service charge when they are ON
        lbl_ref = ctk.CTkLabel(f, text="Approval / Ref no:", text_color=C["text"]); e_ref = ctk.CTkEntry(f, width=330)
        e_wa = None
        if a.s.bool("feat_whatsapp"):
            ctk.CTkLabel(f, text="WhatsApp no (e-bill):", text_color=C["success"]).grid(row=5, column=0, padx=10, pady=6, sticky="w")
            e_wa = ctk.CTkEntry(f, width=330, placeholder_text="0771234567"); e_wa.grid(row=5, column=1, padx=10)

        def on_cust(choice):
            if e_wa is not None and " | " in choice:
                e_wa.delete(0, "end"); e_wa.insert(0, choice.split(" | ")[2])
        opt.configure(command=on_cust)

        qf = ctk.CTkFrame(m, fg_color="transparent"); qf.pack(fill="x", padx=20); qf.grid_columnconfigure((0, 1, 2, 3), weight=1)
        for i, v in enumerate((None, 500, 1000, 5000)):
            a.btn(qf, "Exact" if v is None else f"{a.cur} {v}", "gray", lambda v=v: (e_paid.delete(0, "end"), e_paid.insert(0, f"{(sub if v is None else v):.2f}"), calc()), height=28).grid(row=0, column=i, padx=3, sticky="ew")
        info = ctk.CTkLabel(m, text="", font=a.f(-1, "bold"), text_color=C["muted"], wraplength=600, justify="left"); info.pack(pady=4)
        lbl_net = ctk.CTkLabel(m, text="", font=a.f(5, "bold"), text_color=C["warning"]); lbl_net.pack()
        lbl_bal = ctk.CTkLabel(m, text="", font=a.f(6, "bold"), text_color=C["success"]); lbl_bal.pack(pady=2)

        def parse():
            s = e_disc.get().strip() or "0"
            disc = sub * svc.num(s[:-1], "Discount %", minimum=0, maximum=100) / 100 if s.endswith("%") else svc.num(s, "Discount", minimum=0)
            red = svc.num(e_red.get() or 0, "Redeemed points", minimum=0) if e_red else 0.0
            return round(disc, 2), round(red, 2)

        def calc(*_):
            try:
                disc, red = parse()
                tax = svc.preview_bill(self.cart, disc, red)
                net = tax["net"]
                if mode["v"] in ("Card", "QR"):
                    e_paid.delete(0, "end"); e_paid.insert(0, f"{net:.2f}")
                paid = svc.num(e_paid.get() or 0, "Paid", minimum=0)
            except ValueError:
                return
            extra = ""
            if tax["service"]:
                extra += f"  service {tax['service']:,.2f}"
            if tax["vat"]:
                extra += f"  VAT {tax['vat']:,.2f}" + (" incl." if tax["vat_mode"] == "Inclusive" else "")
            lbl_net.configure(text=f"Net Payable: {a.cur} {net:,.2f}" + (f"\n({extra.strip()})" if extra else ""))
            if mode["v"] == "Credit":
                lbl_bal.configure(text=f"Added to credit book: {a.cur} {max(0, net - paid):,.2f}", text_color=C["danger"])
            else:
                lbl_bal.configure(text=f"Balance: {a.cur} {paid - net:,.2f}", text_color=C["success"] if paid >= net else C["danger"])

        def set_mode(k):
            mode["v"] = k
            colors = {"Cash": "#15803D", "Card": "#2563EB", "QR": "#7C3AED", "Credit": "#B91C1C"}
            for kk, b in mbtn.items():
                b.configure(fg_color=colors[kk] if kk == k else "#475569", border_width=3 if kk == k else 0, border_color="white")
            lbl_paid.configure(text={"Cash": "Cash tendered:", "Card": "Card amount:", "QR": "QR amount:", "Credit": "Advance paid now:"}[k])
            if k in ("Card", "QR"):
                lbl_ref.grid(row=4, column=0, padx=10, pady=6, sticky="w"); e_ref.grid(row=4, column=1, padx=10)
            else:
                lbl_ref.grid_forget(); e_ref.grid_forget()
            info.configure(text={"Cash": "", "Card": "Enter the amount on your card machine, then type the approval code / last 4 digits.",
                                 "QR": f"Customer scans your QR / bank transfer:  {self.bank_text()}",
                                 "Credit": "Select a registered customer above. The unpaid balance goes to their credit book."}[k])
            if k == "Credit":
                e_paid.delete(0, "end"); e_paid.insert(0, "0.00")
            calc()
        for k, b in mbtn.items():
            b.configure(command=lambda k=k: set_mode(k))
        e_disc.bind("<KeyRelease>", calc); e_paid.bind("<KeyRelease>", calc)
        if e_red:
            e_red.bind("<KeyRelease>", calc)

        def finish(send_wa=False):
            try:
                disc, red = parse()
                paid = svc.num(e_paid.get() or 0, "Paid amount", minimum=0)
            except ValueError as ex:
                return messagebox.showerror("Invalid", str(ex), parent=m)
            if disc > sub + 0.004:
                return messagebox.showwarning("Check", "The discount cannot be more than the bill amount.", parent=m)
            c_sel = opt.get()
            cid = int(c_sel.split(" | ")[0]) if " | " in c_sel else None
            if red > sub - disc + 1e-9:
                return messagebox.showwarning("Check", "Redeemed points cannot exceed the bill amount.", parent=m)
            if red and cid and red > pts_of[str(cid)] + 1e-9:
                return messagebox.showwarning("Points", f"Customer has only {pts_of[str(cid)]:.0f} points.", parent=m)
            sale_args = (self.cart, disc, red, paid, mode["v"], e_ref.get().strip() if mode["v"] in ("Card", "QR") else "", cid, a.user)
            try:
                try:
                    sale = svc.create_sale(*sale_args, shift_id=shift["id"] if shift else None)
                except svc.CreditLimitError as ex:                 # over the customer's credit limit: an Admin may approve it
                    approver = a.user if a.is_admin else None
                    if approver is None:
                        from ..dialogs import ask_password
                        pw = ask_password(a, "Admin approval", f"{ex}\n\nAn Admin must approve this. Enter an Admin password:")
                        approver = svc.approve_with_admin_password(pw) if pw else None
                        if pw and not approver:
                            return messagebox.showwarning("Approval", "That is not an Admin password.", parent=m)
                    elif not messagebox.askyesno("Credit limit", f"{ex}\n\nApprove this credit sale anyway?", parent=m):
                        approver = None
                    if not approver:
                        return messagebox.showwarning("Credit limit", "The credit sale was NOT completed.", parent=m)
                    sale = svc.create_sale(*sale_args, shift_id=shift["id"] if shift else None, override_user=approver)
            except ValueError as ex:
                return messagebox.showwarning("Cannot complete", str(ex), parent=m)
            except Exception as ex:                      # nothing was saved: the transaction rolled back
                dbm.audit(a.user, "SALE_ERROR", str(ex))
                return messagebox.showerror("Error", f"Bill NOT saved (nothing changed):\n{ex}", parent=m)
            m.destroy()
            width = 32 if a.s.get("paper_size") == "58mm" else 42
            shop = {"name": a.s.get("shop_name"), "address": a.s.get("address"), "phone": a.s.get("phone")}
            try:
                svc.save_receipt(sale, svc.receipt_text(sale, shop, width, a.cur))
            except Exception:
                pass
            a.pole_thanks(sale["net"], sale["balance"])
            printing.after_sale(a, sale)                    # receipt + cash drawer (per Settings)
            svc.speak(f"Bill completed. Total is {int(sale['net'])}. Thank you!", a.s.bool("feat_voice"))
            if send_wa and a.s.bool("feat_whatsapp"):
                svc.open_url(svc.whatsapp_url(e_wa.get() if e_wa else "", sale, a.s.get("shop_name"), a.cur), a.s.get("whatsapp_mode") == "Desktop App")
            messagebox.showinfo("Done", f"Invoice {sale['invoice']} saved.\nNet: {a.cur} {sale['net']:,.2f}\nBalance: {a.cur} {sale['balance']:,.2f}")
            self.cart.clear(); self.refresh(); self.entry.focus_set()

        row = ctk.CTkFrame(m, fg_color="transparent"); row.pack(fill="x", padx=20, pady=8); row.grid_columnconfigure((0, 1), weight=1)
        a.btn(row, "COMPLETE & SAVE (Enter)", "green", lambda: finish(False), height=46).grid(row=0, column=0, padx=4, sticky="ew")
        if a.s.bool("feat_whatsapp"):
            a.btn(row, "PAY & SEND WHATSAPP", "teal", lambda: finish(True), height=46).grid(row=0, column=1, padx=4, sticky="ew")
        m.bind("<Return>", lambda e: finish(False))
        set_mode("Cash")
        m.after(120, lambda: (m.grab_set(), m.lift(), e_paid.focus_force()))

    def bank_text(self):
        s = self.app.s
        parts = [f"{l}: {s.get(k)}" for l, k in (("Bank", "bank_name"), ("Branch", "bank_branch"), ("A/C", "bank_acc"), ("Name", "bank_holder")) if s.get(k)]
        return " | ".join(parts) or "Set your bank details in Settings"
