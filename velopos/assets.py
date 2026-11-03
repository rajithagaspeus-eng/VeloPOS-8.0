"""Owner's own pictures: payment QR codes (qr_codes/) and logo / window icon (branding/). Headless except load_image().

Folders sit next to run.py (in the Nuitka build: next to VeloPOS.exe). Any picture type works. A missing picture = the old behaviour
(a QR drawn from the text, the normal text title)."""
import os

EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
QR_KINDS = ("international", "bank", "binance", "whatsapp", "about")
LOGO_HEIGHT = {"login": 150, "about": 160, "activate": 90, "setup": 110}


def app_root():
    """Folder that holds run.py / VeloPOS.exe (the parent of the velopos package)."""
    return os.environ.get("VELOPOS_ASSETS") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find(folder, base):
    """First picture called `base` + any picture extension. Also accepts doubled names such as qr_bank.png.jpg (Windows hides extensions)."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    base = base.lower()
    for n in names:
        low = n.lower()
        stem = low
        while stem.endswith(EXTS):                 # strip one or two picture extensions
            stem = os.path.splitext(stem)[0]
        if stem == base and low.endswith(EXTS) and os.path.isfile(os.path.join(folder, n)):
            return os.path.join(folder, n)
    return None


def qr_path(kind, root=None):
    """kind: international | bank | binance | whatsapp | about  (about falls back to whatsapp). -> path or None"""
    folder = os.path.join(root or app_root(), "qr_codes")
    p = _find(folder, "qr_" + kind)
    if p is None and kind == "about":
        p = _find(folder, "qr_whatsapp")
    return p


def logo_path(root=None):
    """dev_logo.* first, then logo.*, then app_icon.ico. -> path or None"""
    folder = os.path.join(root or app_root(), "branding")
    for base in ("dev_logo", "logo"):
        p = _find(folder, base)
        if p:
            return p
    ico = os.path.join(folder, "app_icon.ico")
    return ico if os.path.isfile(ico) else None


def icon_path(root=None):
    p = os.path.join(root or app_root(), "branding", "app_icon.ico")
    return p if os.path.isfile(p) else None


def fit_size(w, h, target_h=None, target_w=None):
    """Size that keeps the picture's shape. Give the height (logos) or the width, or both (then it must fit inside both)."""
    if w <= 0 or h <= 0:
        return (1, 1)
    scale = None
    if target_h:
        scale = target_h / h
    if target_w:
        scale = min(scale, target_w / w) if scale is not None else target_w / w
    scale = scale or 1.0
    return (max(1, round(w * scale)), max(1, round(h * scale)))


_cache = {}


def load_image(path, target_h=None, target_w=None):
    """-> (CTkImage, (w, h)) or None when the file cannot be read. Big pictures are shrunk first (a 3000 px QR must not stay in memory)."""
    key = (path, target_h, target_w)
    if key in _cache:
        return _cache[key]
    try:
        from PIL import Image
        import customtkinter as ctk
        im = Image.open(path)
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "P") else "RGB")
        size = fit_size(im.width, im.height, target_h, target_w)
        im = im.resize((min(im.width, size[0] * 2), min(im.height, size[1] * 2)), Image.LANCZOS)
        res = (ctk.CTkImage(light_image=im, dark_image=im, size=size), size)
    except Exception:
        res = None
    _cache[key] = res
    return res
