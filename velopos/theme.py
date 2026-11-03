"""
One colour-token system. Every token is a (light, dark) pair, which CustomTkinter switches
automatically, so text is ALWAYS readable (the old white-theme faint-text problem is gone).
"""
import customtkinter as ctk
from tkinter import ttk

C = {
    "bg":        ("#F1F5F9", "#0B1220"),
    "surface":   ("#FFFFFF", "#111A2E"),
    "surface2":  ("#F8FAFC", "#182238"),
    "border":    ("#CBD5E1", "#26324D"),
    "text":      ("#0F172A", "#F1F5F9"),
    "muted":     ("#475569", "#94A3B8"),
    "success":   ("#15803D", "#34D399"),
    "danger":    ("#B91C1C", "#F87171"),
    "warning":   ("#B45309", "#FBBF24"),
    "danger_bg": ("#FEE2E2", "#3B1219"),
    "hover":     ("#E2E8F0", "#1E2A44"),
}
ACCENTS = {"Blue": "#2563EB", "Emerald": "#059669", "Purple": "#7C3AED", "Orange": "#EA580C"}
# solid button colours: white text is readable on all of them in both modes
BTN = {"green": "#15803D", "red": "#B91C1C", "amber": "#B45309", "gray": "#475569",
       "blue": "#2563EB", "purple": "#7C3AED", "teal": "#0F766E", "pink": "#BE185D", "indigo": "#4F46E5"}


def apply_ttk(accent, family, size):
    dark = ctk.get_appearance_mode() == "Dark"
    bg, fg = ("#111A2E", "#F1F5F9") if dark else ("#FFFFFF", "#0F172A")
    st = ttk.Style()
    st.theme_use("clam")
    st.configure("Treeview", background=bg, fieldbackground=bg, foreground=fg, borderwidth=0,
                 rowheight=max(32, size * 2 + 4), font=(family, max(10, size - 1)))
    st.configure("Treeview.Heading", background=accent, foreground="#FFFFFF", relief="flat",
                 font=(family, size, "bold"))
    st.map("Treeview", background=[("selected", accent)], foreground=[("selected", "#FFFFFF")])
    st.map("Treeview.Heading", background=[("active", accent)])


def style_tree_tags(tree):
    dark = ctk.get_appearance_mode() == "Dark"
    tree.tag_configure("danger", background="#4C1D1D" if dark else "#FEE2E2",
                       foreground="#FECACA" if dark else "#991B1B")


def qr_canvas(parent, data, size=120):
    """Scannable QR if the `qrcode` package is installed; otherwise a text placeholder."""
    import tkinter as tk
    cv = tk.Canvas(parent, width=size, height=size, bg="white", highlightthickness=1)
    try:
        import qrcode
        q = qrcode.QRCode(version=1, box_size=3, border=1)
        q.add_data(data)
        q.make(fit=True)
        m = q.get_matrix()
        cell = (size - 6) / len(m)
        for r, row in enumerate(m):
            for c, on in enumerate(row):
                if on:
                    cv.create_rectangle(3 + c * cell, 3 + r * cell, 3 + (c + 1) * cell,
                                        3 + (r + 1) * cell, fill="black", outline="black")
    except Exception:
        cv.create_text(size // 2, size // 2, text="pip install\nqrcode", fill="black")
    return cv


def qr_or_image(parent, kind, data, size=150):
    """The owner's own QR picture (qr_codes/qr_<kind>.*) when it exists, otherwise a QR drawn from `data`."""
    from . import assets
    p = assets.qr_path(kind)
    if p:
        r = assets.load_image(p, target_h=size, target_w=size)
        if r:
            return ctk.CTkLabel(parent, image=r[0], text="", width=r[1][0], height=r[1][1])
    return qr_canvas(parent, data, size)
