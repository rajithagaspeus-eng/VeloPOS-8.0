"""
Receipt printing engine.

Thermal (80mm / 58mm): the receipt is DRAWN AS A FULL-WIDTH IMAGE and sent as an ESC/POS raster, so it always
fills the whole paper (fixes the "thin strip in the middle" problem) and Sinhala/Tamil fonts print correctly.
Supports Xprinter / Epson / other ESC/POS printers over: Windows RAW, Windows driver, LAN (IP:9100), COM/Bluetooth.
A4 / A5 (and "Browser only" mode) use an HTML invoice that opens the browser print dialog.
Cash drawer: ESC/POS kick pulse, controlled by Settings -> Printing -> "Cash drawer".
"""
import html as _html
import os
import socket
import struct
import threading
import webbrowser
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps, features

from . import database as dbm

BRANDS = ["Xprinter", "Epson", "Other ESC/POS"]
PROFILES = {  # printable width in dots (203 dpi). Override in Settings if your model differs.
    "Xprinter": {"80mm": 576, "58mm": 384},
    "Epson": {"80mm": 576, "58mm": 384},
    "Other ESC/POS": {"80mm": 576, "58mm": 384},
}
MODES = ["Windows RAW (ESC/POS)", "Windows driver (any printer)", "LAN / Network (IP)",
         "COM / Bluetooth serial", "Browser only"]
CUTS = {"Partial cut (GS V 66)": b"\x1d\x56\x42\x00", "Full cut (GS V 0)": b"\x1d\x56\x00",
        "Partial cut (GS V 1)": b"\x1d\x56\x01"}
DRAWER_WHEN = ["Cash sales only", "All sales", "Manual button only"]
RECEIPT_FONTS = ["Nirmala UI", "Iskoola Pota", "Segoe UI", "Arial"]


class Cfg:
    """Settings view with temporary overrides (used by the Test-print buttons before saving)."""
    def __init__(self, over=None):
        self.o = over or {}

    def get(self, k, default=""):
        return self.o[k] if k in self.o else dbm.settings.get(k, default)

    def bool(self, k):
        return str(self.get(k, "0")) == "1"

    def int(self, k, d=0):
        try:
            return int(float(self.get(k, d)))
        except (TypeError, ValueError):
            return d


