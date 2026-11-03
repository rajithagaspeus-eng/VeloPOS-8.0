"""Stock Control: adjustments / damage log, stock-take (audit count) and batches. UI only - all logic is in services.py."""
import csv
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .. import services as svc, theme
from ..theme import C
from . import Screen

TYPES = {"Damage (remove)": ("DAMAGE", -1, ""), "Expired (remove)": ("EXPIRED", -1, ""), "Lost / stolen (remove)": ("LOST", -1, ""),
         "Own use (remove)": ("ADJUST", -1, "Own use"), "Found (add)": ("FOUND", 1, ""),
         "Correction + (add)": ("ADJUST", 1, ""), "Correction - (remove)": ("ADJUST", -1, "")}
AUTO_BATCH = "(automatic: earliest expiry first)"


def _tree(parent, cols, widths, height=10):
    t = ttk.Treeview(parent, columns=[c for c, _ in cols], show="headings", height=height)
    for (c, title), w in zip(cols, widths):
        t.heading(c, text=title)
        t.column(c, width=w, anchor="w" if w >= 150 else "center")
    theme.style_tree_tags(t)
    return t


class StockScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.see_cost = a.can("see_cost")
        self.use_batches = a.s.bool("feat_batches")
        self.count_id = None
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self.heading(self, "Stock Control").grid(row=0, column=0, sticky="w", pady=(4, 6))
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.grid(row=1, column=0, sticky="ew")
        self.frames = {}
        tabs = [("adjust", "Adjustments & log"), ("count", "Stock-take")] + ([("batches", "Batches")] if self.use_batches else [])
        for key, label in tabs:
            a.btn(bar, label, "accent", lambda k=key: self.show(k), width=170, height=34).pack(side="left", padx=4)
            fr = ctk.CTkFrame(self, fg_color="transparent")
            fr.grid(row=2, column=0, sticky="nsew")
            self.frames[key] = fr
        self.build_adjust(self.frames["adjust"])
        self.build_count(self.frames["count"])
        if self.use_batches:
            self.build_batches(self.frames["batches"])
        self.show("adjust")

    def show(self, key):
        for k, fr in self.frames.items():
            fr.grid() if k == key else fr.grid_remove()
        if key == "count":
            self.load_counts()
        elif key == "batches":
            self.load_batches()

    # ================================================================== adjustments + log
    def build_adjust(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(2, weight=1)
        f = a.card(fr); f.grid(row=0, column=0, sticky="ew", pady=6)
        self.e_bar = ctk.CTkEntry(f, width=170, placeholder_text="Barcode / item name")
        self.e_bar.grid(row=0, column=0, padx=10, pady=10)
        self.e_bar.bind("<Return>", lambda e: self.lookup())
        self.lbl_item = ctk.CTkLabel(f, text="Scan / type an item and press Enter", text_color=C["muted"], width=330, anchor="w")
        self.lbl_item.grid(row=0, column=1, padx=6)
        self.m_type = ctk.CTkOptionMenu(f, values=list(TYPES), width=190)
        self.m_type.grid(row=0, column=2, padx=6)
        self.e_qty = ctk.CTkEntry(f, width=90, placeholder_text="Qty")
        self.e_qty.grid(row=0, column=3, padx=6)
        self.e_note = ctk.CTkEntry(f, width=200, placeholder_text="Note (optional)")
        self.e_note.grid(row=0, column=4, padx=6)
        self.m_batch = None
        if self.use_batches:
            self.m_batch = ctk.CTkOptionMenu(f, values=[AUTO_BATCH], width=250)
            self.m_batch.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="w")
        a.btn(f, "APPLY", "green", self.apply_adjust, width=110, height=36).grid(row=0, column=5, padx=10)
        self.product, self.batch_map = None, {}

        flt = ctk.CTkFrame(fr, fg_color="transparent"); flt.grid(row=1, column=0, sticky="ew")
        today = datetime.now().strftime("%Y-%m-%d")
        self.f_from = ctk.CTkEntry(flt, width=110, placeholder_text="From YYYY-MM-DD"); self.f_from.pack(side="left", padx=3)
        self.f_to = ctk.CTkEntry(flt, width=110, placeholder_text="To"); self.f_to.pack(side="left", padx=3)
        self.f_from.insert(0, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")); self.f_to.insert(0, today)
        self.f_text = ctk.CTkEntry(flt, width=150, placeholder_text="Item / note"); self.f_text.pack(side="left", padx=3)
        self.f_reason = ctk.CTkOptionMenu(flt, values=["All reasons"] + list(svc.STOCK_REASONS), width=140); self.f_reason.pack(side="left", padx=3)
        self.f_user = ctk.CTkEntry(flt, width=100, placeholder_text="User"); self.f_user.pack(side="left", padx=3)
        a.btn(flt, "Filter", "accent", self.load_log, width=80, height=30).pack(side="left", padx=3)
        a.btn(flt, "Export CSV", "purple", self.export_log, width=110, height=30).pack(side="left", padx=3)
        self.lbl_sum = ctk.CTkLabel(flt, text="", font=a.f(-1, "bold"), text_color=C["muted"]); self.lbl_sum.pack(side="left", padx=10)
        cols = [("t", "When"), ("i", "Item"), ("c", "Change"), ("a", "After"), ("r", "Reason"), ("f", "Ref"), ("u", "User"), ("n", "Note")] + ([("v", "Value")] if self.see_cost else [])
        self.log = _tree(fr, cols, [140, 200, 80, 80, 90, 130, 80, 200] + ([90] if self.see_cost else []), 14)
        self.log.grid(row=2, column=0, sticky="nsew", pady=6)
        self.load_log()

    def lookup(self):
        q = self.e_bar.get().strip()
        p = svc.get_product(q) if q else None
        if p is None and q:
            found = svc.search_products(q, 1)
            p = found[0] if found else None
        self.product = p
        if p is None:
            self.lbl_item.configure(text="Item not found", text_color=C["danger"])
            return
        self.e_bar.delete(0, "end"); self.e_bar.insert(0, p["barcode"])
        self.lbl_item.configure(text=f"{p['name_en']}   (stock {p['stock_qty']:g} {p['base_unit'] or 'pcs'})", text_color=C["text"])
        if self.m_batch is not None:
            self.batch_map = {AUTO_BATCH: None}
            for b in svc.list_batches(p["barcode"]):
                self.batch_map[f"#{b['id']}  {b['batch_no']}  exp {b['expiry_date'] or '-'}  qty {b['qty_remaining']:g}"] = b["id"]
            self.m_batch.configure(values=list(self.batch_map))
            self.m_batch.set(AUTO_BATCH)
        self.e_qty.focus_set()

    def apply_adjust(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to change stock.")
        self.lookup()
        if self.product is None:
            return
        reason, sign, auto_note = TYPES[self.m_type.get()]
        try:
            qty = svc.num(self.e_qty.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            return messagebox.showwarning("Quantity", "Enter a quantity greater than zero.")
        note = self.e_note.get().strip() or auto_note
        batch = self.batch_map.get(self.m_batch.get()) if self.m_batch is not None else None
        try:
            new = svc.adjust_stock(self.product["barcode"], sign * qty, reason, self.app.user, note, batch)
        except ValueError as ex:
            return messagebox.showwarning("Stock", str(ex))
        messagebox.showinfo("Stock updated", f"{self.product['name_en']}: stock is now {new:g}")
        self.e_qty.delete(0, "end"); self.e_note.delete(0, "end")
        self.lookup(); self.load_log()

    def _filters(self):
        r = self.f_reason.get()
        return dict(date_from=self.f_from.get().strip() or None, date_to=self.f_to.get().strip() or None, text=self.f_text.get().strip(),
                    reason=None if r.startswith("All") else r, user=self.f_user.get().strip() or None)

    def load_log(self):
        for i in self.log.get_children():
            self.log.delete(i)
        rows = svc.stock_log(limit=500, **self._filters())
        for r in rows:
            vals = [r["ts"].replace("T", " "), r["name_en"] or r["barcode"], f"{r['qty_change']:+g}", f"{r['qty_after']:g}", r["reason"], r["ref"], r["user"], r["note"]]
            if self.see_cost:
                vals.append(f"{r['qty_change'] * (r['cost_price'] or 0):+,.2f}")
            self.log.insert("", "end", values=vals, tags=("danger",) if r["reason"] in svc.WRITE_OFF else ())
        txt = f"{len(rows)} movement(s)"
        if self.see_cost:
            txt += f"   write-off value (damage/expired/lost): {self.app.cur} {svc.write_off_value(rows):,.2f}"
        self.lbl_sum.configure(text=txt)

    def export_log(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="stock_log.csv")
        if p:
            n = svc.export_stock_log(p, include_cost=self.see_cost, **self._filters())
            messagebox.showinfo("Exported", f"{n} row(s) saved.")

    # ================================================================== stock-take
    def build_count(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(fr, fg_color="transparent"); top.grid(row=0, column=0, sticky="ew", pady=6)
        a.btn(top, "New stock-take...", "green", self.new_count, width=150, height=32).pack(side="left", padx=3)
        a.btn(top, "Report", "accent", self.show_report, width=90, height=32).pack(side="left", padx=3)
        a.btn(top, "Import counts CSV", "purple", self.import_counts, width=150, height=32).pack(side="left", padx=3)
        a.btn(top, "Finalize...", "red", self.finalize, width=110, height=32).pack(side="left", padx=3)
        a.btn(top, "Cancel session", "gray", self.cancel, width=120, height=32).pack(side="left", padx=3)
        ent = a.card(fr); ent.grid(row=1, column=0, sticky="ew")
        self.c_bar = ctk.CTkEntry(ent, width=180, placeholder_text="Scan barcode"); self.c_bar.grid(row=0, column=0, padx=10, pady=8)
        self.c_qty = ctk.CTkEntry(ent, width=100, placeholder_text="Counted qty"); self.c_qty.grid(row=0, column=1, padx=6)
        self.c_bar.bind("<Return>", lambda e: self.c_qty.focus_set())
        self.c_qty.bind("<Return>", lambda e: self.add_count())
        a.btn(ent, "Add count (Enter)", "green", self.add_count, width=150, height=32).grid(row=0, column=2, padx=8)
        self.lbl_count = ctk.CTkLabel(ent, text="Select an OPEN session below (or start a new one).", text_color=C["muted"])
        self.lbl_count.grid(row=0, column=3, padx=10)
        self.cnt_tree = _tree(fr, [("id", "#"), ("t", "Started"), ("u", "User"), ("s", "Scope"), ("st", "Status"), ("n", "Items counted")], [50, 150, 90, 220, 90, 110], 8)
        self.cnt_tree.grid(row=2, column=0, sticky="nsew", pady=6)
        self.cnt_tree.bind("<<TreeviewSelect>>", self.pick_count)

    def load_counts(self):
        for i in self.cnt_tree.get_children():
            self.cnt_tree.delete(i)
        for r in svc.list_counts():
            scope = "All products" if r["scope"] == "all" else f"Category: {r['category']}"
            self.cnt_tree.insert("", "end", iid=str(r["id"]), values=(r["id"], r["started_ts"].replace("T", " "), r["user"], scope, r["status"], r["n"]))
        if self.count_id and str(self.count_id) in self.cnt_tree.get_children():
            self.cnt_tree.selection_set(str(self.count_id))

    def pick_count(self, ev=None):
        sel = self.cnt_tree.selection()
        self.count_id = int(sel[0]) if sel else None
        if self.count_id:
            st = self.cnt_tree.item(sel[0])["values"][4]
            self.lbl_count.configure(text=f"Session #{self.count_id} ({st})", text_color=C["success"] if st == "OPEN" else C["muted"])

    def _need_session(self):
        if not self.count_id:
            messagebox.showinfo("Stock-take", "Select a stock-take session first.")
            return False
        return True

    def new_count(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to change stock.")
        d = ctk.CTkToplevel(self); d.title("New stock-take"); d.geometry("380x260"); d.configure(fg_color=C["bg"]); d.transient(self.winfo_toplevel())
        d.after(120, lambda: (d.grab_set(), d.lift()))
        cats = [r["name"] for r in svc.list_categories()]
        scope = ctk.CTkOptionMenu(d, values=["All products"] + (["One category"] if cats else []), width=250); scope.pack(pady=(20, 6))
        cat = ctk.CTkOptionMenu(d, values=cats or ["-"], width=250); cat.pack(pady=6)
        note = ctk.CTkEntry(d, width=250, placeholder_text="Note (optional)"); note.pack(pady=6)

        def go():
            try:
                self.count_id = svc.start_count("category" if scope.get().startswith("One") else "all", cat.get() if scope.get().startswith("One") else "", self.app.user, note.get().strip())
            except ValueError as ex:
                return messagebox.showwarning("Stock-take", str(ex), parent=d)
            d.destroy(); self.load_counts()
        self.app.btn(d, "START", "green", go, width=160, height=38).pack(pady=14)

    def add_count(self):
        if not self._need_session():
            return
        try:
            svc.record_count(self.count_id, self.c_bar.get().strip(), svc.num(self.c_qty.get()), self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("Stock-take", "Enter a barcode and a counted quantity." if "could not convert" in str(ex) else str(ex))
        self.lbl_count.configure(text=f"Counted {self.c_bar.get().strip()} = {self.c_qty.get()}", text_color=C["success"])
        self.c_bar.delete(0, "end"); self.c_qty.delete(0, "end"); self.c_bar.focus_set()
        self.load_counts()

    def import_counts(self):
        if not self._need_session():
            return
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if p:
            with open(p, "r", encoding="utf-8-sig") as f:
                try:
                    ok, bad = svc.import_counts(self.count_id, list(csv.reader(f)), self.app.user)
                except ValueError as ex:
                    return messagebox.showwarning("Stock-take", str(ex))
            messagebox.showinfo("Import", f"Counted: {ok}\nSkipped: {bad}")
            self.load_counts()

    def show_report(self):
        if not self._need_session():
            return
        rep = svc.count_report(self.count_id)
        d = ctk.CTkToplevel(self); d.title(f"Stock-take #{self.count_id} report"); d.geometry("820x560"); d.configure(fg_color=C["bg"]); d.transient(self.winfo_toplevel())
        t = rep["totals"]
        txt = f"Counted {t['counted']}   Not counted {t['uncounted']}   With variance {t['with_variance']}   Net qty {t['net_qty']:+g}"
        if self.see_cost:
            txt += f"\nShortage {self.app.cur} {t['shortage_value']:,.2f}    Surplus {self.app.cur} {t['surplus_value']:,.2f}    Net {self.app.cur} {t['net_value']:+,.2f}"
        ctk.CTkLabel(d, text=txt, font=self.app.f(0, "bold"), text_color=C["text"], justify="left").pack(pady=8)
        cols = [("b", "Barcode"), ("n", "Item"), ("s", "System"), ("c", "Counted"), ("v", "Variance")] + ([("x", "Value")] if self.see_cost else [])
        tr = _tree(d, cols, [110, 280, 90, 90, 90] + ([100] if self.see_cost else []), 18)
        tr.pack(fill="both", expand=True, padx=12, pady=6)
        for ln in rep["lines"]:
            vals = [ln["barcode"], ln["name"], f"{ln['system']:g}", "-" if ln["counted"] is None else f"{ln['counted']:g}",
                    "not counted" if ln["variance"] is None else f"{ln['variance']:+g}"] + ([f"{ln['value']:+,.2f}" if ln["value"] is not None else ""] if self.see_cost else [])
            tr.insert("", "end", values=vals, tags=("danger",) if ln["variance"] else ())
        self.app.btn(d, "Close", "gray", d.destroy, width=100).pack(pady=8)

    def finalize(self):
        if not self._need_session() or not self.app.require_admin():
            return
        warns = svc.count_warnings(self.count_id)
        msg = ""
        if warns:
            msg = (f"WARNING: {len(warns)} item(s) had stock movements (sales, returns, adjustments) since this count started:\n  "
                   + "\n  ".join(f"{w['name']} ({w['net']:+g})" for w in warns[:8]) + ("\n  ..." if len(warns) > 8 else "")
                   + "\n\nThe variance is calculated against the stock at THIS moment. Recount those items if unsure.\n\n")
        rep = svc.count_report(self.count_id)["totals"]
        ans = messagebox.askyesnocancel("Finalize stock-take", msg + f"{rep['with_variance']} item(s) will be corrected.\n{rep['uncounted']} item(s) were NOT counted.\n\n"
                                        "YES = leave uncounted items unchanged\nNO = treat uncounted items as ZERO\nCANCEL = go back")
        if ans is None:
            return
        try:
            res = svc.finalize_count(self.count_id, self.app.user, "ignore" if ans else "zero")
        except ValueError as ex:
            return messagebox.showwarning("Stock-take", str(ex))
        messagebox.showinfo("Stock-take finalized", f"{res['adjusted']} item(s) corrected, net quantity {res['net_qty']:+g}.")
        self.load_counts(); self.load_log()

    def cancel(self):
        if self._need_session() and messagebox.askyesno("Cancel", f"Cancel stock-take #{self.count_id}? Stock is not changed."):
            try:
                svc.cancel_count(self.count_id, self.app.user)
            except ValueError as ex:
                messagebox.showwarning("Stock-take", str(ex))
            self.load_counts()

    # ================================================================== batches
    def build_batches(self, fr):
        a = self.app
        fr.grid_columnconfigure(0, weight=1); fr.grid_rowconfigure(1, weight=1)
        f = a.card(fr); f.grid(row=0, column=0, sticky="ew", pady=6)
        self.b = {}
        for i, (k, ph, w) in enumerate((("bar", "Barcode", 130), ("no", "Batch no", 110), ("exp", "Expiry YYYY-MM-DD", 140), ("qty", "Qty received", 100))
                                       + ((("cost", "Cost / unit", 90),) if self.see_cost else ())):
            self.b[k] = ctk.CTkEntry(f, width=w, placeholder_text=ph); self.b[k].grid(row=0, column=i, padx=5, pady=10)
        a.btn(f, "Receive new batch", "green", self.receive, width=160, height=32).grid(row=0, column=6, padx=8)
        cols = [("id", "#"), ("i", "Item"), ("b", "Batch"), ("e", "Expiry"), ("q", "Qty left"), ("s", "Source")] + ([("c", "Cost")] if self.see_cost else [])
        self.bt = _tree(fr, cols, [50, 240, 120, 110, 90, 110] + ([90] if self.see_cost else []), 14)
        self.bt.grid(row=1, column=0, sticky="nsew", pady=6)

    def load_batches(self):
        for i in self.bt.get_children():
            self.bt.delete(i)
        for r in svc.list_batches():
            st, days = svc.expiry_state(r["expiry_date"])
            vals = [r["id"], r["name_en"], r["batch_no"], r["expiry_date"] or "-", f"{r['qty_remaining']:g}", r["source"]] + ([f"{r['cost_price']:.2f}"] if self.see_cost else [])
            self.bt.insert("", "end", values=vals, tags=("danger",) if st in ("EXPIRED", "SOON") else ())

    def receive(self):
        if not self.app.can("stock"):
            return messagebox.showwarning("Not allowed", "You do not have permission to change stock.")
        g = lambda k: self.b[k].get().strip() if k in self.b else ""
        try:
            svc.receive_batch(g("bar"), g("no"), g("exp"), svc.num(g("qty") or 0), svc.num(g("cost") or 0), self.app.user)
        except ValueError as ex:
            return messagebox.showwarning("Batch", str(ex))
        for e in self.b.values():
            e.delete(0, "end")
        self.load_batches(); self.load_log()
