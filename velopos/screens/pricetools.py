"""Bulk price update (preview -> apply, one transaction) and the price-history viewer."""
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import services as svc, theme
from ..theme import C

FIELD = {"Retail price": "selling_price", "Wholesale price": "wholesale_price", "Cost price": "cost_price"}
MODE = {"Increase / decrease by %": "percent", "Add / subtract an amount": "amount", "Set an exact price": "set"}
ROUND = {"No rounding": 0, "Nearest 1": 1, "Nearest 5": 5, "Nearest 10": 10, "Nearest 50": 50, "Nearest 100": 100}


def _dialog(app, title, w, h):
    d = ctk.CTkToplevel(app)
    d.title(title)
    d.geometry(f"{w}x{h}")
    d.configure(fg_color=C["bg"])
    d.transient(app)
    d.after(120, lambda: (d.grab_set(), d.lift()))
    return d


def open_bulk_price(app, selected=(), on_done=None):
    a = app
    if not a.can("stock"):
        return messagebox.showwarning("Not allowed", "You do not have permission to edit inventory.")
    d = _dialog(a, "Bulk price update", 800, 690)
    state = {"changes": [], "field": ""}
    ctk.CTkLabel(d, text="Bulk price update", font=a.f(5, "bold"), text_color=C["text"]).pack(pady=(14, 2))
    ctk.CTkLabel(d, text="1) choose what to change  2) Preview  3) APPLY. Every change is kept in the price history and the audit log.",
                 font=a.f(-1), text_color=C["muted"], wraplength=740).pack()
    f = a.card(d)
    f.pack(fill="x", padx=16, pady=10)
    cats = [r["name"] for r in svc.list_categories()]
    scopes = ["All products"] + (["One category"] if cats else []) + ([f"Selected items ({len(selected)})"] if selected else [])
    fields = ["Retail price", "Wholesale price"] + (["Cost price"] if a.can("see_cost") else [])

    def invalidate(*_):
        state["changes"] = []
        for i in tree.get_children():
            tree.delete(i)
        btn_apply.configure(state="disabled")
        info.configure(text="Settings changed - press Preview.", text_color=C["muted"])

    def row(r, label, widget_factory):
        ctk.CTkLabel(f, text=label, text_color=C["text"]).grid(row=r, column=0, padx=14, pady=6, sticky="w")
        w = widget_factory()
        w.grid(row=r, column=1, padx=8, pady=6, sticky="w")
        return w
    scope = row(0, "Apply to:", lambda: ctk.CTkOptionMenu(f, values=scopes, width=260, command=invalidate))
    scope.set(scopes[-1] if selected else scopes[0])
    cat = ctk.CTkOptionMenu(f, values=cats or ["-"], width=200, command=invalidate)
    cat.grid(row=0, column=2, padx=8, pady=6)
    field = row(1, "Change:", lambda: ctk.CTkOptionMenu(f, values=fields, width=260, command=invalidate))
    field.set(fields[0])
    mode = row(2, "How:", lambda: ctk.CTkOptionMenu(f, values=list(MODE), width=260, command=invalidate))
    mode.set(list(MODE)[0])
    val = ctk.CTkEntry(f, width=120, placeholder_text="e.g. 5 or -2.5")
    val.grid(row=2, column=2, padx=8, pady=6)
    val.bind("<KeyRelease>", invalidate)
    rnd = row(3, "Rounding:", lambda: ctk.CTkOptionMenu(f, values=list(ROUND), width=260, command=invalidate))
    rnd.set("No rounding")
    reason = row(4, "Reason (saved):", lambda: ctk.CTkEntry(f, width=420))
    reason.insert(0, "Bulk price update")

    def scope_tuple():
        s = scope.get()
        if s.startswith("One category"):
            return ("category", cat.get())
        if s.startswith("Selected"):
            return ("barcodes", list(selected))
        return ("all",)

    def preview():
        try:
            ch = svc.bulk_price_preview(FIELD[field.get()], MODE[mode.get()], svc.num(val.get() or "x"), scope_tuple(), ROUND[rnd.get()],
                                        allow_cost=a.can("see_cost"))
        except ValueError as ex:
            invalidate()
            return info.configure(text=("Enter a number in the value box." if "could not convert" in str(ex) else str(ex)), text_color=C["danger"])
        except PermissionError as ex:
            return info.configure(text=str(ex), text_color=C["danger"])
        state["changes"], state["field"] = ch, FIELD[field.get()]
        for i in tree.get_children():
            tree.delete(i)
        for k, x in enumerate(ch):
            tree.insert("", "end", iid=str(k), tags=("danger",) if x["warn"] else (),
                        values=(x["barcode"], x["name"], f"{x['old']:,.2f}", f"{x['new']:,.2f}", x["warn"]))
        bad = sum(1 for x in ch if x["warn"] == "ZERO / NEGATIVE")
        info.configure(text=f"{len(ch)} item(s) will change." + (f"  {bad} would become zero/negative - fix the settings." if bad else "")
                       if ch else "Nothing would change with these settings.", text_color=C["danger"] if bad else C["success"])
        btn_apply.configure(state="normal" if ch and not bad else "disabled")

    def apply():
        ch = state["changes"]
        if not ch or not messagebox.askyesno("Apply prices", f"Change the {field.get()} of {len(ch)} item(s)?\n\nThe old prices stay in the price history.", parent=d):
            return
        try:
            n = svc.bulk_price_apply(ch, state["field"], a.user, reason.get().strip() or "Bulk price update", allow_cost=a.can("see_cost"))
        except (ValueError, PermissionError) as ex:
            return messagebox.showerror("Not applied", str(ex), parent=d)
        messagebox.showinfo("Done", f"{n} price(s) updated.", parent=d)
        if on_done:
            on_done()
        d.destroy()

    bar = ctk.CTkFrame(d, fg_color="transparent")
    bar.pack()
    a.btn(bar, "Preview", "accent", preview, width=140).pack(side="left", padx=6)
    btn_apply = a.btn(bar, "APPLY CHANGES", "green", apply, width=180)
    btn_apply.pack(side="left", padx=6)
    btn_apply.configure(state="disabled")
    a.btn(bar, "Close", "gray", d.destroy, width=100).pack(side="left", padx=6)
    info = ctk.CTkLabel(d, text="", font=a.f(0, "bold"), text_color=C["muted"], wraplength=740)
    info.pack(pady=6)
    tree = ttk.Treeview(d, columns=("b", "n", "o", "w", "x"), show="headings", height=12)
    for c, t, w in (("b", "Barcode", 110), ("n", "Item", 300), ("o", "Old", 90), ("w", "New", 90), ("x", "Note", 140)):
        tree.heading(c, text=t)
        tree.column(c, width=w)
    theme.style_tree_tags(tree)
    tree.pack(fill="both", expand=True, padx=16, pady=(0, 14))
    return d


