"""Disposable in-memory idempotency inspection for V8 sale rehearsals.

No database, external services, transaction posting or commercial authorization.
This object is an ephemeral diagnostic; it is NOT a durable idempotency ledger.
"""
from dataclasses import dataclass
from threading import RLock

from .sale_request_service import rehearse_sale_request


@dataclass(frozen=True)
class SaleRehearsalReplay:
    reference: str
    fingerprint: str
    replayed: bool
    can_checkout: bool = False
    can_post: bool = False


class PreviewSaleRehearsalJournal:
    """Compare repeated requests under a lock; never reserve a real sale."""

    def __init__(self, *, max_requests=10000):
        if type(max_requests) is not int or not 1 <= max_requests <= 100000:
            raise ValueError("Invalid rehearsal journal capacity")
        self._max_requests = max_requests
        self._lock = RLock()
        self._seen = {}
        self._sequence = 0

    def inspect(self, *, request_id, lines):
        draft = rehearse_sale_request(request_id=request_id, lines=lines)
        with self._lock:
            prior = self._seen.get(request_id)
            if prior is not None:
                if prior.fingerprint != draft.fingerprint:
                    raise ValueError("Preview request id reused with different payload")
                return SaleRehearsalReplay(
                    prior.reference, prior.fingerprint, True
                )
            if len(self._seen) >= self._max_requests:
                raise OverflowError("Preview rehearsal journal capacity exceeded")
            # Local sequence only; cannot be used as a commercial invoice ID.
            self._sequence += 1
            reference = "REHEARSAL-%08d" % self._sequence
            result = SaleRehearsalReplay(reference, draft.fingerprint, False)
            self._seen[request_id] = result
            return result

    def commit(self, **_claims):
        raise PermissionError("In-memory rehearsal journal cannot commit sales")
