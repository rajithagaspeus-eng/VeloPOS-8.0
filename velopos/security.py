"""Password hashing (PBKDF2-SHA256), login throttling and recovery codes."""
import base64, functools, hashlib, hmac, os, secrets, time

from cryptography.fernet import Fernet, InvalidToken

ITERATIONS = 240_000
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


def _b64(b):
    return base64.b64encode(b).decode()


def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${_b64(salt)}${_b64(dk)}"


def verify_password(password, stored):
    try:
        scheme, iters, salt, dk = stored.split("$")
        if scheme != "pbkdf2":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                   base64.b64decode(salt), int(iters))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def new_recovery_code():
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def normalize_code(code):
    return "".join(ch for ch in code.upper() if ch.isalnum())


class LoginGuard:
    """5 wrong passwords => 60 s lock for that username."""
    MAX_FAILS, LOCK_SECONDS = 5, 60

    def __init__(self):
        self._fails, self._until = {}, {}

    def locked_for(self, user):
        return max(0, int(self._until.get(user, 0) - time.time()))

    def failed(self, user):
        self._fails[user] = self._fails.get(user, 0) + 1
        if self._fails[user] >= self.MAX_FAILS:
            self._until[user] = time.time() + self.LOCK_SECONDS
            self._fails[user] = 0

    def ok(self, user):
        self._fails.pop(user, None)
        self._until.pop(user, None)


guard = LoginGuard()


# ------------------------------------------------------------------ vault (machine-bound encryption)
@functools.lru_cache(maxsize=1)
def _vault_key():
    """Key derived from this PC's Machine ID. NOTE: this protects a copied database/backup file from
    being read on another computer; it does NOT protect against someone who is already logged in
    to this same Windows account (they can run the same program)."""
    from .license import machine_id          # read-only use of the existing function
    raw = hashlib.pbkdf2_hmac("sha256", ("VP-VAULT|" + machine_id()).encode(),
                              b"velopos-vault-v1", 200_000)
    return base64.urlsafe_b64encode(raw)


def vault_encrypt(text):
    return "enc1:" + Fernet(_vault_key()).encrypt(text.encode("utf-8")).decode()


def vault_decrypt(blob):
    """-> plain text, or '' when empty / made on another PC / tampered with."""
    try:
        if not blob or not blob.startswith("enc1:"):
            return ""
        return Fernet(_vault_key()).decrypt(blob[5:].encode()).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""
