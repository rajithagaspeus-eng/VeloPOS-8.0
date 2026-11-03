"""Barcode Labels: pick items, set the label size, preview, print on a receipt/label printer or as an A4 sheet. UI only - see barcodes.py."""
import os
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk
from PIL import Image

from .. import barcodes, database as dbm, printing, services as svc, theme
from ..theme import C
from . import Screen


class LabelsScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.queue = []                                         # [dict(barcode, name, price, copies)]
        self.grid_columnconfigure(0, weight=3); self.grid_columnconfigure(1, weight=2); self.grid_rowconfigure(1, weight=1)
        self.heading(self, "Barcode Labels").grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 6))
        # ---------------- left: pick items
        left = ctk.CTkFrame(self, fg_color="transparent"); left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1); left.grid_rowconfigure(1, weight=1); left.grid_rowconfigure(3, weight=1)
        bar = ctk.CTkFrame(left, fg_color="transparent"); bar.grid(row=0, column=0, sticky="ew")
        self.search = ctk.CTkEntry(bar, width=220, placeholder_text="Search items..."); self.search.pack(side="left", padx=3)
        self.search.bind("<KeyRelease>", lambda e: self.load_items())
        cats = ["All categories"] + [r["name"] for r in svc.list_categories()]
        self.cat = ctk.CTkOptionMenu(bar, values=cats, width=170, command=lambda v: self.load_items()); self.cat.pack(side="left", padx=3); self.cat.set(cats[0])
        self.e_copies = ctk.CTkEntry(bar, width=60, placeholder_text="Copies"); self.e_copies.pack(side="left", padx=3); self.e_copies.insert(0, "1")
        self.cb_stock = ctk.CTkCheckBox(bar, text="copies = stock", text_color=C["text"]); self.cb_stock.pack(side="left", padx=6)
        a.btn(bar, "Add selected", "green", self.add_selected, width=110, height=30).pack(side="left", padx=3)
        self.t_items = ttk.Treeview(left, columns=("b", "n", "p", "s"), show="headings", height=9, selectmode="extended")
        for c, t, w in (("b", "Barcode", 120), ("n", "Item", 240), ("p", "Retail", 90), ("s", "Stock", 70)):
            self.t_items.heading(c, text=t); self.t_items.column(c, width=w)
        theme.style_tree_tags(self.t_items)
        self.t_items.grid(row=1, column=0, sticky="nsew", pady=4)
        ctk.CTkLabel(left, text="Label queue", font=a.f(1, "bold"), text_color=C["text"]).grid(row=2, column=0, sticky="w")
        self.t_queue = ttk.Treeview(left, columns=("b", "n", "c"), show="headings", height=7, selectmode="extended")
        for c, t, w in (("b", "Barcode", 120), ("n", "Item", 280), ("c", "Copies", 70)):
            self.t_queue.heading(c, text=t); self.t_queue.column(c, width=w)
        theme.style_tree_tags(self.t_queue)
        self.t_queue.grid(row=3, column=0, sticky="nsew", pady=4)
        qb = ctk.CTkFrame(left, fg_color="transparent"); qb.grid(row=4, column=0, sticky="w")
        a.btn(qb, "Remove selected", "gray", self.remove_selected, width=140, height=28).pack(side="left", padx=3)
        a.btn(qb, "Clear queue", "gray", self.clear_queue, width=110, height=28).pack(side="left", padx=3)
        self.lbl_q = ctk.CTkLabel(qb, text="", text_color=C["muted"]); self.lbl_q.pack(side="left", padx=8)
        # ---------------- right: label design + output
        right = a.card(self); right.grid(row=1, column=1, sticky="nsew")
        self.w = {}
        row = 0
        for key, label, kind, opts in (("label_w_mm", "Width (mm)", "entry", None), ("label_h_mm", "Height (mm)", "entry", None),
                                       ("label_dpi", "Printer DPI", "menu", ["203", "300"]),
                                       ("label_symbology", "Barcode type", "menu", ["Auto", "EAN-13", "Code 39"]),
                                       ("label_cols", "A4 columns", "entry", None), ("label_rows", "A4 rows", "entry", None),
                                       ("label_margin_mm", "A4 margin (mm)", "entry", None)):
            ctk.CTkLabel(right, text=label + ":", text_color=C["text"]).grid(row=row, column=0, padx=12, pady=4, sticky="w")
            if kind == "entry":
                wd = ctk.CTkEntry(right, width=90); wd.insert(0, a.s.get(key))
            else:
                wd = ctk.CTkOptionMenu(right, values=opts, width=110); wd.set(a.s.get(key) if a.s.get(key) in opts else opts[0])
            wd.grid(row=row, column=1, padx=6, pady=4, sticky="w")
            self.w[key] = wd
            row += 1
        for key, label in (("label_shop", "Shop name"), ("label_name", "Item name"), ("label_price", "Price")):
            cb = ctk.CTkCheckBox(right, text=label, text_color=C["text"]); cb.grid(row=row, column=0, columnspan=2, padx=12, pady=2, sticky="w")
            if a.s.bool(key):
                cb.select()
            self.w[key] = cb
            row += 1
        cb = ctk.CTkCheckBox(right, text="Cut after every label (printer)", text_color=C["text"]); cb.grid(row=row, column=0, columnspan=2, padx=12, pady=2, sticky="w")
        if a.s.bool("label_cut"):
            cb.select()
        self.w["label_cut"] = cb
        a.btn(right, "Update preview", "accent", self.preview, width=150, height=30).grid(row=row + 1, column=0, columnspan=2, pady=8)
        self.lbl_prev = ctk.CTkLabel(right, text="(add items, then 'Update preview')", text_color=C["muted"], width=300, height=190)
        self.lbl_prev.grid(row=row + 2, column=0, columnspan=2, padx=8)
        a.btn(right, "Print on label / receipt printer", "green", self.print_printer, width=250, height=36).grid(row=row + 3, column=0, columnspan=2, pady=(10, 4))
        a.btn(right, "A4 sheet (opens in browser)", "blue", self.print_sheet, width=250, height=36).grid(row=row + 4, column=0, columnspan=2, pady=4)
        self.lbl_msg = ctk.CTkLabel(right, text="", font=a.f(-1), text_color=C["muted"], wraplength=300, justify="left")
        self.lbl_msg.grid(row=row + 5, column=0, columnspan=2, padx=10, pady=(4, 10))
        ctk.CTkLabel(right, text="Labels are printed as pictures: they work on receipt / label printers that accept images and on normal printers via the A4 sheet. "
                                 "Printers that only speak TSPL / ZPL are not supported.", font=a.f(-2), text_color=C["muted"], wraplength=300, justify="left"
                     ).grid(row=row + 6, column=0, columnspan=2, padx=10, pady=(0, 10))
        self.load_items()

    # ------------------------------------------------------------------ pick items
    def load_items(self):
        for i in self.t_items.get_children():
            self.t_items.delete(i)
        c = self.cat.get()
        rows, _ = svc.list_products(self.search.get().strip(), None if c.startswith("All") else c, limit=300)
        for r in rows:
            self.t_items.insert("", "end", iid=r["barcode"], values=(r["barcode"], r["name_en"], f"{r['selling_price']:,.2f}", f"{r['stock_qty']:g}"))

    def add_selected(self):
        sel = self.t_items.selection()
        if not sel:
            return messagebox.showinfo("Select", "Select one or more items in the list first.")
        try:
            copies = int(self.e_copies.get() or 1)
            if not 1 <= copies <= 500:
                raise ValueError
        except ValueError:
            return messagebox.showwarning("Copies", "Copies must be a whole number from 1 to 500.")
        for b in sel:
            p = svc.get_product(b)
            if p is None:
                continue
            n = max(1, min(500, int(p["stock_qty"] or 1))) if self.cb_stock.get() else copies
            q = next((x for x in self.queue if x["barcode"] == b), None)
            if q:
                q["copies"] = min(500, q["copies"] + n)
            else:
                self.queue.append(dict(barcode=b, name=p["name_en"], price=p["selling_price"], copies=n))
        self.refresh_queue()
        self.preview()

    def remove_selected(self):
        gone = set(self.t_queue.selection())
        self.queue = [q for q in self.queue if q["barcode"] not in gone]
        self.refresh_queue()

    def clear_queue(self):
        self.queue = []
        self.refresh_queue()

    def refresh_queue(self):
        for i in self.t_queue.get_children():
            self.t_queue.delete(i)
        for q in self.queue:
            self.t_queue.insert("", "end", iid=q["barcode"], values=(q["barcode"], q["name"], q["copies"]))
        self.lbl_q.configure(text=f"{sum(q['copies'] for q in self.queue)} label(s)")

    # ------------------------------------------------------------------ design
    def spec(self):
        g = lambda k: self.w[k].get().strip()               # noqa: E731
        try:
            spec = dict(width_mm=float(g("label_w_mm")), height_mm=float(g("label_h_mm")), dpi=int(g("label_dpi")), symbology=g("label_symbology"),
                        shop=self.app.s.get("shop_name") if self.w["label_shop"].get() else "", show_name=bool(self.w["label_name"].get()),
                        show_price=bool(self.w["label_price"].get()), currency=self.app.cur)
            if not (10 <= spec["width_mm"] <= 200 and 8 <= spec["height_mm"] <= 200):
                raise ValueError
        except ValueError:
            raise ValueError("Width must be 10-200 mm and height 8-200 mm (numbers).")
        return spec

    def save_settings(self):
        vals = {k: (("1" if w.get() else "0") if isinstance(w, ctk.CTkCheckBox) else w.get().strip()) for k, w in self.w.items()}
        self.app.s.set_many(vals)

    def preview(self):
        if not self.queue:
            return
        try:
            im = barcodes.render_label(self.queue[0], self.spec())
        except ValueError as ex:
            return self.lbl_prev.configure(text=str(ex), image=None)
        scale = min(1.0, 300 / im.width, 190 / im.height) if im.width else 1
        small = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))))
        self._pimg = ctk.CTkImage(light_image=small, dark_image=small, size=small.size)
        self.lbl_prev.configure(image=self._pimg, text="")

    # ------------------------------------------------------------------ output
    def _images(self):
        if not self.queue:
            messagebox.showinfo("Labels", "The queue is empty. Add items first.")
            return None
        try:
            spec = self.spec()
        except ValueError as ex:
            messagebox.showwarning("Label", str(ex))
            return None
        imgs, errors = barcodes.render_queue(self.queue, spec)
        if errors:
            messagebox.showwarning("Some labels were skipped", "\n".join(errors[:8]) + ("\n..." if len(errors) > 8 else ""))
        if not imgs:
            return None
        self.save_settings()
        return imgs, spec

    def print_printer(self):
        got = self._images()
        if not got:
            return
        try:
            ok = printing.print_labels(self.app, dbm.settings, got[0], self.w["label_cut"].get() == 1)
        except ValueError as ex:
            return messagebox.showwarning("Label printer", str(ex))
        if ok is None:
            return messagebox.showinfo("Label printer", "Printing mode 'Browser' cannot send labels to a printer. Choose the printer in Settings 3b, or use the A4 sheet.")
        self.lbl_msg.configure(text=f"{len(got[0])} label(s) sent to the printer.", text_color=C["success"])

    def print_sheet(self):
        got = self._images()
        if not got:
            return
        imgs, spec = got
        try:
            page = barcodes.sheet_html(imgs, spec, int(self.w["label_cols"].get()), int(self.w["label_rows"].get()), float(self.w["label_margin_mm"].get() or 0))
        except ValueError as ex:
            return messagebox.showwarning("A4 sheet", str(ex))
        os.makedirs(dbm.p("Exports"), exist_ok=True)
        path = os.path.join(dbm.p("Exports"), "barcode_labels.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        svc.open_url(Path(path).resolve().as_uri())
        self.lbl_msg.configure(text="The sheet opened in your browser: print it at 100% scale (no 'fit to page').", text_color=C["success"])
