"""Product thumbnails: in-memory LRU + on-disk cache + generated placeholders. No tkinter here (headless-testable);
the UI wraps the returned PIL images in CTkImage.

Why a cache: shop photos are often 3000x4000 JPEGs. Decoding 24 of them every time the item grid is shown would freeze the
screen, so each picture is shrunk ONCE to a small JPEG (ProductImages/.thumbs) and then served from memory.
"""
import hashlib
import os
import time
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageFont

from . import database as dbm

BG = (241, 245, 249)
PALETTE = [(37, 99, 235), (5, 150, 105), (124, 58, 237), (234, 88, 12), (190, 24, 93), (15, 118, 110), (180, 83, 9), (71, 85, 105)]


def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def initials(label):
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in str(label)).split() if w]
    if not words:
        return "?"
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()


def placeholder(label, size):
    """A coloured square with the item's initials (colour is stable for the same name)."""
    col = PALETTE[int(hashlib.sha1(str(label).encode("utf-8")).hexdigest(), 16) % len(PALETTE)]
    im = Image.new("RGB", (size, size), col)
    d = ImageDraw.Draw(im)
    txt, f = initials(label), _font(int(size * 0.42))
    box = d.textbbox((0, 0), txt, font=f)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), txt, font=f, fill=(255, 255, 255))
    return im


def _fit(im, size):
    """Whole picture visible (letter-boxed) on a light square."""
    im = im.convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGB", (size, size), BG)
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


def cache_dir():
    d = os.path.join(dbm.p("ProductImages"), ".thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def prune_disk(max_files=3000):
    """Delete the oldest cached thumbnails beyond max_files. Returns how many were removed."""
    try:
        files = [os.path.join(cache_dir(), n) for n in os.listdir(cache_dir())]
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        gone = 0
        for f in files[max_files:]:
            try:
                os.remove(f)
                gone += 1
            except OSError:
                pass
        return gone
    except OSError:
        return 0


def clear_disk():
    n = 0
    for f in os.listdir(cache_dir()):
        try:
            os.remove(os.path.join(cache_dir(), f))
            n += 1
        except OSError:
            pass
    return n


class ThumbCache:
    def __init__(self, max_items=400):
        self.max, self._m = max_items, OrderedDict()
        self.hits = self.misses = self.disk_hits = 0

    def clear(self):
        self._m.clear()

    def _put(self, key, im):
        self._m[key] = im
        self._m.move_to_end(key)
        while len(self._m) > self.max:
            self._m.popitem(last=False)

    def get(self, path, size, label=""):
        """Thumbnail (size x size RGB). `path` may be '' or broken -> a placeholder using `label`. Never raises."""
        if not path:
            return self._placeholder(label, size)
        try:
            mt = os.stat(path).st_mtime_ns
        except OSError:
            return self._placeholder(label, size)
        key = (path, mt, size)
        if key in self._m:
            self.hits += 1
            self._m.move_to_end(key)
            return self._m[key]
        self.misses += 1
        im = self._from_disk_or_build(path, mt, size)
        if im is None:
            im = placeholder(label, size)
        self._put(key, im)
        return im

    def _placeholder(self, label, size):
        key = ("ph", label, size)
        if key not in self._m:
            self._put(key, placeholder(label, size))
        else:
            self._m.move_to_end(key)
        return self._m[key]

    def _from_disk_or_build(self, path, mt, size):
        name = hashlib.sha1(f"{os.path.abspath(path)}|{mt}|{size}".encode("utf-8")).hexdigest() + ".jpg"
        cached = os.path.join(cache_dir(), name)
        try:
            if os.path.isfile(cached):
                with Image.open(cached) as im:
                    im.load()
                    self.disk_hits += 1
                    return im.convert("RGB")
        except Exception:
            pass
        try:
            with Image.open(path) as im:
                try:
                    im.draft("RGB", (size * 2, size * 2))        # JPEG: decode at reduced size (much faster)
                except Exception:
                    pass
                out = _fit(im, size)
        except Exception:
            return None
        try:
            out.save(cached, "JPEG", quality=85)
        except OSError:
            pass
        return out


CACHE = ThumbCache()
