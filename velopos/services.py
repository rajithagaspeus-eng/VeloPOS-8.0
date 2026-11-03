"""Business logic with no UI code, so it can be tested and reused."""
import math, os, re, sqlite3, subprocess, threading, time, urllib.parse, webbrowser
from datetime import datetime

from . import database as dbm, security


# ------------------------------------------------------------------ input validation (Phase 6.5)
PAY_METHODS = ("Cash", "Card", "QR", "Credit")


def num(value, what="Value", *, minimum=None, maximum=None, allow_blank=False, default=0.0):
    """Parse a number typed by a person. Python happily turns 'nan' and 'inf' into floats, which would write NULL / infinite
    values into the database - so those (and anything that is not a number) are refused with a readable message."""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            if allow_blank:
                return float(default)
            raise ValueError(f"{what}: please enter a number")
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what}: '{value}' is not a valid number") from None
    if not math.isfinite(x):
        raise ValueError(f"{what}: '{value}' is not a valid number")
    if minimum is not None and x < minimum:
        raise ValueError(f"{what} cannot be less than {minimum:g}")
    if maximum is not None and x > maximum:
        raise ValueError(f"{what} cannot be more than {maximum:g}")
    return x


def csv_safe(v):
    """Excel / LibreOffice run text starting with = + - @ as a FORMULA. Prefix such text with an apostrophe (real numbers are left alone)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(v)
            return v
        except ValueError:
            return "'" + v
    return v


def _next_no(c, table, column, prefix):
    """Next running number 'PREFIX-0001'. Uses the NUMERIC maximum: sorting the text breaks once a day passes 9999 ('-9999' > '-10000')."""
    r = c.execute(f"SELECT MAX(CAST(SUBSTR({column}, ?) AS INTEGER)) FROM {table} WHERE {column} LIKE ?", (len(prefix) + 2, prefix + "-%")).fetchone()[0]
    return f"{prefix}-{(r or 0) + 1:04d}"


def _require_open_shift(c, shift_id):
    if shift_id:
        sh = c.execute("SELECT status FROM shifts WHERE id=?", (shift_id,)).fetchone()
        if not sh or sh["status"] != "OPEN":
            raise ValueError("This shift is not open (it was closed or does not exist). Open a shift first.")


# ------------------------------------------------------------------ product helpers
def get_product(barcode):
    with dbm.db() as c:
        return c.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()


def search_products(q, limit=8):
    like = f"%{q}%"
    with dbm.db() as c:
        return c.execute(
            "SELECT * FROM products WHERE barcode LIKE ? OR name_en LIKE ? OR name_local LIKE ? "
            "OR keywords LIKE ? ORDER BY name_en LIMIT ?", (like, like, like, like, limit)).fetchall()


def expiry_state(exp):
    """-> ('OK'|'SOON'|'EXPIRED', days)"""
    if not exp or not exp.strip():
        return ("OK", 999)
    try:
        days = (datetime.strptime(exp.strip(), "%Y-%m-%d").date() - datetime.now().date()).days
    except ValueError:
        return ("OK", 999)
    return ("EXPIRED", days) if days < 0 else (("SOON", days) if days <= 30 else ("OK", days))


# ------------------------------------------------------------------ VAT / service charge (Phase 6.3)
class CreditLimitError(ValueError):
    """Raised when a credit sale would push a customer over their credit limit (an Admin can override)."""
    def __init__(self, name, limit, balance, add):
        self.name, self.limit, self.balance, self.add = name, limit, balance, add
        super().__init__(f"{name}: the credit limit of {limit:,.2f} would be exceeded (due {balance:,.2f} + this bill {add:,.2f} = {balance + add:,.2f}).")


def _pct(v, default=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return min(100.0, max(0.0, x))


def compute_bill(lines, discount=0.0, redeem=0.0, cfg=None):
    """Totals of a bill. lines: [(line amount, taxable?)]. Rules (all rounded to 2 decimals PER BILL):
    * discount + redeemed points are spread over all lines proportionally;
    * service charge = service% of the discounted subtotal (not taxed unless 'vat_on_service' and the mode is Exclusive);
    * VAT Exclusive: VAT = vat% of the discounted TAXABLE amount, ADDED to the bill;  Inclusive: prices already contain VAT, the VAT part
      (taxable x vat/(100+vat)) is only shown/recorded;
    * with both features OFF the result equals the pre-6.3 total exactly.
    -> dict(sub, base, service, vat, vat_pct, service_pct, vat_mode, net)"""
    cfg = cfg or dbm.settings
    sub = round(sum(a for a, _ in lines), 2)
    base = round(max(0.0, sub - round(discount, 2) - round(redeem, 2)), 2)
    dis = round(discount, 2) + round(redeem, 2)
    out = dict(sub=sub, base=base, service=0.0, vat=0.0, vat_pct=0.0, service_pct=0.0, vat_mode="", net=base)
    if cfg.bool("feat_service_charge"):
        sp = _pct(cfg.get("service_percent"))
        out.update(service_pct=sp, service=round(base * sp / 100, 2))
    if cfg.bool("feat_vat"):
        vp = _pct(cfg.get("vat_percent"))
        mode = "Inclusive" if cfg.get("vat_mode") == "Inclusive" else "Exclusive"
        out.update(vat_pct=vp, vat_mode=mode)
        if vp > 0:
            tsub = sum(a for a, t in lines if t)
            tnet = max(0.0, tsub - dis * (tsub / sub)) if sub > 0 else 0.0
            if mode == "Inclusive":
                out["vat"] = round(tnet * vp / (100 + vp), 2)
            else:
                tb = tnet + ((out["service"] * tnet / base) if cfg.bool("vat_on_service") and base > 0 else 0.0)
                out["vat"] = round(tb * vp / 100, 2)
    out["net"] = round(base + out["service"] + (out["vat"] if out["vat_mode"] == "Exclusive" else 0.0), 2)
    return out


def _is_taxable(c, barcode):
    r = c.execute("SELECT COALESCE(taxable, 1) t FROM products WHERE barcode=?", (barcode,)).fetchone()
    return bool(r["t"]) if r else True


def preview_bill(cart, discount=0.0, redeem=0.0):
    """Same numbers create_sale will use - for the Billing screen (read-only)."""
    with dbm.db() as c:
        return compute_bill([(round(i["qty"] * i["price"], 2), _is_taxable(c, i["barcode"])) for i in cart], discount, redeem)


# ------------------------------------------------------------------ the sale (ONE transaction)
def create_sale(cart, discount, redeem, paid, method, ref, customer_id, cashier, shift_id=None, override_user=None):
    """
    cart: list of dicts {barcode, name, qty, price, serial, warranty}
    Everything (stock, loyalty, credit, bill) is committed together or rolled back together.
    """
    if not cart:
        raise ValueError("Cart is empty")
    for i in cart:                                                   # the service is the last line of defence - never trust the screen
        if num(i.get("qty"), "Quantity") <= 0:
            raise ValueError("Quantity must be greater than zero")
        num(i.get("price"), "Price", minimum=0)
    sub = round(sum(round(i["qty"] * i["price"], 2) for i in cart), 2)      # sum of the ROUNDED lines, so the receipt always adds up
    discount, redeem = round(num(discount, "Discount", minimum=0), 2), round(num(redeem, "Redeemed points", minimum=0), 2)
    paid = num(paid, "Paid amount", minimum=0)
    if method not in PAY_METHODS:
        raise ValueError(f"Unknown payment method '{method}'")
    if discount > sub + 0.004:
        raise ValueError("The discount cannot be more than the bill amount")
    if redeem > round(sub - discount, 2) + 0.004:
        raise ValueError("Redeemed points cannot be more than the bill amount")
    if method == "Credit" and not customer_id:
        raise ValueError("Select a registered customer for credit sales")

    now = datetime.now()
    dt, tm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    c = dbm.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_open_shift(c, shift_id)
        oversell = dbm.settings.bool("feat_allow_oversell")        # shop chose to sell even when the computer's stock says 0
        facs = [_cart_unit(c, it) for it in cart]                   # (factor, unit name) re-derived here - never trusted from the client
        need = {}
        for it, (f, _u) in zip(cart, facs):
            need[it["barcode"]] = round(need.get(it["barcode"], 0) + it["qty"] * f, 6)
        for b, q in need.items():
            r = c.execute("SELECT stock_qty, name_en FROM products WHERE barcode=?", (b,)).fetchone()
            if not r:
                raise ValueError(f"Product {b} no longer exists")
            if r["stock_qty"] + 1e-9 < q and not oversell:
                raise ValueError(f"Not enough stock for {r['name_en']} (available {r['stock_qty']:g})")

        tax = compute_bill([(round(it["qty"] * it["price"], 2), _is_taxable(c, it["barcode"])) for it in cart], discount, redeem)
        net = tax["net"]
        if method == "Credit":
            paid = min(paid, net)                                   # a credit sale never records more than the bill (no phantom cash in the drawer)
            cdue, bal = round(max(0.0, net - paid), 2), 0.0
        else:
            if paid + 1e-9 < net:
                raise ValueError("Paid amount is less than the net payable")
            cdue, bal = 0.0, round(paid - net, 2)

        inv = _next_no(c, "sales", "invoice_no", "INV" + now.strftime("%Y%m%d"))

        profit, lines = 0.0, []
        skip_expired = _batches_on() and dbm.settings.bool("feat_block_expired")
        for it, (f, uname) in zip(cart, facs):
            cost = c.execute("SELECT cost_price FROM products WHERE barcode=?",
                             (it["barcode"],)).fetchone()["cost_price"]
            line = round(it["qty"] * it["price"], 2)
            profit += ((it["price"] - cost) if f == 1.0 else (it["price"] - cost * f)) * it["qty"]
            shown = it["name"] if not uname else f"{it['name']} [{uname}]"
            cur = c.execute("INSERT INTO sale_items(invoice_no, barcode, item_name, qty, cost_price, "
                            "selling_price, total, serial_no, warranty, unit, factor) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (inv, it["barcode"], shown, it["qty"], cost * f, it["price"], line,
                             it.get("serial", ""), it.get("warranty", ""), uname, f))
            consume_stock(c, it["barcode"], round(it["qty"] * f, 6), "SALE", inv, cashier, sale_item_id=cur.lastrowid, skip_expired=skip_expired, allow_negative=oversell)
            lines.append((shown, it["qty"], it["price"], line, it.get("serial", ""), it.get("warranty", "")))
        if tax["vat_mode"] == "Inclusive":
            profit -= tax["vat"]                         # the VAT inside the prices is not profit (with Exclusive VAT it never enters the profit)
        profit = round(profit - discount - redeem, 2)   # redeemed points are a real cost

        cname = "Walk-in"
        if customer_id:
            cu = c.execute("SELECT name, loyalty_points, credit_limit, credit_balance FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not cu:
                raise ValueError("Customer not found")
            if method == "Credit" and cdue > 0 and dbm.settings.bool("feat_credit_limit"):
                lim = cu["credit_limit"] or 0.0
                if lim > 0 and cu["credit_balance"] + cdue > lim + 1e-9:
                    if not override_user:
                        raise CreditLimitError(cu["name"], lim, cu["credit_balance"], cdue)
                    adm = c.execute("SELECT role FROM users WHERE username=?", (override_user,)).fetchone()
                    if not adm or adm["role"] != "Admin":
                        raise ValueError("Only an Admin can approve a credit-limit override")
                    _audit_c(c, override_user, "CREDIT_LIMIT_OVERRIDE", f"{cu['name']} limit={lim:,.2f} due={cu['credit_balance']:,.2f} + {cdue:,.2f} cashier={cashier}")
            if redeem > cu["loyalty_points"] + 1e-9:
                raise ValueError(f"Customer has only {cu['loyalty_points']:.0f} loyalty points")
            cname = cu["name"]
            c.execute("UPDATE customers SET credit_balance = credit_balance + ?, "
                      "loyalty_points = loyalty_points - ? + ? WHERE id=?",
                      (cdue, redeem, round((net - cdue) / 100, 2), customer_id))        # points are earned on what was actually paid
            if cdue > 0:
                c.execute("INSERT INTO credit_logs(customer_id, date, time, description, amount, type) "
                          "VALUES (?,?,?,?,?,'CREDIT_SALE')", (customer_id, dt, tm, f"Invoice {inv}", cdue))
        elif redeem > 0:
            raise ValueError("Select a customer to redeem loyalty points")

        c.execute("INSERT INTO sales(invoice_no, date, time, subtotal, discount, redeemed, total_amount, "
                  "paid_amount, balance, payment_method, payment_ref, profit, cashier, customer_id, "
                  "customer_name, shift_id, vat_amount, service_amount, vat_pct, service_pct, vat_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (inv, dt, tm, sub, discount, redeem, net, paid, bal, method, ref, profit, cashier,
                   customer_id, cname, shift_id, tax["vat"], tax["service"], tax["vat_pct"], tax["service_pct"], tax["vat_mode"]))
        c.execute("INSERT INTO audit_log(ts, user, action, detail) VALUES (?,?,?,?)",
                  (now.isoformat(timespec="seconds"), cashier, "SALE", f"{inv} net={net} method={method}"))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return dict(invoice=inv, date=dt, time=tm, items=lines, sub=sub, discount=discount, redeem=redeem,
                net=net, paid=paid, balance=bal, credit_due=cdue, customer=cname, method=method,
                ref=ref, cashier=cashier, vat=tax["vat"], service=tax["service"], vat_mode=tax["vat_mode"], vat_pct=tax["vat_pct"],
                service_pct=tax["service_pct"])


def settle_credit(customer_id, amount, user, shift_id=None):
    amount = num(amount, "Amount", minimum=0)
    with dbm.db() as c:
        _require_open_shift(c, shift_id)
        cu = c.execute("SELECT credit_balance AS balance FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not cu:
            raise ValueError("Customer not found")
        amt = min(round(amount, 2), cu["balance"])
        if amt <= 0:
            raise ValueError("Nothing to settle")
        now = datetime.now()
        c.execute("UPDATE customers SET credit_balance = credit_balance - ? WHERE id=?", (amt, customer_id))
        c.execute("INSERT INTO credit_logs(customer_id, date, time, description, amount, type) "
                  "VALUES (?,?,?,?,?,'PAYMENT')",
                  (customer_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "Settlement", amt))
        if shift_id:
            c.execute("INSERT INTO cash_moves(shift_id, ts, kind, amount, reason, user) VALUES (?,?,?,?,?,?)",
                      (shift_id, now.isoformat(timespec="seconds"), "IN", amt, f"Credit settlement (customer {customer_id})", user))
        c.execute("INSERT INTO audit_log(ts, user, action, detail) VALUES (?,?,?,?)",
                  (now.isoformat(timespec="seconds"), user, "CREDIT_PAYMENT", f"cust={customer_id} amt={amt}"))
    return amt


# ------------------------------------------------------------------ receipts
def receipt_text(sale, shop, width, cur):
    w = width
    out = [shop["name"][:w].center(w), shop["address"][:w].center(w), f"Tel: {shop['phone']}".center(w),
           "=" * w, f"Inv: {sale['invoice']}", f"{sale['date']} {sale['time']}",
           f"Cust: {sale['customer']}  Cashier: {sale['cashier'].upper()}",
           f"Mode: {sale['method']}" + (f" ({sale['ref']})" if sale["ref"] else ""), "-" * w]
    for n, q, pr, line, ser, war in sale["items"]:
        out.append(n[:w])
        left, right = f"  {q:g} x {pr:,.2f}", f"{line:,.2f}"
        out.append(left + right.rjust(w - len(left)))
        if ser or war:
            out.append(f"  SN:{ser} War:{war}"[:w])
    out.append("-" * w)

    def row(label, val):
        return label + val.rjust(w - len(label))
    out.append(row("Sub Total", f"{cur} {sale['sub']:,.2f}"))
    if sale["discount"]:
        out.append(row("Discount", f"-{cur} {sale['discount']:,.2f}"))
    if sale["redeem"]:
        out.append(row("Points Redeemed", f"-{cur} {sale['redeem']:,.2f}"))
    if sale.get("service"):
        out.append(row(f"Service ({sale.get('service_pct', 0):g}%)", f"{cur} {sale['service']:,.2f}"))
    if sale.get("vat") and sale.get("vat_mode") == "Exclusive":
        out.append(row(f"VAT ({sale.get('vat_pct', 0):g}%)", f"{cur} {sale['vat']:,.2f}"))
    out.append(row("NET TOTAL", f"{cur} {sale['net']:,.2f}"))
    if sale.get("vat") and sale.get("vat_mode") == "Inclusive":
        out.append(row(f"incl. VAT ({sale.get('vat_pct', 0):g}%)", f"{cur} {sale['vat']:,.2f}"))
    out.append(row(f"Paid ({sale['method']})", f"{cur} {sale['paid']:,.2f}"))
    out.append(row("CREDIT DUE", f"{cur} {sale['credit_due']:,.2f}") if sale["method"] == "Credit"
                else row("Balance", f"{cur} {sale['balance']:,.2f}"))
    out += ["=" * w, "Thank You! Come Again!".center(w)]
    return "\n".join(out)


def save_receipt(sale, text):
    path = dbm.p("Receipts", sale["invoice"] + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def whatsapp_url(phone, sale, shop_name, cur):
    ph = "".join(ch for ch in str(phone) if ch.isdigit())
    if ph.startswith("0") and len(ph) == 10:
        ph = "94" + ph[1:]
    lines = [f"*{shop_name}*", f"Invoice: {sale['invoice']}", f"Date: {sale['date']} {sale['time']}", "-" * 20]
    for n, q, pr, line, ser, war in sale["items"]:
        lines.append(f"• {n} ({q:g} x {pr:,.2f}) = *{cur} {line:,.2f}*")
    lines += ["-" * 20, f"*NET TOTAL: {cur} {sale['net']:,.2f}*",
              f"Paid ({sale['method']}): {cur} {sale['paid']:,.2f}"]
    if sale["balance"] > 0:
        lines.append(f"Balance: {cur} {sale['balance']:,.2f}")
    if sale["credit_due"] > 0:
        lines.append(f"Credit due: {cur} {sale['credit_due']:,.2f}")
    lines.append("\n_Thank you for your business!_")
    return f"https://wa.me/{ph}?text={urllib.parse.quote(chr(10).join(lines))}" if ph else \
        f"https://wa.me/?text={urllib.parse.quote(chr(10).join(lines))}"


def open_url(url, prefer_desktop=False):
    if prefer_desktop and os.name == "nt" and "wa.me" in url:
        try:
            os.startfile(url.replace("https://wa.me/", "whatsapp://send?phone=").replace("?text=", "&text="))
            return
        except Exception:
            pass
    webbrowser.open(url)


# ------------------------------------------------------------------ voice (no shell-injection)
def speak(text, enabled=True):
    if not enabled or not text or os.name != "nt":
        return

    def run():
        try:
            env = dict(os.environ, VP_TEXT=str(text))     # text travels as data, never as code
            subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                            "Add-Type -AssemblyName System.Speech;"
                            "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak($env:VP_TEXT)"],
                           env=env, creationflags=0x08000000, timeout=20)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def list_printers():
    printers = ["Default System Printer"]
    if os.name == "nt":
        try:
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
                                           "Get-Printer | Select-Object -ExpandProperty Name"],
                                          creationflags=0x08000000, text=True, timeout=5)
            printers += [x.strip() for x in out.splitlines() if x.strip() and x.strip() not in printers]
        except Exception:
            pass
    return printers


# ================================================================== PHASE 2: shifts / cash drawer
def _now():
    return datetime.now().isoformat(timespec="seconds")


def current_shift(user):
    with dbm.db() as c:
        return c.execute("SELECT * FROM shifts WHERE cashier=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (user,)).fetchone()


def open_shift(user, opening):
    opening = num(opening, "Opening cash")
    if opening < 0:
        raise ValueError("Opening cash cannot be negative")
    if current_shift(user):
        raise ValueError("You already have an open shift")
    with dbm.db() as c:
        sid = c.execute("INSERT INTO shifts(cashier, opened_at, opening_cash, status) VALUES (?,?,?,'OPEN')",
                        (user, _now(), round(opening, 2))).lastrowid
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "SHIFT_OPEN", f"#{sid} cash={opening}"))
    return sid


def cash_move(shift_id, kind, amount, reason, user):
    amount = num(amount, "Amount")
    if kind not in ("IN", "OUT") or amount <= 0:
        raise ValueError("Enter an amount greater than zero")
    if not reason.strip():
        raise ValueError("Please enter a reason")
    with dbm.db() as c:
        sh = c.execute("SELECT status FROM shifts WHERE id=?", (shift_id,)).fetchone()
        if not sh or sh["status"] != "OPEN":
            raise ValueError("Shift is not open")
        c.execute("INSERT INTO cash_moves(shift_id, ts, kind, amount, reason, user) VALUES (?,?,?,?,?,?)",
                  (shift_id, _now(), kind, round(amount, 2), reason.strip(), user))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "CASH_" + kind, f"shift {shift_id} {amount} {reason}"))


def shift_summary(shift_id):
    with dbm.db() as c:
        sh = c.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
        by = {r["m"]: (r["n"], r["t"]) for r in c.execute(
            "SELECT payment_method m, COUNT(*) n, COALESCE(SUM(total_amount),0) t FROM sales "
            "WHERE shift_id=? AND status='OK' GROUP BY payment_method", (shift_id,))}
        cash_sales = c.execute("SELECT COALESCE(SUM(CASE payment_method WHEN 'Cash' THEN total_amount "
                               "WHEN 'Credit' THEN paid_amount ELSE 0 END),0) FROM sales WHERE shift_id=? AND status='OK'", (shift_id,)).fetchone()[0]
        mv = {r["kind"]: r["t"] for r in c.execute("SELECT kind, SUM(amount) t FROM cash_moves WHERE shift_id=? GROUP BY kind", (shift_id,))}
        moves = c.execute("SELECT ts, kind, amount, reason FROM cash_moves WHERE shift_id=? ORDER BY id", (shift_id,)).fetchall()
        rets = c.execute("SELECT COALESCE(SUM(amount),0) FROM returns WHERE shift_id=?", (shift_id,)).fetchone()[0]
    ins, outs = mv.get("IN", 0.0), mv.get("OUT", 0.0)
    expected = round(sh["opening_cash"] + cash_sales + ins - outs, 2)
    return dict(shift=sh, by=by, sales_total=sum(t for _, t in by.values()), cash_sales=round(cash_sales, 2),
                ins=ins, outs=outs, returns=rets, expected=expected, moves=moves)


def close_shift(shift_id, counted, note, user):
    sm = shift_summary(shift_id)
    if sm["shift"]["status"] != "OPEN":
        raise ValueError("Shift already closed")
    counted = num(counted, "Counted cash")
    if counted < 0:
        raise ValueError("Counted cash cannot be negative")
    diff = round(counted - sm["expected"], 2)
    with dbm.db() as c:
        c.execute("UPDATE shifts SET closed_at=?, counted_cash=?, expected_cash=?, difference=?, status='CLOSED', note=? WHERE id=?",
                  (_now(), round(counted, 2), sm["expected"], diff, note, shift_id))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "SHIFT_CLOSE", f"#{shift_id} expected={sm['expected']} counted={counted} diff={diff}"))
    return diff


def z_report_text(shift_id, width, cur, shop_name):
    sm = shift_summary(shift_id)
    sh, w = sm["shift"], width

    def row(a, b):
        return a + str(b).rjust(w - len(a))
    out = [shop_name[:w].center(w), "Z-REPORT / SHIFT SUMMARY".center(w), "=" * w,
           row("Shift #", sh["id"]), row("Cashier", sh["cashier"].upper()), row("Opened", sh["opened_at"].replace("T", " ")),
           row("Closed", (sh["closed_at"] or "still open").replace("T", " ")), "-" * w, "SALES (excl. voids)"]
    for m, (n, t) in sorted(sm["by"].items()):
        out.append(row(f"  {m} ({n} bills)", f"{cur} {t:,.2f}"))
    out += [row("  TOTAL SALES", f"{cur} {sm['sales_total']:,.2f}"), row("  Returns/refunds", f"{cur} {sm['returns']:,.2f}"), "-" * w, "CASH DRAWER",
            row("  Opening cash", f"{cur} {sh['opening_cash']:,.2f}"), row("  + Cash from sales", f"{cur} {sm['cash_sales']:,.2f}"),
            row("  + Cash in", f"{cur} {sm['ins']:,.2f}"), row("  - Cash out", f"{cur} {sm['outs']:,.2f}"),
            row("  = EXPECTED", f"{cur} {sm['expected']:,.2f}")]
    if sh["status"] == "CLOSED":
        d = sh["difference"]
        out += [row("  COUNTED", f"{cur} {sh['counted_cash']:,.2f}"),
                row("  DIFFERENCE", f"{cur} {d:+,.2f} " + ("(OVER)" if d > 0 else "(SHORT)" if d < 0 else "(OK)"))]
    if sm["moves"]:
        out += ["-" * w, "CASH IN / OUT LOG"]
        out += [f"  {m['ts'][11:16]} {m['kind']:<3} {m['amount']:,.2f}  {m['reason']}"[:w] for m in sm["moves"]]
    if sh["note"]:
        out += ["-" * w, f"Note: {sh['note']}"]
    out += ["=" * w, "Signature: ______________".center(w)]
    return "\n".join(out)


# ================================================================== PHASE 2: returns / void
def load_sale(inv):
    with dbm.db() as c:
        s = c.execute("SELECT * FROM sales WHERE invoice_no=?", (inv,)).fetchone()
        if not s:
            return None
        its = c.execute("SELECT * FROM sale_items WHERE invoice_no=? ORDER BY id", (inv,)).fetchall()
    sale = dict(invoice=inv, date=s["date"], time=s["time"], sub=s["subtotal"], discount=s["discount"], redeem=s["redeemed"] or 0,
                net=s["total_amount"], paid=s["paid_amount"], balance=s["balance"], method=s["payment_method"], ref=s["payment_ref"] or "",
                cashier=s["cashier"], customer=s["customer_name"], status=s["status"], shift_id=s["shift_id"], customer_id=s["customer_id"],
                credit_due=max(0.0, s["total_amount"] - s["paid_amount"]) if s["payment_method"] == "Credit" else 0.0,
                vat=s["vat_amount"] or 0.0, service=s["service_amount"] or 0.0, vat_mode=s["vat_mode"] or "", vat_pct=s["vat_pct"] or 0.0,
                service_pct=s["service_pct"] or 0.0,
                items=[(i["item_name"], i["qty"], i["selling_price"], i["total"], i["serial_no"], i["warranty"]) for i in its])
    return sale


def returnable_items(inv):
    """[(sale_item_id, barcode, name, sold, already_returned, price)]"""
    with dbm.db() as c:
        return [(r["id"], r["barcode"], r["item_name"], r["qty"], r["done"], r["selling_price"]) for r in c.execute(
            "SELECT si.*, COALESCE((SELECT SUM(qty) FROM return_items ri WHERE ri.sale_item_id=si.id),0) done "
            "FROM sale_items si WHERE si.invoice_no=? ORDER BY si.id", (inv,))]


def create_return(invoice, lines, method, reason, user, shift_id=None):
    """lines: [(sale_item_id, qty)]; method: 'Cash' | 'Credit Book' | 'Card/QR (manual)'"""
    lines = [(i, num(q, "Return quantity")) for i, q in lines]
    lines = [(i, q) for i, q in lines if q > 0]
    if not lines:
        raise ValueError("Select at least one item and quantity to return")
    if not reason.strip():
        raise ValueError("Please enter a reason for the return")
    if method not in ("Cash", "Credit Book", "Card/QR (manual)"):
        raise ValueError(f"Unknown refund method '{method}'")
    now = datetime.now()
    c = dbm.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        s = c.execute("SELECT * FROM sales WHERE invoice_no=?", (invoice,)).fetchone()
        if not s or s["status"] != "OK":
            raise ValueError("Invoice not found or already voided")
        gross = cost = 0.0
        rows = []
        for iid, q in lines:
            it = c.execute("SELECT * FROM sale_items WHERE id=? AND invoice_no=?", (iid, invoice)).fetchone()
            if not it:
                raise ValueError("Item is not on this invoice")
            done = c.execute("SELECT COALESCE(SUM(qty),0) FROM return_items WHERE sale_item_id=?", (iid,)).fetchone()[0]
            if q > it["qty"] - done + 1e-9:
                raise ValueError(f"Only {it['qty'] - done:g} of '{it['item_name']}' can still be returned")
            gross += q * it["selling_price"]
            cost += q * it["cost_price"]
            rows.append((it, q))
        factor = (s["total_amount"] / s["subtotal"]) if s["subtotal"] > 0 else 1.0   # keeps bill discount fair
        amount = round(gross * factor, 2)
        tot = s["total_amount"] or 0.0
        vat_adj = round(amount * (s["vat_amount"] or 0.0) / tot, 2) if tot > 0 else 0.0           # tax / service charge are returned in proportion
        svc_adj = round(amount * (s["service_amount"] or 0.0) / tot, 2) if tot > 0 else 0.0
        rno = _next_no(c, "returns", "return_no", "RET" + now.strftime("%Y%m%d"))
        cid = s["customer_id"]
        credit_offset, cash_out = 0.0, amount
        if method == "Credit Book":
            if not cid:
                raise ValueError("This bill has no registered customer - choose Cash")
            due = c.execute("SELECT credit_balance FROM customers WHERE id=?", (cid,)).fetchone()[0]
            if amount > due + 1e-9:
                raise ValueError(f"Refund {amount:,.2f} is more than the customer's credit due ({due:,.2f}). Use Cash.")
            c.execute("UPDATE customers SET credit_balance = credit_balance - ? WHERE id=?", (amount, cid))
            c.execute("INSERT INTO credit_logs(customer_id,date,time,description,amount,type) VALUES (?,?,?,?,?,'RETURN')",
                      (cid, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), f"Return {rno} ({invoice})", amount))
            credit_offset, cash_out = amount, 0.0
        elif method == "Cash" and cid and s["payment_method"] == "Credit":
            # A credit sale: the part the customer has NOT paid yet is taken off their debt first - only the rest is paid back in cash.
            owed = c.execute("SELECT credit_balance FROM customers WHERE id=?", (cid,)).fetchone()[0] or 0.0
            prior = c.execute("SELECT COALESCE(SUM(credit_offset),0) FROM returns WHERE invoice_no=?", (invoice,)).fetchone()[0] or 0.0
            unpaid_left = max(0.0, round((s["total_amount"] or 0.0) - (s["paid_amount"] or 0.0) - prior, 2))
            credit_offset = round(min(amount, max(0.0, owed), unpaid_left), 2)
            if credit_offset > 0:
                c.execute("UPDATE customers SET credit_balance = credit_balance - ? WHERE id=?", (credit_offset, cid))
                c.execute("INSERT INTO credit_logs(customer_id,date,time,description,amount,type) VALUES (?,?,?,?,?,'RETURN')",
                          (cid, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), f"Return {rno} ({invoice})", credit_offset))
                cash_out = round(amount - credit_offset, 2)
        if method == "Cash" and shift_id and cash_out > 0:
            c.execute("INSERT INTO cash_moves(shift_id,ts,kind,amount,reason,user) VALUES (?,?,?,?,?,?)",
                      (shift_id, _now(), "OUT", cash_out, f"Refund {rno}", user))
        for it, q in rows:
            restore_stock(c, it["id"], it["barcode"], round(q * (it["factor"] or 1), 6), "RETURN", rno, user)
            c.execute("INSERT INTO return_items(return_no,sale_item_id,barcode,item_name,qty,price,total) VALUES (?,?,?,?,?,?,?)",
                      (rno, it["id"], it["barcode"], it["item_name"], q, it["selling_price"], round(q * it["selling_price"], 2)))
        if cid:
            c.execute("UPDATE customers SET loyalty_points = MAX(0, loyalty_points - ?) WHERE id=?", (round(amount / 100, 2), cid))
        c.execute("INSERT INTO returns(return_no,invoice_no,date,time,amount,refund_method,reason,cashier,shift_id,profit_adj,vat_adj,service_adj,credit_offset) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (rno, invoice, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), amount, method, reason.strip(), user, shift_id,
                   round(-(amount - vat_adj - svc_adj - cost), 2), vat_adj, svc_adj, credit_offset))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "RETURN", f"{rno} inv={invoice} amt={amount} {method} credit_offset={credit_offset} cash_out={cash_out if method == 'Cash' else 0}"))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return dict(return_no=rno, amount=amount, method=method, credit_offset=credit_offset, cash_out=cash_out if method == "Cash" else 0.0)


def void_sale(invoice, user, reason=""):
    """Admin action. Restores stock, credit and loyalty. Only for bills in an open/no shift, with no returns."""
    c = dbm.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        s = c.execute("SELECT * FROM sales WHERE invoice_no=?", (invoice,)).fetchone()
        if not s or s["status"] != "OK":
            raise ValueError("Invoice not found or already voided")
        if c.execute("SELECT 1 FROM returns WHERE invoice_no=?", (invoice,)).fetchone():
            raise ValueError("This bill already has returns - void is not allowed")
        if s["shift_id"]:
            sh = c.execute("SELECT status FROM shifts WHERE id=?", (s["shift_id"],)).fetchone()
            if sh and sh["status"] != "OPEN":
                raise ValueError("This bill belongs to a CLOSED shift. Use Returns & Refunds instead.")
        for it in c.execute("SELECT id, barcode, qty, COALESCE(factor, 1) f FROM sale_items WHERE invoice_no=?", (invoice,)).fetchall():
            restore_stock(c, it["id"], it["barcode"], round(it["qty"] * it["f"], 6), "VOID", invoice, user)
        if s["customer_id"]:
            cdue = max(0.0, s["total_amount"] - s["paid_amount"]) if s["payment_method"] == "Credit" else 0.0
            if cdue > 0:
                bal = c.execute("SELECT credit_balance FROM customers WHERE id=?", (s["customer_id"],)).fetchone()[0] or 0.0
                if bal + 0.004 < cdue:
                    raise ValueError(f"The customer has already paid back part of this credit (they owe {bal:,.2f} now, this bill added {cdue:,.2f}). "
                                     "Voiding would swallow that payment - use Returns & Refunds instead.")
            c.execute("UPDATE customers SET credit_balance = MAX(0, credit_balance - ?), "
                      "loyalty_points = MAX(0, loyalty_points + ? - ?) WHERE id=?",
                      (cdue, s["redeemed"] or 0, round((s["total_amount"] - cdue) / 100, 2), s["customer_id"]))
            if cdue > 0:
                c.execute("INSERT INTO credit_logs(customer_id,date,time,description,amount,type) VALUES (?,?,?,?,?,'VOID')",
                          (s["customer_id"], datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S"), f"Void {invoice}", cdue))
        c.execute("UPDATE sales SET status='VOID' WHERE invoice_no=?", (invoice,))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "VOID", f"{invoice} net={s['total_amount']} reason={reason}"))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


# ================================================================== PHASE 2: reports
def report_data(df, dt):
    with dbm.db() as c:
        s = c.execute("SELECT COUNT(*) n, COALESCE(SUM(total_amount),0) rev, COALESCE(SUM(profit),0) prof FROM sales "
                      "WHERE date BETWEEN ? AND ? AND status='OK'", (df, dt)).fetchone()
        r = c.execute("SELECT COALESCE(SUM(amount),0) a, COALESCE(SUM(profit_adj),0) p FROM returns WHERE date BETWEEN ? AND ?", (df, dt)).fetchone()
        exp = c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date BETWEEN ? AND ?", (df, dt)).fetchone()[0]
        tx = c.execute("SELECT COALESCE(SUM(vat_amount),0) v, COALESCE(SUM(service_amount),0) s FROM sales WHERE date BETWEEN ? AND ? AND status='OK'", (df, dt)).fetchone()
        rt = c.execute("SELECT COALESCE(SUM(vat_adj),0) v, COALESCE(SUM(service_adj),0) s FROM returns WHERE date BETWEEN ? AND ?", (df, dt)).fetchone()
        methods = {x["m"]: x["t"] for x in c.execute("SELECT payment_method m, SUM(total_amount) t FROM sales WHERE date BETWEEN ? AND ? "
                                                    "AND status='OK' GROUP BY payment_method", (df, dt))}
        rows = c.execute("SELECT invoice_no,date,time,customer_name,total_amount,payment_method,profit,cashier,status FROM sales "
                         "WHERE date BETWEEN ? AND ? ORDER BY id DESC", (df, dt)).fetchall()
    return dict(bills=s["n"], sales=s["rev"], returns=r["a"], revenue=round(s["rev"] - r["a"], 2), expenses=exp,
                profit=round(s["prof"] + r["p"] - exp, 2), methods=methods, rows=rows,
                vat=round(tx["v"] - rt["v"], 2), service=round(tx["s"] - rt["s"], 2))


def low_stock_level():
    """Items at or below this quantity count as 'low stock' (Settings -> 4d; default 5)."""
    return max(0, dbm.settings.int("low_stock_level", 5))


def insights():
    with dbm.db() as c:
        top = c.execute("SELECT si.item_name, SUM(si.qty) q, SUM(si.total) t FROM sale_items si JOIN sales s ON s.invoice_no = si.invoice_no "
                        "WHERE s.status='OK' GROUP BY si.barcode ORDER BY t DESC LIMIT 5").fetchall()      # voided bills do not count
        low = c.execute("SELECT barcode, name_en, stock_qty FROM products WHERE stock_qty <= ? ORDER BY stock_qty", (low_stock_level(),)).fetchall()
        dead = c.execute("SELECT barcode, name_en, stock_qty, selling_price FROM products WHERE barcode NOT IN "
                         "(SELECT DISTINCT si.barcode FROM sale_items si JOIN sales s ON s.invoice_no = si.invoice_no WHERE s.status='OK') "
                         "AND stock_qty > 0 ORDER BY stock_qty * selling_price DESC LIMIT 10").fetchall()
    return top, low, dead


# ================================================================== PHASE 3: quotations
def create_quote(cart, customer, phone, valid_days, discount, note, user):
    from datetime import timedelta
    if not cart:
        raise ValueError("Cart is empty")
    for i in cart:
        if num(i.get("qty"), "Quantity") <= 0:
            raise ValueError("Quantity must be greater than zero")
        num(i.get("price"), "Price", minimum=0)
    valid_days = int(num(valid_days, "Valid days", minimum=1, maximum=3650))
    sub = round(sum(i["qty"] * i["price"] for i in cart), 2)
    discount = round(num(discount, "Discount", minimum=0), 2)
    if discount > sub + 0.004:
        raise ValueError("The discount cannot be more than the quotation amount")
    now = datetime.now()
    with dbm.db() as c:
        no = _next_no(c, "quotations", "quote_no", "QUO" + now.strftime("%Y%m%d"))
        c.execute("INSERT INTO quotations(quote_no,date,valid_until,customer_name,phone,subtotal,discount,total,note,status,created_by) "
                  "VALUES (?,?,?,?,?,?,?,?,?, 'OPEN', ?)",
                  (no, now.strftime("%Y-%m-%d"), (now + timedelta(days=max(1, valid_days))).strftime("%Y-%m-%d"),
                   customer, phone, sub, discount, max(0.0, round(sub - discount, 2)), note, user))
        for it in cart:
            c.execute("INSERT INTO quote_items(quote_no,barcode,item_name,qty,price,total) VALUES (?,?,?,?,?,?)",
                      (no, it["barcode"], it["name"], it["qty"], it["price"], round(it["qty"] * it["price"], 2)))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "QUOTE_CREATE", f"{no} total={sub - discount}"))
    return load_quote(no)


def load_quote(no):
    with dbm.db() as c:
        q = c.execute("SELECT * FROM quotations WHERE quote_no=?", (no,)).fetchone()
        if not q:
            return None
        its = c.execute("SELECT * FROM quote_items WHERE quote_no=? ORDER BY id", (no,)).fetchall()
    d = dict(q)
    d["items"] = [(i["item_name"], i["qty"], i["price"], i["total"]) for i in its]
    d["raw"] = [dict(barcode=i["barcode"], name=i["item_name"], qty=i["qty"], price=i["price"], serial="", warranty="") for i in its]
    return d


def list_quotes(search=""):
    like = f"%{search}%"
    with dbm.db() as c:
        return c.execute("SELECT * FROM quotations WHERE quote_no LIKE ? OR customer_name LIKE ? OR phone LIKE ? ORDER BY id DESC LIMIT 300",
                         (like, like, like)).fetchall()


def set_quote_status(no, status, user):
    if status not in ("OPEN", "ACCEPTED", "REJECTED", "EXPIRED", "CONVERTED", "CLOSED"):
        raise ValueError(f"Unknown quotation status '{status}'")
    with dbm.db() as c:
        c.execute("UPDATE quotations SET status=? WHERE quote_no=?", (status, no))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "QUOTE_" + status, no))


def delete_quote(no, user):
    with dbm.db() as c:
        c.execute("DELETE FROM quote_items WHERE quote_no=?", (no,))
        c.execute("DELETE FROM quotations WHERE quote_no=?", (no,))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user, "QUOTE_DELETE", no))


def quote_text(q, shop, width, cur):
    w = width
    out = [shop["name"][:w].center(w), "QUOTATION / ESTIMATE".center(w), "=" * w, f"No: {q['quote_no']}", f"Date: {q['date']}   Valid until: {q['valid_until']}",
           f"Customer: {q['customer_name'] or '-'} {q['phone'] or ''}".strip(), "-" * w]
    for n, qty, p, t in q["items"]:
        out.append(n[:w])
        left, right = f"  {qty:g} x {p:,.2f}", f"{t:,.2f}"
        out.append(left + right.rjust(w - len(left)))
    out.append("-" * w)
    out.append("Sub Total".ljust(w - len(f"{cur} {q['subtotal']:,.2f}")) + f"{cur} {q['subtotal']:,.2f}")
    if q["discount"]:
        out.append("Discount".ljust(w - len(f"-{cur} {q['discount']:,.2f}")) + f"-{cur} {q['discount']:,.2f}")
    out.append("QUOTED TOTAL".ljust(w - len(f"{cur} {q['total']:,.2f}")) + f"{cur} {q['total']:,.2f}")
    if q["note"]:
        out += ["-" * w, q["note"]]
    out += ["=" * w, "Estimate only - not a tax invoice".center(w)]
    return "\n".join(out)


# ================================================================== PHASE 4: safety & recovery
RESET_SCOPES = {
    "everything": "EVERYTHING: products, customers, suppliers, credit book, sales, returns, purchases, shifts, expenses, quotations",
    "sales_stock": "SALES + STOCK: all bills, returns, shifts, expenses, quotations, purchases & supplier payments, credit book; stock set to 0 "
                   "(product list and customer list are kept)",
    "products": "PRODUCTS ONLY: the product list (old bills stay, but returns of old bills can no longer restore stock)",
}
_SALES_TABLES = ["return_items", "returns", "sale_item_batches", "sale_items", "sales", "credit_logs", "cash_moves", "shifts",
                 "expenses", "quote_items", "quotations", "stock_count_lines", "stock_counts", "purchase_items", "purchases", "supplier_payments",
                 "reminder_log"]
_WIPE = {"everything": _SALES_TABLES + ["customers", "products", "price_history", "categories", "stock_moves", "batches", "product_units", "suppliers"],
         "sales_stock": _SALES_TABLES,
         "products": ["products", "price_history", "stock_moves", "batches", "product_units", "sale_item_batches", "stock_count_lines"]}


def table_counts():
    """{table: rows} for everything a Factory Reset could remove (shown in the confirmation dialog)."""
    out = {}
    with dbm.db() as c:
        for t in _WIPE["everything"]:
            out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return out


def verify_admin_password(user, password):
    with dbm.db() as c:
        r = c.execute("SELECT pw_hash, role FROM users WHERE username=?", (user,)).fetchone()
    return bool(r and r["role"] == "Admin" and security.verify_password(password, r["pw_hash"]))


def verify_recovery_code(code):
    with dbm.db() as c:
        r = c.execute("SELECT value FROM settings WHERE key='recovery_hash'").fetchone()
    stored = r["value"] if r else ""
    return bool(stored and code.strip() and security.verify_password(security.normalize_code(code), stored))


def regenerate_recovery_code(user):
    """Caller must already have checked the Admin password. The old code stops working immediately."""
    code = security.new_recovery_code()
    dbm.settings.set_many({"recovery_hash": security.hash_password(security.normalize_code(code))})
    dbm.audit(user, "RECOVERY_CODE_REGENERATED")
    return code


def admin_usernames():
    with dbm.db() as c:
        return [r["username"] for r in c.execute("SELECT username FROM users WHERE role='Admin' ORDER BY username")]


def reset_password(username, new_password, via, actor=None):
    """Forgot-password flow (after Recovery Code / OTP proof). Admin accounts only."""
    if len(new_password) < 6:
        raise ValueError("Password must be at least 6 characters")
    with dbm.db() as c:
        r = c.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        if not r:
            raise ValueError("User not found")
        if r["role"] != "Admin":
            raise ValueError("Only Admin passwords can be reset here. An Admin can reset a Cashier in Settings -> Staff accounts.")
        c.execute("UPDATE users SET pw_hash=? WHERE username=?", (security.hash_password(new_password), username))
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)",
                  (_now(), actor or username, "PASSWORD_RESET", f"{username} via={via}"))
    security.guard.ok(username)


# persistent lock-out (survives restarting the program, unlike LoginGuard)
def lock_remaining(scope):
    with dbm.db() as c:
        r = c.execute("SELECT locked_until FROM reset_attempts WHERE scope=?", (scope,)).fetchone()
    return max(0, int((r["locked_until"] if r else 0) - time.time()))


def register_fail(scope, max_fails=5, lock_secs=900):
    """Count a wrong Recovery Code / OTP. After `max_fails` the scope is locked. Returns True if now locked."""
    with dbm.db() as c:
        r = c.execute("SELECT fails FROM reset_attempts WHERE scope=?", (scope,)).fetchone()
        fails, until = (r["fails"] if r else 0) + 1, 0.0
        if fails >= max_fails:
            until, fails = time.time() + lock_secs, 0
        c.execute("INSERT INTO reset_attempts(scope, fails, locked_until) VALUES (?,?,?) "
                  "ON CONFLICT(scope) DO UPDATE SET fails=excluded.fails, locked_until=excluded.locked_until",
                  (scope, fails, until))
    return until > 0


def clear_fails(scope):
    with dbm.db() as c:
        c.execute("DELETE FROM reset_attempts WHERE scope=?", (scope,))


def factory_reset(scope, user, confirm_text):
    """Wipe business data. Order: validate -> automatic backup (abort if it fails) -> ONE transaction.
    Users, licence, settings and the audit log are always kept."""
    if scope not in _WIPE:
        raise ValueError("Unknown reset type")
    if confirm_text.strip() != "RESET":
        raise ValueError("Type RESET (capital letters) to confirm")
    from . import backup
    pre = backup.create("pre-reset")
    tables, counts = _WIPE[scope], {}
    c = dbm.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        for t in tables:
            counts[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            c.execute(f"DELETE FROM {t}")
        if scope == "sales_stock":
            for pr in c.execute("SELECT barcode, stock_qty FROM products WHERE stock_qty != 0").fetchall():
                apply_stock_move(c, pr["barcode"], -pr["stock_qty"], "RESET", "FACTORY_RESET", user, allow_negative=True)
            c.execute("UPDATE batches SET qty_remaining=0")
            c.execute("UPDATE customers SET credit_balance=0, loyalty_points=0")
        try:
            c.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({','.join('?' * len(tables))})", tables)
        except sqlite3.OperationalError:
            pass                                    # no AUTOINCREMENT table has been used yet
        c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)",
                  (_now(), user, "FACTORY_RESET", f"scope={scope} backup={os.path.basename(pre)} deleted={counts}"))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return dict(scope=scope, backup=pre, counts=counts)


# ================================================================== PHASE 6.1: catalogue (categories, product save/import, price tools, pictures)
import hashlib, math, re

IMAGE_MAX_BYTES = 25 * 1024 * 1024
BULK_FIELDS = {"selling_price": "sell", "wholesale_price": "whole", "cost_price": "cost"}


def _clean_cat(name):
    n = " ".join(str(name or "").split())
    if len(n) > 40:
        raise ValueError("Category name is too long (max 40 characters)")
    if any(ch in n for ch in ",;|"):
        raise ValueError("Category names cannot contain  ,  ;  or  |")
    return n


def _ensure_category(c, name):
    """Create the category if it does not exist (case-insensitive); returns the stored spelling ('' for none)."""
    n = _clean_cat(name)
    if not n:
        return ""
    row = c.execute("SELECT name FROM categories WHERE name=? COLLATE NOCASE", (n,)).fetchone()
    if row:
        return row["name"]
    so = c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories").fetchone()[0]
    c.execute("INSERT INTO categories(name, sort_order) VALUES (?,?)", (n, so))
    return n


def _audit_c(c, user, action, detail=""):
    c.execute("INSERT INTO audit_log(ts,user,action,detail) VALUES (?,?,?,?)", (_now(), user or "-", action, detail))


def list_categories():
    with dbm.db() as c:
        return c.execute("SELECT * FROM categories ORDER BY sort_order, name COLLATE NOCASE").fetchall()


def category_counts():
    """{category name: number of products, '': uncategorised} - categories in their display order."""
    with dbm.db() as c:
        names = [r["name"] for r in c.execute("SELECT name FROM categories ORDER BY sort_order, name COLLATE NOCASE")]
        out = {n: 0 for n in names}
        lower = {n.lower(): n for n in names}
        out[""] = 0
        for r in c.execute("SELECT COALESCE(category,'') cat, COUNT(*) n FROM products GROUP BY COALESCE(category,'') COLLATE NOCASE"):
            key = lower.get(r["cat"].lower(), r["cat"]) if r["cat"] else ""
            out[key] = out.get(key, 0) + r["n"]
    return out


def add_category(name, user):
    n = _clean_cat(name)
    if not n:
        raise ValueError("Enter a category name")
    with dbm.db() as c:
        if c.execute("SELECT 1 FROM categories WHERE name=? COLLATE NOCASE", (n,)).fetchone():
            raise ValueError(f"The category '{n}' already exists")
        _ensure_category(c, n)
        _audit_c(c, user, "CATEGORY_ADD", n)
    return n


def rename_category(old, new, user):
    """Renames the category AND every product in it, in one transaction. Returns the number of products moved."""
    new = _clean_cat(new)
    if not new:
        raise ValueError("Enter the new name")
    with dbm.db() as c:
        row = c.execute("SELECT id, name FROM categories WHERE name=? COLLATE NOCASE", (old,)).fetchone()
        if not row:
            raise ValueError("Category not found")
        if c.execute("SELECT 1 FROM categories WHERE name=? COLLATE NOCASE AND id != ?", (new, row["id"])).fetchone():
            raise ValueError(f"The category '{new}' already exists")
        c.execute("UPDATE categories SET name=? WHERE id=?", (new, row["id"]))
        n = c.execute("UPDATE products SET category=? WHERE category=? COLLATE NOCASE", (new, row["name"])).rowcount
        _audit_c(c, user, "CATEGORY_RENAME", f"{row['name']} -> {new} ({n} products)")
    return n


def delete_category(name, user):
    """Products in it become uncategorised (they are NOT deleted). Returns how many products were affected."""
    with dbm.db() as c:
        row = c.execute("SELECT id, name FROM categories WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if not row:
            raise ValueError("Category not found")
        n = c.execute("UPDATE products SET category='' WHERE category=? COLLATE NOCASE", (row["name"],)).rowcount
        c.execute("DELETE FROM categories WHERE id=?", (row["id"],))
        _audit_c(c, user, "CATEGORY_DELETE", f"{row['name']} ({n} products now uncategorised)")
    return n


def move_category(name, direction, user):
    with dbm.db() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM categories ORDER BY sort_order, name COLLATE NOCASE")]
        row = c.execute("SELECT id FROM categories WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if not row:
            raise ValueError("Category not found")
        i = ids.index(row["id"])
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        for pos, cid in enumerate(ids, 1):
            c.execute("UPDATE categories SET sort_order=? WHERE id=?", (pos, cid))


def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_products(text="", category=None, limit=12, offset=0, only_in_stock=False):
    """-> (rows, total). category: None = all, '' = uncategorised, 'Name' = that category. limit=None returns everything."""
    where, args = [], []
    if text and text.strip():
        lk = _like(text.strip())
        where.append("(barcode LIKE ? ESCAPE '\\' OR name_en LIKE ? ESCAPE '\\' OR name_local LIKE ? ESCAPE '\\' OR keywords LIKE ? ESCAPE '\\')")
        args += [lk] * 4
    if category is not None:
        where.append("COALESCE(category,'') = ? COLLATE NOCASE")
        args.append(category)
    if only_in_stock:
        where.append("stock_qty > 0")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    with dbm.db() as c:
        total = c.execute("SELECT COUNT(*) FROM products" + w, args).fetchone()[0]
        q, a2 = "SELECT * FROM products" + w + " ORDER BY name_en COLLATE NOCASE, barcode", list(args)
        if limit is not None:
            q, a2 = q + " LIMIT ? OFFSET ?", a2 + [int(limit), int(offset)]
        return c.execute(q, a2).fetchall(), total


# ------------------------------------------------------------------ price history
def _chg(a, b):
    return abs((a or 0) - (b or 0)) > 0.004


def _log_price(c, barcode, old, cost, sell, whole, user, reason):
    """Writes a price_history row when something really changed (and the feature is on). `old` = product row or None."""
    if old is None or not dbm.settings.bool("feat_price_history"):
        return False
    if not (_chg(old["cost_price"], cost) or _chg(old["selling_price"], sell) or _chg(old["wholesale_price"], whole)):
        return False
    c.execute("INSERT INTO price_history(barcode,ts,user,cost_old,cost_new,sell_old,sell_new,whole_old,whole_new,reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (barcode, _now(), user or "-", old["cost_price"], cost, old["selling_price"], sell, old["wholesale_price"], whole, reason))
    return True


def price_history(barcode, limit=200):
    with dbm.db() as c:
        return c.execute("SELECT * FROM price_history WHERE barcode=? ORDER BY id DESC LIMIT ?", (barcode, limit)).fetchall()


_UPSERT = """INSERT INTO products(barcode, name_en, name_local, keywords, cost_price, selling_price, wholesale_price, stock_qty,
 expiry_date, image_path, warranty, category, taxable) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
 ON CONFLICT(barcode) DO UPDATE SET name_en=excluded.name_en, name_local=excluded.name_local, keywords=excluded.keywords,
 cost_price=excluded.cost_price, selling_price=excluded.selling_price, wholesale_price=excluded.wholesale_price,
 stock_qty=excluded.stock_qty, expiry_date=excluded.expiry_date, warranty=excluded.warranty, category=excluded.category,
 taxable=excluded.taxable"""


def save_product(barcode, name_en, user, *, name_local="", keywords="", cost=None, sell=0.0, wholesale=0.0, stock=0.0, add=0.0,
                 expiry="", warranty="", category=None, reason="Inventory edit", taxable=None):
    """Create or update one product in ONE transaction (+ price history + audit).
    cost=None keeps the old cost (users without 'see cost' cannot change it); category=None keeps the old category, '' clears it."""
    barcode, name_en = str(barcode).strip(), str(name_en).strip()
    if not barcode or not name_en:
        raise ValueError("Barcode and English name are required.")
    expiry = (expiry or "").strip()
    if expiry:
        datetime.strptime(expiry, "%Y-%m-%d")
    total = num(stock, "Stock", allow_blank=True) + num(add, "Stock to add", allow_blank=True)
    if total < 0:
        raise ValueError("Stock cannot be negative.")
    sell, wholesale = num(sell, "Selling price", minimum=0, allow_blank=True), num(wholesale, "Wholesale price", minimum=0, allow_blank=True)
    cost = None if cost is None else num(cost, "Cost price", minimum=0, allow_blank=True)
    with dbm.db() as c:
        old = c.execute("SELECT * FROM products WHERE barcode=?", (barcode,)).fetchone()
        cost_v = cost if cost is not None else (old["cost_price"] if old else 0.0)
        cat = _ensure_category(c, category) if category is not None else ((old["category"] or "") if old else "")
        cur_stock = (old["stock_qty"] or 0.0) if old else 0.0
        c.execute(_UPSERT, (barcode, name_en, name_local, keywords, cost_v, sell, wholesale, cur_stock, expiry,
                            old["image_path"] if old else "", warranty, cat,
                            int(bool(taxable)) if taxable is not None else (1 if old is None or old["taxable"] is None else old["taxable"])))
        _set_stock(c, barcode, cur_stock, total, "OPENING" if old is None else "EDIT", "Inventory", user)
        changed = _log_price(c, barcode, old, cost_v, sell, wholesale, user, reason)
        _audit_c(c, user, "PRODUCT_SAVE", f"{barcode} stock {float(stock or 0):g}+{float(add or 0):g}")
    return dict(created=old is None, stock=total, price_changed=changed)


def delete_product(barcode, user):
    with dbm.db() as c:
        row = c.execute("SELECT image_path, stock_qty FROM products WHERE barcode=?", (barcode,)).fetchone()
        if not row:
            raise ValueError("Product not found")
        if abs(row["stock_qty"] or 0.0) > _EPS:                          # close the ledger: sum(moves) must be 0 for a product that no longer exists,
            apply_stock_move(c, barcode, -(row["stock_qty"] or 0.0), "ADJUST", "PRODUCT_DELETE", user, note="Product deleted", allow_negative=True)
        c.execute("DELETE FROM products WHERE barcode=?", (barcode,))
        c.execute("DELETE FROM batches WHERE barcode=?", (barcode,))     # ... otherwise a NEW product with the same barcode inherits old batches / units
        c.execute("DELETE FROM sale_item_batches WHERE barcode=? AND batch_id NOT IN (SELECT id FROM batches)", (barcode,))
        c.execute("DELETE FROM product_units WHERE barcode=?", (barcode,))
        c.execute("DELETE FROM price_history WHERE barcode=?", (barcode,))
        _audit_c(c, user, "PRODUCT_DELETE", barcode)
    _remove_image_file(row["image_path"])


def import_products(rows, add_mode, user):
    """rows: CSV rows (header optional). Columns: barcode,name_en,name_local,keywords,cost,sell,wholesale,stock,expiry,warranty[,category].
    Old 10-column files still work. Empty category keeps the product's current category. Returns (imported, skipped)."""
    rows = [r for r in rows if r]
    if rows and rows[0][0].strip().lower() == "barcode":
        rows = rows[1:]
    ok = bad = 0
    with dbm.db() as c:
        for r in rows:
            try:
                r = (list(r) + [""] * 11)[:11]
                b, name = r[0].strip(), r[1].strip()
                if not b or not name:
                    raise ValueError
                if re.fullmatch(r"\d+(\.\d+)?[eE][+-]?\d+", b):         # Excel turned 8901234567890 into 8.90123E+12 - that barcode is lost, never import it
                    raise ValueError("barcode in scientific notation")
                cost, sell, whole, stock = (num(r[4], "cost", allow_blank=True), num(r[5], "sell", allow_blank=True),
                                            num(r[6], "wholesale", allow_blank=True), num(r[7], "stock", allow_blank=True))
                if min(cost, sell, whole, stock) < 0:
                    raise ValueError
                exp = r[8].strip()
                if exp:
                    datetime.strptime(exp, "%Y-%m-%d")
                old = c.execute("SELECT * FROM products WHERE barcode=?", (b,)).fetchone()
                if old and add_mode:
                    stock += old["stock_qty"]
                cat = _ensure_category(c, r[10]) if r[10].strip() else ((old["category"] or "") if old else "")
                cur_stock = (old["stock_qty"] or 0.0) if old else 0.0
                c.execute(_UPSERT, (b, name, r[2].strip(), r[3].strip(), cost, sell, whole, cur_stock, exp, old["image_path"] if old else "", r[9].strip(), cat,
                                    1 if old is None or old["taxable"] is None else old["taxable"]))
                _set_stock(c, b, cur_stock, stock, "IMPORT", "CSV import", user)
                _log_price(c, b, old, cost, sell, whole, user, "CSV import")
                ok += 1
            except ValueError:
                bad += 1
        _audit_c(c, user, "CSV_IMPORT", f"ok={ok} bad={bad}")
    return ok, bad


