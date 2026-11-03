from tkinter import ttk

import customtkinter as ctk

from .. import database as dbm
from . import Screen


class AuditScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self.heading(self, "Audit Log (who did what, and when)").grid(row=0, column=0, sticky="w")
        self.q = ctk.CTkEntry(self, width=320, placeholder_text="Filter: user, action (VOID, RETURN, LOGIN_FAILED ...)"); self.q.grid(row=1, column=0, sticky="w", pady=6)
        self.q.bind("<KeyRelease>", lambda e: self.load())
        cols = ("Time", "User", "Action", "Detail")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (160, 110, 160, 600)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w)
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.load()

    def load(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        q = f"%{self.q.get().strip()}%"
        with dbm.db() as c:
            for r in c.execute("SELECT ts,user,action,detail FROM audit_log WHERE user LIKE ? OR action LIKE ? OR detail LIKE ? ORDER BY id DESC LIMIT 600", (q, q, q)):
                self.tree.insert("", "end", values=(r["ts"].replace("T", " "), r["user"], r["action"], r["detail"]))
