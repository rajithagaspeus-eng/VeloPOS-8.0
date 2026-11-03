import customtkinter as ctk

from .. import branding as B, services as svc, theme
from ..theme import C
from . import Screen


class AboutScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        card = a.card(self); card.pack(fill="both", expand=True, padx=30, pady=16)
        lg = a.logo(card, "about")
        if lg:
            lg.pack(pady=(20, 2))
        else:
            ctk.CTkLabel(card, text=B.DEV_COMPANY, font=a.f(9, "bold"), text_color=a.accent).pack(pady=(30, 2))
        ctk.CTkLabel(card, text="Global Enterprise Point of Sale & Inventory System  -  v7.2", font=a.f(1, "bold"), text_color=C["text"]).pack()
        ok = a.lic_status == "ACTIVATED"
        ctk.CTkLabel(card, text=("ACTIVE LIFETIME LICENSE" if ok else f"FREE TRIAL ({a.lic_days} days remaining)") + f"   |   Machine ID: {a.machine_id}",
                     font=a.f(0, "bold"), text_color=C["success"] if ok else C["warning"]).pack(pady=10)
        mid = ctk.CTkFrame(card, fg_color=C["surface2"], corner_radius=10); mid.pack(padx=50, pady=8, fill="x")
        theme.qr_or_image(mid, "about", f"https://wa.me/{B.DEV_WHATSAPP}", 130).pack(side="left", padx=20, pady=12)
        info = ctk.CTkFrame(mid, fg_color="transparent"); info.pack(side="left", padx=10)
        ctk.CTkLabel(info, text=f"Hotline / WhatsApp: {B.DEV_PHONE}", font=a.f(1, "bold"), text_color=C["text"]).pack(anchor="w", pady=2)
        ctk.CTkLabel(info, text=f"Email: {B.DEV_EMAIL}", font=a.f(0), text_color=C["text"]).pack(anchor="w", pady=2)
        row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(pady=10)
        a.btn(row, "Open Gumroad checkout", "pink", lambda: svc.open_url(B.DEV_WEBSITE), width=220).pack(side="left", padx=6)
        a.btn(row, "Keyboard shortcuts (F1)", "indigo", a.show_shortcuts, width=200).pack(side="left", padx=6)
        a.btn(row, "Check for updates", "teal", lambda: a.start_update_check(force=True), width=170).pack(side="left", padx=6)
        a.btn(row, "Chat on WhatsApp", "green", lambda: svc.open_url(f"https://wa.me/{B.DEV_WHATSAPP}"), width=190).pack(side="left", padx=6)
        if not ok:
            a.btn(row, "Payment info & Activate", "accent", lambda: a.show_activation(True), width=230).pack(side="left", padx=6)
        warn = ctk.CTkFrame(card, fg_color=C["danger_bg"], corner_radius=8); warn.pack(padx=50, pady=14, fill="x")
        ctk.CTkLabel(warn, text=B.DEV_COPYRIGHT, font=a.f(0, "bold"), text_color=C["danger"]).pack(pady=(8, 2))
        ctk.CTkLabel(warn, text=B.DEV_WARNING, font=a.f(-2), text_color=C["text"], wraplength=800).pack(padx=16, pady=(2, 8))
