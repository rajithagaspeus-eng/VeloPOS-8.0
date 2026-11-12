"""Cashier shift information for non-transactional V8 draft screens.

This is a display-only preview. It does NOT authorize checkout or open/close
shifts. The real service enforces shift state inside create_sale.
"""
from .product_editor import _guard


class PreviewShiftReader:
    def __init__(self, database):
        _guard(database)
        self.database = database

    def current(self):
        _guard(self.database)
        with self.database.db() as connection:
            row = connection.execute(
                "SELECT id, cashier, opened_at FROM shifts "
                "WHERE status='OPEN' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