# ------------------------------------------------------------------ bulk price update
def _round_to(x, step):
    return math.floor(x / step + 0.5) * step


def bulk_price_preview(field, mode, value, scope=("all",), rounding=0, allow_cost=False):
    """-> list of dict(barcode, name, old, new, warn). Nothing is changed.
    field: selling_price | wholesale_price | cost_price;  mode: percent | amount | set;  scope: ('all',) | ('category', name) | ('barcodes', [..])
    rounding: 0 or a step (1, 5, 10, 50, 100) used for percent / amount modes."""
    if field not in BULK_FIELDS:
        raise ValueError("Unknown price type")
    if field == "cost_price" and not allow_cost:
        raise PermissionError("You do not have permission to change cost prices.")
    if mode not in ("percent", "amount", "set"):
        raise ValueError("Unknown change type")
    value = num(value, "Value")
    if mode == "percent" and not -90 <= value <= 500:
        raise ValueError("Percentage must be between -90 and 500")
    if mode == "amount" and abs(value) > 1_000_000:
        raise ValueError("Amount is too large")
    if mode == "set" and value < 0.01:
        raise ValueError("The new price must be greater than zero")
    where, args = "", []
    if scope[0] == "category":
        where, args = " WHERE COALESCE(category,'') = ? COLLATE NOCASE", [scope[1]]
    elif scope[0] == "barcodes":
        if not scope[1]:
            return []
        where, args = f" WHERE barcode IN ({','.join('?' * len(scope[1]))})", list(scope[1])
    with dbm.db() as c:
        rows = c.execute("SELECT * FROM products" + where + " ORDER BY name_en COLLATE NOCASE", args).fetchall()
    out = []
    for r in rows:
        old = r[field] or 0.0
        if field == "wholesale_price" and old <= 0 and mode != "set":
            continue                                    # wholesale price not set for this item
        new = old * (1 + value / 100) if mode == "percent" else (old + value if mode == "amount" else value)
        if rounding and mode != "set":
            new = _round_to(new, rounding)
        new = round(new, 2)
        if abs(new - old) < 0.005:
            continue
        warn = ""
        if new < 0.01:
            warn = "ZERO / NEGATIVE"
        elif field == "selling_price" and (r["cost_price"] or 0) > new:
            warn = "below cost"
        elif field == "cost_price" and (r["selling_price"] or 0) and r["selling_price"] < new:
            warn = "cost above retail"
        out.append(dict(barcode=r["barcode"], name=r["name_en"], old=round(old, 2), new=new, warn=warn))
    return out


