"""Preview-only user credential verification and role decision foundation.

No default passwords, session persistence, live checkout, email sending or
licensing mutations. Protected POS operations must later enforce server/service
authorization; this is not a production authentication gateway.
"""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from pathlib import Path
from secrets import token_bytes, token_hex
from .product_editor import _guard


# Session proofs are HMAC-authenticated with a process-local random key.
# They are never derived from a public hash alone. Restart invalidates them.
_PROCESS_KEY = token_bytes(32)
_ACTIVE_TOKENS = set()


def _proof(database, username, role, pw_hash, nonce):
    database_id = str(Path(database.DB_PATH).resolve())
    message = "\\0".join((database_id, username, role, str(pw_hash), nonce))
    return hmac_new(_PROCESS_KEY, message.encode("utf-8"), sha256).hexdigest()


def _issue_preview_token(database, username, role, pw_hash):
    nonce = token_hex(16)
    token = nonce + "." + _proof(database, username, role, pw_hash, nonce)
    _ACTIVE_TOKENS.add(token)
    return token


def revoke_preview_session(identity):
    """Invalidate an individual process-local preview login immediately."""
    _ACTIVE_TOKENS.discard(getattr(identity, "credential_tag", None))


def verify_preview_session(database, identity, persisted):
    """Validate a live identity against one DB row read in the caller's TX.

    The caller MUST have independently enforced _guard(database) and opened
    the canonical preview connection. Never a commercial transaction license.
    """
    if identity is None:
        return False
    if persisted is None:
        revoke_preview_session(identity)
        return False
    username = getattr(identity, "username", None)
    role = getattr(identity, "role", None)
    token = getattr(identity, "credential_tag", None)
    if not isinstance(username, str) or not isinstance(role, str):
        return False
    if not isinstance(token, str) or token not in _ACTIVE_TOKENS:
        return False
    try:
        nonce, mac = token.split(".", 1)
        if len(nonce) != 32 or len(mac) != 64:
            return False
        int(nonce, 16)
        int(mac, 16)
        if persisted["role"] != role or role not in ("Admin", "Cashier"):
            return False
        expected = _proof(database, username, role, persisted["pw_hash"], nonce)
        valid = compare_digest(mac, expected)
    except (ValueError, TypeError, KeyError, AttributeError):
        valid = False
    if not valid:
        revoke_preview_session(identity)
    return valid


@dataclass(frozen=True)
class PreviewIdentity:
    username: str
    role: str
    credential_tag: str = ""  # runtime-only fingerprint; never the password/hash

    @property
    def can_manage_staff(self):
        return self.role == "Admin"

    @property
    def can_open_draft(self):
        return self.role in ("Admin", "Cashier")


class PreviewAuthenticator:
    def __init__(self, database, services=None, security=None):
        _guard(database)
        self.database = database
        if services is None:
            from velopos import services
        if security is None:
            from velopos import security
        self.services = services
        self.security = security

    def current_role(self, identity):
        """Revalidate a preview identity against the persisted user role.

        Fail closed if the account was removed, demoted or storage fails.
        This does NOT replace a cryptographic session or a production
        transaction authorization boundary.
        """
        _guard(self.database)
        if identity is None or not getattr(identity, "username", None):
            return None
        try:
            with self.database.db() as connection:
                row = connection.execute(
                    "SELECT role, pw_hash FROM users WHERE username=?",
                    (identity.username,),
                ).fetchone()
        except (OSError, RuntimeError):
            return None
        role = row["role"] if row else None
        if role not in ("Admin", "Cashier"):
            revoke_preview_session(identity)
            return None
        # An HMAC-authenticated, process-local token binds DB, user, role,
        # password hash and a random nonce; invalidation is irreversible.
        # A role restore after revocation cannot revive this session.
        if not verify_preview_session(self.database, identity, row):
            return None
        return role

    def needs_setup(self):
        _guard(self.database)
        with self.database.db() as connection:
            return not bool(connection.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def bootstrap_admin(self, username, password):
        """Initialize an empty *preview-only* DB with an owner-selected account."""
        _guard(self.database)
        if not self.needs_setup():
            raise ValueError("Preview administrator is already configured")
        if len(str(password or "")) < 12:
            raise ValueError("Choose a password with at least 12 characters")
        self.services.save_user(username, password, "Admin", "v8-preview-setup")
        return self.authenticate(username, password)

    def authenticate(self, username, password):
        """Verify an existing account with persistent throttling in test DB.

        Always give the same failure response for unknown and wrong-password
        users. Never return a database row or password hash to the UI.
        """
        _guard(self.database)
        name = str(username or "").strip().lower()
        password = str(password or "")
        if not name or len(name) > 30 or not password:
            raise ValueError("Invalid username or password")
        if self.services.login_locked_for(name):
            raise ValueError("Too many attempts. Try again later.")
        with self.database.db() as connection:
            row = connection.execute(
                "SELECT username, pw_hash, role FROM users WHERE username=?",
                (name,),
            ).fetchone()
        valid = bool(
            row and row["role"] in ("Admin", "Cashier")
            and self.security.verify_password(password, row["pw_hash"])
        )
        if not valid:
            self.services.login_failed(name)
            raise ValueError("Invalid username or password")
        self.services.login_ok(name)
        tag = _issue_preview_token(
            self.database, row["username"], row["role"], row["pw_hash"]
        )
        return PreviewIdentity(row["username"], row["role"], tag)
