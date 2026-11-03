"""Preview-only user credential verification and role decision foundation.

No default passwords, session persistence, live checkout, email sending or
licensing mutations. Protected POS operations must later enforce server/service
authorization; this is not a production authentication gateway.
"""
from dataclasses import dataclass
from .product_editor import _guard


@dataclass(frozen=True)
class PreviewIdentity:
    username: str
    role: str

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
        return PreviewIdentity(row["username"], row["role"])
