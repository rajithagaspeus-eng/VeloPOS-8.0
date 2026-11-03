"""Read-only customer loyalty preview.

Customer details are accessible to an authenticated preview Admin/Cashier
only. Existing legacy loyalty points and credit balances are shown exactly as
stored: selecting a customer never redeems/earns points or extends credit.
"""
from decimal import Decimal
from .product_editor import _guard


class DraftCustomerReader:
    def __init__(self, database, authorize):
        _guard(database)
        self.database = database
        self.authorize = authorize

    def _require_access(self):
        _guard(self.database)
        if not self.authorize():
            raise PermissionError("Sign in as a preview cashier to view customer data")

    def search(self, query="", limit=20):
        self._require_access()
        limit = max(1, min(int(limit), 50))
        term = str(query or "").strip()
        if len(term) > 100:
            raise ValueError("Customer search is too long")
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.database.db() as connection:
            rows = connection.execute(
                "SELECT id, name, COALESCE(phone,'') phone "
                "FROM customers WHERE name LIKE ? ESCAPE '\\' "
                "OR phone LIKE ? ESCAPE '\\' ORDER BY name COLLATE NOCASE, id LIMIT ?",
                (like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, customer_id):
        self._require_access()
        if isinstance(customer_id, bool):
            raise ValueError("Invalid customer")
        try:
            key = int(customer_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid customer") from exc
        if key <= 0:
            raise ValueError("Invalid customer")
        with self.database.db() as connection:
            row = connection.execute(
                "SELECT id, name, COALESCE(loyalty_points,0) loyalty_points, "
                "COALESCE(credit_balance,0) credit_balance, "
                "COALESCE(credit_limit,0) credit_limit FROM customers WHERE id=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        for field in ("loyalty_points", "credit_balance", "credit_limit"):
            data[field] = Decimal(str(data[field]))
        return data
