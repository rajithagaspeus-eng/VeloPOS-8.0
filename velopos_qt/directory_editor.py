"""Guarded customer/supplier editing in isolated V8 preview only.

The existing audited VeloPOS services own all writes and validation.
No customer financial balances or supplier payment details are editable here.
"""
from .product_editor import _guard


class PreviewDirectoryEditor:
    def __init__(self, database, services=None, authorize=None):
        _guard(database)
        self.database = database
        self.authorize = authorize
        if services is None:
            from velopos import services
        self.services = services

    def get(self, kind, identifier):
        _guard(self.database)
        if self.authorize is not None and not self.authorize():
            raise PermissionError("Preview Admin sign-in is required to read editor details")
        table = self._table(kind)
        with self.database.db() as connection:
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id=?", (int(identifier),)
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _table(kind):
        # SQL identifiers are never derived from user-provided strings.
        if kind == "customers":
            return "customers"
        if kind == "suppliers":
            return "suppliers"
        raise ValueError("Unknown directory type")

    def save(self, kind, *, identifier=None, name="", phone="",
             address="", contact="", whatsapp="", notes="", active=True):
        _guard(self.database)
        self._table(kind)
        if self.authorize is not None and not self.authorize():
            raise PermissionError("Preview Admin sign-in is required for directory changes")
        if not str(name).strip():
            raise ValueError("Name is required")
        if len(str(address)) > 500 or len(str(notes)) > 1000:
            raise ValueError("Text field is too long")
        actor = "v8-preview"
        if kind == "customers":
            if identifier is None:
                return self.services.add_customer(
                    name, phone, actor, address=address
                )
            return self.services.update_customer(
                int(identifier), name, phone, actor, address=address
            )
        if identifier is None:
            return self.services.add_supplier(
                name, actor, contact=contact, phone=phone,
                whatsapp=whatsapp, address=address, notes=notes,
            )
        return self.services.update_supplier(
            int(identifier), actor, name, contact=contact, phone=phone,
            whatsapp=whatsapp, address=address, notes=notes, active=active,
        )