def open_price_history(app, barcode):
    a = app
    p = svc.get_product(barcode) if barcode else None
    if p is None:
        return messagebox.showinfo("Price history", "Select a saved product first.")
    d = _dialog(a, "Price history", 780, 500)
    ctk.CTkLabel(d, text=f"Price history - {p['name_en']}", font=a.f(4, "bold"), text_color=C["text"]).pack(pady=(14, 6))
    see = a.can("see_cost")
    cols = ["When", "User", "Retail", "Wholesale"] + (["Cost"] if see else []) + ["Reason"]
    tree = ttk.Treeview(d, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=170 if c in ("When", "Reason") else 100)
    theme.style_tree_tags(tree)
    tree.pack(fill="both", expand=True, padx=14, pady=6)
    rows = svc.price_history(barcode)
    for r in rows:
        vals = [r["ts"].replace("T", " "), r["user"], f"{r['sell_old'] or 0:,.2f} -> {r['sell_new'] or 0:,.2f}", f"{r['whole_old'] or 0:,.2f} -> {r['whole_new'] or 0:,.2f}"]
        if see:
            vals.append(f"{r['cost_old'] or 0:,.2f} -> {r['cost_new'] or 0:,.2f}")
        tree.insert("", "end", values=vals + [r["reason"]])
    if not rows:
        ctk.CTkLabel(d, text="No price changes have been recorded for this item yet.", text_color=C["muted"]).pack()
    a.btn(d, "Close", "gray", d.destroy, width=120).pack(pady=10)
    return d
