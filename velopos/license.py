"""
License verification (Ed25519 asymmetric signatures) + tamper-resistant 30-day trial.

The app contains ONLY the PUBLIC key (velopos/_pubkey.py). Keys can be *verified* here but can
never be *generated* from this code. The private key lives only on the developer's machine
(tools/keygen.py). Run `python tools/keygen.py init` once to create the key pair.
"""
import base64, hashlib, hmac, json, os, ssl, subprocess, urllib.request, uuid
from datetime import date, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import database as dbm
from . import branding
from .branding import TRIAL_DAYS

try:
    from ._pubkey import PUBLIC_KEY_B64
except ImportError:  # developer forgot to run keygen init
    PUBLIC_KEY_B64 = ""


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ------------------------------------------------------------------ machine id
def machine_id():
    raw = None
    if os.name == "nt":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                               winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            raw = None
    raw = raw or str(uuid.getnode())
    h = hashlib.sha256(("VELOPOS|" + str(raw)).encode()).hexdigest().upper()
    return f"POS-{h[:4]}-{h[4:8]}-{h[8:12]}"


# ------------------------------------------------------------------ online first-run registry (anti trial-reset)
_BAD_HW = ("", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", "00000000-0000-0000-0000-000000000000", "03000200-0400-0500-0006-000700080009")
_remote = {"tried": False, "date": None}


def hw_id():
    """Hash of the PC's SMBIOS UUID (survives a Windows reinstall, unlike the Machine ID). '' when unknown. Only the hash leaves the PC."""
    raw = ""
    if os.name == "nt":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                                 capture_output=True, text=True, timeout=6, creationflags=0x08000000).stdout.strip().upper()
            raw = "" if out in _BAD_HW else out
        except Exception:
            raw = ""
    return hashlib.sha256(("VP-HW|" + raw).encode()).hexdigest()[:32] if raw else ""


def _remote_first_seen(mid):
    """The local DATE this PC first started its trial according to the developer's server, or None (no server set / offline / bad answer).
    Tried once per program start so an offline shop never waits more than a few seconds."""
    if _remote["tried"]:
        return _remote["date"]
    _remote["tried"] = True
    base = (getattr(branding, "TRIAL_SERVER_URL", "") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        body = json.dumps({"m": mid, "h": hw_id()}).encode()
        req = urllib.request.Request(base + "/trial", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=4, context=ssl.create_default_context()) as r:
            ts = int(json.loads(r.read().decode())["first"])
        d = datetime.fromtimestamp(ts).date()
        if date(2024, 1, 1) <= d <= date.today():
            _remote["date"] = d.isoformat()
    except Exception:
        _remote["date"] = None
    return _remote["date"]


# ------------------------------------------------------------------ key verification
def verify_key(key, mid):
    """Returns the license payload dict if `key` is a valid signature for machine `mid`."""
    try:
        if not PUBLIC_KEY_B64:
            return None
        body, sig = "".join(key.split()).split(".")
        payload, signature = _b64d(body), _b64d(sig)
        Ed25519PublicKey.from_public_bytes(_b64d(PUBLIC_KEY_B64)).verify(signature, payload)
        data = json.loads(payload)
        return data if data.get("m") == mid else None
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return None
    except Exception:
        return None


# ------------------------------------------------------------------ trial state (3 sealed stores)
def _mac_key(mid):
    return hashlib.sha256(("VP-TRIAL|" + mid).encode()).digest()


def _seal(d, mid):
    body = json.dumps(d, sort_keys=True)
    return body + "." + hmac.new(_mac_key(mid), body.encode(), "sha256").hexdigest()


def _unseal(s, mid):
    try:
        body, mac = s.rsplit(".", 1)
        good = hmac.new(_mac_key(mid), body.encode(), "sha256").hexdigest()
        return json.loads(body) if hmac.compare_digest(mac, good) else None
    except Exception:
        return None


def _cache_dir():
    d = os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), ".vp_cache")
    os.makedirs(d, exist_ok=True)
    return d


_REG_PATH = r"Software\VeloPOS"


def _read_raw():
    out = []
    try:
        with dbm.db() as c:
            r = c.execute("SELECT blob FROM license_state WHERE id=1").fetchone()
            out.append(r["blob"] if r else None)
    except Exception:
        out.append(None)
    try:
        with open(os.path.join(_cache_dir(), "sys.dat"), "r", encoding="utf-8") as f:
            out.append(f.read())
    except Exception:
        out.append(None)
    if os.name == "nt":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH)
            out.append(winreg.QueryValueEx(k, "State")[0])
        except Exception:
            out.append(None)
    return out


def _write_all(blob):
    try:
        with dbm.db() as c:
            c.execute("INSERT INTO license_state(id, blob) VALUES(1, ?) "
                      "ON CONFLICT(id) DO UPDATE SET blob=excluded.blob", (blob,))
    except Exception:
        pass
    try:
        with open(os.path.join(_cache_dir(), "sys.dat"), "w", encoding="utf-8") as f:
            f.write(blob)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import winreg
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH)
            winreg.SetValueEx(k, "State", 0, winreg.REG_SZ, blob)
        except Exception:
            pass


def _key_file():
    return os.path.join(_cache_dir(), "lic.dat")


def _load_key():
    try:
        with dbm.db() as c:
            r = c.execute("SELECT value FROM settings WHERE key='license_key'").fetchone()
            if r and r["value"]:
                return r["value"]
    except Exception:
        pass
    try:
        with open(_key_file(), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def check_status():
    """-> (status, days_left, machine_id)   status: ACTIVATED | TRIAL | EXPIRED | TAMPERED"""
    mid = machine_id()
    key = _load_key()
    if key and verify_key(key, mid):
        return ("ACTIVATED", 9999, mid)

    today = date.today()
    raws = [r for r in _read_raw() if r]
    states = [s for s in (_unseal(r, mid) for r in raws) if s]
    if not states:
        if raws:                      # data existed but every copy failed its seal -> edited by hand
            return ("TAMPERED", 0, mid)
        state = {"i": today.isoformat(), "l": today.isoformat()}
    else:
        install = min(s["i"] for s in states)
        last = max(s["l"] for s in states)
        if (date.fromisoformat(last) - today).days > 1:   # clock rolled back
            return ("TAMPERED", 0, mid)
        state = {"i": install, "l": max(last, today.isoformat())}
    first = _remote_first_seen(mid)                   # the server remembers the TRUE first day, even if the local files were deleted
    if first and first < state["i"]:
        state["i"] = first
    _write_all(_seal(state, mid))
    used = (today - date.fromisoformat(state["i"])).days
    left = TRIAL_DAYS - used
    return ("TRIAL" if left > 0 else "EXPIRED", max(0, left), mid)


def activate(key):
    mid = machine_id()
    data = verify_key(key, mid)
    if not data:
        return False
    clean = "".join(key.split())
    try:
        dbm.settings.set_many({"license_key": clean})
    except Exception:
        pass
    try:
        with open(_key_file(), "w", encoding="utf-8") as f:
            f.write(clean)
    except Exception:
        pass
    return True
