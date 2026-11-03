"""Item grid for the Billing screen: search + category chips + picture cards + pages. Picking a card calls on_pick(product_row)."""
import math

import customtkinter as ctk

from .. import services as svc, thumbs
from ..theme import C

CARD_W, CARD_H, IMG = 150, 142, 80


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


class ItemGrid(ctk.CTkFrame):
    def __init__(self, parent, app, on_pick, price_of, pname):
        super().__init__(parent, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=12)
        self.app, self.on_pick, self.price_of, self.pname = app, on_pick, price_of, pname
        self.cols = _int(app.s.get("grid_cols"), 2, 4, 3)
        self.size = _int(app.s.get("grid_page_size"), 4, 40, 12)
        self.category, self.page, self.text, self._job, self._refs = None, 0, "", None, []
        a = app
        self.search = ctk.CTkEntry(self, height=34, font=a.f(0), placeholder_text="Search items...")
        self.search.pack(fill="x", padx=8, pady=(8, 4))
        self.search.bind("<KeyRelease>", self._typed)
        self.chip_bar = None
        if a.s.bool("feat_categories"):
            self.chip_bar = ctk.CTkScrollableFrame(self, orientation="horizontal", height=46, fg_color="transparent")
            self.chip_bar.pack(fill="x", padx=6)
        self.cards = ctk.CTkFrame(self, fg_color="transparent")
        self.cards.pack(fill="both", expand=True, padx=6, pady=4)
        pager = ctk.CTkFrame(self, fg_color="transparent")
        pager.pack(fill="x", padx=8, pady=(0, 8))
        self.btn_prev = a.btn(pager, "< Prev", "gray", self.prev_page, width=80, height=30)
        self.btn_prev.pack(side="left")
        self.lbl_page = ctk.CTkLabel(pager, text="", font=a.f(-1, "bold"), text_color=C["muted"])
        self.lbl_page.pack(side="left", expand=True)
        self.btn_next = a.btn(pager, "Next >", "gray", self.next_page, width=80, height=30)
        self.btn_next.pack(side="right")
        self.build_chips()
        self.reload()

    # ------------------------------------------------------------------ chips
    def build_chips(self):
        if self.chip_bar is None:
            return
        for w in self.chip_bar.winfo_children():
            w.destroy()
        counts = svc.category_counts()
        total = sum(counts.values())
        items = [("All", None, total)] + [(n, n, k) for n, k in counts.items() if n and k] + ([("Uncategorised", "", counts[""])] if counts.get("") and any(counts[n] for n in counts if n) else [])
        for label, value, n in items:
            on = self.category == value
            ctk.CTkButton(self.chip_bar, text=f"{label} ({n})", height=28, corner_radius=14, font=self.app.f(-2, "bold"),
                          fg_color=self.app.accent if on else "transparent", border_width=1, border_color=self.app.accent,
                          text_color="white" if on else C["text"], hover_color=C["hover"],
                          command=lambda v=value: self.set_category(v)).pack(side="left", padx=3, pady=4)

    def set_category(self, value):
        self.category, self.page = value, 0
        self.build_chips()
        self.reload()

    # ------------------------------------------------------------------ search / paging
    def _typed(self, ev=None):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(250, self._search_now)

    def _search_now(self):
        self._job, self.text, self.page = None, self.search.get().strip(), 0
        self.reload()

    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.reload()

    def next_page(self):
        self.page += 1
        self.reload()

    # ------------------------------------------------------------------ cards
    def reload(self):
        a = self.app
        rows, total = svc.list_products(self.text, self.category, self.size, self.page * self.size)
        pages = max(1, math.ceil(total / self.size))
        if self.page >= pages:                                  # e.g. after the filter changed
            self.page = pages - 1
            rows, total = svc.list_products(self.text, self.category, self.size, self.page * self.size)
        for w in self.cards.winfo_children():
            w.destroy()
        self._refs = []
        low = svc.low_stock_level()
        for i, r in enumerate(rows):
            pil = thumbs.CACHE.get(svc.product_image_path(r), IMG, r["name_en"])
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(IMG, IMG))
            self._refs.append(img)
            qty = r["stock_qty"] or 0
            name = self.pname(r)
            name = name if len(name) <= 22 else name[:21] + "…"
            tag = "  OUT" if qty <= 0 else (f"  ({qty:g} left)" if qty <= low else "")
            ctk.CTkButton(self.cards, text=f"{name}\n{a.cur} {self.price_of(r):,.2f}{tag}", image=img, compound="top", width=CARD_W, height=CARD_H,
                          fg_color=C["surface2"], hover_color=C["hover"], border_width=1, border_color=C["border"], corner_radius=10,
                          text_color=C["muted"] if qty <= 0 else C["text"], font=a.f(-2, "bold"),
                          command=lambda row=r: self.on_pick(row)).grid(row=i // self.cols, column=i % self.cols, padx=3, pady=3)
        self.lbl_page.configure(text=f"Page {self.page + 1} / {pages}   ({total} items)")
        self.btn_prev.configure(state="normal" if self.page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.page + 1 < pages else "disabled")
