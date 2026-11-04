"""Atomic sale policy + immutable recovery status, disposable V8 databases.

No test is authorized to post an actual sale or stock movement. The fixture
uses random disposable Ed25519 keys, and rolls back all owned inspections.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_v8_phase2_atomic_sale_boundary import FIXTURE

EXTENSION = """
from velopos_qt.atomic_sale_recovery import (
    PreviewAtomicSaleRecovery, canonical_sale_recovery_payload,
)
from velopos_qt.idempotency_ledger import (
    PreviewIdempotencyLedger, IdempotencyConflict,
)
recovery = PreviewAtomicSaleRecovery(
    database, license_public_key_b64=pub(license_signer)
)
journal = PreviewIdempotencyLedger(database)
def payload_for(values):
    return canonical_sale_recovery_payload(
        identity=values["identity"], shift_id=values["shift_id"],
        lines=values["lines"],
        expected_branch_id=values["expected_branch_id"],
        license_id=values["license_id"],
        machine_id=values["machine_id"], today=values["today"],
    )
def journal_tx():
    c = database.connect()
    c.execute("BEGIN IMMEDIATE")
    return c
"""


class AtomicSaleRecoveryTests(unittest.TestCase):
    def isolated(self, source):
        with tempfile.TemporaryDirectory(prefix="v8_atomic_recovery_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", FIXTURE + EXTENSION + textwrap.dedent(source)],
                env=env, capture_output=True, text=True, timeout=80,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_policy_and_missing_journal_are_never_checkout_authority(self):
        self.isolated("""
            from dataclasses import FrozenInstanceError
            with database.db() as c:
                before = snapshot(c)
            result = recovery.inspect(**args)
            assert result.readiness.policy_consistent, result
            assert result.journal.state == "not_recorded", result
            assert result.can_execute is False and result.can_checkout is False
            assert "sale_recovery_diagnostic_only" in result.reasons
            try:
                result.can_checkout = True
            except FrozenInstanceError:
                pass
            else:
                raise AssertionError("Readiness object was mutable")
            try:
                recovery.require(**args)
            except PermissionError:
                pass
            else:
                raise AssertionError("Diagnostic authorized commerce")
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_pending_claim_then_completed_journal_still_no_sale(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            c = journal_tx()
            try:
                assert journal.claim(
                    c, "sale", args["request_id"], payload_for(args)
                ).is_new
                c.commit()  # intentionally simulate orphan PENDING
            finally:
                c.close()
            pending = recovery.inspect(**args)
            assert pending.journal.state == "pending_manual_reconciliation"
            assert "journal_pending_manual_reconciliation" in pending.reasons
            assert pending.can_checkout is False
            # A stranded PENDING claim must never be silently completed.
            # Test a separate correctly owned claim/completion transaction.
            another = dict(args, request_id="atomic-completed-0002")
            c = journal_tx()
            try:
                assert journal.claim(
                    c, "sale", another["request_id"], payload_for(another)
                ).is_new
                journal.complete(c, "sale", another["request_id"], "SIM-ONLY-123")
                c.commit()
            finally:
                c.close()
            completed = recovery.inspect(**another)
            assert completed.journal.state == "journal_completed_unverified"
            assert completed.journal.result_ref == "SIM-ONLY-123"
            assert completed.can_checkout is False
            with database.db() as c:
                after = snapshot(c)
            for field in ("sales", "sale_items", "returns", "stock",
                          "moves", "payments"):
                assert after[field] == before[field], (field, before, after)
        """)

    def test_same_key_cannot_cross_branch_device_actor_shift_or_draft(self):
        self.isolated("""
            from velopos_qt.auth_model import PreviewIdentity
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-A")
                c.commit()
            finally:
                c.close()
            unauthorized = (
                dict(args, expected_branch_id="BRANCH-002"),
                dict(args, license_id="LIC-999"),
                dict(args, machine_id="OTHER-MACHINE"),
                dict(args, shift_id=shift + 99),
                dict(args, identity=PreviewIdentity("someone", "Cashier", "fake")),
            )
            for variant in unauthorized:
                observed = recovery.inspect(**variant)
                assert observed.journal.state == "withheld_authorization_required"
                assert observed.journal.result_ref is None
                assert observed.can_checkout is False
            # A changed, otherwise valid draft reaches the journal and
            # must still detect immutable request-id reuse.
            changed_draft = dict(
                args, lines=[{"barcode": "RICE", "qty": 1, "price": 45}]
            )
            try:
                recovery.inspect(**changed_draft)
            except IdempotencyConflict:
                pass
            else:
                raise AssertionError("Different valid draft reused request key")
            assert recovery.inspect(**args).journal.result_ref == "SIM-A"
        """)

    def test_revocation_or_closed_shift_stays_denied_after_journal_completion(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-REVOKED")
                c.commit()
            finally:
                c.close()
            with database.db() as c:
                c.execute("UPDATE v8_preview_branch_memberships SET active=0")
                c.execute("UPDATE shifts SET status='CLOSED' WHERE id=?", (shift,))
            denied = recovery.inspect(**args)
            assert denied.journal.state == "withheld_authorization_required"
            assert denied.journal.result_ref is None
            assert denied.readiness.branch_verified is False
            assert denied.readiness.policy_consistent is False
            assert "shift_not_open" in denied.reasons
            assert denied.can_checkout is False
        """)

    def test_equivalent_decimal_lines_share_one_immutable_request_payload(self):
        self.isolated("""
            from decimal import Decimal
            normalized = dict(args, lines=[
                {"barcode": "RICE", "qty": Decimal("2.000"), "price": "45.00"},
                {"barcode": "RICE", "qty": "3", "price": Decimal("45.0")},
                {"barcode": "SOAP", "qty": "1.00", "price": "25.0"},
            ])
            assert payload_for(normalized) == payload_for(args)
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-CANONICAL")
                c.commit()
            finally:
                c.close()
            replay = recovery.inspect(**normalized)
            assert replay.journal.state == "journal_completed_unverified"
            assert replay.journal.result_ref == "SIM-CANONICAL"
            assert replay.can_checkout is False
        """)

    def test_single_use_generator_is_snapshotted_for_policy_and_replay(self):
        self.isolated("""
            c = journal_tx()
            try:
                assert journal.claim(
                    c, "sale", args["request_id"], payload_for(args)
                ).is_new
                journal.complete(c, "sale", args["request_id"], "SIM-GENERATOR")
                c.commit()
            finally:
                c.close()
            generator = (dict(row) for row in lines)
            observed = recovery.inspect(**dict(args, lines=generator))
            assert observed.readiness.policy_consistent, observed
            assert observed.journal.state == "journal_completed_unverified"
            assert observed.journal.result_ref == "SIM-GENERATOR"
            assert observed.can_checkout is False
        """)

    def test_caller_draft_mutation_cannot_split_policy_and_fingerprint(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-IMMUTABLE")
                c.commit()
            finally:
                c.close()
            caller_lines = [dict(row) for row in lines]
            original_check = recovery.boundary.inspect_in_transaction

            def malicious_mutation_during_inspection(connection, **kwargs):
                # Simulate another caller mutating the original draft after
                # the recovery boundary has taken its validated snapshot.
                caller_lines[0]["qty"] = 999999
                return original_check(connection, **kwargs)

            recovery.boundary.inspect_in_transaction = malicious_mutation_during_inspection
            observed = recovery.inspect(**dict(args, lines=caller_lines))
            assert caller_lines[0]["qty"] == 999999
            assert observed.readiness.policy_consistent, observed
            assert observed.journal.state == "journal_completed_unverified"
            assert observed.journal.result_ref == "SIM-IMMUTABLE"
            assert observed.can_execute is False
        """)

    def test_implicit_day_is_pinned_across_policy_and_journal(self):
        self.isolated("""
            from datetime import date
            from velopos_qt.atomic_sale_boundary import PreviewAtomicSaleBoundary
            original_day = PreviewAtomicSaleBoundary._day
            seen_days = []

            def controlled_day(today):
                seen_days.append(today)
                if today is None:
                    return date(2026, 11, 4)
                return original_day(today)

            PreviewAtomicSaleBoundary._day = staticmethod(controlled_day)
            try:
                observed = recovery.inspect(**dict(args, today=None))
            finally:
                PreviewAtomicSaleBoundary._day = staticmethod(original_day)
            assert observed.readiness.policy_consistent, observed
            assert observed.journal.state == "not_recorded"
            assert seen_days[0] is None, seen_days
            assert all(day == "2026-11-04" for day in seen_days[1:]), seen_days
            assert observed.can_checkout is False
        """)

    def test_oversized_stream_is_rejected_before_any_journal_change(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            yielded = []
            def hostile_draft():
                for i in range(101):
                    yielded.append(i)
                    yield {"barcode": "RICE", "qty": 1, "price": 45}
                raise AssertionError("Unbounded iterator consumption")
            try:
                recovery.inspect(**dict(args, lines=hostile_draft()))
            except ValueError as exc:
                assert "1-100 lines" in str(exc), exc
            else:
                raise AssertionError("Oversized stream was accepted")
            assert len(yielded) == 101, len(yielded)
            with database.db() as c:
                assert snapshot(c) == before
        """)

    def test_mutable_identity_cannot_split_policy_actor_and_journal(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-IDENTITY")
                c.commit()
            finally:
                c.close()

            class MutableIdentity:
                def __init__(self, source):
                    self.username = source.username
                    self.role = source.role
                    self.credential_tag = source.credential_tag

            proxy = MutableIdentity(user)
            original = recovery.boundary.inspect_in_transaction

            def mutate_original_during_policy(connection, **kwargs):
                proxy.username = "impostor"
                proxy.role = "Admin"
                proxy.credential_tag = "forged"
                return original(connection, **kwargs)

            recovery.boundary.inspect_in_transaction = mutate_original_during_policy
            result = recovery.inspect(**dict(args, identity=proxy))
            assert proxy.username == "impostor"
            assert result.readiness.session_bound, result
            assert result.readiness.policy_consistent, result
            assert result.journal.state == "journal_completed_unverified"
            assert result.journal.result_ref == "SIM-IDENTITY"
            assert result.can_execute is False and result.can_checkout is False
        """)

    def test_account_role_change_revokes_even_completed_journal_request(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-ROLE")
                c.commit()
            finally:
                c.close()
            with database.db() as c:
                c.execute("UPDATE users SET role='Admin' WHERE username='cashier'")
            result = recovery.inspect(**args)
            assert result.journal.state == "withheld_authorization_required"
            assert result.journal.result_ref is None
            assert not result.readiness.session_bound, result
            assert not result.readiness.policy_consistent, result
            assert "verified_session_required" in result.reasons
            assert result.can_checkout is False
        """)

    def test_password_hash_rotation_permanently_revokes_cached_session(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-ROTATION")
                c.commit()
            finally:
                c.close()
            with database.db() as c:
                old_hash = c.execute(
                    "SELECT pw_hash FROM users WHERE username='cashier'"
                ).fetchone()[0]
                c.execute(
                    "UPDATE users SET pw_hash=? WHERE username='cashier'",
                    ("different-credential-hash",),
                )
            blocked = recovery.inspect(**args)
            assert not blocked.readiness.session_bound
            assert blocked.journal.state == "withheld_authorization_required"
            assert blocked.journal.result_ref is None
            with database.db() as c:
                c.execute(
                    "UPDATE users SET pw_hash=? WHERE username='cashier'",
                    (old_hash,),
                )
            still_blocked = recovery.inspect(**args)
            assert not still_blocked.readiness.session_bound, still_blocked
            assert not still_blocked.readiness.policy_consistent
            assert still_blocked.can_checkout is False
        """)

    def test_shift_branch_rebinding_after_completion_never_authorizes(self):
        self.isolated("""
            c = journal_tx()
            try:
                journal.claim(c, "sale", args["request_id"], payload_for(args))
                journal.complete(c, "sale", args["request_id"], "SIM-BRANCH")
                c.commit()
            finally:
                c.close()
            with database.db() as c:
                c.execute(
                    "UPDATE v8_preview_branch_shifts SET branch_id='BRANCH-OTHER' "
                    "WHERE shift_id=?", (shift,),
                )
            result = recovery.inspect(**args)
            assert result.journal.state == "withheld_authorization_required"
            assert result.journal.result_ref is None
            assert not result.readiness.branch_verified, result
            assert not result.readiness.policy_consistent, result
            assert "shift_branch_mismatch" in result.reasons
            assert result.can_checkout is False
        """)

    def test_caller_transaction_ownership_and_foreign_connection_refusal(self):
        self.isolated("""
            import sqlite3
            c = database.connect()
            try:
                try:
                    recovery.inspect_in_transaction(c, **args)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Transaction was optional")
                c.execute("BEGIN IMMEDIATE")
                c.execute("CREATE TABLE caller_uncommitted_marker (x INT)")
                c.execute("INSERT INTO caller_uncommitted_marker VALUES(123)")
                result = recovery.inspect_in_transaction(c, **args)
                assert result.journal.state == "not_recorded"
                assert c.in_transaction
                assert c.execute(
                    "SELECT x FROM caller_uncommitted_marker"
                ).fetchone()[0] == 123
                c.rollback()
            finally:
                c.close()
            with database.db() as check:
                assert not check.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='caller_uncommitted_marker'"
                ).fetchone()
            foreign = sqlite3.connect(":memory:")
            try:
                foreign.execute("BEGIN IMMEDIATE")
                try:
                    recovery.inspect_in_transaction(foreign, **args)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Foreign connection was trusted")
            finally:
                foreign.close()
        """)


if __name__ == "__main__":
    unittest.main()
