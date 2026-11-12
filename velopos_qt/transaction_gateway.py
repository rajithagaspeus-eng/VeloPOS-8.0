"""A mandatory-deny service gateway for the *nontransactional* V8 preview.

All contemplated transaction entry points must be represented by this gateway
when introduced in Qt. Every method calls PreviewTransactionGate.require
BEFORE touching any delegated original service, even if the caller supplies an
Admin role, payment information, or a fabricated license/shift claim.

This protects ONLY calls through the new gateway. The original V7 services
remain directly importable and must be refactored behind a verified production
session before any commercial checkout or other financial UI is enabled.
"""
from .transaction_policy import PreviewTransactionGate
from .commercial_boundary_assessment import assess_commercial_boundary
from .sale_request_service import PreviewSaleRequestService
from .sale_rehearsal_journal import PreviewSaleRehearsalJournal
from .durable_sale_rehearsal import DurablePreviewSaleJournal


class PreviewTransactionGateway:
    """Fail closed without storing a service reference or making a DB write."""

    def __init__(self, database):
        self._gate = PreviewTransactionGate(database)
        self._rehearsal_journal = PreviewSaleRehearsalJournal()

    @staticmethod
    def disposable_durable_rehearsal(path, *, max_requests=10000):
        """Explicit opt-in disposable journal; never attaches POS database."""
        return DurablePreviewSaleJournal(path, max_requests=max_requests)

    def rehearse_sale_replay(self, *, request_id, lines):
        """In-memory replay diagnostics only; never posts or reserves a sale."""
        return self._rehearsal_journal.inspect(
            request_id=request_id, lines=lines
        )

    def rehearse_sale(self, *, request_id, lines):
        """Pure preview-only draft; never verifies or posts a sale."""
        return PreviewSaleRequestService().inspect(
            request_id=request_id, lines=lines
        )

    def assess_future_boundary(self, action, evidence=None):
        """Read-only planning diagnostics; never unlocks any gateway method."""
        return assess_commercial_boundary(action, evidence)

    def _block(self, action, identity):
        self._gate.require(action, identity)
        # Defensive redundancy if a broken policy is ever substituted.
        raise PermissionError("V8 preview transactions are disabled")

    def sale(self, *, identity=None, **_payload):
        self._block("sale", identity)

    def return_sale(self, *, identity=None, **_payload):
        self._block("return", identity)

    def purchase(self, *, identity=None, **_payload):
        self._block("purchase", identity)

    def supplier_payment(self, *, identity=None, **_payload):
        self._block("supplier_payment", identity)

    def credit_payment(self, *, identity=None, **_payload):
        self._block("credit_payment", identity)

    def redeem_points(self, *, identity=None, **_payload):
        self._block("points_redemption", identity)

    def open_shift(self, *, identity=None, **_payload):
        self._block("shift_open", identity)

    def close_shift(self, *, identity=None, **_payload):
        self._block("shift_close", identity)

    def print_receipt(self, *, identity=None, **_payload):
        self._block("receipt_print", identity)

    def void_sale(self, *, identity=None, **_payload):
        self._block("sale_void", identity)

    def void_purchase(self, *, identity=None, **_payload):
        self._block("purchase_void", identity)

    def cash_move(self, *, identity=None, **_payload):
        self._block("cash_move", identity)

    def add_expense(self, *, identity=None, **_payload):
        self._block("expense_add", identity)

    def delete_expense(self, *, identity=None, **_payload):
        self._block("expense_delete", identity)

    def adjust_stock(self, *, identity=None, **_payload):
        self._block("stock_adjustment", identity)

    def finalize_stock_take(self, *, identity=None, **_payload):
        self._block("stock_take_finalize", identity)

    def receive_batch(self, *, identity=None, **_payload):
        self._block("batch_receive", identity)
