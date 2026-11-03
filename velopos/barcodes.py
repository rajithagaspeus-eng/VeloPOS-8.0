"""Barcode encoders (EAN-13, Code 39), label rendering and A4 label-sheet HTML. Pure Python + Pillow, no UI, headless-testable.

Honest limit: labels are produced as IMAGES. They print on receipt/label printers that accept raster images (the same ESC/POS path as receipts)
and on normal printers through an A4 sheet. Printers that only understand their own label language (TSPL, ZPL, EPL ...) are NOT driven natively.
"""
import base64
import html
import io

from PIL import Image, ImageDraw, ImageFont

# ====================================================================== EAN-13
_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_check_digit(d12):
    """Check digit for the first 12 digits: weights 1,3,1,3... from the left."""
    if len(d12) != 12 or not d12.isdigit():
        raise ValueError("EAN-13 needs exactly 12 digits to calculate the check digit")
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return (10 - s % 10) % 10


def ean13_digits(value):
    """12 digits -> adds the check digit; 13 digits -> verifies it. Returns the 13-digit string."""
    v = str(value).strip()
    if not v.isdigit():
        raise ValueError("EAN-13 can only contain digits")
    if len(v) == 12:
        return v + str(ean13_check_digit(v))
    if len(v) == 13:
        if int(v[12]) != ean13_check_digit(v[:12]):
            raise ValueError(f"Wrong EAN-13 check digit (it should be {ean13_check_digit(v[:12])})")
        return v
    raise ValueError("EAN-13 needs 12 or 13 digits")


def ean13_bits(value):
    """95 modules: start 101 + 6 left digits (L/G by the first digit) + centre 01010 + 6 right digits (R) + end 101."""
    d = ean13_digits(value)
    par = _PARITY[int(d[0])]
    left = "".join((_L if par[i] == "L" else _G)[int(d[i + 1])] for i in range(6))
    right = "".join(_R[int(c)] for c in d[7:])
    return "101" + left + "01010" + right + "101"


def decode_ean13_bits(bits):
    """Inverse of ean13_bits (used by the tests). Raises ValueError for anything that is not a valid EAN-13."""
    if len(bits) != 95 or bits[:3] != "101" or bits[45:50] != "01010" or bits[-3:] != "101":
        raise ValueError("Not an EAN-13 pattern")
    digits, par = [], ""
    for i in range(6):
        w = bits[3 + 7 * i: 10 + 7 * i]
        if w in _L:
            digits.append(_L.index(w)); par += "L"
        elif w in _G:
            digits.append(_G.index(w)); par += "G"
        else:
            raise ValueError("Bad left digit")
    first = _PARITY.index(par)
    for i in range(6):
        w = bits[50 + 7 * i: 57 + 7 * i]
        if w not in _R:
            raise ValueError("Bad right digit")
        digits.append(_R.index(w))
    out = str(first) + "".join(map(str, digits))
    ean13_digits(out)
    return out


# ====================================================================== Code 39
# 9 elements per character (bar, space, bar, space ...), N = narrow, W = wide; exactly 3 are wide.
_C39 = {
    "0": "NNNWWNWNN", "1": "WNNWNNNNW", "2": "NNWWNNNNW", "3": "WNWWNNNNN", "4": "NNNWWNNNW", "5": "WNNWWNNNN", "6": "NNWWWNNNN", "7": "NNNWNNWNW",
    "8": "WNNWNNWNN", "9": "NNWWNNWNN", "A": "WNNNNWNNW", "B": "NNWNNWNNW", "C": "WNWNNWNNN", "D": "NNNNWWNNW", "E": "WNNNWWNNN", "F": "NNWNWWNNN",
    "G": "NNNNNWWNW", "H": "WNNNNWWNN", "I": "NNWNNWWNN", "J": "NNNNWWWNN", "K": "WNNNNNNWW", "L": "NNWNNNNWW", "M": "WNWNNNNWN", "N": "NNNNWNNWW",
    "O": "WNNNWNNWN", "P": "NNWNWNNWN", "Q": "NNNNNNWWW", "R": "WNNNNNWWN", "S": "NNWNNNWWN", "T": "NNNNWNWWN", "U": "WWNNNNNNW", "V": "NWWNNNNNW",
    "W": "WWWNNNNNN", "X": "NWNNWNNNW", "Y": "WWNNWNNNN", "Z": "NWWNWNNNN", "-": "NWNNNNWNW", ".": "WWNNNNWNN", " ": "NWWNNNWNN", "*": "NWNNWNWNN",
    "$": "NWNWNWNNN", "/": "NWNWNNNWN", "+": "NWNNNWNWN", "%": "NNNWNWNWN",
}
CODE39_CHARS = "".join(k for k in _C39 if k != "*")


