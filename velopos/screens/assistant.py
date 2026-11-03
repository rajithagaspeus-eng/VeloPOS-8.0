"""Ask VeloPOS: chat screen (full) and floating pop-up (compact) share the same ChatPanel."""
import customtkinter as ctk

from .. import assistant, assistant_i18n as I, voice
from ..dialogs import run_bg
from ..theme import C
from . import Screen


def label_for(setting):
    """Settings value (label or code) -> the label shown in the language menu."""
    if setting in I.LANG_LABELS:
        return setting
    return I.LANGS.get(setting, I.AUTO_LABEL)


class ChatPanel(ctk.CTkFrame):
    def __init__(self, parent, app, compact=False):
        super().__init__(parent, fg_color="transparent")
        self.app, self.compact, self._warned_voice = app, compact, False
        a = app
        self.wrap = 330 if compact else 640
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 4))
        self.lang_menu = ctk.CTkOptionMenu(top, values=[I.AUTO_LABEL] + list(I.LANGS.values()), command=self.set_lang,
                                           width=170 if compact else 220, fg_color=a.accent, button_color=a.accent)
        self.lang_menu.pack(side="left")
        self.lang_menu.set(label_for(a.s.get("assistant_lang")))
        self.speak_cb = ctk.CTkCheckBox(top, text="Speak answers", font=a.f(-1), text_color=C["text"], command=self.toggle_speak)
        self.speak_cb.pack(side="left", padx=12)
        if a.s.bool("feat_assistant_voice"):
            self.speak_cb.select()
        self.sc = ctk.CTkScrollableFrame(self, fg_color=C["surface"], border_color=C["border"], border_width=1, corner_radius=12)
        self.sc.pack(fill="both", expand=True, pady=4)
        self.chip_row = ctk.CTkFrame(self, fg_color="transparent")
        self.chip_row.pack(fill="x", pady=2)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.entry = ctk.CTkEntry(row, height=40, font=a.f(1), placeholder_text="Ask about sales, stock, credit...  (any language)")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self.ask(self.entry.get()))
        if a.s.bool("feat_voice_input"):
            a.btn(row, "Mic", "purple", self.listen, width=56, height=40).pack(side="left", padx=(0, 6))
        a.btn(row, "Send", "green", lambda: self.ask(self.entry.get()), width=80, height=40).pack(side="left")
        self.build_chips()
        self.add_bot(assistant.T(self.chip_lang(), "hello"), None)

    # ------------------------------------------------------------------ language
    def chip_lang(self):
        code = I.LANG_LABELS.get(label_for(self.app.s.get("assistant_lang")), "auto")
        return code if code in I.LANGS else "en"

    def set_lang(self, label):
        self.app.s.set_many({"assistant_lang": label})
        self.build_chips()

    def toggle_speak(self):
        self.app.s.set_many({"feat_assistant_voice": "1" if self.speak_cb.get() else "0"})

    def build_chips(self):
        for w in self.chip_row.winfo_children():
            w.destroy()
        per_row = 2 if self.compact else 5
        for i, (label, query) in enumerate(assistant.chips(self.chip_lang())):
            b = ctk.CTkButton(self.chip_row, text=label, height=28, corner_radius=14, font=self.app.f(-2, "bold"), fg_color="transparent",
                              border_width=1, border_color=self.app.accent, text_color=C["text"], hover_color=C["hover"],
                              command=lambda q=query: self.ask(q))
            b.grid(row=i // per_row, column=i % per_row, padx=3, pady=2, sticky="w")

    # ------------------------------------------------------------------ messages
    def bubble(self, text, mine, rtl=False):
        outer = ctk.CTkFrame(self.sc, fg_color="transparent")
        outer.pack(fill="x", pady=3, padx=6)
        bub = ctk.CTkFrame(outer, fg_color=self.app.accent if mine else C["bg"], corner_radius=14,
                           border_width=0 if mine else 1, border_color=C["border"])
        bub.pack(anchor="e" if (mine or rtl) else "w", padx=(50, 0) if mine else (0, 30))
        ctk.CTkLabel(bub, text=text, wraplength=self.wrap, justify="right" if rtl else "left", font=self.app.f(0),
                     text_color="white" if mine else C["text"]).pack(padx=12, pady=8)
        self.after(60, self._bottom)
        return bub

    def _bottom(self):
        try:
            self.sc._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def add_user(self, text):
        self.bubble(text, True)

    def add_bot(self, text, reply):
        rtl = bool(reply and reply.lang in I.RTL) or (reply is None and self.chip_lang() in I.RTL)
        bub = self.bubble(text, False, rtl)
        if reply is not None and reply.intent == "daily_summary":
            lang, summ = reply.lang, reply.data["summary"]
            row = ctk.CTkFrame(bub, fg_color="transparent")
            row.pack(padx=10, pady=(0, 8), anchor="w")
            self.app.btn(row, assistant.T(lang, "send_owner"), "green", lambda: self.app.daily_summary_now("chat"), height=30).pack(side="left", padx=3)
            self.app.btn(row, assistant.T(lang, "copy"), "accent",
                         lambda: (self.clipboard_clear(), self.clipboard_append(summ["text"])), height=30).pack(side="left", padx=3)

    def note(self, text):
        ctk.CTkLabel(self.sc, text=text, font=self.app.f(-2), text_color=C["muted"], wraplength=self.wrap, justify="left").pack(anchor="w", padx=10, pady=2)
        self.after(60, self._bottom)

    # ------------------------------------------------------------------ asking
    def ctx(self):
        a = self.app
        return assistant.Ctx(cur=a.cur, shop=a.s.get("shop_name"), user=a.user, is_admin=a.is_admin, can=a.can, lang=a.s.get("assistant_lang"), cfg=a.s)

    def ask(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.add_user(text)
        try:
            reply = assistant.respond(text, self.ctx())
        except Exception as e:                      # never crash the chat; show what went wrong
            reply = assistant.Reply(f"Sorry, something went wrong: {e}", "error", "en")
        self.add_bot(reply.text, reply)
        if self.app.s.bool("feat_assistant_voice"):
            voice.speak(reply.text, reply.lang, True, lambda st, lg=reply.lang: self._voice_done(st, lg))

    def _voice_done(self, status, lang):
        if status == "novoice" and not self._warned_voice:
            self._warned_voice = True
            try:
                self.after(0, lambda: self.note(assistant.T(lang, "no_voice", lang=I.LANGS[lang])))
            except Exception:
                pass

    def listen(self):
        ok, msg = voice.stt_available()
        if not ok:
            return self.note(msg)
        code = I.LANG_LABELS.get(label_for(self.app.s.get("assistant_lang")), "auto")
        self.note("Listening... speak now (audio is sent to Google for recognition).")

        def done(text, err):
            if err:
                self.note(str(err))
            else:
                self.ask(text)
        run_bg(self, lambda: voice.listen_once(code if code in I.LANGS else "en"), done)


class AssistantScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.heading(self, "Ask VeloPOS").pack(anchor="w", pady=(4, 6))
        ctk.CTkLabel(self, text="Works offline from your own shop data. Answers respect each user's permissions.",
                     font=app.f(-2), text_color=C["muted"]).pack(anchor="w")
        ChatPanel(self, app).pack(fill="both", expand=True, pady=6)


def open_popup(app):
    """Floating-button chat window (one instance)."""
    p = getattr(app, "_chat_popup", None)
    try:
        if p is not None and p.winfo_exists():
            p.deiconify()
            p.lift()
            return p
    except Exception:
        pass
    p = ctk.CTkToplevel(app)
    p.title("Ask VeloPOS")
    p.geometry("440x660")
    p.configure(fg_color=C["bg"])
    ChatPanel(p, app, compact=True).pack(fill="both", expand=True, padx=8, pady=8)
    app._chat_popup = p
    return p
