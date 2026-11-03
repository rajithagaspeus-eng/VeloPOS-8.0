"""The F1 keyboard-shortcut sheet (generated from velopos/shortcuts.py)."""
import os
from pathlib import Path
from tkinter import ttk

import customtkinter as ctk

from .. import database as dbm, services as svc, shortcuts, theme
from ..theme import C


def open_shortcut_sheet(app):
    d = ctk.CTkToplevel(app)
    d.title("Keyboard shortcuts")
    d.geometry("720x560")
    d.configure(fg_color=C["bg"])
    d.transient(app)
    ctk.CTkLabel(d, text="Keyboard shortcuts", font=app.f(5, "bold"), text_color=C["text"]).pack(pady=(14, 6))
    tree = ttk.Treeview(d, columns=("k", "w", "d"), show="headings", height=16)
    for c, t, w in (("k", "Key", 100), ("w", "Where", 220), ("d", "What it does", 370)):
        tree.heading(c, text=t)
        tree.column(c, width=w, anchor="w")
    theme.style_tree_tags(tree)
    tree.pack(fill="both", expand=True, padx=14, pady=6)
    for scope, key, desc in shortcuts.sheet_rows():
        tree.insert("", "end", values=(key, scope, desc))

    def print_page():
        os.makedirs(dbm.p("Exports"), exist_ok=True)
        path = os.path.join(dbm.p("Exports"), "keyboard_shortcuts.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(shortcuts.sheet_html(dbm.settings.get("shop_name")))
        svc.open_url(Path(path).resolve().as_uri())
    row = ctk.CTkFrame(d, fg_color="transparent")
    row.pack(pady=10)
    app.btn(row, "Print / save as page", "accent", print_page, width=190).pack(side="left", padx=6)
    app.btn(row, "Close", "gray", d.destroy, width=110).pack(side="left", padx=6)
    return d
