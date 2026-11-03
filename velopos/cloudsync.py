"""Owner phone dashboard (Phase 7.1): uploads a small sales SUMMARY to the developer's Cloudflare Worker.  No UI code.

What is sent: today's totals, the last 30 days (sales / profit / bills), top 5 items of the week, low-stock items, the
total credit still owed.  What is NEVER sent: customer names, phone numbers, addresses, bills, passwords, cost prices.

Security model (see cloud/README_CLOUD.txt):
* every shop has its own Ed25519 key pair. The private key never leaves this PC (stored with the machine-bound vault);
  each upload is signed, so nobody can write to a shop's dashboard without it;
* the phone link carries a random view token; the Worker only stores its SHA-256 hash;
* a new shop is accepted only with a one-time INVITE code issued by the developer (this is how the paid add-on is controlled).

The upload is a STATE snapshot (latest wins), so there is no queue: if the internet is down the POS simply tries again later and
billing is never blocked.
"""
import base64, hashlib, json, secrets, ssl, threading, time, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import database as dbm, security

PUSH_EVERY, RETRY_EVERY, FORCE_EVERY = 900, 300, 3600     # seconds: normal / after a failure / re-send even if nothing changed
MAX_BODY = 60_000
_lock = threading.Lock()
_state = {"last_try": 0.0, "last_ok": 0.0, "last_hash": ""}


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ------------------------------------------------------------------ identity
def _priv(cfg):
    raw = security.vault_decrypt(cfg.get("dash_key_enc"))
    if not raw:
        return None
    try:
        return Ed25519PrivateKey.from_private_bytes(_b64d(raw))
    except ValueError:
        return None


def _pub_b64(key):
    return _b64e(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def ensure_identity(cfg=None):
    """Creates the shop id, the signing key and the view token once. Returns the shop id."""
    cfg = cfg or dbm.settings
    upd = {}
    if not cfg.get("dash_shop_id"):
        upd["dash_shop_id"] = secrets.token_hex(8)
    if _priv(cfg) is None:       # first time, or the data was restored on another PC (vault key differs) -> a new invite is needed
        key = Ed25519PrivateKey.generate()
        upd["dash_key_enc"] = security.vault_encrypt(_b64e(key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())))
    if not cfg.get("dash_view_token"):
        upd["dash_view_token"] = secrets.token_urlsafe(16)
    if upd:
        cfg.set_many(upd)
    return cfg.get("dash_shop_id")


def rotate_view_token(cfg=None):
    """Invalidates the old phone link (the Worker learns the new token's hash with the next upload)."""
    cfg = cfg or dbm.settings
    cfg.set_many({"dash_view_token": secrets.token_urlsafe(16)})
    _state["last_hash"] = ""


def normalize_url(url):
    """Only HTTPS addresses are accepted (plain http only for a Worker running on this very PC, for testing)."""
    url = (url or "").strip().rstrip("/")
    if url.startswith("https://") and "." in url[8:]:
        return url
    if url.startswith(("http://127.0.0.1", "http://localhost")):
        return url
    return ""


def view_url(cfg=None):
    cfg = cfg or dbm.settings
    base = normalize_url(cfg.get("dash_url"))
    if not base or not cfg.get("dash_shop_id"):
        return ""
    return f"{base}/d/{cfg.get('dash_shop_id')}?t={urllib.parse.quote(cfg.get('dash_view_token'))}"


def normalize_invite(code):
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def enabled(cfg=None):
    cfg = cfg or dbm.settings
    return cfg.bool("feat_dashboard") and bool(normalize_url(cfg.get("dash_url")))


# ------------------------------------------------------------------ the summary
def build_snapshot(cfg=None, today=None, days=30):
    cfg = cfg or dbm.settings
    ensure_identity(cfg)
    today = today or date.today()
    d1 = today.isoformat()
    d0 = (today - timedelta(days=days - 1)).isoformat()
    w0 = (today - timedelta(days=6)).isoformat()
    with dbm.db() as c:
        sales = {r["date"]: r for r in c.execute(
            "SELECT date, COUNT(*) n, COALESCE(SUM(total_amount),0) t, COALESCE(SUM(profit),0) p FROM sales "
            "WHERE date BETWEEN ? AND ? AND status='OK' GROUP BY date", (d0, d1))}
        rets = {r["date"]: r for r in c.execute(
            "SELECT date, COALESCE(SUM(amount),0) a, COALESCE(SUM(profit_adj),0) p FROM returns WHERE date BETWEEN ? AND ? GROUP BY date", (d0, d1))}
        exps = {r["date"]: r["a"] for r in c.execute(
            "SELECT date, COALESCE(SUM(amount),0) a FROM expenses WHERE date BETWEEN ? AND ? GROUP BY date", (d0, d1))}
        methods = {r["m"] or "?": round(r["t"], 2) for r in c.execute(
            "SELECT payment_method m, SUM(total_amount) t FROM sales WHERE date=? AND status='OK' GROUP BY payment_method", (d1,))}
        top = [dict(n=r["n"], q=round(r["q"], 3), t=round(r["t"], 2)) for r in c.execute(
            "SELECT si.item_name n, SUM(si.qty) q, SUM(si.total) t FROM sale_items si JOIN sales s ON s.invoice_no = si.invoice_no "
            "WHERE s.status='OK' AND s.date BETWEEN ? AND ? GROUP BY si.barcode ORDER BY t DESC LIMIT 5", (w0, d1))]
        low = [dict(n=r["name_en"], q=round(r["stock_qty"], 3)) for r in c.execute(
            "SELECT name_en, stock_qty FROM products WHERE stock_qty <= ? ORDER BY stock_qty, name_en LIMIT 20", (max(0, cfg.int("low_stock_level", 5)),))]
        cr = c.execute("SELECT COALESCE(SUM(credit_balance),0) t, COUNT(*) n FROM customers WHERE credit_balance > 0").fetchone()

    def day(d):
        s, r = sales.get(d), rets.get(d)
        st, sp, sn = (s["t"], s["p"], s["n"]) if s else (0, 0, 0)
        ra, rp = (r["a"], r["p"]) if r else (0, 0)
        return dict(d=d, bills=sn, sales=round(st, 2), returns=round(ra, 2), revenue=round(st - ra, 2),
                    expenses=round(exps.get(d, 0), 2), profit=round(sp + rp - exps.get(d, 0), 2))

    series = [day((today - timedelta(days=days - 1 - i)).isoformat()) for i in range(days)]
    t = series[-1]
    return {"v": 1, "shop": cfg.get("shop_name"), "cur": cfg.get("currency"), "date": d1, "ts": int(time.time()),
            "today": dict(t, methods=methods), "days": series, "top": top, "low": low,
            "credit": dict(total=round(cr["t"], 2), count=cr["n"]),
            "view_hash": hashlib.sha256(cfg.get("dash_view_token").encode()).hexdigest()}