def bulk_price_apply(changes, field, user, reason="Bulk price update", allow_cost=False):
    """Applies a preview in ONE transaction. Refuses (and changes nothing) if any price moved since the preview."""
    if field not in BULK_FIELDS:
        raise ValueError("Unknown price type")
    if field == "cost_price" and not allow_cost:
        raise PermissionError("You do not have permission to change cost prices.")
    if not changes:
        raise ValueError("There is nothing to change")
    if any(ch["new"] < 0.01 for ch in changes):
        raise ValueError("Some new prices are zero or negative. Change the settings and preview again.")
    col = field                                          # taken from the fixed BULK_FIELDS keys above, never from user text
    with dbm.db() as c:
        for ch in changes:
            cur = c.execute("SELECT * FROM products WHERE barcode=?", (ch["barcode"],)).fetchone()
            if cur is None or _chg(cur[col], ch["old"]):
                raise ValueError(f"The price of '{ch['name']}' changed after the preview. Please preview again - nothing was changed.")
            new = {"cost_price": cur["cost_price"], "selling_price": cur["selling_price"], "wholesale_price": cur["wholesale_price"]}
            new[col] = ch["new"]
            c.execute(f"UPDATE products SET {col}=? WHERE barcode=?", (ch["new"], ch["barcode"]))
            _log_price(c, ch["barcode"], cur, new["cost_price"], new["selling_price"], new["wholesale_price"], user, reason)
        _audit_c(c, user, "BULK_PRICE", f"{field} {len(changes)} items: {reason}")
    return len(changes)


