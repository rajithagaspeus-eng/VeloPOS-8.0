from tkinter import filedialog

import customtkinter as ctk

from ..theme import C


class Screen(ctk.CTkFrame):
    def __init__(self, app, parent):
        super().__init__(parent, fg_color="transparent")
        self.app = app

    def heading(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=self.app.f(6, "bold"), text_color=C["text"])

    def dialog(self, title, w, h):
        d = ctk.CTkToplevel(self)
        d.title(title)
        d.geometry(f"{w}x{h}")
        d.transient(self.winfo_toplevel())
        d.after(120, lambda: (d.grab_set(), d.lift()))
        return d

    def show_text(self, title, text, on_print=None):
        d = self.dialog(title, 560, 680)
        tb = ctk.CTkTextbox(d, font=("Consolas", 13), wrap="none")
        tb.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        tb.insert("1.0", text)
        tb.configure(state="disabled")

        def save():
            p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=title.replace(" ", "_") + ".txt")
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
        row = ctk.CTkFrame(d, fg_color="transparent")
        row.pack(pady=8)
        self.app.btn(row, "Copy", "accent", lambda: (self.clipboard_clear(), self.clipboard_append(text)), width=100).pack(side="left", padx=4)
        from .. import printing
        self.app.btn(row, "Print", "teal", on_print or (lambda: printing.print_text(self.app, text, title)), width=100).pack(side="left", padx=4)
        self.app.btn(row, "Save .txt", "green", save, width=100).pack(side="left", padx=4)
        self.app.btn(row, "Close", "gray", d.destroy, width=100).pack(side="left", padx=4)
