"""Customer display model (headless). The Billing screen pushes its cart here; the display window only READS snapshots.
Nothing in this module touches widgets, so billing can never be blocked or broken by the display."""
from datetime import datetime, timedelta


class DisplayModel:
    MAX_LINES = 8
    THANKS_SECONDS = 8

    def __init__(self, shop="", promo="", cur="Rs."):
        self.shop, self.promo, self.cur = shop, promo, cur
        self.mode, self.lines, self.hidden, self.total, self.change = "idle", [], 0, 0.0, 0.0
        self.until, self.version = None, 0

    def configure(self, shop=None, promo=None, cur=None):
        self.shop = self.shop if shop is None else shop
        self.promo = self.promo if promo is None else promo
        self.cur = self.cur if cur is None else cur
        self.version += 1

    def idle(self):
        if self.mode != "idle":
            self.mode, self.lines, self.hidden, self.total, self.change, self.until = "idle", [], 0, 0.0, 0.0, None
            self.version += 1

    def set_cart(self, cart, total=None, now=None):
        """cart: the billing cart (dicts with name, qty, price, optional unit). An EMPTY cart returns to idle - except right after a payment,
        when the thank-you stays up for THANKS_SECONDS."""
        now = now or datetime.now()
        if not cart:
            if not (self.mode == "thanks" and self.until and now < self.until):
                self.idle()
            return
        items = [(str(i.get("name", ""))[:40], float(i.get("qty", 0)), (i.get("unit") or ""), float(i.get("price", 0)), round(float(i.get("qty", 0)) * float(i.get("price", 0)), 2)) for i in cart]
        self.lines = items[-self.MAX_LINES:]
        self.hidden = max(0, len(items) - self.MAX_LINES)
        self.total = round(sum(x[4] for x in items), 2) if total is None else round(float(total), 2)
        self.mode, self.change, self.until = "bill", 0.0, None
        self.version += 1

    def show_thanks(self, total, change=0.0, now=None):
        now = now or datetime.now()
        self.mode, self.lines, self.hidden = "thanks", [], 0
        self.total, self.change, self.until = round(float(total), 2), round(float(change or 0), 2), now + timedelta(seconds=self.THANKS_SECONDS)
        self.version += 1

    def tick(self, now=None):
        """Call regularly; the thank-you screen returns to idle by itself. True if the display changed."""
        now = now or datetime.now()
        if self.mode == "thanks" and self.until and now >= self.until:
            self.idle()
            return True
        return False

    def snapshot(self):
        return dict(mode=self.mode, shop=self.shop, promo=self.promo, cur=self.cur, lines=list(self.lines), hidden=self.hidden,
                    total=self.total, change=self.change, version=self.version)