# ------------------------------------------------------------------ product pictures
def image_dir():
    return dbm.p("ProductImages")


def product_image_path(p):
    """Absolute path of the product's picture, or '' when it has none / the file is missing."""
    ip = ((p["image_path"] if p is not None else "") or "").strip()
    if not ip:
        return ""
    path = ip if os.path.isabs(ip) else os.path.join(image_dir(), ip)
    return path if os.path.isfile(path) else ""


def _remove_image_file(image_path):
    ip = (image_path or "").strip()
    if ip and not os.path.isabs(ip):
        try:
            os.remove(os.path.join(image_dir(), ip))
        except OSError:
            pass


def set_product_image(barcode, src, user):
    """Copies a picture into ProductImages (resized to max 640 px, JPEG) and links it to the product."""
    from PIL import Image, ImageOps
    old = get_product(barcode)
    if old is None:
        raise ValueError("Save the product first, then add its picture.")
    try:
        if os.path.getsize(src) > IMAGE_MAX_BYTES:
            raise ValueError("The picture is larger than 25 MB.")
        im = ImageOps.exif_transpose(Image.open(src))
        if im.mode != "RGB":
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, "white")
            bg.alpha_composite(im)
            im = bg.convert("RGB")
        im.thumbnail((640, 640))
        name = re.sub(r"[^A-Za-z0-9_-]", "_", barcode)[:40] + "_" + hashlib.sha1(barcode.encode("utf-8")).hexdigest()[:6] + ".jpg"
        os.makedirs(image_dir(), exist_ok=True)
        im.save(os.path.join(image_dir(), name), "JPEG", quality=85, optimize=True)
    except ValueError:
        raise
    except Exception:                                    # unreadable / not a picture / decompression bomb ...
        raise ValueError("This file is not a picture VeloPOS can read (use JPG, PNG or WEBP).")
    with dbm.db() as c:
        c.execute("UPDATE products SET image_path=? WHERE barcode=?", (name, barcode))
        _audit_c(c, user, "PRODUCT_IMAGE", barcode)
    if (old["image_path"] or "") != name:
        _remove_image_file(old["image_path"])
    return name


