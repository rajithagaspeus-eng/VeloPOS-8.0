"""Manage categories dialog (add / rename / delete / reorder)."""
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk

from .. import services as svc, theme
from ..theme import C


def open_manage_categories(app, on_change=None):
    if not app.can("stock"):
        return messagebox.showwarning("Not allowed", "You do not have permission to edit inventory.")
    d = ctk.CTkToplevel(app)
    d.title("Product categories")
    d.geometry("470x590")
    d.configure(fg_color=C["bg"])
    d.transient(app)
    d.after(120, lambda: (d.grab_set(), d.lift()))
    ctk.CTkLabel(d, text="Product categories", font=app.f(4, "bold"), text_color=C["text"]).pack(pady=(14, 2))
    ctk.CTkLabel(d, text="Deleting a category never deletes its products - they become 'uncategorised'.", font=app.f(-2),
                 text_color=C["muted"], wraplength=420).pack()
    tree = ttk.Treeview(d, columns=("name", "n"), show="headings", height=13)
    tree.heading("name", text="Category")
    tree.heading("n", text="Products")
    tree.column("name", width=300)
    tree.column("n", width=90, anchor="center")
    theme.style_tree_tags(tree)
    tree.pack(fill="x", padx=16, pady=10)
    lbl = ctk.CTkLabel(d, text="", font=app.f(-1), text_color=C["muted"])
    lbl.pack()
    row = ctk.CTkFrame(d, fg_color="transparent")
    row.pack(pady=6)
    e = ctk.CTkEntry(row, width=230, placeholder_text="New category name")
    e.pack(side="left", padx=4)

    def refresh():
        for i in tree.get_children():
            tree.delete(i)
        counts = svc.category_counts()
        for r in svc.list_categories():
            tree.insert("", "end", iid=r["name"], values=(r["name"], counts.get(r["name"], 0)))
        lbl.configure(text=f"Uncategorised products: {counts.get('', 0)}")
        if on_change:
            on_change()

    def selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a category first.", parent=d)
            return None
        return sel[0]

    def guard(fn):
        try:
            fn()
        except ValueError as ex:
            messagebox.showwarning("Check", str(ex), parent=d)
        refresh()

    def add(ev=None):
        guard(lambda: (svc.add_category(e.get(), app.user), e.delete(0, "end")))

    def rename():
        n = selected()
        new = simpledialog.askstring("Rename category", f"New name for '{n}':", initialvalue=n, parent=d) if n else None
        if new:
            guard(lambda: svc.rename_category(n, new, app.user))

    def delete():
        n = selected()
        if n and messagebox.askyesno("Delete category", f"Delete '{n}'? Its products stay in inventory as uncategorised.", parent=d):
            guard(lambda: svc.delete_category(n, app.user))

    def move(direction):
        n = selected()
        if n:
            guard(lambda: svc.move_category(n, direction, app.user))
            if n in tree.get_children():
                tree.selection_set(n)

    e.bind("<Return>", add)
    app.btn(row, "Add", "green", add, width=80).pack(side="left", padx=4)
    row2 = ctk.CTkFrame(d, fg_color="transparent")
    row2.pack(pady=6)
    app.btn(row2, "Rename", "accent", rename, width=90).pack(side="left", padx=3)
    app.btn(row2, "Delete", "red", delete, width=90).pack(side="left", padx=3)
    app.btn(row2, "Up", "gray", lambda: move("up"), width=60).pack(side="left", padx=3)
    app.btn(row2, "Down", "gray", lambda: move("down"), width=60).pack(side="left", padx=3)
    app.btn(d, "Close", "gray", d.destroy, width=120).pack(pady=10)
    refresh()
    return d
