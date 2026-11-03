"""Developer-only support override (Phase 7.2). No UI code.

Problem: a customer forgot the Admin password AND lost the Recovery Code. The developer (you) must be able to let them in remotely.
Why NOT a fixed per-PC code: any fixed code that the program can check would have to be computable from something inside the program,
so it would leak (and once leaked it works forever). Instead this is CHALLENGE-RESPONSE:

  1. The forgot-password screen shows a random CHALLENGE (e.g. K7QP-2MXD) and the Machine ID.
  2. The developer runs   python tools/support_code.py <MACHINE-ID> <CHALLENGE>   on HIS PC (it holds private_key.pem).
  3. The developer types / pastes the printed code into the customer's screen (e.g. over AnyDesk) - the customer never sees or keeps it.

The code is an Ed25519 signature over (purpose, Machine ID, challenge, expiry). It works only on that PC, only for that challenge, only
until it expires, only once. The program holds only the PUBLIC key, so nobody can make a code without private_key.pem.
"""
import base64, secrets, time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import license as lic

DEFAULT_MINUTES, MAX_SECONDS = 30, 24 * 3600
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_used = set()


def new_challenge():
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return raw[:4] + "-" + raw[4:]


def normalize(challenge):
    return "".join(ch for ch in str(challenge).upper() if ch.isalnum())


def message(purpose, mid, challenge, exp):
    """The exact bytes that are signed (shared by the program and tools/support_code.py)."""
    return f"VPSUPPORT1|{purpose}|{mid}|{normalize(challenge)}|{int(exp)}".encode()


def verify(code, challenge, purpose, mid=None, now=None):
    """-> (ok, message). A good code is consumed: it cannot be used twice."""
    now = int(now if now is not None else time.time())
    mid = mid or lic.machine_id()
    key = (purpose, mid, normalize(challenge))
    try:
        if not lic.PUBLIC_KEY_B64:
            return False, "This copy has no public key."
        if key in _used:
            return False, "This challenge was already used. Press 'New challenge'."
        exp_s, sig_s = "".join(str(code).split()).split(".")
        exp = int(exp_s)
        if exp < now:
            return False, "The support code has expired. Ask for a new one."
        if exp > now + MAX_SECONDS:
            return False, "Invalid support code."
        sig = base64.urlsafe_b64decode(sig_s + "=" * (-len(sig_s) % 4))
        Ed25519PublicKey.from_public_bytes(lic._b64d(lic.PUBLIC_KEY_B64)).verify(sig, message(purpose, mid, challenge, exp))
    except (InvalidSignature, ValueError, TypeError):
        return False, "Wrong support code."
    except Exception:
        return False, "Wrong support code."
    _used.add(key)
    return True, "OK"