def clear_product_image(barcode, user):
    old = get_product(barcode)
    if old is None:
        raise ValueError("Product not found")
    with dbm.db() as c:
        c.execute("UPDATE products SET image_path='' WHERE barcode=?", (barcode,))
        _audit_c(c, user, "PRODUCT_IMAGE_REMOVED", barcode)
    _remove_image_file(old["image_path"])


# ================================================================== PHASE 6.2: stock control
# RULE: products.stock_qty is changed ONLY by apply_stock_move() (directly or through consume_stock / restore_stock / _set_stock).
STOCK_REASONS = ("SALE", "VOID", "RETURN", "ADJUST", "DAMAGE", "EXPIRED", "LOST", "FOUND", "COUNT", "EDIT", "IMPORT", "RESET", "PURCHASE", "OPENING")
ADJUST_REASONS = ("ADJUST", "DAMAGE", "EXPIRED", "LOST", "FOUND")
WRITE_OFF = ("DAMAGE", "EXPIRED", "LOST")
_EPS = 1e-6


def _batches_on():
    return dbm.settings.bool("feat_batches")


def _units_on():
    return dbm.settings.bool("feat_multi_unit")


def apply_stock_move(c, barcode, qty_change, reason, ref="", user="", batch_id=None, note="", allow_negative=False):
    """THE one place that changes stock. Runs inside the caller's transaction `c`: updates products.stock_qty (and the batch when
    batch_id is given) and appends a stock_moves row. Returns the new stock quantity. A zero change is ignored."""
    if reason not in STOCK_REASONS:
        raise ValueError(f"Unknown stock reason '{reason}'")
    qty_change = round(float(qty_change), 6)
    row = c.execute("SELECT stock_qty, name_en FROM products WHERE barcode=?", (barcode,)).fetchone()
    if row is None:
        raise ValueError(f"Product {barcode} no longer exists")
    old = row["stock_qty"] or 0.0
    if abs(qty_change) < _EPS:
        return old
    new = round(old + qty_change, 6)
    if new < -_EPS and not allow_negative:
        raise ValueError(f"Stock of {row['name_en']} cannot go below zero (available {old:g})")
    if abs(new) < _EPS:
        new = 0.0
    if batch_id is not None:
        b = c.execute("SELECT barcode, qty_remaining FROM batches WHERE id=?", (batch_id,)).fetchone()
        if b is None or b["barcode"] != barcode:
            raise ValueError("Batch not found for this item")
        nb = round((b["qty_remaining"] or 0.0) + qty_change, 6)
        if nb < -_EPS:
            raise ValueError(f"That batch has only {b['qty_remaining']:g} left")
        c.execute("UPDATE batches SET qty_remaining=? WHERE id=?", (max(0.0, nb), batch_id))
    c.execute("UPDATE products SET stock_qty=? WHERE barcode=?", (new, barcode))
    c.execute("INSERT INTO stock_moves(ts, barcode, qty_change, qty_after, reason, ref, user, batch_id, note) VALUES (?,?,?,?,?,?,?,?,?)",
              (_now(), barcode, qty_change, new, reason, ref, user or "-", batch_id, note))
    return new


def _loose_stock(c, barcode):
    """Stock that belongs to no batch = product stock - sum(batches). Never negative."""
    r = c.execute("SELECT stock_qty, (SELECT COALESCE(SUM(qty_remaining),0) FROM batches b WHERE b.barcode=p.barcode) bsum "
                  "FROM products p WHERE barcode=?", (barcode,)).fetchone()
    return max(0.0, round((r["stock_qty"] or 0.0) - r["bsum"], 6)) if r else 0.0


def consume_stock(c, barcode, qty, reason, ref="", user="", note="", sale_item_id=None, skip_expired=False, allow_negative=False):
    """Remove `qty` (BASE units). Batch tracking OFF: one plain move. ON: FEFO - earliest expiry first (batches without an expiry last),
    then loose (unbatched) stock. Returns [(batch_id or None, qty)] and, for a sale line, remembers it in sale_item_batches."""
    qty = round(float(qty), 6)
    if qty <= _EPS:
        return []
    allocs = []
    if _batches_on():
        today = datetime.now().strftime("%Y-%m-%d")
        left = qty
        for b in c.execute("SELECT id, qty_remaining, expiry_date FROM batches WHERE barcode=? AND qty_remaining > 0 "
                           "ORDER BY (expiry_date = '' OR expiry_date IS NULL), expiry_date, id", (barcode,)).fetchall():
            if skip_expired and b["expiry_date"] and b["expiry_date"] < today:
                continue
            take = min(left, b["qty_remaining"])
            if take <= _EPS:
                continue
            apply_stock_move(c, barcode, -take, reason, ref, user, batch_id=b["id"], note=note)
            allocs.append((b["id"], take))
            left = round(left - take, 6)
            if left <= _EPS:
                break
        if left > _EPS:
            if not allow_negative and _loose_stock(c, barcode) + _EPS < left:
                name = c.execute("SELECT name_en FROM products WHERE barcode=?", (barcode,)).fetchone()
                raise ValueError(("Not enough NON-EXPIRED stock for " if skip_expired else "Not enough stock for ") + (name["name_en"] if name else barcode))
            apply_stock_move(c, barcode, -left, reason, ref, user, None, note, allow_negative=allow_negative)
            allocs.append((None, left))
    else:
        apply_stock_move(c, barcode, -qty, reason, ref, user, None, note, allow_negative=allow_negative)
        allocs.append((None, qty))
    if sale_item_id:
        for bid, q in allocs:
            if bid is not None:
                c.execute("INSERT INTO sale_item_batches(sale_item_id, barcode, batch_id, qty_base) VALUES (?,?,?,?)", (sale_item_id, barcode, bid, q))
    return allocs


def restore_stock(c, sale_item_id, barcode, qty_base, reason, ref="", user="", note=""):
    """Put sold stock back (void / return): into the SAME batches the sale took it from, anything else as loose stock.
    A product that has been deleted since is skipped (same as before Phase 6.2)."""
    if c.execute("SELECT 1 FROM products WHERE barcode=?", (barcode,)).fetchone() is None:
        return
    left = round(float(qty_base), 6)
    for m in c.execute("SELECT * FROM sale_item_batches WHERE sale_item_id=? ORDER BY id", (sale_item_id,)).fetchall():
        give = min(left, round(m["qty_base"] - m["returned_base"], 6))
        if give <= _EPS:
            continue
        apply_stock_move(c, barcode, give, reason, ref, user, batch_id=m["batch_id"], note=note)
        c.execute("UPDATE sale_item_batches SET returned_base = returned_base + ? WHERE id=?", (give, m["id"]))
        left = round(left - give, 6)
        if left <= _EPS:
            break
    if left > _EPS:
        apply_stock_move(c, barcode, left, reason, ref, user, None, note)


def _set_stock(c, barcode, current, target, reason, ref, user):
    delta = round(float(target) - float(current), 6)
    if delta > _EPS:
        apply_stock_move(c, barcode, delta, reason, ref, user)
    elif delta < -_EPS:
        consume_stock(c, barcode, -delta, reason, ref, user)


# ------------------------------------------------------------------ ledger checks
def verify_stock_ledger():
    """Products whose stock_qty differs from the sum of their stock_moves. [] = the ledger reconciles."""
    with dbm.db() as c:
        rows = c.execute("SELECT p.barcode, p.name_en, p.stock_qty stock, "
                         "COALESCE((SELECT SUM(m.qty_change) FROM stock_moves m WHERE m.barcode=p.barcode), 0) ledger FROM products p").fetchall()
    out = []
    for r in rows:
        diff = round((r["stock"] or 0.0) - r["ledger"], 6)
        if abs(diff) > 0.0005:
            out.append(dict(barcode=r["barcode"], name=r["name_en"], stock=r["stock"], ledger=r["ledger"], diff=diff))
    return out


def repair_stock_ledger(user):
    """Adds a reconciling 'EDIT' move for every mismatch (stock itself is NOT changed). Returns how many products were fixed."""
    bad = verify_stock_ledger()
    with dbm.db() as c:
        for b in bad:
            c.execute("INSERT INTO stock_moves(ts, barcode, qty_change, qty_after, reason, ref, user, note) VALUES (?,?,?,?,?,?,?,?)",
                      (_now(), b["barcode"], b["diff"], b["stock"], "EDIT", "LEDGER_REPAIR", user or "-", "Ledger reconciliation"))
        if bad:
            _audit_c(c, user, "LEDGER_REPAIR", f"{len(bad)} products")
    return len(bad)


def verify_batches():
    """Batch invariant: no negative batch, and sum(batches) <= product stock (the rest is loose stock). [] = fine."""
    out = []
    with dbm.db() as c:
        for r in c.execute("SELECT b.id, b.barcode, b.qty_remaining FROM batches b WHERE b.qty_remaining < -0.0005").fetchall():
            out.append(dict(barcode=r["barcode"], problem=f"batch {r['id']} is negative ({r['qty_remaining']:g})"))
        for r in c.execute("SELECT p.barcode, p.stock_qty, SUM(b.qty_remaining) s FROM products p JOIN batches b ON b.barcode=p.barcode "
                           "GROUP BY p.barcode HAVING SUM(b.qty_remaining) > p.stock_qty + 0.0005").fetchall():
            out.append(dict(barcode=r["barcode"], problem=f"batches hold {r['s']:g} but stock is {r['stock_qty']:g}"))
    return out


# ------------------------------------------------------------------ batches
def _add_batch(c, barcode, batch_no, expiry, qty, cost, user, reason="ADJUST", ref="", source="MANUAL"):
    """Inside the caller's transaction (also used by the Phase 6.3 purchase / GRN code)."""
    qty = round(float(qty), 6)
    if qty <= 0:
        raise ValueError("Quantity must be greater than zero")
    expiry = (expiry or "").strip()
    if expiry:
        datetime.strptime(expiry, "%Y-%m-%d")
    batch_no = " ".join(str(batch_no or "").split())[:30] or datetime.now().strftime("B%Y%m%d")
    if cost is not None and float(cost) < 0:
        raise ValueError("Cost cannot be negative")
    cur = c.execute("INSERT INTO batches(barcode, batch_no, expiry_date, qty_remaining, cost_price, received_ts, source, ref) VALUES (?,?,?,?,?,?,?,?)",
                    (barcode, batch_no, expiry, 0.0, float(cost or 0), _now(), source, ref))
    apply_stock_move(c, barcode, qty, reason, ref, user, batch_id=cur.lastrowid, note=f"Batch {batch_no}")
    _audit_c(c, user, "BATCH_ADD", f"{barcode} batch {batch_no} qty {qty:g} exp {expiry or '-'}")
    return cur.lastrowid


def receive_batch(barcode, batch_no, expiry, qty, cost, user, reason="ADJUST", ref="", source="MANUAL"):
    with dbm.db() as c:
        return _add_batch(c, barcode, batch_no, expiry, qty, cost, user, reason, ref, source)


def list_batches(barcode=None, include_empty=False):
    q = ("SELECT b.*, p.name_en FROM batches b LEFT JOIN products p ON p.barcode=b.barcode WHERE 1=1"
         + ("" if include_empty else " AND b.qty_remaining > 0") + (" AND b.barcode=?" if barcode else "")
         + " ORDER BY (b.expiry_date = ''), b.expiry_date, b.id")
    with dbm.db() as c:
        return c.execute(q, (barcode,) if barcode else ()).fetchall()


def enable_batches(user):
    """Run when batch tracking is switched ON (safe to repeat). Products with stock but no batch get ONE batch built from the
    product's expiry date; batches that hold more than the product stock (stock changed while tracking was OFF) are trimmed."""
    created = trimmed = 0
    with dbm.db() as c:
        for p in c.execute("SELECT barcode, stock_qty, expiry_date, cost_price FROM products").fetchall():
            bsum = c.execute("SELECT COALESCE(SUM(qty_remaining),0) FROM batches WHERE barcode=?", (p["barcode"],)).fetchone()[0]
            stock = p["stock_qty"] or 0.0
            if bsum > stock + _EPS:
                over = round(bsum - stock, 6)
                for b in c.execute("SELECT id, qty_remaining FROM batches WHERE barcode=? AND qty_remaining>0 ORDER BY id DESC", (p["barcode"],)).fetchall():
                    cut = min(over, b["qty_remaining"])
                    c.execute("UPDATE batches SET qty_remaining=? WHERE id=?", (round(b["qty_remaining"] - cut, 6), b["id"]))
                    over = round(over - cut, 6)
                    if over <= _EPS:
                        break
                trimmed += 1
            elif stock > _EPS and bsum <= _EPS:
                c.execute("INSERT INTO batches(barcode, batch_no, expiry_date, qty_remaining, cost_price, received_ts, source, ref) VALUES (?,?,?,?,?,?,?,?)",
                          (p["barcode"], "OPENING", (p["expiry_date"] or "").strip(), stock, p["cost_price"] or 0, _now(), "MIGRATION", ""))
                created += 1
        _audit_c(c, user, "BATCHES_ENABLED", f"created={created} trimmed={trimmed}")
    return dict(created=created, trimmed=trimmed)


