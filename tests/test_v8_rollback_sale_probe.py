"""Disposable V8 service-owned, NEVER-COMMIT sale journal probe regressions.

The production checkout gateway is never called and remains disabled. All
integration cases run inside an isolated VeloPOS8PreviewData subprocess.
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
from velopos_qt.rollback_sale_probe import PreviewRollbackOnlySaleProbe
from velopos_qt.atomic_sale_recovery import canonical_sale_recovery_payload
from velopos_qt.idempotency_ledger import PreviewIdempotencyLedger
probe = PreviewRollbackOnlySaleProbe(
    database, license_public_key_b64=pub(license_signer)
)
journal = PreviewIdempotencyLedger(database)
def journal_payload(kwargs):
    return canonical_sale_recovery_payload(
        identity=kwargs["identity"], shift_id=kwargs["shift_id"],
        lines=kwargs["lines"], expected_branch_id=kwargs["expected_branch_id"],
        license_id=kwargs["license_id"], machine_id=kwargs["machine_id"],
        today=kwargs["today"],
    )
def start_tx():
    c = database.connect()
    c.execute("BEGIN IMMEDIATE")
    return c
"""


class RollbackSaleProbeTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_sale_probe_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            run = subprocess.run(
                [sys.executable, "-c", FIXTURE + "\n" + EXTENSION + "\n" +
                 textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=80,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_service_owned_signed_probe_stages_then_always_rolls_back(self):
        self.isolated("""
            from dataclasses import FrozenInstanceError
            with database.db() as c:
                before = snapshot(c)
            for _ in range(2):
                result = probe.simulate(**args)
                assert result.stage == "journal_only_rolled_back", result
                assert result.simulated_result_ref.startswith("SIM-")
                assert result.journal_replayed_in_transaction is True
                assert result.persisted is False
                assert result.can_execute is False
                assert result.can_checkout is False
                try:
                    result.can_checkout = True
                except FrozenInstanceError:
                    pass
                else:
                    raise AssertionError("Probe evidence unexpectedly mutable")
            with database.db() as c:
                assert snapshot(c) == before, (snapshot(c), before)
            assert probe.recovery.inspect(**args).journal.state == "not_recorded"
            try:
                probe.require(**args)
            except PermissionError:
                pass
            else:
                raise AssertionError("Real checkout was unlocked")
        """)

    def test_simulated_failpoints_leave_no_durable_claim_or_financial_writes(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            for step in ("after_claim", "after_complete", "after_replay"):
                try:
                    probe.simulate(**dict(args, inject_failure_at=step))
                except RuntimeError as exc:
                    assert "Injected failure" in str(exc), exc
                else:
                    raise AssertionError("Failpoint did not abort: " + step)
                with database.db() as c:
                    assert snapshot(c) == before, (step, snapshot(c), before)
                assert probe.recovery.inspect(**args).journal.state == "not_recorded"
            assert probe.simulate(**args).persisted is False
        """)

    def test_bad_session_branch_shift_and_license_cannot_claim(self):
        self.isolated("""
            from velopos_qt.auth_model import PreviewIdentity
            with database.db() as c:
                before = snapshot(c)
            altered = (
                dict(args, identity=PreviewIdentity("cashier", "Admin", "fake")),
                dict(args, expected_branch_id="OTHER-BRANCH"),
                dict(args, shift_id=shift + 999),
                dict(args, license_key="INVALID-SIGNATURE"),
                dict(args, previous_status="INVALID-SIGNATURE"),
            )
            for variant in altered:
                try:
                    probe.simulate(**variant)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Unauthorized probe staged journal")
                with database.db() as c:
                    assert snapshot(c) == before
        """)

    def test_committed_pending_and_completed_claims_require_reconciliation(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            c = start_tx()
            try:
                journal.claim(c, "sale", args["request_id"], journal_payload(args))
                c.commit()
            finally:
                c.close()
            try:
                probe.simulate(**args)
            except PermissionError:
                pass
            else:
                raise AssertionError("Stranded PENDING was replayed")
            assert probe.recovery.inspect(**args).journal.state == (
                "pending_manual_reconciliation"
            )
            other = dict(args, request_id="rollback-probe-completed-0001")
            c = start_tx()
            try:
                journal.claim(c, "sale", other["request_id"], journal_payload(other))
                journal.complete(c, "sale", other["request_id"], "SIM-EXISTING")
                c.commit()
            finally:
                c.close()
            try:
                probe.simulate(**other)
            except PermissionError:
                pass
            else:
                raise AssertionError("Completed journal was treated as posting proof")
            evidence = probe.recovery.inspect(**other).journal
            assert evidence.state == "journal_completed_unverified"
            assert evidence.result_ref == "SIM-EXISTING"
            with database.db() as c:
                after = snapshot(c)
            for key in ("sales", "sale_items", "returns", "stock", "moves",
                        "payments"):
                assert before[key] == after[key], (key, before, after)
        """)

    def test_one_shot_generator_and_mutable_identity_are_snapshotted(self):
        self.isolated("""
            class MutableIdentity:
                def __init__(self, source):
                    self.username = source.username
                    self.role = source.role
                    self.credential_tag = source.credential_tag
            mutable = MutableIdentity(user)
            original = probe.recovery.inspect_in_transaction
            def mutate_during_probe(connection, **kwargs):
                mutable.username = "forged-after-snapshot"
                mutable.role = "Admin"
                mutable.credential_tag = "forged"
                return original(connection, **kwargs)
            probe.recovery.inspect_in_transaction = mutate_during_probe
            draft = (dict(row) for row in lines)
            evidence = probe.simulate(
                **dict(args, identity=mutable, lines=draft)
            )
            assert mutable.username == "forged-after-snapshot"
            assert evidence.stage == "journal_only_rolled_back"
            assert evidence.persisted is False and evidence.can_checkout is False
            assert probe.recovery.inspect(**args).journal.state == "not_recorded"
        """)

    def test_unknown_failure_point_denies_without_opening_business_transaction(self):
        self.isolated("""
            with database.db() as c:
                before = snapshot(c)
            try:
                probe.simulate(**dict(args, inject_failure_at="commit"))
            except ValueError:
                pass
            else:
                raise AssertionError("Caller selected a forbidden commit stage")
            with database.db() as c:
                assert snapshot(c) == before
        """)


if __name__ == "__main__":
    unittest.main()
