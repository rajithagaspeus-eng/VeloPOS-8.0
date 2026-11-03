"""Test-only idempotency journal: request conflicts, rollback, replay, concurrency."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class IdempotencyLedgerIntegrationTests(unittest.TestCase):
    def isolated(self, code, directory="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_idempotency_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / directory)
            p = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                env=env, text=True, capture_output=True, timeout=45,
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_atomic_replay_conflict_and_rollback(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.idempotency_ledger import (
                PreviewIdempotencyLedger, IdempotencyConflict, request_fingerprint
            )
            database.init_db()
            journal = PreviewIdempotencyLedger(database)
            payload = {"items": [{"barcode": "A", "qty": 2}], "paid": "10.00"}
            assert request_fingerprint({"paid":"10.00","items":[{"qty":2,"barcode":"A"}]}) == request_fingerprint(payload)

            # Simulated power loss: both claim and mutation must roll back.
            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                outcome = journal.claim(c, "sale", "retry-on-crash-0001", payload)
                assert outcome.is_new
                c.execute("INSERT INTO audit_log(ts,user,action,detail) "
                          "VALUES('now','test','UNCOMMITTED','must rollback')")
                c.rollback()
            finally:
                c.close()
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='UNCOMMITTED'").fetchone()[0] == 0

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                claim = journal.claim(c, "sale", "retry-on-crash-0001", payload)
                assert claim.is_new and claim.result_ref is None
                journal.complete(c, "sale", "retry-on-crash-0001", "INV-0001")
                c.commit()
            finally:
                c.close()

            c = database.connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                replay = journal.claim(c, "sale", "retry-on-crash-0001", payload)
                assert replay.is_new is False and replay.result_ref == "INV-0001"
                try:
                    journal.claim(c, "sale", "retry-on-crash-0001", {"items":[]})
                except IdempotencyConflict:
                    pass
                else:
                    raise AssertionError("Conflicting payload accepted")
                # Scopes are isolated; return can reuse a sale's request key.
                assert journal.claim(c, "return", "retry-on-crash-0001", payload).is_new
                c.rollback()
            finally:
                c.close()

            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_request_journal"
                ).fetchone()[0] == 1
                for table in ("sales","returns","sale_items","supplier_payments"):
                    assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            """
        )

    def test_validation_connection_guards_and_unfinished_requests(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.idempotency_ledger import (
                PreviewIdempotencyLedger, request_fingerprint
            )
            database.init_db()
            journal = PreviewIdempotencyLedger(database)
            for bad in ({"a":float("nan")}, {"a":object()}, []):
                try:
                    request_fingerprint(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid payload accepted")
            c = database.connect()
            try:
                try:
                    journal.claim(c,"sale","request-00000001",{})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Claim without explicit transaction allowed")
                c.execute("BEGIN IMMEDIATE")
                for scope, key in (
                    ("unknown","request-00000001"),
                    ("sale","a"),
                    ("sale","not valid characters!"),
                ):
                    try:
                        journal.claim(c,scope,key,{})
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Bad scope/key accepted")
                journal.claim(c,"sale","request-00000001",{})
                c.commit()  # Intentionally unfinished; never treat as successful.
                c.execute("BEGIN IMMEDIATE")
                try:
                    journal.claim(c,"sale","request-00000001",{})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Unfinished claim silently retried")
                journal.complete(c,"sale","request-00000001","INV-X")
                try:
                    journal.complete(c,"sale","request-00000001","INV-Y")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Completed request overwritten")
                c.rollback()
            finally:
                c.close()
            # Reject an unrelated database even if a transaction is open.
            import sqlite3
            another = sqlite3.connect(":memory:")
            try:
                another.execute("BEGIN IMMEDIATE")
                try:
                    journal.claim(another, "sale", "request-00000002", {})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Unrelated DB accepted")
            finally:
                another.rollback()
                another.close()
            """
        )

    def test_serialized_competing_claims_return_same_result(self):
        self.isolated(
            """
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            from velopos import database
            from velopos_qt.idempotency_ledger import PreviewIdempotencyLedger
            database.init_db()
            journal = PreviewIdempotencyLedger(database)
            start = Barrier(2)
            def worker():
                start.wait(timeout=10)
                c = database.connect()
                try:
                    c.execute("BEGIN IMMEDIATE")
                    result = journal.claim(
                        c, "sale", "parallel-request-0001",
                        {"barcode":"RICE","qty":3},
                    )
                    if result.is_new:
                        journal.complete(c,"sale","parallel-request-0001","INV-123")
                    c.commit()
                    return result
                finally:
                    c.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                left = pool.submit(worker)
                right = pool.submit(worker)
                results = [left.result(timeout=20),right.result(timeout=20)]
            assert sum(r.is_new for r in results) == 1, results
            assert [r.result_ref for r in results if not r.is_new] == ["INV-123"], results
            with database.db() as c:
                assert c.execute(
                    "SELECT COUNT(*) FROM v8_preview_request_journal"
                ).fetchone()[0] == 1
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
            """
        )

    def test_no_production_database_access(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.idempotency_ledger import PreviewIdempotencyLedger
            database.init_db()
            try:
                PreviewIdempotencyLedger(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Non-preview database accepted")
            """, directory="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