def expiry_alert_rows():
    """[(days, row)] for items expired or expiring within 30 days. Batch tracking ON: per batch that still has stock; OFF: products.expiry_date."""
    out = []
    with dbm.db() as c:
        if _batches_on():
            rows = c.execute("SELECT b.barcode, CASE WHEN b.batch_no != '' THEN p.name_en || ' [' || b.batch_no || ']' ELSE p.name_en END AS name_en, "
                             "b.expiry_date FROM batches b JOIN products p ON p.barcode=b.barcode "
                             "WHERE b.qty_remaining > 0 AND TRIM(b.expiry_date) != ''").fetchall()
        else:
            rows = c.execute("SELECT barcode, name_en, expiry_date FROM products WHERE TRIM(expiry_date) != ''").fetchall()
    for r in rows:
        st, days = expiry_state(r["expiry_date"])
        if st in ("EXPIRED", "SOON"):
            out.append((days, r))
    out.sort(key=lambda x: (x[0], x[1]["name_en"]))
    return out


def product_expiry_map():
    """{barcode: earliest expiry date} used by the Inventory status column. Batch tracking ON: earliest batch that still has stock."""
    if not _batches_on():
        return {}
    with dbm.db() as c:
        return {r["barcode"]: r["e"] for r in c.execute("SELECT barcode, MIN(expiry_date) e FROM batches WHERE qty_remaining > 0 AND TRIM(expiry_date) != '' GROUP BY barcode")}


# ------------------------------------------------------------------ multi-unit
def _cart_unit(c, it):
    """(factor, unit name) for one cart line. Feature OFF / no unit / base unit -> (1.0, ''). Factors are always read from the database."""
    if not _units_on():
        return 1.0, ""
    q = round(float(it["qty"]) * 1000, 6)
    if abs(q - round(q)) > 1e-6:
        raise ValueError("Quantity can have at most 3 decimal places")
    unit = (it.get("unit") or "").strip()
    if not unit:
        return 1.0, ""
    p = c.execute("SELECT base_unit, name_en FROM products WHERE barcode=?", (it["barcode"],)).fetchone()
    if p is None:
        raise ValueError(f"Product {it['barcode']} no longer exists")
    if unit.lower() == (p["base_unit"] or "pcs").lower():
        return 1.0, ""
    u = c.execute("SELECT unit_name, factor_to_base FROM product_units WHERE barcode=? AND unit_name=?", (it["barcode"], unit)).fetchone()
    if u is None:
        raise ValueError(f"Unknown unit '{unit}' for {p['name_en']}")
    return float(u["factor_to_base"]), u["unit_name"]


def list_units(barcode):
    """[{name, factor, price (override, 0 = automatic), base}] with the base unit first."""
    p = get_product(barcode)
    if p is None:
        return []
    out = [dict(name=p["base_unit"] or "pcs", factor=1.0, price=0.0, base=True)]
    with dbm.db() as c:
        for r in c.execute("SELECT * FROM product_units WHERE barcode=? ORDER BY factor_to_base, unit_name", (barcode,)):
            out.append(dict(name=r["unit_name"], factor=r["factor_to_base"], price=r["price_override"] or 0.0, base=False))
    return out


def unit_price(base_price, factor, override=0.0):
    """Price of ONE selling unit: the override if set, else base price x factor."""
    return round(override, 2) if override and override > 0 else round(base_price * factor, 2)


def _clean_unit(name):
    n = " ".join(str(name or "").split())
    if not 1 <= len(n) <= 12:
        raise ValueError("Unit name must be 1 to 12 characters")
    if any(ch in n for ch in "[],;|"):
        raise ValueError("Unit names cannot contain  [ ] , ; |")
    return n


def save_unit(barcode, unit_name, factor, price_override, user):
    """Add or change an extra selling unit. factor = how many BASE units one of this unit is (g of kg: 0.001, dozen of pcs: 12)."""
    n = _clean_unit(unit_name)
    factor, price_override = round(num(factor, "Factor"), 6), num(price_override, "Price", allow_blank=True)
    if not 0 < factor <= 1_000_000:
        raise ValueError("Factor must be greater than zero")
    if price_override < 0:
        raise ValueError("Price cannot be negative")
    with dbm.db() as c:
        p = c.execute("SELECT base_unit FROM products WHERE barcode=?", (barcode,)).fetchone()
        if p is None:
            raise ValueError("Product not found")
        if n.lower() == (p["base_unit"] or "pcs").lower():
            raise ValueError("That is the base unit already")
        c.execute("INSERT INTO product_units(barcode, unit_name, factor_to_base, price_override) VALUES (?,?,?,?) "
                  "ON CONFLICT(barcode, unit_name) DO UPDATE SET factor_to_base=excluded.factor_to_base, price_override=excluded.price_override",
                  (barcode, n, factor, price_override))
        _audit_c(c, user, "UNIT_SAVE", f"{barcode} {n} x{factor:g}")


def delete_unit(barcode, unit_name, user):
    with dbm.db() as c:
        if c.execute("DELETE FROM product_units WHERE barcode=? AND unit_name=?", (barcode, unit_name)).rowcount == 0:
            raise ValueError("Unit not found")
        _audit_c(c, user, "UNIT_DELETE", f"{barcode} {unit_name}")


def set_base_unit(barcode, name, user):
    """Only renames the label of the unit the stock is counted in (stock numbers are unchanged)."""
    n = _clean_unit(name)
    with dbm.db() as c:
        if c.execute("SELECT 1 FROM product_units WHERE barcode=? AND unit_name=?", (barcode, n)).fetchone():
            raise ValueError("That name is already used by an extra unit")
        if c.execute("UPDATE products SET base_unit=? WHERE barcode=?", (n, barcode)).rowcount == 0:
            raise ValueError("Product not found")
        _audit_c(c, user, "BASE_UNIT", f"{barcode} -> {n}")


# ------------------------------------------------------------------ adjustments + log
def adjust_stock(barcode, qty, reason, user, note="", batch_id=None):
    """qty is SIGNED (+ adds, - removes). reason: ADJUST | DAMAGE | EXPIRED | LOST | FOUND. Stock can never go below zero.
    Removing with batch_id takes it from that batch; otherwise FEFO (when batch tracking is on). Returns the new stock."""
    qty = round(num(qty, "Quantity"), 6)
    if reason not in ADJUST_REASONS:
        raise ValueError("Unknown adjustment type")
    if abs(qty) < _EPS:
        raise ValueError("Enter a quantity")
    if reason in WRITE_OFF and qty > 0:
        raise ValueError(f"{reason.title()} must REMOVE stock")
    if reason == "FOUND" and qty < 0:
        raise ValueError("Found stock must ADD stock")
    with dbm.db() as c:
        if qty < 0 and batch_id is None:
            consume_stock(c, barcode, -qty, reason, "", user, note)
            new = c.execute("SELECT stock_qty FROM products WHERE barcode=?", (barcode,)).fetchone()["stock_qty"]
        else:
            new = apply_stock_move(c, barcode, qty, reason, "", user, batch_id=batch_id, note=note)
        _audit_c(c, user, "STOCK_ADJUST", f"{barcode} {qty:+g} {reason} {note}")
    return new


def _log_where(date_from, date_to, text, reason, user, barcode):
    w, args = [], []
    if date_from:
        w.append("substr(m.ts,1,10) >= ?"); args.append(date_from)
    if date_to:
        w.append("substr(m.ts,1,10) <= ?"); args.append(date_to)
    if text and text.strip():
        lk = _like(text.strip())
        w.append("(m.barcode LIKE ? ESCAPE '\\' OR p.name_en LIKE ? ESCAPE '\\' OR m.note LIKE ? ESCAPE '\\' OR m.ref LIKE ? ESCAPE '\\')")
        args += [lk] * 4
    if reason:
        w.append("m.reason = ?"); args.append(reason)
    if user:
        w.append("m.user = ?"); args.append(user)
    if barcode:
        w.append("m.barcode = ?"); args.append(barcode)
    return (" WHERE " + " AND ".join(w)) if w else "", args


def stock_log(date_from=None, date_to=None, text="", reason=None, user=None, barcode=None, limit=500):
    where, args = _log_where(date_from, date_to, text, reason, user, barcode)
    with dbm.db() as c:
        return c.execute("SELECT m.*, p.name_en, p.cost_price FROM stock_moves m LEFT JOIN products p ON p.barcode=m.barcode" + where +
                         " ORDER BY m.id DESC LIMIT ?", args + [int(limit)]).fetchall()


def write_off_value(rows):
    """Cost value of stock written off (DAMAGE / EXPIRED / LOST) in the given log rows. Uses the CURRENT cost price."""
    return round(sum(-r["qty_change"] * (r["cost_price"] or 0.0) for r in rows if r["reason"] in WRITE_OFF), 2)


def export_stock_log(path, include_cost=False, **filters):
    import csv
    rows = stock_log(limit=1_000_000, **filters)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["time", "barcode", "item", "change", "stock_after", "reason", "ref", "user", "batch_id", "note"] + (["value_at_cost"] if include_cost else []))
        for r in rows:
            w.writerow([csv_safe(x) for x in [r["ts"], r["barcode"], r["name_en"] or "", f"{r['qty_change']:g}", f"{r['qty_after']:g}", r["reason"], r["ref"], r["user"],
                        r["batch_id"] or "", r["note"]] + ([f"{r['qty_change'] * (r['cost_price'] or 0):.2f}"] if include_cost else [])])
    return len(rows)


# ------------------------------------------------------------------ stock-take (audit count)
# Sales during an open count: the variance is ALWAYS  counted - stock at the moment of finalizing.  Anything sold / returned / adjusted
# after the session started is listed by count_warnings() so the user can recount those items; count when the shop is closed if possible.
def _count_open(c, count_id):
    r = c.execute("SELECT * FROM stock_counts WHERE id=?", (count_id,)).fetchone()
    if r is None:
        raise ValueError("Stock-take not found")
    if r["status"] != "OPEN":
        raise ValueError(f"This stock-take is {r['status'].lower()} and can no longer be changed")
    return r


def _count_scope(c, cnt):
    if cnt["scope"] == "category":
        return c.execute("SELECT * FROM products WHERE COALESCE(category,'') = ? COLLATE NOCASE ORDER BY name_en COLLATE NOCASE", (cnt["category"],)).fetchall()
    return c.execute("SELECT * FROM products ORDER BY name_en COLLATE NOCASE").fetchall()


def start_count(scope, category, user, note=""):
    if scope not in ("all", "category"):
        raise ValueError("Unknown scope")
    category = (category or "").strip()
    if scope == "category" and not category:
        raise ValueError("Choose a category")
    with dbm.db() as c:
        op = c.execute("SELECT id FROM stock_counts WHERE status='OPEN'").fetchone()
        if op:
            raise ValueError(f"Stock-take #{op['id']} is still open. Finalize or cancel it first.")
        cur = c.execute("INSERT INTO stock_counts(started_ts, user, scope, category, status, note) VALUES (?,?,?,?, 'OPEN', ?)",
                        (_now(), user, scope, category if scope == "category" else "", note))
        n = len(_count_scope(c, c.execute("SELECT * FROM stock_counts WHERE id=?", (cur.lastrowid,)).fetchone()))
        if n == 0:
            raise ValueError("There are no products in that scope")
        _audit_c(c, user, "COUNT_START", f"#{cur.lastrowid} scope={scope} {category} ({n} products)")
        return cur.lastrowid


def _record(c, cnt, barcode, qty, user):
    p = c.execute("SELECT stock_qty FROM products WHERE barcode=?", (barcode,)).fetchone()
    if p is None:
        raise ValueError(f"Product {barcode} not found")
    if cnt["scope"] == "category":
        if not c.execute("SELECT 1 FROM products WHERE barcode=? AND COALESCE(category,'') = ? COLLATE NOCASE", (barcode, cnt["category"])).fetchone():
            raise ValueError(f"{barcode} is not in the category '{cnt['category']}'")
    qty = round(num(qty, "Counted quantity"), 3)
    if qty < 0:
        raise ValueError("Counted quantity cannot be negative")
    c.execute("INSERT INTO stock_count_lines(count_id, barcode, counted_qty, system_qty, ts) VALUES (?,?,?,?,?) "
              "ON CONFLICT(count_id, barcode) DO UPDATE SET counted_qty=excluded.counted_qty, system_qty=excluded.system_qty, ts=excluded.ts",
              (cnt["id"], barcode, qty, p["stock_qty"] or 0.0, _now()))


def record_count(count_id, barcode, qty, user):
    with dbm.db() as c:
        _record(c, _count_open(c, count_id), str(barcode).strip(), qty, user)


def import_counts(count_id, rows, user):
    """rows: [barcode, counted_qty] (header optional). Returns (imported, skipped)."""
    rows = [r for r in rows if r]
    if rows and str(rows[0][0]).strip().lower() == "barcode":
        rows = rows[1:]
    ok = bad = 0
    with dbm.db() as c:
        cnt = _count_open(c, count_id)
        for r in rows:
            try:
                _record(c, cnt, str(r[0]).strip(), float(r[1]), user)
                ok += 1
            except (ValueError, IndexError):
                bad += 1
        _audit_c(c, user, "COUNT_IMPORT", f"#{count_id} ok={ok} bad={bad}")
    return ok, bad