def code39_clean(value):
    """Upper-case conversion + validation. Raises a clear ValueError for characters Code 39 cannot hold."""
    v = str(value).strip().upper()
    if not v:
        raise ValueError("Nothing to encode")
    bad = sorted({c for c in v if c not in CODE39_CHARS})
    if bad:
        raise ValueError("Code 39 cannot encode: " + " ".join(repr(c) for c in bad) + "  (allowed: 0-9 A-Z - . space $ / + %)")
    if len(v) > 40:
        raise ValueError("Too long for Code 39 (max 40 characters)")
    return v


def code39_bits(value, wide=3):
    """Modules (1 = bar). narrow = 1 module, wide = `wide` modules, 1 narrow space between characters; start/stop '*' added."""
    v = code39_clean(value)
    out = []
    for ci, ch in enumerate("*" + v + "*"):
        if ci:
            out.append("0")
        bar = True
        for el in _C39[ch]:
            out.append(("1" if bar else "0") * (wide if el == "W" else 1))
            bar = not bar
    return "".join(out)


def decode_code39_bits(bits, wide=3):
    """Inverse of code39_bits (used by the tests)."""
    rev = {v: k for k, v in _C39.items()}
    runs, i = [], 0
    while i < len(bits):
        j = i
        while j < len(bits) and bits[j] == bits[i]:
            j += 1
        runs.append((bits[i], j - i))
        i = j
    chars, k = [], 0
    while k < len(runs):
        els = runs[k:k + 9]
        if len(els) < 9:
            raise ValueError("Truncated Code 39 pattern")
        pat = "".join("W" if n >= (1 + wide) / 2 else "N" for _, n in els)
        if pat not in rev:
            raise ValueError("Unknown Code 39 character")
        chars.append(rev[pat])
        k += 9
        if k < len(runs):
            if runs[k] != ("0", 1):
                raise ValueError("Bad inter-character gap")
            k += 1
    if len(chars) < 2 or chars[0] != "*" or chars[-1] != "*":
        raise ValueError("Missing start/stop character")
    return "".join(chars[1:-1])


# ====================================================================== choosing the symbology for an item
def choose_symbology(barcode, pref="Auto"):
    """-> ('EAN13', 13 digits) or ('CODE39', text). Auto: a valid 13-digit EAN (or a 12-digit UPC-A, which is an EAN with a leading 0) becomes EAN-13,
    anything else Code 39. Raises ValueError with a clear message when the item's barcode cannot be encoded."""
    b = str(barcode).strip()
    if pref == "EAN-13":
        return "EAN13", ean13_digits(b)
    if pref == "Code 39":
        return "CODE39", code39_clean(b)
    if b.isdigit() and len(b) == 13:
        try:
            return "EAN13", ean13_digits(b)
        except ValueError:
            pass
    if b.isdigit() and len(b) == 12:
        try:
            return "EAN13", ean13_digits("0" + b)
        except ValueError:
            pass
    return "CODE39", code39_clean(b)