# ------------------------------------------------------------------ fonts & shaping
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_DIRS = [_WIN, "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/noto"]
FONT_FILES = {
    "Nirmala UI": (["nirmala.ttf", "nirmala.ttc"], ["nirmalab.ttf", "nirmala.ttc"]),
    "Iskoola Pota": (["iskpota.ttf"], ["iskpotab.ttf"]),
    "Segoe UI": (["segoeui.ttf"], ["segoeuib.ttf"]),
    "Arial": (["arial.ttf"], ["arialbd.ttf"]),
}
_FALLBACK = (["DejaVuSans.ttf", "LiberationSans-Regular.ttf"], ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"])


def _find(names):
    for n in names:
        for d in _DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def load_font(name, size, bold=False):
    reg, bld = FONT_FILES.get(name, _FALLBACK)
    path = _find(bld if bold else reg) or _find(_FALLBACK[1 if bold else 0])
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def is_complex(text):
    return any(0x0900 <= ord(c) <= 0x0DFF or 0x0600 <= ord(c) <= 0x06FF for c in text)


def raqm_ok():
    try:
        return features.check("raqm")
    except Exception:
        return False


def gdi_ok():
    if os.name != "nt":
        return False
    try:
        import win32ui  # noqa: F401
        return True
    except Exception:
        return False


def shaping_status():
    if raqm_ok():
        return "Sinhala/Tamil shaping: OK (Raqm)"
    if gdi_ok():
        return "Sinhala/Tamil shaping: using Windows GDI (print a test to verify)"
    return "Sinhala/Tamil shaping: NOT available (English prints fine; install pywin32 for Sinhala)"


class PILText:
    def __init__(self, fname, S):
        self.fname = fname
        self.styles = {"n": (S, False), "b": (S, True), "h": (int(S * 1.45), True), "s": (max(14, S - 5), False)}
        self._c = {}
        self._w = {}

    def _f(self, st):
        if st not in self._c:
            self._c[st] = load_font(self.fname, *self.styles[st])
        return self._c[st]

    def width(self, text, st):
        if not text:
            return 0
        k = (text, st)
        if k not in self._w:                      # _wrap() asks for the same widths many times
            self._w[k] = int(self._f(st).getlength(text))
        return self._w[k]

    def height(self, st):
        return int(self.styles[st][0] * 1.35)

    def draw(self, img, x, y, text, st):
        d, f = ImageDraw.Draw(img), self._f(st)
        if "-" not in text:
            d.text((x, y), text, font=f, fill=0)
            return
        # A hyphen is only ~1.5 px thick: after 1-bit conversion it can disappear (INV...-0007 printed as
        # "INV... 0007"). Draw every '-' as a solid bar at the glyph's own position, at least 2 px thick.
        parts, cx = text.split("-"), float(x)
        hw = f.getlength("-")
        _, top, _, bot = f.getbbox("-")
        th = max(2, round(self.styles[st][0] / 12))
        for i, part in enumerate(parts):
            if part:
                d.text((round(cx), y), part, font=f, fill=0)
                cx += f.getlength(part)
            if i < len(parts) - 1:
                y0 = y + round((top + bot) / 2 - th / 2)
                d.rectangle((round(cx + hw * 0.12), y0, round(cx + hw * 0.88), y0 + th - 1), fill=0)
                cx += hw


class GDIText(PILText):
    """Windows GDI/Uniscribe text -> bitmap. Shapes Sinhala/Tamil correctly without Raqm.
    (Windows-only; every bitmap is cached and all GDI handles are released in `finally`.)"""
    def _render(self, text, st):
        k = (text, st)
        if k in self._c:
            return self._c[k]
        import win32gui
        import win32ui
        size, bold = self.styles[st]
        hdc = win32gui.GetDC(0)
        mdc = None
        try:
            dc = win32ui.CreateDCFromHandle(hdc)
            mdc = dc.CreateCompatibleDC()
            font = win32ui.CreateFont({"name": self.fname, "height": -size, "weight": 700 if bold else 400})
            mdc.SelectObject(font)
            w, h = mdc.GetTextExtent(text)
            w, h = max(1, w + 2), max(1, h + 2)
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(dc, w, h)
            mdc.SelectObject(bmp)
            mdc.FillSolidRect((0, 0, w, h), 0xFFFFFF)
            mdc.SetTextColor(0)
            mdc.SetBkMode(1)
            mdc.TextOut(0, 0, text)
            img = Image.frombuffer("RGB", (w, h), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1).convert("L")
        finally:
            if mdc is not None:
                mdc.DeleteDC()
            win32gui.ReleaseDC(0, hdc)
        self._c[k] = img
        return img

    def width(self, text, st):
        return self._render(text, st).size[0] if text else 0

    def draw(self, img, x, y, text, st):
        if text:
            img.paste(0, (x, y), ImageOps.invert(self._render(text, st)))


def pick_renderer(cfg, S, texts):
    fname = cfg.get("receipt_font", "Nirmala UI")
    if any(is_complex(t) for t in texts) and not raqm_ok() and gdi_ok():
        try:
            g = GDIText(fname, S)
            g.width("test", "n")
            return g
        except Exception:
            pass
    return PILText(fname, S)


# ------------------------------------------------------------------ documents (shared by thermal + HTML)
def _money(cfg, v):
    return f"{cfg.get('currency', 'Rs.')} {v:,.2f}"


def sale_doc(cfg, sale, reprint=False):
    meta = [("Invoice", sale["invoice"]), ("Date", f"{sale['date']} {sale['time']}"), ("Customer", sale["customer"]),
            ("Cashier", sale["cashier"].upper()), ("Payment", sale["method"] + (f" ({sale['ref']})" if sale["ref"] else ""))]
    if cfg.bool("feat_vat") and cfg.get("vat_number"):
        meta.insert(0, ("VAT No", cfg.get("vat_number")))
    items = [(n, q, p, l, " ".join(x for x in ((f"S/N:{s}" if s else ""), (f"Warranty:{w}" if w else "")) if x))
             for n, q, p, l, s, w in sale["items"]]
    tot = [("Sub total", _money(cfg, sale["sub"]), False)]
    if sale["discount"]:
        tot.append(("Discount", "-" + _money(cfg, sale["discount"]), False))
    if sale["redeem"]:
        tot.append(("Points redeemed", "-" + _money(cfg, sale["redeem"]), False))
    if sale.get("service"):
        tot.append((f"Service charge ({sale.get('service_pct', 0):g}%)", _money(cfg, sale["service"]), False))
    if sale.get("vat") and sale.get("vat_mode") == "Exclusive":
        tot.append((f"VAT ({sale.get('vat_pct', 0):g}%)", _money(cfg, sale["vat"]), False))
    tot.append(("NET TOTAL", _money(cfg, sale["net"]), True))
    if sale.get("vat") and sale.get("vat_mode") == "Inclusive":
        tot.append((f"VAT included ({sale.get('vat_pct', 0):g}%)", _money(cfg, sale["vat"]), False))
    tot.append((f"Paid ({sale['method']})", _money(cfg, sale["paid"]), False))
    tot.append(("CREDIT DUE", _money(cfg, sale["credit_due"]), False) if sale["method"] == "Credit"
               else ("Balance", _money(cfg, sale["balance"]), False))
    return dict(title="*** DUPLICATE ***" if reprint else "", meta=meta, items=items, totals=tot,
                footer=cfg.get("receipt_footer", "Thank You! Come Again!"), kind="INVOICE")


def grn_doc(cfg, g):
    """Goods Received Note as a printable document (use with open_html(cfg, doc, 'A4', name)). g = services.get_purchase(id)."""
    h = g["header"]
    meta = [("GRN", h["grn_no"]), ("Date", h["date"]), ("Supplier", h.get("supplier") or "-"), ("Supplier invoice", h["supplier_invoice"] or "-"), ("Received by", h["user"])]
    if h["status"] != "OK":
        meta.append(("Status", f"VOID - {h['void_reason']}"))
    items = []
    for i in g["items"]:
        extra = " ".join(x for x in ((f"Batch {i['batch_no']}" if i["batch_no"] else ""), (f"Exp {i['expiry']}" if i["expiry"] else "")) if x)
        items.append((f"{i['name']}" + (f" [{i['unit']}]" if i["unit"] else ""), i["qty"], i["cost_price"], i["line_total"], extra))
    paid = sum(p["amount"] for p in g["payments"])
    tot = [("Sub total", _money(cfg, h["subtotal"]), False)]
    if h["discount"]:
        tot.append(("Discount", "-" + _money(cfg, h["discount"]), False))
    tot += [("TOTAL", _money(cfg, h["total"]), True), ("Paid", _money(cfg, paid), False), ("Balance due", _money(cfg, max(0.0, h["total"] - paid)), False)]
    return dict(title="GOODS RECEIVED NOTE", meta=meta, items=items, totals=tot, footer=h["note"] or "", kind="GRN")


def quote_doc(cfg, q):
    meta = [("Quotation", q["quote_no"]), ("Date", q["date"]), ("Valid until", q["valid_until"]), ("Customer", q["customer_name"] or "-")]
    if q["phone"]:
        meta.append(("Phone", q["phone"]))
    items = [(n, qty, p, t, "") for n, qty, p, t in q["items"]]
    tot = [("Sub total", _money(cfg, q["subtotal"]), False)]
    if q["discount"]:
        tot.append(("Discount", "-" + _money(cfg, q["discount"]), False))
    tot.append(("QUOTED TOTAL", _money(cfg, q["total"]), True))
    foot = (q["note"] + "\n" if q["note"] else "") + "This is an estimate, not a tax invoice. Prices valid until the date shown."
    return dict(title="QUOTATION / ESTIMATE", meta=meta, items=items, totals=tot, footer=foot, kind="QUOTATION")


def width_dots(cfg):
    over = cfg.int("print_width_dots", 0)
    if over > 0:
        return max(256, over // 8 * 8)
    return PROFILES.get(cfg.get("printer_brand", "Xprinter"), PROFILES["Other ESC/POS"]).get(cfg.get("paper_size", "80mm"), 576)


def _wrap(R, text, st, maxw):
    out = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            t = (cur + " " + word) if cur else word
            if R.width(t, st) <= maxw:
                cur = t
                continue
            if cur:
                out.append(cur)
            while len(word) > 1 and R.width(word, st) > maxw:
                k = len(word)
                while k > 1 and R.width(word[:k], st) > maxw:
                    k -= 1
                out.append(word[:k])
                word = word[k:]
            cur = word
        out.append(cur)
    return out


def _logo(cfg, W):
    p = dbm.p("Assets", "shop_logo.png")
    if not cfg.bool("feat_print_logo") or not os.path.exists(p):
        return None
    try:
        im = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", im.size, "white")
        bg.alpha_composite(im)
        im = bg.convert("L")
        box = im.point(lambda v: 255 if v < 215 else 0).getbbox()     # ink only; ignore the empty border
        if box:
            pad = 3
            im = im.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad)))
        im.thumbnail((int(W * 0.5), 130))
        return im.convert("1").convert("L")
    except Exception:
        return None