def _signed_headers(cfg, body, invite=""):
    key = _priv(cfg)
    ts = str(int(time.time()))
    h = {"Content-Type": "application/json", "X-Shop": cfg.get("dash_shop_id"), "X-Ts": ts, "X-Pub": _pub_b64(key),
         "X-Sig": _b64e(key.sign(ts.encode() + b"." + body))}
    if invite:
        h["X-Invite"] = invite
    return h


_MSG = {
    401: "The Worker refused the signature / key. If you restored this data on another PC, ask for a new invite code.",
    402: "The dashboard subscription has ended. Ask the developer for a renewal code and enter it above.",
    403: "A valid invite code is needed (first use, renewal, or a new PC). Enter the code you received.",
    404: "Wrong dashboard address (Worker URL).",
    413: "Summary too large (should not happen) - contact the developer.",
}


def _post(url, body, headers, timeout=12):
    from . import __version__
    headers = {"User-Agent": f"VeloPOS/{__version__}", **headers}      # Cloudflare refuses Python's default User-Agent (403)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                   # no internet, DNS, TLS, timeout ...
        return 0, str(e).encode()


def push_snapshot(cfg=None, snap=None, invite=None):
    """-> (ok, message). Never raises."""
    cfg = cfg or dbm.settings
    try:
        base = normalize_url(cfg.get("dash_url"))
        if not base:
            return False, "Enter the dashboard address (Worker URL, https://...) in Settings 4h."
        snap = snap or build_snapshot(cfg)
        body = json.dumps(snap, separators=(",", ":"), ensure_ascii=True).encode()
        if len(body) > MAX_BODY:
            return False, "Summary too large."
        invite = normalize_invite(cfg.get("dash_invite") if invite is None else invite)
        code, resp = _post(base + "/push", body, _signed_headers(cfg, body, invite))
    except Exception as e:
        return False, f"Could not prepare the upload: {e}"
    if code == 200:
        if invite and cfg.get("dash_invite"):
            cfg.set_many({"dash_invite": ""})                # one-time code is used up
        return True, "Uploaded."
    if code == 0:
        return False, "No internet / cannot reach the Worker. Will retry automatically."
    return False, _MSG.get(code, f"Worker answered {code}: {resp[:120].decode('utf-8', 'replace')}")


def run_push(cfg=None, force=False):
    """Builds + uploads if something changed (or `force`, or the last upload is over an hour old). Records the result in settings."""
    cfg = cfg or dbm.settings
    if not _lock.acquire(blocking=False):
        return False, "Another upload is running."
    try:
        _state["last_try"] = time.time()
        snap = build_snapshot(cfg)
        sig = hashlib.sha256(json.dumps({k: v for k, v in snap.items() if k != "ts"}, sort_keys=True).encode()).hexdigest()
        if not force and sig == _state["last_hash"] and time.time() - _state["last_ok"] < FORCE_EVERY:
            return True, "No changes."
        ok, msg = push_snapshot(cfg, snap)
        if ok:
            _state.update(last_ok=time.time(), last_hash=sig)
        cfg.set_many({"dash_last_ok": time.strftime("%Y-%m-%d %H:%M") if ok else cfg.get("dash_last_ok"),
                      "dash_last_msg": msg})
        return ok, msg
    except Exception as e:
        return False, f"Upload failed: {e}"
    finally:
        _lock.release()


def due(cfg=None, now=None):
    cfg = cfg or dbm.settings
    if not enabled(cfg):
        return False
    now = now or time.time()
    wait = PUSH_EVERY if _state["last_ok"] >= _state["last_try"] else RETRY_EVERY
    return now - _state["last_try"] >= wait


def reset_state():
    """For tests."""
    _state.update(last_try=0.0, last_ok=0.0, last_hash="")
