"""Customer display window (put it on the second monitor). It only reads DisplayModel snapshots, so it can never slow billing down."""
import customtkinter as ctk

from ..theme import C


class PoleDisplay(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self._last, self._rows = app, -1, []
        s = app.s
        self.title("Customer display")
        self.configure(fg_color=C["bg"])
        try:
            self.geometry(f"{max(320, s.int('pole_w', 800))}x{max(240, s.int('pole_h', 600))}+{s.int('pole_x', 0)}+{s.int('pole_y', 0)}")
            if s.bool("pole_fullscreen"):
                self.attributes("-fullscreen", True)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.close)
        fs = max(14, min(80, s.int("pole_font", 28)))
        self.fs = fs
        self.lbl_shop = ctk.CTkLabel(self, text="", font=("Segoe UI", int(fs * 1.5), "bold"), text_color=app.accent)
        self.lbl_shop.pack(pady=(18, 4))
        self.lbl_msg = ctk.CTkLabel(self, text="", font=("Segoe UI", int(fs * 0.8)), text_color=C["muted"], wraplength=700)
        self.lbl_msg.pack(pady=4)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=6)
        for _ in range(9):
            r = ctk.CTkLabel(self.body, text="", font=("Segoe UI", int(fs * 0.75)), text_color=C["text"], anchor="w", justify="left")
            r.pack(fill="x")
            self._rows.append(r)
        self.lbl_total = ctk.CTkLabel(self, text="", font=("Segoe UI", int(fs * 1.8), "bold"), text_color=C["success"])
        self.lbl_total.pack(pady=(4, 20))
        self.after(200, self.poll)

    def close(self):
        try:
            self.app.pole_window = None
        except Exception:
            pass
        self.destroy()

    def poll(self):
        try:
            m = self.app.pole_model
            m.tick()
            snap = m.snapshot()
            if snap["version"] != self._last:
                self._last = snap["version"]
                self.render(snap)
        except Exception:
            pass                                    # the display must never raise into the program
        try:
            self.after(300, self.poll)
        except Exception:
            pass

    def render(self, snap):
        cur = snap["cur"]
        self.lbl_shop.configure(text=snap["shop"])
        for r in self._rows:
            r.configure(text="")
        if snap["mode"] == "idle":
            self.lbl_msg.configure(text=snap["promo"])
            self.lbl_total.configure(text="")
        elif snap["mode"] == "thanks":
            self.lbl_msg.configure(text="Thank you! Please come again.")
            self._rows[0].configure(text=f"Total paid:  {cur} {snap['total']:,.2f}")
            if snap["change"]:
                self._rows[1].configure(text=f"Change:  {cur} {snap['change']:,.2f}")
            self.lbl_total.configure(text="")
        else:
            self.lbl_msg.configure(text="")
            for r, (name, qty, unit, price, total) in zip(self._rows, snap["lines"]):
                r.configure(text=f"{name}   {qty:g}{(' ' + unit) if unit else ''} x {price:,.2f}   =  {total:,.2f}")
            if snap["hidden"]:
                self._rows[min(len(snap["lines"]), 8)].configure(text=f"... and {snap['hidden']} earlier item(s)")
            self.lbl_total.configure(text=f"TOTAL  {cur} {snap['total']:,.2f}")