def list_counts(limit=50):
    with dbm.db() as c:
        return c.execute("SELECT s.*, (SELECT COUNT(*) FROM stock_count_lines l WHERE l.count_id=s.id) n FROM stock_counts s ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def count_report(count_id):
    """dict(count, lines, totals). OPEN: variance = counted - CURRENT stock. FINAL: the variance that was applied. Value uses cost price."""
    with dbm.db() as c:
        cnt = c.execute("SELECT * FROM stock_counts WHERE id=?", (count_id,)).fetchone()
        if cnt is None:
            raise ValueError("Stock-take not found")
        lines = {r["barcode"]: r for r in c.execute("SELECT * FROM stock_count_lines WHERE count_id=?", (count_id,))}
        prods = _count_scope(c, cnt)
    out, tot = [], dict(counted=0, uncounted=0, with_variance=0, net_qty=0.0, net_value=0.0, shortage_value=0.0, surplus_value=0.0)
    for p in prods:
        ln = lines.get(p["barcode"])
        if ln is None:
            tot["uncounted"] += 1
            out.append(dict(barcode=p["barcode"], name=p["name_en"], system=p["stock_qty"], counted=None, variance=None, value=None))
            continue
        system = ln["system_qty"] if cnt["status"] == "FINAL" else (p["stock_qty"] or 0.0)
        var = ln["applied_qty"] if cnt["status"] == "FINAL" and ln["applied_qty"] is not None else round(ln["counted_qty"] - system, 6)
        val = round(var * (p["cost_price"] or 0.0), 2)
        tot["counted"] += 1
        if abs(var) > _EPS:
            tot["with_variance"] += 1
            tot["net_qty"] = round(tot["net_qty"] + var, 6)
            tot["net_value"] = round(tot["net_value"] + val, 2)
            tot["shortage_value" if var < 0 else "surplus_value"] += val
        out.append(dict(barcode=p["barcode"], name=p["name_en"], system=system, counted=ln["counted_qty"], variance=var, value=val))
    tot["shortage_value"], tot["surplus_value"] = round(tot["shortage_value"], 2), round(tot["surplus_value"], 2)
    return dict(count=dict(cnt), lines=out, totals=tot)


def count_warnings(count_id):
    """Items in the count's scope that had stock movements (sale, return, void, adjustment...) since the session started."""
    with dbm.db() as c:
        cnt = c.execute("SELECT * FROM stock_counts WHERE id=?", (count_id,)).fetchone()
        if cnt is None:
            raise ValueError("Stock-take not found")
        scope = {p["barcode"] for p in _count_scope(c, cnt)}
        rows = c.execute("SELECT m.barcode, p.name_en, SUM(m.qty_change) net, COUNT(*) n FROM stock_moves m JOIN products p ON p.barcode=m.barcode "
                         "WHERE m.ts >= ? AND m.reason NOT IN ('COUNT','OPENING') GROUP BY m.barcode", (cnt["started_ts"],)).fetchall()
    return [dict(barcode=r["barcode"], name=r["name_en"], net=r["net"], moves=r["n"]) for r in rows if r["barcode"] in scope]


def finalize_count(count_id, user, uncounted="ignore"):
    """ONE transaction: applies every variance as a COUNT move (decreases use FEFO when batch tracking is on) and closes the session.
    uncounted='ignore' leaves items that were not counted alone; 'zero' treats them as counted 0."""
    if uncounted not in ("ignore", "zero"):
        raise ValueError("Unknown option")
    adjusted, net_qty, net_value = 0, 0.0, 0.0
    with dbm.db() as c:
        cnt = _count_open(c, count_id)
        lines = {r["barcode"]: r for r in c.execute("SELECT * FROM stock_count_lines WHERE count_id=?", (count_id,))}
        if uncounted == "zero":
            for p in _count_scope(c, cnt):
                if p["barcode"] not in lines:
                    c.execute("INSERT INTO stock_count_lines(count_id, barcode, counted_qty, system_qty, ts) VALUES (?,?,?,?,?)", (count_id, p["barcode"], 0.0, p["stock_qty"], _now()))
            lines = {r["barcode"]: r for r in c.execute("SELECT * FROM stock_count_lines WHERE count_id=?", (count_id,))}
        if not lines:
            raise ValueError("Nothing has been counted yet")
        ref = f"COUNT#{count_id}"
        for b, ln in lines.items():
            p = c.execute("SELECT stock_qty, cost_price FROM products WHERE barcode=?", (b,)).fetchone()
            if p is None:
                continue
            cur_stock = p["stock_qty"] or 0.0
            var = round(ln["counted_qty"] - cur_stock, 6)
            if var > _EPS:
                apply_stock_move(c, b, var, "COUNT", ref, user, note="Stock-take surplus")
            elif var < -_EPS:
                consume_stock(c, b, -var, "COUNT", ref, user, note="Stock-take shortage")
            c.execute("UPDATE stock_count_lines SET system_qty=?, applied_qty=? WHERE id=?", (cur_stock, var, ln["id"]))
            if abs(var) > _EPS:
                adjusted += 1
                net_qty = round(net_qty + var, 6)
                net_value = round(net_value + var * (p["cost_price"] or 0.0), 2)
        c.execute("UPDATE stock_counts SET status='FINAL', finalized_ts=? WHERE id=?", (_now(), count_id))
        _audit_c(c, user, "COUNT_FINAL", f"#{count_id} adjusted={adjusted} net_qty={net_qty:g}")
    return dict(count_id=count_id, adjusted=adjusted, net_qty=net_qty, net_value=net_value)


def cancel_count(count_id, user):
    with dbm.db() as c:
        _count_open(c, count_id)
        c.execute("UPDATE stock_counts SET status='CANCELLED', finalized_ts=? WHERE id=?", (_now(), count_id))
        _audit_c(c, user, "COUNT_CANCEL", f"#{count_id}")


# ================================================================== PHASE 6.3: buying & money rules
from datetime import date as _date, timedelta as _td


# ------------------------------------------------------------------ credit limit
def set_credit_limit(customer_id, limit, user):
    """0 = no limit. Only enforced when 'feat_credit_limit' is ON."""
    limit = round(num(limit, "Credit limit"), 2)
    if limit < 0:
        raise ValueError("The credit limit cannot be negative")
    with dbm.db() as c:
        if c.execute("UPDATE customers SET credit_limit=? WHERE id=?", (limit, customer_id)).rowcount == 0:
            raise ValueError("Customer not found")
        _audit_c(c, user, "CREDIT_LIMIT_SET", f"customer {customer_id} = {limit:,.2f}")


def approve_with_admin_password(password):
    """For a credit-limit override by a cashier: returns the Admin's username when the password belongs to an Admin, else None.
    Wrong tries are counted persistently: 5 wrong -> locked for 15 minutes."""
    wait = lock_remaining("override")
    if wait:
        raise ValueError(f"Too many wrong attempts. Try again in {wait // 60 + 1} minute(s).")
    for u in admin_usernames():
        if verify_admin_password(u, password):
            clear_fails("override")
            return u
    register_fail("override")
    return None


# ------------------------------------------------------------------ overdue credit + WhatsApp reminders
class ReminderCooldown(ValueError):
    pass


def overdue_customers(days=None, today=None, only_overdue=True):
    """Customers with a credit balance. Payments are applied to the OLDEST credit sales first (FIFO); what is left of sales older than
    `days` is 'overdue'. -> [dict(id, name, phone, balance, credit_limit, overdue, oldest_days, last_reminder)] biggest overdue first."""
    days = max(0, dbm.settings.int("overdue_days", 30)) if days is None else int(days)
    today = today or _date.today()
    out = []
    with dbm.db() as c:
        for cu in c.execute("SELECT id, name, phone, credit_balance, credit_limit FROM customers WHERE credit_balance > 0.004").fetchall():
            sales = [(r["date"], r["amount"]) for r in c.execute(
                "SELECT date, amount FROM credit_logs WHERE customer_id=? AND type='CREDIT_SALE' ORDER BY date, time, id", (cu["id"],))]
            left = max(0.0, sum(a for _, a in sales) - cu["credit_balance"])                 # money already paid back
            over, oldest = 0.0, 0
            for d, a in sales:
                use = min(a, left)
                left -= use
                rem = round(a - use, 2)
                if rem <= 0.004:
                    continue
                try:
                    age = (today - _date.fromisoformat(d)).days
                except ValueError:
                    age = 0
                oldest = max(oldest, age)
                if age >= days:
                    over += rem
            last = c.execute("SELECT MAX(ts) FROM reminder_log WHERE customer_id=?", (cu["id"],)).fetchone()[0]
            out.append(dict(id=cu["id"], name=cu["name"], phone=cu["phone"], balance=cu["credit_balance"], credit_limit=cu["credit_limit"] or 0.0,
                            overdue=round(over, 2), oldest_days=oldest, last_reminder=last))
    if only_overdue:
        out = [r for r in out if r["overdue"] > 0.004]
    out.sort(key=lambda r: (-r["overdue"], r["name"]))
    return out


def reminder_message(row, template=None, shop=None):
    msg = template or dbm.settings.get("reminder_template")
    for k, v in (("name", row["name"]), ("amount", f"{row['overdue']:,.2f}"), ("days", str(row["oldest_days"])), ("shop", shop or dbm.settings.get("shop_name"))):
        msg = msg.replace("{" + k + "}", v)                  # plain replace: stray braces in the template can never crash
    return msg


def reminder_allowed(customer_id, now=None):
    """-> (allowed, last reminder timestamp or None). Not allowed again until 'reminder_cooldown_days' have passed."""
    now = now or datetime.now()
    with dbm.db() as c:
        last = c.execute("SELECT MAX(ts) FROM reminder_log WHERE customer_id=?", (customer_id,)).fetchone()[0]
    if not last:
        return True, None
    try:
        t = datetime.fromisoformat(last)
    except ValueError:
        return True, last
    return now - t >= _td(days=max(0, dbm.settings.int("reminder_cooldown_days", 7))), last


def create_reminder(customer_id, user, force=False, template=None, now=None):
    """Builds the wa.me link for an overdue customer and records the reminder. The caller opens the link (the owner presses Send)."""
    from . import otp as _otp
    row = next((r for r in overdue_customers(only_overdue=False) if r["id"] == customer_id), None)
    if row is None or row["overdue"] <= 0.004:
        raise ValueError("This customer has nothing overdue")
    if not _otp.normalize_phone(row["phone"]):
        raise ValueError("This customer has no phone number")
    ok, last = reminder_allowed(customer_id, now)
    if not ok and not force:
        raise ReminderCooldown(f"A reminder was already prepared on {last[:10]}. Wait {dbm.settings.int('reminder_cooldown_days', 7)} days between reminders, or send it anyway.")
    msg = reminder_message(row, template)
    url = _otp.whatsapp_link(row["phone"], msg)
    with dbm.db() as c:
        c.execute("INSERT INTO reminder_log(customer_id, ts, channel, amount, message, user) VALUES (?,?,?,?,?,?)",
                  (customer_id, _now(), "WhatsApp", row["overdue"], msg, user))
        _audit_c(c, user, "REMINDER", f"{row['name']} overdue {row['overdue']:,.2f}")
    return dict(url=url, message=msg, amount=row["overdue"])


# ------------------------------------------------------------------ suppliers
def _supplier_fields(name, contact, phone, whatsapp, address, notes):
    name = " ".join(str(name or "").split())
    if not 1 <= len(name) <= 60:
        raise ValueError("Supplier name must be 1 to 60 characters")
    return name, (contact or "").strip(), (phone or "").strip(), (whatsapp or "").strip(), (address or "").strip(), (notes or "").strip()


def add_supplier(name, user, contact="", phone="", whatsapp="", address="", notes=""):
    f = _supplier_fields(name, contact, phone, whatsapp, address, notes)
    with dbm.db() as c:
        if c.execute("SELECT 1 FROM suppliers WHERE name=? COLLATE NOCASE", (f[0],)).fetchone():
            raise ValueError(f"The supplier '{f[0]}' already exists")
        cur = c.execute("INSERT INTO suppliers(name, contact, phone, whatsapp, address, notes) VALUES (?,?,?,?,?,?)", f)
        _audit_c(c, user, "SUPPLIER_ADD", f[0])
        return cur.lastrowid


def update_supplier(sid, user, name, contact="", phone="", whatsapp="", address="", notes="", active=True):
    f = _supplier_fields(name, contact, phone, whatsapp, address, notes)
    with dbm.db() as c:
        if c.execute("SELECT 1 FROM suppliers WHERE name=? COLLATE NOCASE AND id != ?", (f[0], sid)).fetchone():
            raise ValueError(f"The supplier '{f[0]}' already exists")
        if c.execute("UPDATE suppliers SET name=?, contact=?, phone=?, whatsapp=?, address=?, notes=?, active=? WHERE id=?", f + (int(bool(active)), sid)).rowcount == 0:
            raise ValueError("Supplier not found")
        _audit_c(c, user, "SUPPLIER_EDIT", f"{f[0]} active={int(bool(active))}")


def get_supplier(sid):
    with dbm.db() as c:
        return c.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()


def list_suppliers(active_only=False):
    with dbm.db() as c:
        return c.execute("SELECT * FROM suppliers" + (" WHERE active=1" if active_only else "") + " ORDER BY name COLLATE NOCASE").fetchall()


# ------------------------------------------------------------------ purchases (GRN)
def _new_cost(policy, old_stock, old_cost, base_qty, base_cost):
    if policy == "Weighted average" and old_stock > 0 and old_cost is not None:
        return round((old_stock * old_cost + base_qty * base_cost) / (old_stock + base_qty), 4)
    return round(base_cost, 4)


def create_purchase(supplier_id, items, user, supplier_invoice="", date=None, discount=0.0, paid_now=0.0, method="Cash", pay_ref="", note="", shift_id=None):
    """Goods Received Note, ONE transaction. items: [dict(barcode, qty, cost, unit='', batch_no='', expiry='')]  (cost = per entered unit).
    Stock: apply_stock_move(reason PURCHASE) - or a new batch when batch tracking is ON. Product cost: policy 'Last cost' or 'Weighted average'
    (setting purchase_cost_policy; switch off with grn_update_cost=0) and every cost change is written to the price history.
    paid_now is recorded as a supplier payment (Cash + open shift -> drawer OUT)."""
    if not items:
        raise ValueError("Add at least one item")
    date = (date or _date.today().isoformat()).strip()
    datetime.strptime(date, "%Y-%m-%d")
    discount, paid_now = round(num(discount, "Discount", allow_blank=True), 2), round(num(paid_now, "Payment", allow_blank=True), 2)
    if discount < 0 or paid_now < 0:
        raise ValueError("Discount and payment cannot be negative")
    if method not in ("Cash", "Bank", "Cheque"):
        raise ValueError("Unknown payment method")
    policy = dbm.settings.get("purchase_cost_policy") or "Last cost"
    update_cost = dbm.settings.bool("grn_update_cost")
    with dbm.db() as c:
        c.execute("BEGIN IMMEDIATE")
        sup = c.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if sup is None or not sup["active"]:
            raise ValueError("Choose an active supplier")
        lines, sub = [], 0.0
        for it in items:
            p = c.execute("SELECT * FROM products WHERE barcode=?", (it["barcode"],)).fetchone()
            if p is None:
                raise ValueError(f"Product {it['barcode']} not found")
            qty, cost = round(num(it["qty"], "Quantity"), 3), num(it["cost"], "Cost")
            if qty <= 0:
                raise ValueError(f"Quantity of {p['name_en']} must be greater than zero")
            if cost < 0:
                raise ValueError(f"Cost of {p['name_en']} cannot be negative")
            fac, uname = _cart_unit(c, dict(barcode=it["barcode"], qty=qty, unit=it.get("unit", "")))
            exp = (it.get("expiry") or "").strip()
            if exp:
                datetime.strptime(exp, "%Y-%m-%d")
            total = round(qty * cost, 2)
            sub += total
            lines.append(dict(p=p, qty=qty, cost=cost, fac=fac, unit=uname, base_qty=round(qty * fac, 6), total=total,
                              batch_no=" ".join(str(it.get("batch_no") or "").split())[:30], expiry=exp))
        sub = round(sub, 2)
        if discount > sub + 1e-9:
            raise ValueError("The discount is more than the purchase total")
        total = round(sub - discount, 2)
        if paid_now > total + 1e-9:
            raise ValueError("The payment is more than the purchase total")
        grn = _next_no(c, "purchases", "grn_no", "GRN" + datetime.now().strftime("%Y%m%d"))
        _require_open_shift(c, shift_id if (paid_now > 0 and method == "Cash") else None)
        pid = c.execute("INSERT INTO purchases(grn_no, supplier_id, supplier_invoice, date, ts, user, subtotal, discount, total, paid, status, note) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?, 'OK', ?)", (grn, supplier_id, (supplier_invoice or "").strip(), date, _now(), user, sub, discount, total, paid_now, note)).lastrowid
        for ln in lines:
            p = c.execute("SELECT * FROM products WHERE barcode=?", (ln["p"]["barcode"],)).fetchone()          # fresh (an earlier line may have changed it)
            base_cost = ln["cost"] / ln["fac"]
            if update_cost:
                new_cost = _new_cost(policy, p["stock_qty"] or 0.0, p["cost_price"], ln["base_qty"], base_cost)
                c.execute("UPDATE products SET cost_price=? WHERE barcode=?", (new_cost, p["barcode"]))
                _log_price(c, p["barcode"], p, new_cost, p["selling_price"], p["wholesale_price"], user, f"GRN {grn}")
            bid = None
            if _batches_on():
                bid = _add_batch(c, p["barcode"], ln["batch_no"], ln["expiry"], ln["base_qty"], base_cost, user, reason="PURCHASE", ref=grn, source="PURCHASE")
            else:
                apply_stock_move(c, p["barcode"], ln["base_qty"], "PURCHASE", grn, user, note=f"GRN {grn}")
                if ln["expiry"]:
                    c.execute("UPDATE products SET expiry_date=? WHERE barcode=?", (ln["expiry"], p["barcode"]))
            c.execute("INSERT INTO purchase_items(purchase_id, barcode, name, qty, unit, factor, base_qty, cost_price, line_total, batch_id, batch_no, expiry) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (pid, p["barcode"], p["name_en"], ln["qty"], ln["unit"], ln["fac"], ln["base_qty"], ln["cost"], ln["total"], bid, ln["batch_no"], ln["expiry"]))
        if paid_now > 0:
            _pay(c, supplier_id, sup["name"], paid_now, method, user, pay_ref, f"With {grn}", shift_id, pid)
        _audit_c(c, user, "PURCHASE", f"{grn} {sup['name']} total={total:,.2f} paid={paid_now:,.2f}")
    return dict(grn_no=grn, purchase_id=pid, total=total, paid=paid_now, due=round(total - paid_now, 2), supplier=sup["name"])


def get_purchase(pid):
    with dbm.db() as c:
        h = c.execute("SELECT p.*, s.name supplier FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?", (pid,)).fetchone()
        if h is None:
            return None
        items = c.execute("SELECT * FROM purchase_items WHERE purchase_id=? ORDER BY id", (pid,)).fetchall()
        pays = c.execute("SELECT * FROM supplier_payments WHERE purchase_id=? ORDER BY id", (pid,)).fetchall()
    return dict(header=dict(h), items=[dict(i) for i in items], payments=[dict(x) for x in pays])


def list_purchases(supplier_id=None, status=None, limit=300):
    q = ("SELECT p.*, s.name supplier, COALESCE((SELECT SUM(amount) FROM supplier_payments sp WHERE sp.purchase_id=p.id),0) paid_total "
         "FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1")
    args = []
    if supplier_id:
        q += " AND p.supplier_id=?"; args.append(supplier_id)
    if status:
        q += " AND p.status=?"; args.append(status)
    with dbm.db() as c:
        return c.execute(q + " ORDER BY p.id DESC LIMIT ?", args + [int(limit)]).fetchall()


def void_purchase(purchase_id, user, reason):
    """Admin action (the screen checks). Refused when any of the received stock has already been sold / used.
    Payments made stay with the supplier as an advance (balance goes negative); product costs are NOT reverted."""
    if not (reason or "").strip():
        raise ValueError("Please enter a reason")
    with dbm.db() as c:
        c.execute("BEGIN IMMEDIATE")
        h = c.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
        if h is None or h["status"] != "OK":
            raise ValueError("Purchase not found or already voided")
        items = c.execute("SELECT * FROM purchase_items WHERE purchase_id=?", (purchase_id,)).fetchall()
        for it in items:
            p = c.execute("SELECT stock_qty, name_en FROM products WHERE barcode=?", (it["barcode"],)).fetchone()
            if p is None or (p["stock_qty"] or 0) + 1e-6 < it["base_qty"]:
                raise ValueError(f"Cannot void: part of '{it['name']}' has already been sold or used (stock {p['stock_qty'] if p else 0:g}, received {it['base_qty']:g})")
            if it["batch_id"]:
                b = c.execute("SELECT qty_remaining FROM batches WHERE id=?", (it["batch_id"],)).fetchone()
                if b is None or (b["qty_remaining"] or 0) + 1e-6 < it["base_qty"]:
                    raise ValueError(f"Cannot void: batch {it['batch_no'] or it['batch_id']} of '{it['name']}' has already been used")
        for it in items:
            apply_stock_move(c, it["barcode"], -it["base_qty"], "PURCHASE", h["grn_no"], user, batch_id=it["batch_id"], note=f"GRN {h['grn_no']} voided")
        c.execute("UPDATE purchases SET status='VOID', void_reason=?, void_ts=?, void_user=? WHERE id=?", (reason.strip(), _now(), user, purchase_id))
        _audit_c(c, user, "PURCHASE_VOID", f"{h['grn_no']} {reason.strip()}")


# ------------------------------------------------------------------ supplier payments + payables
def _supplier_balance(c, supplier_id):
    bought = c.execute("SELECT COALESCE(SUM(total),0) FROM purchases WHERE supplier_id=? AND status='OK'", (supplier_id,)).fetchone()[0]
    paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM supplier_payments WHERE supplier_id=?", (supplier_id,)).fetchone()[0]
    return round(bought - paid, 2)


def _pay(c, supplier_id, name, amount, method, user, ref, note, shift_id, purchase_id):
    c.execute("INSERT INTO supplier_payments(supplier_id, purchase_id, ts, date, amount, method, ref, note, user, shift_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (supplier_id, purchase_id, _now(), _date.today().isoformat(), amount, method, ref, note, user, shift_id))
    if method == "Cash" and shift_id:                       # cash leaves the drawer -> expected drawer cash stays correct
        c.execute("INSERT INTO cash_moves(shift_id, ts, kind, amount, reason, user) VALUES (?,?,?,?,?,?)", (shift_id, _now(), "OUT", amount, f"Supplier payment: {name}", user))


def pay_supplier(supplier_id, amount, method, user, ref="", note="", shift_id=None, purchase_id=None, allow_advance=False):
    """Records a payment. Cash with a shift id also takes the money out of the drawer (DOCUMENTED decision: pass shift_id=None for cash that did
    not come from the drawer). Paying more than the balance is refused unless allow_advance."""
    amount = round(num(amount, "Amount"), 2)
    if amount <= 0:
        raise ValueError("Enter an amount greater than zero")
    if method not in ("Cash", "Bank", "Cheque"):
        raise ValueError("Unknown payment method")
    with dbm.db() as c:
        c.execute("BEGIN IMMEDIATE")
        _require_open_shift(c, shift_id if method == "Cash" else None)
        sup = c.execute("SELECT name FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        if sup is None:
            raise ValueError("Supplier not found")
        if purchase_id and not c.execute("SELECT 1 FROM purchases WHERE id=? AND supplier_id=? AND status='OK'", (purchase_id, supplier_id)).fetchone():
            raise ValueError("That purchase does not belong to this supplier")
        bal = _supplier_balance(c, supplier_id)
        if amount > bal + 0.004 and not allow_advance:
            raise ValueError(f"The payment ({amount:,.2f}) is more than the balance owed ({max(bal, 0):,.2f})")
        _pay(c, supplier_id, sup["name"], amount, method, user, ref, note, shift_id, purchase_id)
        _audit_c(c, user, "SUPPLIER_PAYMENT", f"{sup['name']} {amount:,.2f} {method}")
    return round(bal - amount, 2)


def list_supplier_payments(supplier_id, limit=200):
    with dbm.db() as c:
        return c.execute("SELECT * FROM supplier_payments WHERE supplier_id=? ORDER BY id DESC LIMIT ?", (supplier_id, limit)).fetchall()


def supplier_balances():
    """[dict(id, name, phone, bought, paid, balance)] for every supplier that has any purchase or payment, biggest balance first."""
    out = []
    with dbm.db() as c:
        for s in c.execute("SELECT id, name, phone, whatsapp FROM suppliers").fetchall():
            bought = c.execute("SELECT COALESCE(SUM(total),0) FROM purchases WHERE supplier_id=? AND status='OK'", (s["id"],)).fetchone()[0]
            paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM supplier_payments WHERE supplier_id=?", (s["id"],)).fetchone()[0]
            if bought or paid:
                out.append(dict(id=s["id"], name=s["name"], phone=s["phone"], bought=round(bought, 2), paid=round(paid, 2), balance=round(bought - paid, 2)))
    out.sort(key=lambda r: (-r["balance"], r["name"]))
    return out


def payables_total():
    """Total owed to suppliers (advances paid to one supplier do not reduce what is owed to another)."""
    return round(sum(r["balance"] for r in supplier_balances() if r["balance"] > 0.004), 2)


def payables_ageing(today=None):
    """Per supplier: what is still unpaid, grouped by the age of the purchase (payments settle the OLDEST purchases first).
    -> (rows, totals)  rows: dict(id, name, b0 (0-30 days), b1 (31-60), b2 (61-90), b3 (90+), balance)"""
    today = today or _date.today()
    rows, tot = [], dict(b0=0.0, b1=0.0, b2=0.0, b3=0.0, balance=0.0)
    with dbm.db() as c:
        for s in c.execute("SELECT id, name FROM suppliers").fetchall():
            paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM supplier_payments WHERE supplier_id=?", (s["id"],)).fetchone()[0]
            b = [0.0, 0.0, 0.0, 0.0]
            for p in c.execute("SELECT date, total FROM purchases WHERE supplier_id=? AND status='OK' ORDER BY date, id", (s["id"],)):
                use = min(p["total"], paid)
                paid -= use
                rem = round(p["total"] - use, 2)
                if rem <= 0.004:
                    continue
                try:
                    age = (today - _date.fromisoformat(p["date"])).days
                except ValueError:
                    age = 0
                b[0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3] += rem
            bal = round(sum(b), 2)
            if bal > 0.004:
                rows.append(dict(id=s["id"], name=s["name"], b0=round(b[0], 2), b1=round(b[1], 2), b2=round(b[2], 2), b3=round(b[3], 2), balance=bal))
    rows.sort(key=lambda r: (-r["balance"], r["name"]))
    for r in rows:
        for k in tot:
            tot[k] = round(tot[k] + r[k], 2)
    return rows, tot


# ================================================================== PHASE 6.5: quality pass (expenses, customers, staff accounts)
# These used to be written straight from the screens (several separate transactions, no checks). They live here now, headless and tested.
def add_expense(category, description, amount, user, shift_id=None):
    """Expense + (optional) drawer cash-out + audit in ONE transaction. shift_id = the OPEN shift whose drawer paid for it (None = not from the drawer)."""
    amount = round(num(amount, "Amount"), 2)
    if amount <= 0:
        raise ValueError("Enter an amount greater than zero")
    category = (category or "").strip() or "General"
    desc = (description or "").strip() or category
    with dbm.db() as c:
        _require_open_shift(c, shift_id)
        cur = c.execute("INSERT INTO expenses(date, category, description, amount, added_by, shift_id) VALUES (?,?,?,?,?,?)",
                        (datetime.now().strftime("%Y-%m-%d"), category, desc, amount, user, shift_id))
        if shift_id:
            c.execute("INSERT INTO cash_moves(shift_id, ts, kind, amount, reason, user) VALUES (?,?,?,?,?,?)",
                      (shift_id, _now(), "OUT", amount, f"Expense: {desc}", user))
        _audit_c(c, user, "EXPENSE", f"{category} {amount:,.2f}" + (f" (drawer, shift {shift_id})" if shift_id else ""))
        return cur.lastrowid


def delete_expense(expense_id, user):
    """Admin action (the screen checks). If the expense was paid from the drawer of a shift that is still OPEN the cash is put back."""
    with dbm.db() as c:
        e = c.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if e is None:
            raise ValueError("Expense not found")
        refunded = False
        if e["shift_id"]:
            sh = c.execute("SELECT status FROM shifts WHERE id=?", (e["shift_id"],)).fetchone()
            if sh and sh["status"] == "OPEN":
                c.execute("INSERT INTO cash_moves(shift_id, ts, kind, amount, reason, user) VALUES (?,?,?,?,?,?)",
                          (e["shift_id"], _now(), "IN", e["amount"], f"Expense deleted: {e['description']}", user))
                refunded = True
        c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        _audit_c(c, user, "EXPENSE_DELETE", f"#{expense_id} {e['category']} {e['amount']:,.2f} '{e['description']}' (added by {e['added_by']}); "
                                            + ("drawer cash put back" if refunded else "drawer not changed"))
    return refunded


def _customer_fields(name, phone):
    from . import otp as _otp
    name = " ".join(str(name or "").split())
    if not 1 <= len(name) <= 60:
        raise ValueError("Customer name must be 1 to 60 characters")
    phone = " ".join(str(phone or "").split())
    digits = _otp.normalize_phone(phone)
    if phone and not 7 <= len(digits) <= 15:                    # the phone number is optional, but when typed it must be valid
        raise ValueError("Enter a valid phone number (7 to 15 digits) or leave it empty")
    return name, phone, digits


def _phone_owner(c, digits, except_id=None):
    """Another customer with the same number? 077 123 4567, 0771234567 and +94771234567 are ONE number."""
    from . import otp as _otp
    for r in c.execute("SELECT id, name, phone FROM customers"):
        if r["id"] != except_id and _otp.normalize_phone(r["phone"] or "") == digits:
            return r
    return None


def add_customer(name, phone, user, address=""):
    name, phone, digits = _customer_fields(name, phone)
    with dbm.db() as c:
        own = _phone_owner(c, digits) if digits else None
        if own:
            raise ValueError(f"That phone number already belongs to {own['name']}")
        cur = c.execute("INSERT INTO customers(name, phone, address) VALUES (?,?,?)", (name, phone or None, (address or "").strip()))
        _audit_c(c, user, "CUSTOMER_ADD", f"{name} {phone}")
        return cur.lastrowid


def update_customer(customer_id, name, phone, user, address=""):
    name, phone, digits = _customer_fields(name, phone)
    with dbm.db() as c:
        own = _phone_owner(c, digits, except_id=customer_id) if digits else None
        if own:
            raise ValueError(f"That phone number already belongs to {own['name']}")
        if c.execute("UPDATE customers SET name=?, phone=?, address=? WHERE id=?", (name, phone or None, (address or "").strip(), customer_id)).rowcount == 0:
            raise ValueError("Customer not found")
        _audit_c(c, user, "CUSTOMER_EDIT", f"#{customer_id} {name} {phone}")


def delete_customer(customer_id, user):
    """Admin action (the screen checks). Refused while the customer owes money (or is owed). Old bills keep the customer's name."""
    with dbm.db() as c:
        cu = c.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if cu is None:
            raise ValueError("Customer not found")
        if abs(cu["credit_balance"] or 0.0) > 0.004:
            raise ValueError(f"{cu['name']} still has a credit balance of {cu['credit_balance']:,.2f}. Settle it first.")
        c.execute("DELETE FROM credit_logs WHERE customer_id=?", (customer_id,))
        c.execute("DELETE FROM reminder_log WHERE customer_id=?", (customer_id,))
        c.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        _audit_c(c, user, "CUSTOMER_DELETE", f"#{customer_id} {cu['name']} (loyalty points lost: {cu['loyalty_points'] or 0:g})")


_USERNAME = re.compile(r"[a-z0-9._@-]{2,30}")


def save_user(username, password, role, actor):
    """Create a staff account or change its role / password. -> dict(created=bool). Rules: at least one Admin must always remain,
    nobody changes their own role, passwords have at least 6 characters, new usernames use letters, digits and . _ @ -"""
    u = (username or "").strip().lower()
    if role not in ("Admin", "Cashier"):
        raise ValueError("Role must be Admin or Cashier")
    if not u:
        raise ValueError("Enter a username")
    with dbm.db() as c:
        old = c.execute("SELECT role FROM users WHERE username=?", (u,)).fetchone()
        if old is None:
            if not _USERNAME.fullmatch(u):
                raise ValueError("Username: 2 to 30 characters - letters, digits and . _ @ - only")
            if len(password or "") < 6:
                raise ValueError("New users need a password of at least 6 characters.")
            c.execute("INSERT INTO users(username, pw_hash, role, created) VALUES (?,?,?,datetime('now'))", (u, security.hash_password(password), role))
            _audit_c(c, actor, "USER_SAVE", f"{u} ({role}) created")
            return dict(created=True)
        if password and len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if old["role"] != role:
            if u == actor:
                raise ValueError("You cannot change the role of the account you are logged in with.")
            if old["role"] == "Admin" and c.execute("SELECT COUNT(*) FROM users WHERE role='Admin'").fetchone()[0] <= 1:
                raise ValueError("At least one Admin account must remain.")
            c.execute("UPDATE users SET role=? WHERE username=?", (role, u))
        if password:
            c.execute("UPDATE users SET pw_hash=? WHERE username=?", (security.hash_password(password), u))
        _audit_c(c, actor, "USER_SAVE", f"{u} ({role})" + (" password changed" if password else ""))
        return dict(created=False)


def delete_user(username, actor):
    u = (username or "").strip().lower()
    with dbm.db() as c:
        row = c.execute("SELECT role FROM users WHERE username=?", (u,)).fetchone()
        if row is None:
            raise ValueError("User not found")
        if u == actor:
            raise ValueError("You cannot delete the account you are logged in with.")
        if row["role"] == "Admin" and c.execute("SELECT COUNT(*) FROM users WHERE role='Admin'").fetchone()[0] <= 1:
            raise ValueError("At least one Admin account must remain.")
        if c.execute("SELECT 1 FROM shifts WHERE cashier=? AND status='OPEN'", (u,)).fetchone():
            raise ValueError(f"'{u}' still has an open shift. Close the shift first.")
        c.execute("DELETE FROM users WHERE username=?", (u,))
        _audit_c(c, actor, "USER_DELETE", u)


# ------------------------------------------------------------------ login throttling that survives a restart
def login_locked_for(username):
    return lock_remaining("login:" + username)


def login_failed(username):
    """Count a wrong password: 5 wrong -> locked for 60 seconds (stored in the database, so closing the program does not reset it)."""
    return register_fail("login:" + username, 5, 60)


def login_ok(username):
    clear_fails("login:" + username)
