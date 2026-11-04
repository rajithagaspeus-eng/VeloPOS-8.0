"""Disposable SQLite recovery/idempotency triage; NEVER enables a V8 sale."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


FIXTURE = """
import sqlite3
from velopos import database
from velopos_qt.idempotency_ledger import (
    PreviewIdempotencyLedger, IdempotencyConflict, request_fingerprint,
)
database.init_db()
ledger = PreviewIdempotencyLedger(database)
payload = {"branch_id": "BR-A", "lines": [{"barcode": "RICE", "qty": "1"}]}
request_id = "crash-recovery-0001"

def transaction():
    connection = database.connect()
    connection.execute("BEGIN IMMEDIATE")
    return connection
"""


class IdempotencyRecoveryTriageTests(unittest.TestCase):
    def isolated(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_journal_recovery_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", FIXTURE + "\n" + textwrap.dedent(script)],
                capture_output=True, text=True, env=env, timeout=75,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_completed_request_survives_reopen_but_is_not_posting_evidence(self):
        self.isolated("""
            c = transaction()
            assert ledger.inspect_request(c, "sale", request_id, payload).state == "not_recorded"
            assert ledger.claim(c, "sale", request_id, payload).is_new
            ledger.complete(c, "sale", request_id, "SIM-INVOICE-001")
            c.commit()
            c.close()
            c = transaction()
            state = ledger.inspect_request(c, "sale", request_id, payload)
            assert state.state == "journal_completed_unverified", state
            assert state.result_ref == "SIM-INVOICE-001"
            replay = ledger.claim(c, "sale", request_id, payload)
            assert not replay.is_new and replay.result_ref == "SIM-INVOICE-001"
            try:
                ledger.claim(c, "sale", request_id, dict(payload, branch_id="BR-B"))
            except IdempotencyConflict:
                pass
            else:
                raise AssertionError("Cross-branch payload reused a request ID")
            c.rollback()
            c.close()
        """)

    def test_committed_pending_requires_manual_reconciliation_and_denies_replay(self):
        self.isolated("""
            c = transaction()
            ledger.claim(c, "sale", request_id, payload)
            c.commit()  # Simulate a faulty integration committing only the claim.
            c.close()
            c = transaction()
            result = ledger.inspect_request(c, "sale", request_id, payload)
            assert result.state == "pending_manual_reconciliation", result
            assert result.result_ref is None
            try:
                ledger.claim(c, "sale", request_id, payload)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unreconciled PENDING row was retried")
            assert c.execute(
                "SELECT count(*) FROM v8_preview_request_journal"
            ).fetchone()[0] == 1
            c.rollback()
            c.close()
        """)

    def test_rollback_of_claim_and_completion_leaves_no_recovery_row(self):
        self.isolated("""
            c = transaction()
            ledger.claim(c, "sale", request_id, payload)
            ledger.complete(c, "sale", request_id, "SIM-ROLLBACK-1")
            c.rollback()
            c.close()
            c = transaction()
            assert ledger.inspect_request(c, "sale", request_id, payload).state == "not_recorded"
            assert ledger.claim(c, "sale", request_id, payload).is_new
            c.rollback()
            c.close()
        """)

    def test_bad_result_reference_is_rejected_before_completion(self):
        self.isolated("""
            c = transaction()
            ledger.claim(c, "sale", request_id, payload)
            for bad in ("", " ", " SIM-001", "SIM-001 ", "SIM\\n001", "SIM\\x00001"):
                try:
                    ledger.complete(c, "sale", request_id, bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unsafe result ref accepted: " + repr(bad))
            state = ledger.inspect_request(c, "sale", request_id, payload)
            assert state.state == "pending_manual_reconciliation"
            ledger.complete(c, "sale", request_id, "SIM-OK-1")
            c.commit()
            c.close()
        """)

    def test_corrupt_legacy_completed_row_not_replayed(self):
        self.isolated("""
            c = transaction()
            # Old journal table permits a COMPLETED row with NULL result_ref.
            c.execute("CREATE TABLE v8_preview_request_journal ("
                      "scope TEXT NOT NULL, request_id TEXT NOT NULL, "
                      "payload_sha256 TEXT NOT NULL, status TEXT NOT NULL, "
                      "result_ref TEXT, PRIMARY KEY(scope,request_id))")
            c.execute("INSERT INTO v8_preview_request_journal VALUES(?,?,?,?,?)",
                      ("sale", request_id, request_fingerprint(payload),
                       "COMPLETED", None))
            c.commit()
            c.close()
            c = transaction()
            state = ledger.inspect_request(c, "sale", request_id, payload)
            assert state.state == "corrupt_manual_reconciliation", state
            try:
                ledger.claim(c, "sale", request_id, payload)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Corrupt completion was accepted as a replay")
            c.rollback()
            c.close()
        """)

    def test_new_journal_schema_enforces_pending_and_completed_invariants(self):
        self.isolated("""
            c = transaction()
            ledger.claim(c, "sale", request_id, payload)
            for status, ref in (("PENDING", "ghost"), ("COMPLETED", None),
                                ("COMPLETED", "")):
                try:
                    c.execute("INSERT INTO v8_preview_request_journal "
                              "VALUES(?,?,?,?,?)",
                              ("sale", "other-request-0001",
                               request_fingerprint(payload), status, ref))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError("Malformed journal row inserted")
            assert c.execute("SELECT count(*) FROM v8_preview_request_journal"
                             ).fetchone()[0] == 1
            c.rollback()
            c.close()
        """)


if __name__ == "__main__":
    unittest.main()
