"""Units dialog: extra selling units for one item (kg/g, dozen/pcs, box/pcs ...). Stock is always kept in the BASE unit."""
from tkinter import messagebox, ttk

import customtkinter as ctk

from .. import services as svc, theme
from ..theme import C


def open_units(app, barcode, on_done=None):
    a = app
    p = svc.get_product(barcode) if barcode else None
    if p is None:
        return messagebox.showinfo("Units", "Select a saved product first.")
    if not a.can("stock"):
        return messagebox.showwarning("Not allowed", "You do not have permission to edit inventory.")
    d = ctk.CTkToplevel(a); d.title("Selling units"); d.geometry("620x560"); d.configure(fg_color=C["bg"]); d.transient(a)
    d.after(120, lambda: (d.grab_set(), d.lift()))
    ctk.CTkLabel(d, text=f"Units - {p['name_en']}", font=a.f(4, "bold"), text_color=C["text"]).pack(pady=(14, 2))
    ctk.CTkLabel(d, text="Stock is kept in the BASE unit. 'Factor' = how many base units ONE of the extra unit is "
                         "(base kg: g = 0.001; base pcs: dozen = 12). Price empty/0 = base price x factor.",
                 font=a.f(-1), text_color=C["muted"], wraplength=560).pack()
    tree = ttk.Treeview(d, columns=("u", "f", "p"), show="headings", height=8)
    for c, t, w in (("u", "Unit", 160), ("f", "Factor (base units)", 160), ("p", "Fixed price", 130)):
        tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
    theme.style_tree_tags(tree)
    tree.pack(fill="x", padx=16, pady=10)
    row = ctk.CTkFrame(d, fg_color="transparent"); row.pack(pady=4)
    e_n = ctk.CTkEntry(row, width=120, placeholder_text="Unit name"); e_n.pack(side="left", padx=4)
    e_f = ctk.CTkEntry(row, width=110, placeholder_text="Factor"); e_f.pack(side="left", padx=4)
    e_p = ctk.CTkEntry(row, width=110, placeholder_text="Fixed price"); e_p.pack(side="left", padx=4)

    def refresh():
        for i in tree.get_children():
            tree.delete(i)
        for u in svc.list_units(barcode):
            tree.insert("", "end", iid=u["name"], values=(u["name"] + ("  (base)" if u["base"] else ""), f"{u['factor']:g}", f"{u['price']:,.2f}" if u["price"] else "automatic"))
        if on_done:
            on_done()

    def guard(fn):
        try:
            fn()
        except ValueError as ex:
            messagebox.showwarning("Units", str(ex), parent=d)
        refresh()

    def save():
        guard(lambda: svc.save_unit(barcode, e_n.get(), e_f.get() or "x", e_p.get() or 0, a.user))

    def delete():
        sel = tree.selection()
        if sel:
            guard(lambda: svc.delete_unit(barcode, sel[0], a.user))

    def rename_base():
        guard(lambda: svc.set_base_unit(barcode, e_n.get(), a.user))
    bar = ctk.CTkFrame(d, fg_color="transparent"); bar.pack(pady=8)
    a.btn(bar, "Add / update unit", "green", save, width=150).pack(side="left", padx=4)
    a.btn(bar, "Delete selected", "red", delete, width=130).pack(side="left", padx=4)
    a.btn(bar, "Rename BASE unit", "amber", rename_base, width=150).pack(side="left", padx=4)
    if not a.s.bool("feat_multi_unit"):
        ctk.CTkLabel(d, text="Note: 'Multiple units' is switched OFF in Settings, so the Billing screen ignores these units for now.",
                     font=a.f(-1, "bold"), text_color=C["warning"], wraplength=560).pack(pady=6)
    a.btn(d, "Close", "gray", d.destroy, width=110).pack(pady=10)
    refresh()
    return d
