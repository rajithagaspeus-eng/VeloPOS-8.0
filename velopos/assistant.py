"""Offline assistant ("Ask VeloPOS"): keyword/regex + fuzzy intent engine that answers from the local database.
No internet, no API, no UI code (headless-testable). Permissions are respected: the engine never answers with
data the logged-in user may not see in the normal screens (profit/sales totals need 'reports', expenses need 'expenses').
"""
import difflib
import html as _html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from . import assistant_i18n as I, database as dbm, otp, services as svc

# ====================================================================== text normalisation
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ـ": None})
_DROP = {"\u200d", "\u200c", "\u093c"}          # ZWJ, ZWNJ, Devanagari nukta (typed inconsistently)


def norm(s):
    """lower-case, strip Latin accents, unify Arabic/Hindi/Sinhala spelling variants, drop punctuation."""
    s = unicodedata.normalize("NFC", str(s)).lower().translate(_AR)
    out = []
    for ch in s:
        o = ord(ch)
        if ch in _DROP or 0x064B <= o <= 0x065F or o == 0x0670:
            continue
        if o < 0x250 or 0x1E00 <= o <= 0x1EFF:
            ch = unicodedata.normalize("NFD", ch)[0]
        out.append(ch if unicodedata.category(ch)[0] in "LMN" else " ")
    return " ".join("".join(out).split())


def _latin(kw):
    return all(ord(c) < 0x250 for c in kw if c.isalpha())


def _prep(words):
    seen, out = set(), []
    for w in words:
        k = norm(w)
        if k and k not in seen:
            seen.add(k)
            out.append((k, _latin(k), k.count(" ") + 1))
    return out


KW = {k: _prep(v) for k, v in I.KW.items()}
PERIOD_KW = {k: _prep(v) for k, v in I.PERIODS.items()}
HOW = _prep(I.HOW_MARKERS)
# extra multi-word topic phrases so that "how do I cancel a bill" is not mistaken for plain "bill"
_TOPIC_EXTRA = {"void": ["cancel a bill", "cancel the bill", "void a bill", "void the bill", "delete a bill", "bill eka cancel"],
                "printer": ["print a bill", "print receipt", "print a receipt", "reprint", "print the receipt"],
                "bill": ["make a bill", "create a bill", "bill eka hadanne", "new bill"]}
TOPIC_KW = {k: _prep(v + _TOPIC_EXTRA.get(k, [])) for k, v in I.TOPIC_KW.items()}


def _ratio(a, b):
    sm = difflib.SequenceMatcher(None, a, b)
    return sm.ratio() if sm.real_quick_ratio() >= 0.8 and sm.quick_ratio() >= 0.8 else 0.0


def _hit(kw, latin, text, padded, tokens):
    if latin:
        if " " in kw:
            return 1.0 if f" {kw} " in padded else 0.0
        if kw in tokens:
            return 1.0
        if len(kw) >= 4:
            for t in tokens:
                if len(t) >= 4 and abs(len(t) - len(kw)) <= 2 and _ratio(t, kw) >= 0.84:
                    return 0.8
        return 0.0
    return 1.0 if kw in text else 0.0


def _score(table, text):
    padded, tokens = f" {text} ", text.split()
    res = {}
    for key in table:
        s = sum(_hit(k, lat, text, padded, tokens) * nw for k, lat, nw in table[key])
        if s:
            res[key] = s
    return res


def _exact_hit(kw, latin, text, padded, tokens):
    if latin:
        return (f" {kw} " in padded) if " " in kw else (kw in tokens)
    return kw in text


