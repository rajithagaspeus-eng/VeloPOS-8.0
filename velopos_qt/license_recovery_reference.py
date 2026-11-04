"""Reference license renewal and device transfer for isolated V8 preview.

Requires the existing signed Admin operator command gateway and caller-owned
server transaction. It is NOT a public HTTP endpoint, production licensing,
automatic reactivation, device attestation or checkout authorization.

A transfer must never silently reset the revoked state, sequence, or prior
signed observation digest. The new device must separately authenticate and
obtain a new signed receipt; the old receipt cannot pass server inspection.
"""
from dataclasses import dataclass
from datetime import timedelta

from .activation_chain import _identifier, _sequence, _utc
from .server_activation_reference import (
    PreviewServerActivationAuthority, _clock,
)


@dataclass(frozen=True)
class PreviewRecoveryResult:
    license_id: str
    operation: str
    last_sequence: int
    new_expires_utc: str
    machine_id: str
    branch_id: str
    can_execute: bool = False


class PreviewLicenseRecoveryReference:
    """Atomic, fail-closed administrator operations on disposable server state."""

    def __init__(self, authority):
        if not isinstance(authority, PreviewServerActivationAuthority):
            raise TypeError("PreviewServerActivationAuthority required")
        self.authority = authority

    def _current(self, connection, license_id, expected_sequence, server_now):
        self.authority._check(connection)
        if not _identifier(license_id):
            raise ValueError("Canonical license ID required")
        if (_sequence(expected_sequence) is None
                or expected_sequence == 0):
            raise ValueError("Positive integer expected sequence required")
        clock = _clock(server_now)  # Test injection, not production trust.
        row = connection.execute(
            "SELECT license_id,machine_id,branch_id,expires_utc,status,"
            "last_sequence,last_observed_utc FROM "
            "v8_preview_server_license_state WHERE license_id=?",
            (license_id,),
        ).fetchone()
        if row is None or row["status"] != "active":
            raise PermissionError("Unknown/revoked license cannot be recovered")
        if row["last_sequence"] != expected_sequence:
            raise PermissionError("Recovery command is stale")
        if (row["last_observed_utc"] is not None
                and clock < _utc(row["last_observed_utc"])):
            raise PermissionError("Server clock rollback at recovery")
        return row, clock

    def renew(self, connection, *, license_id, expected_sequence,
              new_expires_utc, server_now=None):
        """Strictly extend an active license; never reactivate a revoked one."""
        row, clock = self._current(
            connection, license_id, expected_sequence, server_now,
        )
        new_expiry = _utc(new_expires_utc)
        old_expiry = _utc(row["expires_utc"])
        if (new_expiry <= clock or new_expiry <= old_expiry
                or new_expiry > clock + timedelta(days=366)):
            raise ValueError("Renewal must extend expiry by at most 366 days")
        updated = connection.execute(
            "UPDATE v8_preview_server_license_state SET expires_utc=? "
            "WHERE license_id=? AND status='active' AND last_sequence=? "
            "AND expires_utc=?",
            (new_expires_utc, license_id, expected_sequence,
             row["expires_utc"]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Concurrent renewal state changed")
        # Prior signed receipt is now invalid because its signed expiry does
        # not match this new server state; only a fresh issue can establish it.
        return PreviewRecoveryResult(
            license_id, "renew", expected_sequence, new_expires_utc,
            row["machine_id"], row["branch_id"],
        )

    def transfer(self, connection, *, license_id, expected_sequence,
                 expected_machine_id, expected_branch_id,
                 new_machine_id, new_branch_id, server_now=None):
        """Admin-approved device/branch replacement, never a client self-reset."""
        for value in (expected_machine_id, expected_branch_id,
                      new_machine_id, new_branch_id):
            if not _identifier(value):
                raise ValueError("Canonical transfer device/branch required")
        row, clock = self._current(
            connection, license_id, expected_sequence, server_now,
        )
        if clock > _utc(row["expires_utc"]):
            raise PermissionError("Expired license must be renewed first")
        if (row["machine_id"] != expected_machine_id
                or row["branch_id"] != expected_branch_id):
            raise PermissionError("Recovery expected binding mismatch")
        if (new_machine_id == expected_machine_id
                and new_branch_id == expected_branch_id):
            raise ValueError("Transfer must change device or branch")
        updated = connection.execute(
            "UPDATE v8_preview_server_license_state "
            "SET machine_id=?, branch_id=? "
            "WHERE license_id=? AND status='active' AND last_sequence=? "
            "AND machine_id=? AND branch_id=?",
            (new_machine_id, new_branch_id, license_id, expected_sequence,
             expected_machine_id, expected_branch_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Concurrent transfer state changed")
        # Signed sequence and prior SHA-256 digest intentionally persist.
        # Old device receipts/grants cannot pass *online* server-state checks.
        return PreviewRecoveryResult(
            license_id, "transfer", expected_sequence, row["expires_utc"],
            new_machine_id, new_branch_id,
        )

    def require_checkout(self, *args, **kwargs):
        raise PermissionError("Recovery reference cannot authorize checkout")
