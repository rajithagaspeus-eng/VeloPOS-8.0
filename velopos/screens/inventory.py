import csv
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .. import services as svc, theme, thumbs
from ..theme import C
from . import Screen
from .categories import open_manage_categories
from .pricetools import open_bulk_price, open_price_history
from .units import open_units


class InventoryScreen(Screen):
    FIELDS = [("barcode", "Barcode", 100), ("name_en", "English name", 160), ("name_local", "2nd language", 130),
              ("keywords", "Keywords", 100), ("cost", "Cost", 75), ("sell", "Retail", 80), ("whole", "Wholesale", 85),
              ("stock", "Stock", 70), ("add", "+ Add stock", 95), ("expiry", "Exp YYYY-MM-DD", 120), ("war", "Warranty", 90)]

    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.use_cat = a.s.bool("feat_categories")
        self.cat_filter = None                                   # None = all, "" = uncategorised
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(4, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew")
        self.heading(top, "Inventory, Wholesale & Expiry").pack(side="left")
        a.btn(top, "Import CSV", "purple", self.import_csv, width=100).pack(side="right", padx=3)
        a.btn(top, "CSV template", "blue", self.template, width=110).pack(side="right", padx=3)
        if a.s.bool("feat_multi_unit"):
            a.btn(top, "Units", "indigo", self.units_dialog, width=80).pack(side="right", padx=3)
        if self.use_cat:
            a.btn(top, "Categories", "teal", lambda: open_manage_categories(a, self.refresh_all), width=100).pack(side="right", padx=3)
        if a.s.bool("feat_price_history"):
            a.btn(top, "Bulk price", "amber", self.bulk_price, width=100).pack(side="right", padx=3)
            a.btn(top, "Price history", "pink", self.price_history, width=110).pack(side="right", padx=3)

        form = a.card(self); form.grid(row=1, column=0, sticky="ew", pady=6)
        self.e = {}
        for i, (k, ph, w) in enumerate(self.FIELDS):
            if k == "cost" and not a.can("see_cost"):
                continue
            en = ctk.CTkEntry(form, width=w, placeholder_text=ph)
            if k == "add":
                en.configure(fg_color=C["surface2"], border_color="#22C55E", border_width=2)
                en.bind("<Return>", lambda ev: self.save())
            en.grid(row=0, column=i, padx=3, pady=10); self.e[k] = en
        row2 = ctk.CTkFrame(form, fg_color="transparent"); row2.grid(row=1, column=0, columnspan=len(self.FIELDS), sticky="w", padx=6, pady=(0, 8))
        self.cat_box = None
        if self.use_cat:
            ctk.CTkLabel(row2, text="Category:", text_color=C["text"]).pack(side="left", padx=(6, 4))
            self.cat_box = ctk.CTkComboBox(row2, width=190, values=[""])
            self.cat_box.pack(side="left", padx=4)
        self.cb_tax = None
        if a.s.bool("feat_vat"):
            self.cb_tax = ctk.CTkCheckBox(row2, text="Taxable (VAT)", text_color=C["text"])
            self.cb_tax.pack(side="left", padx=(18, 4)); self.cb_tax.select()
        ctk.CTkLabel(row2, text="Picture:", text_color=C["text"]).pack(side="left", padx=(18, 4))
        self._blank = thumbs.placeholder("", 64)
        self._img = ctk.CTkImage(light_image=self._blank, dark_image=self._blank, size=(56, 56))
        self.preview = ctk.CTkLabel(row2, text="", image=self._img, width=60)
        self.preview.pack(side="left", padx=4)
        a.btn(row2, "Choose...", "accent", self.choose_image, width=90, height=30).pack(side="left", padx=3)
        a.btn(row2, "Remove", "gray", self.remove_image, width=80, height=30).pack(side="left", padx=3)

        act = ctk.CTkFrame(self, fg_color="transparent"); act.grid(row=2, column=0, sticky="ew")
        self.search = ctk.CTkEntry(act, width=280, placeholder_text="Search inventory..."); self.search.pack(side="left", padx=4)
        self.search.bind("<KeyRelease>", lambda ev: self.load())
        self.hint = ctk.CTkLabel(act, text="Click an item, type arrived qty in '+ Add stock', press Enter.", font=a.f(-2, "bold"), text_color=C["success"])
        self.hint.pack(side="left", padx=10)
        a.btn(act, "Clear", "gray", self.clear_form, width=70).pack(side="right", padx=3)
        a.btn(act, "Delete", "red", self.delete, width=80).pack(side="right", padx=3)
        a.btn(act, "Save / Update", "green", self.save, width=130).pack(side="right", padx=3)

        self.chip_bar = None
        if self.use_cat:
            self.chip_bar = ctk.CTkScrollableFrame(self, orientation="horizontal", height=46, fg_color="transparent")
            self.chip_bar.grid(row=3, column=0, sticky="ew", pady=(4, 0))

        cols = ["Barcode", "English name", "2nd language"] + (["Category"] if self.use_cat else []) + (["Cost"] if a.can("see_cost") else []) + \
               ["Retail", "Wholesale", "Stock", "Expiry", "Warranty", "Status"]
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c); self.tree.column(c, width=110 if c != "English name" else 200)
        theme.style_tree_tags(self.tree)
        self.tree.grid(row=4, column=0, sticky="nsew", pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.refresh_all()

    # ------------------------------------------------------------------ categories / chips
    def refresh_all(self):
        if self.use_cat:
            self.cat_box.configure(values=[""] + [r["name"] for r in svc.list_categories()])
            self.build_chips()
        self.load()

    def build_chips(self):
        for w in self.chip_bar.winfo_children():
            w.destroy()
        counts = svc.category_counts()
        items = [("All", None, sum(counts.values()))] + [(n, n, k) for n, k in counts.items() if n] + ([("Uncategorised", "", counts.get("", 0))] if counts.get("") else [])
        for label, value, n in items:
            on = self.cat_filter == value
            ctk.CTkButton(self.chip_bar, text=f"{label} ({n})", height=28, corner_radius=14, font=self.app.f(-2, "bold"),
                          fg_color=self.app.accent if on else "transparent", border_width=1, border_color=self.app.accent,
                          text_color="white" if on else C["text"], hover_color=C["hover"],
                          command=lambda v=value: self.set_filter(v)).pack(side="left", padx=3, pady=4)

    def set_filter(self, value):
        self.cat_filter = value
        self.build_chips()
        self.load()

    # ------------------------------------------------------------------ form
    def clear_form(self):
        for en in self.e.values():
            en.delete(0, "end")
        if self.cat_box is not None:
            self.cat_box.set("")
        if self.cb_tax is not None:
            self.cb_tax.select()
        self.show_picture(None)

    def show_picture(self, p):
        pil = self._blank.resize((56, 56)) if p is None else thumbs.CACHE.get(svc.product_image_path(p), 56, p["name_en"])
        self._img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(56, 56))
        self.preview.configure(image=self._img)

    def on_select(self, ev=None):
        sel = self.tree.selection()
        p = svc.get_product(sel[0]) if sel else None
        if not p:
            return
        self.clear_form()
        vals = {"barcode": p["barcode"], "name_en": p["name_en"], "name_local": p["name_local"], "keywords": p["keywords"],
                "cost": f"{p['cost_price']:.2f}", "sell": f"{p['selling_price']:.2f}", "whole": f"{p['wholesale_price']:.2f}",
                "stock": f"{p['stock_qty']:g}", "expiry": p["expiry_date"], "war": p["warranty"]}
        for k, v in vals.items():
            if k in self.e:
                self.e[k].insert(0, v or "")
        if self.cat_box is not None:
            self.cat_box.set(p["category"] or "")
        if self.cb_tax is not None:
            self.cb_tax.select() if (p["taxable"] is None or p["taxable"]) else self.cb_tax.deselect()
        self.show_picture(p)
        self.e["add"].focus_set()
        self.hint.configure(text=f"Selected: {p['name_en']} (stock {p['stock_qty']:g}). Type arrived qty in '+ Add stock', Enter.")

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        rows, _ = svc.list_products(self.search.get().strip(), self.cat_filter if self.use_cat else None, limit=None)
        low = svc.low_stock_level()
        emap = svc.product_expiry_map()                           # earliest batch expiry when batch tracking is ON
        for r in rows:
            alerts = []
            if r["stock_qty"] <= low:
                alerts.append("LOW STOCK")
            exp_date = emap.get(r["barcode"]) or r["expiry_date"]
            st, days = svc.expiry_state(exp_date)
            if st == "EXPIRED":
                alerts.append("EXPIRED")
            elif st == "SOON":
                alerts.append(f"EXP {days}d")
            vals = [r["barcode"], r["name_en"], r["name_local"]] + ([r["category"] or ""] if self.use_cat else []) + \
                   ([f"{r['cost_price']:.2f}"] if self.app.can("see_cost") else []) + \
                   [f"{r['selling_price']:.2f}", f"{r['wholesale_price']:.2f}", f"{r['stock_qty']:g}", exp_date, r["warranty"], " | ".join(alerts) or "OK"]
            self.tree.insert("", "end", iid=r["barcode"], values=vals, tags=("danger",) if alerts else ())

    # ------------------------------------------------------------------ actions
    def save(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to edit inventory.")
        g = lambda k: self.e[k].get().strip() if k in self.e else ""
        b, name = g("barcode"), g("name_en")
        if not b or not name:
            return messagebox.showwarning("Required", "Barcode and English name are required.")
        try:
            res = svc.save_product(b, name, self.app.user, name_local=g("name_local"), keywords=g("keywords"),
                                   cost=g("cost") if self.app.can("see_cost") else None, sell=g("sell"),
                                   wholesale=g("whole"), stock=g("stock"), add=g("add"),
                                   expiry=g("expiry"), warranty=g("war"), category=self.cat_box.get().strip() if self.cat_box is not None else None,
                                   taxable=bool(self.cb_tax.get()) if self.cb_tax is not None else None)
        except ValueError as ex:
            if str(ex).startswith("time data"):
                return messagebox.showerror("Invalid date", "Expiry date must look like 2026-12-31 (YYYY-MM-DD).")
            return messagebox.showwarning("Check", str(ex))
        self.clear_form(); self.refresh_all()
        messagebox.showinfo("Saved", f"'{name}' saved. Total stock: {res['stock']:g}")

    def delete(self):
        if not self.app.require_admin():
            return
        b = self.e["barcode"].get().strip()
        if b and messagebox.askyesno("Delete", f"Delete product {b}?"):
            try:
                svc.delete_product(b, self.app.user)
            except ValueError as ex:
                return messagebox.showwarning("Delete", str(ex))
            self.clear_form(); self.refresh_all()

    def choose_image(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to edit inventory.")
        b = self.e["barcode"].get().strip()
        if not b or svc.get_product(b) is None:
            return messagebox.showinfo("Picture", "Select (or save) the product first, then choose its picture.")
        p = filedialog.askopenfilename(title="Choose a picture", filetypes=[("Pictures", "*.jpg *.jpeg *.png *.webp *.bmp")])
        if not p:
            return
        try:
            svc.set_product_image(b, p, self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("Picture", str(ex))
        self.show_picture(svc.get_product(b))

    def remove_image(self):
        b = self.e["barcode"].get().strip()
        if b and svc.get_product(b) is not None and self.app.can("stock"):
            svc.clear_product_image(b, self.app.user)
            self.show_picture(svc.get_product(b))

    def bulk_price(self):
        open_bulk_price(self.app, list(self.tree.selection()), self.refresh_all)

    def units_dialog(self):
        sel = self.tree.selection()
        open_units(self.app, sel[0] if sel else self.e["barcode"].get().strip(), self.refresh_all)

    def price_history(self):
        sel = self.tree.selection()
        open_price_history(self.app, sel[0] if sel else self.e["barcode"].get().strip())

    def template(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="inventory_template.csv")
        if p:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerows([["barcode", "name_en", "name_local", "keywords", "cost_price", "selling_price", "wholesale_price", "stock_qty", "expiry_date", "warranty", "category"],
                                         ["1001", "Sample Item", "", "sample", "200", "250", "230", "50", "2027-12-31", "1 Year", "Groceries"]])

    def import_csv(self):
        if not self.app.require_admin():
            return
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not p:
            return
        add_mode = messagebox.askyesno("Stock mode", "For products that already exist:\n\nYES = ADD imported stock to current stock\nNO = REPLACE stock with imported value")
        with open(p, "r", encoding="utf-8-sig") as f:
            ok, bad = svc.import_products(list(csv.reader(f)), add_mode, self.app.user)
        self.refresh_all()
        messagebox.showinfo("Import finished", f"Imported: {ok}\nSkipped (bad rows): {bad}")