# ====================================================================== language detection
def detect_lang(text):
    counts = {"si": 0, "ta": 0, "hi": 0, "ar": 0}
    for ch in text:
        o = ord(ch)
        if 0x0D80 <= o <= 0x0DFF:
            counts["si"] += 1
        elif 0x0B80 <= o <= 0x0BFF:
            counts["ta"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["hi"] += 1
        elif 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
            counts["ar"] += 1
    best = max(counts, key=counts.get)
    if counts[best]:
        return best
    toks = set(norm(text).split())
    if toks & I.SINGLISH_WORDS:
        return "si"
    if toks & I.SPANISH_ONLY or re.search(r"[ñ¿¡áéíóú]", text.lower()):
        return "es"
    return "en"


def resolve_lang(setting, text):
    code = I.LANG_LABELS.get(setting, setting)
    return code if code in I.LANGS else detect_lang(text)


def T(lang, key, **kw):
    s = I.STR.get(lang, {}).get(key) or I.STR["en"][key]
    return s.format(**kw) if kw else s


# ====================================================================== context / reply
@dataclass
class Ctx:
    cur: str = "Rs."
    shop: str = ""
    user: str = ""
    is_admin: bool = True
    can: Callable = field(default_factory=lambda: (lambda p: True))
    lang: str = "English"                  # the Settings value: a language label, a code, or "Auto (match my question)"
    now: datetime = None
    cfg: object = None

    def __post_init__(self):
        self.now = self.now or datetime.now()
        self.cfg = self.cfg or dbm.settings


@dataclass
class Reply:
    text: str
    intent: str
    lang: str
    data: dict = field(default_factory=dict)


PERM = {"sales": "reports", "profit": "reports", "top_sellers": "reports", "expenses": "expenses", "daily_summary": "reports", "payables": "reports"}


def fmt(x):
    return f"{x:,.2f}"


def date_range(period, now):
    d = now.date()
    if period == "yesterday":
        d = d - timedelta(days=1)
        return d, d
    if period == "week":
        return d - timedelta(days=6), d
    if period == "month":
        return d.replace(day=1), d
    return d, d


def detect_period(text, default="today"):
    padded, tokens = f" {text} ", text.split()
    for p in ("yesterday", "today", "week", "month"):
        if any(_exact_hit(k, lat, text, padded, tokens) for k, lat, _ in PERIOD_KW[p]):
            return p
    return default


# ====================================================================== product lookup (fuzzy)
_STOP = {"of", "the", "is", "are", "in", "do", "we", "have", "a", "an", "for", "item", "items", "product", "show", "tell", "me", "what", "whats",
         "check", "please", "there", "any", "much", "many", "how", "got", "still", "da", "eke", "ekak", "eka", "ekata", "mokakda", "wala", "wage", "gana",
         "වල", "වලට", "ගැන", "ද", "එකේ", "එක", "පුළුවන්", "මට", "කියන්න", "என்ன", "உள்ளது", "எவ்வளவு", "பற்றி", "का", "की", "के", "है", "में", "क्या", "बताओ",
         "ما", "هو", "من", "في", "هل", "لي", "اخبرني", "de", "el", "la", "los", "las", "del", "un", "una", "en", "que", "me", "dime", "cuantas", "por", "mas"}
_REMOVE_LATIN = set()
_REMOVE_NONLATIN = []
for _tbl in list(KW.values()) + list(PERIOD_KW.values()) + [HOW]:
    for _k, _lat, _ in _tbl:
        if _lat:
            _REMOVE_LATIN.update(_k.split())
        else:
            _REMOVE_NONLATIN.append(_k)
_REMOVE_LATIN |= {norm(w) for w in _STOP if _latin(w)}


def entity_text(text):
    keep = []
    for t in text.split():
        if t in _REMOVE_LATIN or t in _STOP:
            continue
        if not _latin(t) and any(k in t for k in _REMOVE_NONLATIN):
            continue
        keep.append(t)
    return " ".join(keep)


def find_products(query, limit=3):
    qn = norm(query)
    if not qn:
        return []
    qtok = [t for t in qn.split() if len(t) >= 2]
    with dbm.db() as c:
        rows = c.execute("SELECT barcode, name_en, name_local, keywords, stock_qty, selling_price FROM products").fetchall()
    scored = []
    for r in rows:
        if r["barcode"].lower() == qn.replace(" ", ""):
            scored.append((1.0, r))
            continue
        names = [norm(r["name_en"]), norm(r["name_local"] or "")]
        names += [norm(k) for k in (r["keywords"] or "").replace(";", ",").split(",") if k.strip()]
        best = 0.0
        for n in names:
            if not n:
                continue
            if qn == n:
                s = 1.0
            elif qn in n or (len(n) >= 3 and n in qn):
                s = 0.92
            else:
                s = _ratio(qn, n)
                ntok = n.split()
                if qtok and ntok:
                    per = [max(_ratio(q, t) if len(q) >= 3 else (1.0 if q == t else 0.0) for t in ntok) for q in qtok]
                    s = max(s, 0.95 * sum(per) / len(per))
            best = max(best, s)
        if best >= 0.66:
            scored.append((best, r))
    scored.sort(key=lambda x: (-x[0], x[1]["name_en"]))
    if scored and scored[0][0] >= 0.92:
        scored = [x for x in scored if x[0] >= 0.92]
    return [r for _, r in scored[:limit]]


# ====================================================================== data queries
def _level(cfg):
    return max(0, cfg.int("low_stock_level", 5))


def low_stock_rows(cfg, limit=None):
    with dbm.db() as c:
        rows = c.execute("SELECT barcode, name_en, name_local, stock_qty FROM products WHERE stock_qty <= ? ORDER BY stock_qty, name_en", (_level(cfg),)).fetchall()
    return rows if limit is None else rows[:limit]


def expiry_rows(now=None):
    """Batch-aware (Phase 6.2): per batch when batch tracking is ON, else products.expiry_date."""
    return svc.expiry_alert_rows()


def top_sellers(df, dt, limit=5):
    with dbm.db() as c:
        return c.execute("SELECT si.item_name n, SUM(si.qty) q, SUM(si.total) t FROM sale_items si JOIN sales s ON s.invoice_no = si.invoice_no "
                         "WHERE s.date BETWEEN ? AND ? AND s.status = 'OK' GROUP BY si.barcode ORDER BY t DESC LIMIT ?", (df, dt, limit)).fetchall()


def credit_rows(limit=5):
    with dbm.db() as c:
        rows = c.execute("SELECT name, credit_balance FROM customers WHERE credit_balance > 0 ORDER BY credit_balance DESC").fetchall()
    return rows[:limit], sum(r["credit_balance"] for r in rows)


def _shift_pick(ctx, status):
    with dbm.db() as c:
        q, args = "SELECT * FROM shifts WHERE status=?", [status]
        if not ctx.is_admin:
            q, args = q + " AND cashier=?", args + [ctx.user]
        return c.execute(q + " ORDER BY id DESC LIMIT 1", args).fetchone()


# ====================================================================== answer handlers
def _period_label(lang, p):
    return T(lang, "p_" + p)


def h_sales(ctx, lang, text, focus="sales"):
    p = detect_period(text)
    df, dt = (d.strftime("%Y-%m-%d") for d in date_range(p, ctx.now))
    rd = svc.report_data(df, dt)
    per = _period_label(lang, p)
    if not rd["bills"] and not rd["returns"]:
        return T(lang, "no_sales", period=per), rd
    sales = T(lang, "sales", period=per, cur=ctx.cur, sales=fmt(rd["sales"]), bills=rd["bills"], returns=fmt(rd["returns"]), revenue=fmt(rd["revenue"]))
    prof = T(lang, "profit", period=per, cur=ctx.cur, exp=fmt(rd["expenses"]), profit=fmt(rd["profit"]))
    return "\n".join([prof, sales] if focus == "profit" else [sales, prof]), rd


def h_top(ctx, lang, text):
    p = detect_period(text, "week")
    df, dt = (d.strftime("%Y-%m-%d") for d in date_range(p, ctx.now))
    rows = top_sellers(df, dt)
    per = _period_label(lang, p)
    if not rows:
        return T(lang, "no_sales", period=per), {}
    lines = [T(lang, "top_head", period=per)]
    lines += [T(lang, "top_line", i=i, name=r["n"], qty=f"{r['q']:g}", cur=ctx.cur, total=fmt(r["t"])) for i, r in enumerate(rows, 1)]
    return "\n".join(lines), {"rows": [tuple(r) for r in rows]}


def h_credit(ctx, lang, text):
    rows, total = credit_rows()
    if not rows:
        return T(lang, "credit_none"), {}
    lines = [T(lang, "credit_head", cur=ctx.cur, total=fmt(total))]
    lines += [T(lang, "credit_line", i=i, name=r["name"], cur=ctx.cur, amount=fmt(r["credit_balance"])) for i, r in enumerate(rows, 1)]
    return "\n".join(lines), {"total": total}


def h_payables(ctx, lang, text):
    rows = [r for r in svc.supplier_balances() if r["balance"] > 0.004]
    if not rows:
        return T(lang, "payables_none"), {}
    total = sum(r["balance"] for r in rows)
    lines = [T(lang, "payables_head", cur=ctx.cur, total=fmt(total))]
    lines += [T(lang, "payables_line", i=i, name=r["name"], cur=ctx.cur, amount=fmt(r["balance"])) for i, r in enumerate(rows[:8], 1)]
    return "\n".join(lines), {"total": total}


def h_expenses(ctx, lang, text):
    p = detect_period(text)
    df, dt = (d.strftime("%Y-%m-%d") for d in date_range(p, ctx.now))
    per = _period_label(lang, p)
    with dbm.db() as c:
        total = c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date BETWEEN ? AND ?", (df, dt)).fetchone()[0]
        cats = c.execute("SELECT category c, SUM(amount) a FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY a DESC LIMIT 5", (df, dt)).fetchall()
    if not cats:
        return T(lang, "exp_none", period=per), {"total": 0}
    lines = [T(lang, "exp_head", period=per, cur=ctx.cur, total=fmt(total))]
    lines += [T(lang, "exp_line", cat=r["c"] or "-", cur=ctx.cur, amount=fmt(r["a"])) for r in cats]
    return "\n".join(lines), {"total": total}


def h_low(ctx, lang, text):
    lvl = _level(ctx.cfg)
    rows = low_stock_rows(ctx.cfg)
    if not rows:
        return T(lang, "low_none", lvl=lvl), {}
    lines = [T(lang, "low_head", lvl=lvl, n=len(rows))]
    lines += [f"- {r['name_en']}: {r['stock_qty']:g}" for r in rows[:10]]
    if len(rows) > 10:
        lines.append(T(lang, "low_more", n=len(rows) - 10))
    return "\n".join(lines), {"count": len(rows)}


def h_expiry(ctx, lang, text):
    rows = expiry_rows()
    if not rows:
        return T(lang, "expiry_none", days=30), {}
    lines = [T(lang, "expiry_head", days=30, n=len(rows))]
    for days, r in rows[:10]:
        st = T(lang, "st_expired") if days < 0 else T(lang, "st_soon", d=days)
        lines.append("- " + T(lang, "expiry_line", name=r["name_en"], date=r["expiry_date"], state=st))
    if len(rows) > 10:
        lines.append(T(lang, "low_more", n=len(rows) - 10))
    return "\n".join(lines), {"count": len(rows)}


def h_shift(ctx, lang, text):
    if not ctx.cfg.bool("feat_shift"):
        return T(lang, "shift_off"), {}
    op = _shift_pick(ctx, "OPEN")
    if op:
        sm = svc.shift_summary(op["id"])
        return T(lang, "shift_open", id=op["id"], cashier=op["cashier"], since=op["opened_at"].replace("T", " ")[:16], cur=ctx.cur,
                 sales=fmt(sm["sales_total"]), expected=fmt(sm["expected"])), {"open": True}
    last = _shift_pick(ctx, "CLOSED")
    if last:
        return T(lang, "shift_closed", id=last["id"], cashier=last["cashier"], at=(last["closed_at"] or "").replace("T", " ")[:16], cur=ctx.cur,
                 diff=f"{last['difference'] or 0:+,.2f}"), {"open": False}
    return T(lang, "shift_none"), {}


def h_stock(ctx, lang, text):
    cand = entity_text(text)
    matches = find_products(cand) if cand else []
    if not matches and cand != text:
        matches = find_products(text) if len(text.split()) <= 4 else []
    if not cand and not matches:
        return T(lang, "item_which"), {}
    if not matches:
        return T(lang, "item_unknown", q=cand or text), {}
    lvl = _level(ctx.cfg)

    def line(r):
        q = r["stock_qty"] or 0
        key = "stock_zero" if q <= 0 else ("stock_low" if q <= lvl else "stock_item")
        return T(lang, key, name=r["name_en"], qty=f"{q:g}")
    if len(matches) == 1:
        return line(matches[0]), {"barcode": matches[0]["barcode"]}
    return "\n".join([T(lang, "item_multi")] + ["- " + line(r) for r in matches]), {"count": len(matches)}


# ====================================================================== daily summary
def build_daily_summary(ctx, lang=None, day=None):
    """-> dict(title, text, html, lang). Money lines only when ctx.can('reports'), so a cashier never sees more than the screens allow."""
    lang = lang if lang in I.LANGS else "en"
    day = day or ctx.now.date()
    ds = day.strftime("%Y-%m-%d")
    full = ctx.can("reports")
    rd = svc.report_data(ds, ds)
    title = T(lang, "sum_title", shop=ctx.shop or ctx.cfg.get("shop_name"), date=ds)
    lines = [T(lang, "sum_sales", cur=ctx.cur, sales=fmt(rd["sales"]), bills=rd["bills"])]
    if full:
        lines.append(T(lang, "sum_returns", cur=ctx.cur, returns=fmt(rd["returns"])))
        lines.append(T(lang, "sum_expenses", cur=ctx.cur, exp=fmt(rd["expenses"])))
        lines.append(T(lang, "sum_profit", cur=ctx.cur, profit=fmt(rd["profit"])))
        if rd["methods"]:
            lines.append(T(lang, "sum_methods", parts=" | ".join(f"{m} {fmt(v)}" for m, v in sorted(rd["methods"].items()))))
        tops = top_sellers(ds, ds, 3)
        if tops:
            lines.append(T(lang, "sum_top"))
            lines += [f"  {i}. {r['n']} - {r['q']:g} ({ctx.cur} {fmt(r['t'])})" for i, r in enumerate(tops, 1)]
        _, owed = credit_rows()
        if owed:
            lines.append(T(lang, "sum_credit", cur=ctx.cur, total=fmt(owed)))
        pay = svc.payables_total()
        if pay:
            lines.append(T(lang, "sum_payables", cur=ctx.cur, total=fmt(pay)))
        if ctx.cfg.bool("feat_vat"):
            lines.append(T(lang, "sum_vat", cur=ctx.cur, vat=fmt(rd["vat"])))
    low = len(low_stock_rows(ctx.cfg))
    if low:
        lines.append(T(lang, "sum_low", n=low))
    exp = len(expiry_rows())
    if exp:
        lines.append(T(lang, "sum_expiry", n=exp))
    if ctx.cfg.bool("feat_shift"):
        op = _shift_pick(ctx, "OPEN")
        if op:
            lines.append(T(lang, "sum_shift_open", id=op["id"], cashier=op["cashier"]))
        else:
            last = _shift_pick(ctx, "CLOSED")
            if last:
                lines.append(T(lang, "sum_shift_closed", id=last["id"], cashier=last["cashier"], cur=ctx.cur, diff=f"{last['difference'] or 0:+,.2f}"))
    footer = T(lang, "sum_footer")
    text = "\n".join([title, "=" * min(40, len(title)), *lines, "", footer])
    rtl = lang in I.RTL
    body = "".join(f"<p style='margin:4px 0'>{_html.escape(l).replace('  ', '&nbsp;&nbsp;')}</p>" for l in lines)
    page = (f"<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#111' dir='{'rtl' if rtl else 'ltr'}'>"
            f"<h2 style='margin:0 0 8px'>{_html.escape(title)}</h2>{body}"
            f"<p style='color:#777;font-size:12px;margin-top:14px'>{_html.escape(footer)}</p></body></html>")
    return dict(title=title, text=text, html=page, lang=lang, data=rd)


def deliver_summary(summary, channel, cfg=None):
    """Email -> sent now ('email', address). WhatsApp -> ('whatsapp', wa.me link) that the caller opens (the owner presses Send)."""
    cfg = cfg or dbm.settings
    if str(channel).lower().startswith("email"):
        to = cfg.get("owner_email").strip()
        otp.send_email(to, summary["title"], summary["text"], html=summary["html"])
        return "email", to
    text = summary["text"]
    return "whatsapp", otp.whatsapp_link(cfg.get("owner_whatsapp"), text if len(text) <= 1500 else text[:1497] + "...")


def summary_due(cfg, now=None):
    """Day-end summary: switched on, the set time has passed and it has not been sent for today yet."""
    now = now or datetime.now()
    if not (cfg.bool("feat_daily_summary") and cfg.bool("feat_summary_dayend")):
        return False
    if cfg.get("last_summary_date") == now.strftime("%Y-%m-%d"):
        return False
    try:
        hh, mm = (int(x) for x in cfg.get("summary_time", "21:00").split(":"))
    except ValueError:
        hh, mm = 21, 0
    return (now.hour, now.minute) >= (hh, mm)


# ====================================================================== main entry
def chips(lang):
    return I.CHIPS.get(lang, I.CHIPS["en"])


def topic_list(lang):
    return ", ".join(I.TOPIC_LABEL[lang])


def respond(text, ctx):
    lang = resolve_lang(ctx.lang, text)
    n = norm(text)
    if not n:
        return Reply(T(lang, "hello"), "greeting", lang)
    padded, tokens = f" {n} ", n.split()
    marker = any(_exact_hit(k, lat, n, padded, tokens) for k, lat, _ in HOW)
    topics = _score(TOPIC_KW, n)
    scores = _score(KW, n)
    data_scores = {k: v for k, v in scores.items() if k not in ("help", "greeting", "thanks")}

    if marker and topics:
        best = max(topics, key=lambda k: (topics[k], -I.TOPIC_ORDER.index(k)))
        return Reply(I.TOPIC_TEXT[lang][best], "howto", lang, {"topic": best})
    if marker and not data_scores:
        return Reply(T(lang, "howto_which", topics=topic_list(lang)), "howto", lang)

    pool = data_scores or scores
    if not pool:
        found = find_products(entity_text(n) or n) if len(tokens) <= 4 else []
        if found:
            txt, data = h_stock(ctx, lang, n)
            return Reply(txt, "stock_of", lang, data)
        return Reply(T(lang, "unknown"), "unknown", lang)
    intent = max(pool, key=lambda k: (pool[k], -I.INTENT_ORDER.index(k)))

    if intent == "greeting":
        return Reply(T(lang, "hello"), "greeting", lang)
    if intent == "thanks":
        return Reply(T(lang, "thanks"), "thanks", lang)
    if intent == "help":
        return Reply(T(lang, "hello") + "\n\n" + T(lang, "howto_which", topics=topic_list(lang)), "help", lang)
    perm = PERM.get(intent)
    if perm and not ctx.can(perm):
        return Reply(T(lang, "denied"), "denied", lang, {"intent": intent})

    if intent in ("sales", "profit"):
        txt, data = h_sales(ctx, lang, n, "profit" if intent == "profit" else "sales")
    elif intent == "top_sellers":
        txt, data = h_top(ctx, lang, n)
    elif intent == "payables":
        txt, data = h_payables(ctx, lang, n)
    elif intent == "credit_owed":
        txt, data = h_credit(ctx, lang, n)
    elif intent == "expenses":
        txt, data = h_expenses(ctx, lang, n)
    elif intent == "low_stock":
        txt, data = h_low(ctx, lang, n)
    elif intent == "expiry":
        txt, data = h_expiry(ctx, lang, n)
    elif intent == "shift_status":
        txt, data = h_shift(ctx, lang, n)
    elif intent == "daily_summary":
        s = build_daily_summary(ctx, lang)
        return Reply(T(lang, "summary_ready") + "\n\n" + s["text"], "daily_summary", lang, {"summary": s})
    else:
        txt, data = h_stock(ctx, lang, n)
    return Reply(txt, intent, lang, data)