# ====================================================================== rendering
def mm_to_px(mm, dpi):
    return max(1, round(float(mm) / 25.4 * int(dpi)))


def _font(size, bold=False):
    names = (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf") if bold
             else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"))
    for n in names:
        try:
            return ImageFont.truetype(n, max(6, int(size)))
        except OSError:
            continue
    try:
        return ImageFont.load_default(max(6, int(size)))
    except TypeError:
        return ImageFont.load_default()


def _fs(f):
    return getattr(f, "size", 10)


def _fit_text(d, text, maxw, size, bold, min_size=7):
    """Largest font (<= size) in which the text fits maxw; otherwise cut with an ellipsis."""
    s = int(size)
    while s >= min_size:
        f = _font(s, bold)
        if d.textlength(text, font=f) <= maxw:
            return f, text
        s -= 1
    f, t = _font(min_size, bold), text
    while len(t) > 1 and d.textlength(t + "…", font=f) > maxw:
        t = t[:-1]
    return f, t + "…"


def barcode_image(kind, value, width_px, height_px, quiet=True):
    """Bars (+ human-readable digits for EAN-13) in a white image that is exactly width_px x height_px. Raises ValueError if it cannot fit."""
    bits = ean13_bits(value) if kind == "EAN13" else code39_bits(value)
    q_l, q_r = (11, 7) if kind == "EAN13" else (10, 10)
    total = len(bits) + ((q_l + q_r) if quiet else 0)
    mod = width_px // total
    if mod < 1:
        raise ValueError(f"The label is too narrow for this barcode ({len(bits)} modules need at least {total} dots)")
    img = Image.new("L", (width_px, height_px), 255)
    d = ImageDraw.Draw(img)
    text_h = max(10, int(height_px * 0.24))
    bar_h = max(4, height_px - text_h)
    x0 = (width_px - mod * len(bits)) // 2
    guards = set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95)) if kind == "EAN13" else set()
    i = 0
    while i < len(bits):
        if bits[i] == "1":
            j = i
            while j < len(bits) and bits[j] == "1":
                j += 1
            ext = int(text_h * 0.5) if (kind == "EAN13" and i in guards) else 0
            d.rectangle((x0 + i * mod, 0, x0 + j * mod - 1, bar_h + ext - 1), fill=0)
            i = j
        else:
            i += 1
    if kind == "CODE39":
        f, t = _fit_text(d, code39_clean(value), width_px, text_h * 0.9, False, 6)
        d.text(((width_px - d.textlength(t, font=f)) / 2, bar_h + 1), t, font=f, fill=0)
    if kind == "EAN13":
        f = _font(text_h * 0.9)
        digs = ean13_digits(value)
        for txt, a, b in ((digs[0], 0, x0 + 3 * mod), (digs[1:7], x0 + 3 * mod, x0 + 45 * mod), (digs[7:], x0 + 50 * mod, x0 + 92 * mod)):
            w = d.textlength(txt, font=f)
            d.text((a + (b - a - w) / 2, bar_h + 1), txt, font=f, fill=0)
    return img