def margins(cfg):
    """(left, right) in dots. 'Shift content left' moves everything left inside the printable area:
    use it when the left gap is wider than the right gap on the paper (printer/paper alignment)."""
    shift = max(0, min(40, cfg.int("print_shift_left", 0)))
    base = 14
    return max(2, base - shift), base + shift


def render_doc(cfg, doc, W=None):
    """Draw a document as a grayscale image exactly W dots wide. Two passes: the first only MEASURES the
    height, so long item names can never be cut off at the bottom."""
    W = W or width_dots(cfg)
    S = 26 if W >= 500 else 22
    ML, MR = margins(cfg)
    CW = W - ML - MR
    shop = [cfg.get("shop_name"), cfg.get("address"), ("Tel: " + cfg.get("phone")) if cfg.get("phone") else ""]
    texts = shop + [doc["title"], doc["footer"]] + [m[1] for m in doc["meta"]] + [i[0] for i in doc["items"]]
    R = pick_renderer(cfg, S, texts)
    logo = _logo(cfg, W)

    def paint(img):                                 # img=None -> measure only
        d = ImageDraw.Draw(img) if img is not None else None
        y = 0                                       # avoid extra top feed before first glyph

        def put(x, yy, text, st):
            if img is not None:
                R.draw(img, x, yy, text, st)

        def center(text, st, gap=3):
            nonlocal y
            for line in _wrap(R, text, st, CW):
                put(max(ML, ML + (CW - R.width(line, st)) // 2), y, line, st)
                y += R.height(st) + gap

        def lr(left, right, st="n"):
            nonlocal y
            wr = R.width(right, st)
            lines = _wrap(R, left, st, max(40, CW - wr - 10))
            for k, line in enumerate(lines):
                put(ML, y, line, st)
                if k == len(lines) - 1 and right:
                    put(W - MR - wr, y, right, st)
                y += R.height(st) + 2

        def rule(dash=True):
            nonlocal y
            y += 4
            if d is not None:
                if dash:
                    for x in range(ML, W - MR - 1, 12):
                        d.line((x, y, min(x + 6, W - MR - 1), y), fill=0, width=2)
                else:
                    d.line((ML, y, W - MR - 1, y), fill=0, width=3)
            y += 10

        if logo:
            if img is not None:
                img.paste(logo, ((W - logo.size[0]) // 2, y))
            y += logo.size[1] + 5
        center(shop[0], "h", 6)
        for line in shop[1:]:
            if line:
                center(line, "n")
        if doc["title"]:
            y += 4
            center(doc["title"], "b")
        rule(False)
        for k, v in doc["meta"]:
            lr(k + ":", str(v))
        rule()
        for name, qty, price, total, extra in doc["items"]:
            for line in _wrap(R, name, "b", CW):
                put(ML, y, line, "b")
                y += R.height("b") + 1
            if extra:
                for line in _wrap(R, extra, "s", CW - 12):
                    put(ML + 12, y, line, "s")
                    y += R.height("s")
            lr(f"   {qty:g} x {price:,.2f}", f"{total:,.2f}")
            y += 4
        rule()
        for label, val, strong in doc["totals"]:
            if strong:
                rule(False)
                lr(label, val, "h")
                rule(False)
            else:
                lr(label, val)
        y += 6
        for line in _wrap(R, doc["footer"], "n", CW):
            center(line, "n")
        center("Powered by VeloPOS", "s")
        return y

    h = paint(None)
    img = Image.new("L", (W, h + 8), 255)           # small bottom padding (was 24): paper is fed by the printer
    paint(img)
    return img


def render_text(cfg, text, W=None):
    """Plain monospaced text (Z-report, credit note...) -> image that fills the paper width."""
    W = W or width_dots(cfg)
    ML, MR = margins(cfg)
    lines = text.split("\n")
    longest = max((len(l) for l in lines), default=1)
    mono = _find(["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"])
    size = 30
    while size > 12:
        f = ImageFont.truetype(mono, size) if mono else ImageFont.load_default()
        if f.getlength("M" * longest) <= W - ML - MR:
            break
        size -= 1
    lh = int(size * 1.3)
    img = Image.new("L", (W, lh * len(lines) + 50), 255)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((ML, 10 + i * lh), l, font=f, fill=0)
    return img


def calibration_image(W):
    img = Image.new("L", (W, 330), 255)
    d = ImageDraw.Draw(img)
    f = load_font("Arial", 22, True)
    d.rectangle((0, 0, W - 1, 329), outline=0, width=4)
    for x in range(0, W, 50):
        d.line((x, 40, x, 80 if x % 100 == 0 else 62), fill=0, width=2)
        if x % 100 == 0:
            d.text((x + 3, 82), str(x), font=f, fill=0)
    d.text((14, 130), f"PRINT WIDTH = {W} dots", font=f, fill=0)
    d.text((14, 165), "Left & right borders must be visible.", font=load_font("Arial", 20), fill=0)
    d.text((14, 195), "Cut off  -> reduce 'Print width'.", font=load_font("Arial", 20), fill=0)
    d.text((14, 225), "White gap -> increase 'Print width'.", font=load_font("Arial", 20), fill=0)
    return img


# ------------------------------------------------------------------ ESC/POS bytes
def raster_bytes(img, band=240, threshold=190):
    W, H = img.size
    W8 = (W + 7) // 8 * 8
    if W8 != W:
        canvas = Image.new("L", (W8, H), 255)
        canvas.paste(img, (0, 0))
        img = canvas
    bw = img.point(lambda p: 255 if p < threshold else 0).convert("1", dither=Image.Dither.NONE)
    data, bpr, out = bw.tobytes(), W8 // 8, bytearray()
    for r in range(0, H, band):
        rows = min(band, H - r)
        out += b"\x1d\x76\x30\x00" + struct.pack("<HH", bpr, rows) + data[r * bpr:(r + rows) * bpr]
    return bytes(out)


def drawer_bytes(cfg):
    pin = 1 if "5" in cfg.get("drawer_pin", "Pin 2") else 0
    return b"\x1b\x70" + bytes([pin, 60, 120])          # ESC p m t1 t2  (pulse ~120 ms)


def build_job(cfg, img, kick=False, cut=True):
    thr = max(100, min(240, cfg.int("print_threshold", 190)))   # higher = thin strokes such as '-' survive
    feed = max(0, min(10, cfg.int("print_bottom_feed", 0)))     # was a hard-coded 4 lines
    if not cut:
        feed = max(feed, 4)                                      # no cutter: keep a tear-off margin
    job = b"\x1b@" + (drawer_bytes(cfg) if kick else b"") + raster_bytes(img, threshold=thr)
    if feed:
        job += b"\x1b\x64" + bytes([feed])
    if cut:
        job += CUTS.get(cfg.get("cut_cmd", "Partial cut (GS V 66)"), CUTS["Partial cut (GS V 66)"])
    return job


def print_labels(app, cfg, images, cut_each=False):
    """Barcode labels on a receipt / label printer that accepts raster images (same path as receipts). One job for all labels.
    Not supported: 'Browser' mode (use the A4 sheet) and printers that only understand TSPL / ZPL / EPL."""
    from . import barcodes
    mode = cfg.get("print_mode", MODES[0])
    if mode.startswith("Browser"):
        return None
    dots = width_dots(cfg)
    canvases = [barcodes.printer_canvas(im, dots) for im in images]

    def job():
        if mode.startswith("Windows driver"):
            for im in canvases:
                _print_gdi(cfg, im)
        else:
            data = b"".join(build_job(cfg, im, cut=cut_each or (n == len(canvases) - 1 and cfg.bool("feat_cut"))) for n, im in enumerate(canvases))
            send_bytes(cfg, data)
    _async(app, job)
    return True


# ------------------------------------------------------------------ transports
def send_bytes(cfg, data):
    mode = cfg.get("print_mode", MODES[0])
    if mode.startswith("LAN"):
        with socket.create_connection((cfg.get("lan_ip"), cfg.int("lan_port", 9100)), timeout=5) as s:
            s.sendall(data)
    elif mode.startswith("COM"):
        import serial
        with serial.Serial(cfg.get("com_port", "COM3"), cfg.int("com_baud", 9600), timeout=3, write_timeout=8) as s:
            s.write(data)
    else:
        import win32print
        name = cfg.get("printer", "Default System Printer")
        if name.startswith("Default"):
            name = win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(name)
        try:
            win32print.StartDocPrinter(h, 1, ("VeloPOS", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)


def _print_gdi(cfg, img):
    import win32print
    import win32ui
    from PIL import ImageWin
    name = cfg.get("printer", "Default System Printer")
    if name.startswith("Default"):
        name = win32print.GetDefaultPrinter()
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(name)
    hdc.StartDoc("VeloPOS")
    hdc.StartPage()
    page_w = hdc.GetDeviceCaps(8)                       # HORZRES: scale to the FULL printable width
    w, h = img.size
    scale = page_w / w
    ImageWin.Dib(img.convert("RGB")).draw(hdc.GetHandleOutput(), (0, 0, int(w * scale), int(h * scale)))
    hdc.EndPage()
    hdc.EndDoc()
    hdc.DeleteDC()


# ------------------------------------------------------------------ high level API
def _async(app, fn):
    def run():
        try:
            fn()
        except Exception as ex:
            msg = f"{type(ex).__name__}: {ex}"
            if "win32" in msg or "No module" in msg:
                msg += "\n\nInstall the Windows printing library:  pip install pywin32"
            app.after(0, lambda: __import__("tkinter.messagebox", fromlist=["x"]).showwarning("Printer", f"Could not print:\n{msg}"))
    threading.Thread(target=run, daemon=True).start()


def print_image(app, cfg, img, kick=False):
    mode = cfg.get("print_mode", MODES[0])
    if mode.startswith("Browser"):
        return None
    copies = max(1, cfg.int("print_copies", 1))

    def job():
        if mode.startswith("Windows driver"):
            for _ in range(copies):
                _print_gdi(cfg, img)
            if kick:
                try:
                    send_bytes(Cfg({"print_mode": MODES[0]}), b"\x1b@" + drawer_bytes(cfg))
                except Exception:
                    pass
        else:
            for n in range(copies):
                send_bytes(cfg, build_job(cfg, img, kick=kick and n == 0, cut=cfg.bool("feat_cut")))
    _async(app, job)
    return True


def _kick_wanted(cfg, sale):
    if not cfg.bool("feat_cash_drawer"):
        return False
    when = cfg.get("drawer_open_on", DRAWER_WHEN[0])
    if when.startswith("Manual"):
        return False
    return when.startswith("All") or sale["method"] == "Cash"


def after_sale(app, sale):
    """Called once after every completed bill: prints the receipt and/or opens the cash drawer."""
    cfg = app.s
    kick = _kick_wanted(cfg, sale)
    if cfg.bool("feat_auto_print"):
        print_sale(app, sale, kick=kick)
    elif kick:
        open_drawer(app, log=False)


def print_sale(app, sale, cfg=None, reprint=False, kick=False):
    cfg = cfg or app.s
    doc = sale_doc(cfg, sale, reprint)
    paper = cfg.get("paper_size", "80mm")
    if paper in ("A4", "A5") or cfg.get("print_mode", "").startswith("Browser"):
        return open_html(cfg, doc, paper, sale["invoice"])
    return print_image(app, cfg, render_doc(cfg, doc), kick=kick and not reprint)


def print_quote(app, q, cfg=None):
    cfg = cfg or app.s
    doc = quote_doc(cfg, q)
    paper = cfg.get("paper_size", "80mm")
    if paper in ("A4", "A5") or cfg.get("print_mode", "").startswith("Browser"):
        return open_html(cfg, doc, paper, q["quote_no"])
    return print_image(app, cfg, render_doc(cfg, doc))


def print_text(app, text, title="Report", cfg=None):
    cfg = cfg or app.s
    if cfg.get("print_mode", "").startswith("Browser"):
        p = dbm.p("Exports", title.replace(" ", "_") + ".html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"<html><body onload='window.print()'><pre style='font:14px Consolas,monospace'>{_html.escape(text)}</pre></body></html>")
        return webbrowser.open("file:///" + p.replace("\\", "/"))
    return print_image(app, cfg, render_text(cfg, text))


def open_drawer(app, cfg=None, log=True):
    cfg = cfg or app.s
    if not cfg.bool("feat_cash_drawer"):
        from tkinter import messagebox
        return messagebox.showinfo("Cash drawer", "Cash drawer is switched OFF in Settings -> Printing.")
    if log:
        dbm.audit(getattr(app, "user", "-"), "DRAWER_OPEN_MANUAL")
    _async(app, lambda: send_bytes(cfg, b"\x1b@" + drawer_bytes(cfg)))


def sample_doc(cfg):
    sale = dict(invoice="TEST-0001", date=datetime.now().strftime("%Y-%m-%d"), time=datetime.now().strftime("%H:%M:%S"),
                customer="Walk-in", cashier="admin", method="Cash", ref="", sub=1150.0, discount=0.0, redeem=0.0, net=1150.0,
                paid=2000.0, balance=850.0, credit_due=0.0,
                items=[("Sugar 1kg", 2, 250.0, 500.0, "", ""), ("සීනි 1kg (Sinhala test)", 1, 350.0, 350.0, "", ""),
                       ("Mobile phone with a very long product name for wrapping", 1, 300.0, 300.0, "IMEI123456", "1 Year")])
    return sale_doc(cfg, sale)


def run_test(app, cfg, kind):
    """kind: sample | calibration | drawer   (cfg = Cfg with unsaved form values)"""
    if kind == "drawer":
        return open_drawer(app, cfg)
    img = calibration_image(width_dots(cfg)) if kind == "calibration" else render_doc(cfg, sample_doc(cfg))
    if cfg.get("print_mode", "").startswith("Browser") or cfg.get("paper_size") in ("A4", "A5"):
        p = dbm.p("Exports", "test_print.png")
        img.save(p)
        return webbrowser.open("file:///" + p.replace("\\", "/"))
    return print_image(app, cfg, img, kick=False)


# ------------------------------------------------------------------ A4 / A5 / browser HTML
def open_html(cfg, doc, paper, name):
    e = _html.escape
    page = {"A4": ("A4", "210mm"), "A5": ("A5", "148mm"), "80mm": ("80mm auto", "76mm"), "58mm": ("58mm auto", "54mm")}.get(paper, ("A4", "210mm"))
    rows = "".join(f"<tr><td>{i}</td><td><b>{e(str(n))}</b>{('<br><small>' + e(x) + '</small>') if x else ''}</td>"
                   f"<td class=r>{q:g}</td><td class=r>{p:,.2f}</td><td class=r><b>{t:,.2f}</b></td></tr>"
                   for i, (n, q, p, t, x) in enumerate(doc["items"], 1))
    meta = "".join(f"<div><b>{e(k)}:</b> {e(str(v))}</div>" for k, v in doc["meta"])
    tot = "".join(f"<tr class='{'big' if s else ''}'><td>{e(l)}</td><td class=r>{e(v)}</td></tr>" for l, v, s in doc["totals"])
    sig = "<div class=sig><div>Customer signature</div><div>Authorized signature</div></div>" if paper in ("A4", "A5") else ""
    bank = ""
    parts = [f"{l}: {cfg.get(k)}" for l, k in (("Bank", "bank_name"), ("Branch", "bank_branch"), ("A/C", "bank_acc"), ("Name", "bank_holder")) if cfg.get(k)]
    if parts and paper in ("A4", "A5"):
        bank = f"<p class=sm>Bank details: {e(' | '.join(parts))}</p>"
    logo = dbm.p("Assets", "shop_logo.png")
    logo_html = f"<img src='file:///{logo.replace(chr(92), '/')}' style='height:60px'>" if cfg.bool("feat_print_logo") and os.path.exists(logo) else ""
    doc_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{e(name)}</title><style>
@page {{ size: {page[0]}; margin: 8mm; }}
body {{ font-family:'Nirmala UI','Segoe UI',Arial,sans-serif; width:{page[1]}; margin:0 auto; color:#111; font-size:{'13px' if paper in ('A4','A5') else '11px'}; }}
.top {{ display:flex; justify-content:space-between; border-bottom:3px solid #2563eb; padding-bottom:10px; }}
.shop {{ font-size:22px; font-weight:bold; color:#1e3a8a; }} h2 {{ margin:0 0 6px 0; }}
table {{ width:100%; border-collapse:collapse; margin-top:12px; }} th,td {{ border:1px solid #cbd5e1; padding:6px 8px; }}
th {{ background:#1e3a8a; color:#fff; text-align:left; }} .r {{ text-align:right; }} .tot {{ width:50%; margin-left:auto; }}
.big td {{ background:#eff6ff; font-size:1.2em; font-weight:bold; }} .sig {{ display:flex; justify-content:space-between; margin-top:50px; }}
.sig div {{ border-top:1px dashed #333; width:40%; text-align:center; padding-top:4px; }} .sm {{ font-size:11px; color:#555; }}
@media print {{ .noprint {{ display:none; }} }}</style></head><body onload="window.print()">
<button class="noprint" onclick="window.print()">Print</button>
<div class=top><div>{logo_html}<div class=shop>{e(cfg.get('shop_name'))}</div><div>{e(cfg.get('address'))}</div><div>Tel: {e(cfg.get('phone'))}</div></div>
<div style="text-align:right"><h2>{e(doc['kind'])}</h2>{meta}</div></div>
<table><thead><tr><th>#</th><th>Description</th><th class=r>Qty</th><th class=r>Unit price</th><th class=r>Total</th></tr></thead><tbody>{rows}</tbody></table>
<table class=tot>{tot}</table>{bank}<p style="text-align:center">{e(doc['footer']).replace(chr(10), '<br>')}</p>{sig}
<p class=sm style="text-align:center">Powered by VeloPOS</p></body></html>"""
    path = dbm.p("Receipts", f"{name}_{paper}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc_html)
    webbrowser.open("file:///" + path.replace("\\", "/"))
    return True