def render_label(item, spec):
    """One label as a grayscale PIL image. item: dict(barcode, name, price). spec: dict(width_mm, height_mm, dpi, symbology, shop, show_name, show_price, currency)."""
    dpi = int(spec.get("dpi", 203))
    W, H = mm_to_px(spec.get("width_mm", 50), dpi), mm_to_px(spec.get("height_mm", 30), dpi)
    if W < 80 or H < 60:
        raise ValueError("The label is too small (minimum about 10 x 8 mm)")
    kind, val = choose_symbology(item["barcode"], spec.get("symbology", "Auto"))
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    m = max(3, mm_to_px(1.5, dpi))
    y, usable = m, W - 2 * m
    if spec.get("shop"):
        f, t = _fit_text(d, str(spec["shop"]), usable, H * 0.10, True)
        d.text(((W - d.textlength(t, font=f)) / 2, y), t, font=f, fill=0)
        y += int(_fs(f) * 1.25)
    if spec.get("show_name", True):
        f, t = _fit_text(d, str(item["name"]), usable, H * 0.11, False)
        d.text(((W - d.textlength(t, font=f)) / 2, y), t, font=f, fill=0)
        y += int(_fs(f) * 1.3)
    price_h = 0
    if spec.get("show_price", True):
        price_txt = f"{spec.get('currency', 'Rs.')} {float(item['price']):,.2f}"
        pf, price_txt = _fit_text(d, price_txt, usable, H * 0.16, True)
        price_h = int(_fs(pf) * 1.3)
        d.text(((W - d.textlength(price_txt, font=pf)) / 2, H - m - price_h + 2), price_txt, font=pf, fill=0)
    bar_h = H - m - price_h - y
    if bar_h < 12:
        raise ValueError("The label is too small for the chosen content - turn off the shop name / item name or make the label taller")
    img.paste(barcode_image(kind, val, usable, bar_h), (m, y))
    return img


def expand_queue(queue):
    """queue: [dict(barcode, name, price, copies)] -> flat list with every copy."""
    out = []
    for q in queue:
        n = int(q.get("copies", 1))
        if not 1 <= n <= 500:
            raise ValueError("Copies must be between 1 and 500")
        out += [q] * n
    return out


def render_queue(queue, spec):
    """-> (images, errors). Items whose barcode cannot be encoded are skipped and reported by name, never silently."""
    imgs, errors = [], []
    for q in queue:
        try:
            im = render_label(q, spec)
        except ValueError as e:
            errors.append(f"{q['name']} ({q['barcode']}): {e}")
            continue
        imgs += [im] * int(q.get("copies", 1))
    return imgs, errors


# ====================================================================== printer path (receipt / label printers that take raster images)
def printer_canvas(img, paper_dots):
    """Centre the label on a canvas as wide as the printer's printable width (a label never gets stretched)."""
    if img.width > paper_dots:
        raise ValueError(f"The label ({img.width} dots) is wider than the printer ({paper_dots} dots). Make the label narrower.")
    out = Image.new("L", (paper_dots, img.height), 255)
    out.paste(img, ((paper_dots - img.width) // 2, 0))
    return out


# ====================================================================== A4 label sheet (HTML, printed from the browser)
def sheet_html(images, spec, cols, rows, margin_mm=8, title="Barcode labels"):
    """Labels in a cols x rows grid per A4 page. Every label is a PNG embedded in the page (works offline)."""
    cols, rows = int(cols), int(rows)
    w, h, mm = float(spec.get("width_mm", 50)), float(spec.get("height_mm", 30)), float(margin_mm)
    if cols < 1 or rows < 1:
        raise ValueError("Columns and rows must be at least 1")
    if mm * 2 + cols * w > 210.01 or mm * 2 + rows * h > 297.01:
        raise ValueError(f"{cols} x {rows} labels of {w:g} x {h:g} mm do not fit on an A4 page with {mm:g} mm margins")
    per = cols * rows
    pages = []
    for p in range(0, len(images), per):
        cells = []
        for im in images[p:p + per]:
            buf = io.BytesIO()
            im.convert("L").save(buf, "PNG")
            cells.append(f"<div class='l'><img src='data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}'></div>")
        pages.append("<div class='pg'>" + "".join(cells) + "</div>")
    css = (f"@page{{size:A4;margin:0}}body{{margin:0}}.pg{{box-sizing:border-box;width:210mm;height:297mm;padding:{mm}mm;display:grid;"
           f"grid-template-columns:repeat({cols},{w}mm);grid-auto-rows:{h}mm;align-content:start;page-break-after:always}}"
           f".l{{width:{w}mm;height:{h}mm;overflow:hidden}}.l img{{width:{w}mm;height:{h}mm;display:block}}")
    return f"<html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body>{''.join(pages)}</body></html>"
