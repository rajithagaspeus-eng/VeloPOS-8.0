"""Customer loyalty/credit read-only isolation and permission regression tests."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class CustomerLoyaltyPreviewTests(unittest.TestCase):
    def isolated(self, source, folder="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_loyalty_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / folder)
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                env=env, capture_output=True, text=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_points_credit_and_lookup_are_never_mutated(self):
        self.isolated(
            """
            from decimal import Decimal
            from velopos import database
            from velopos_qt.customer_loyalty import DraftCustomerReader
            database.init_db()
            with database.db() as connection:
                connection.execute(
                    "INSERT INTO customers(name,phone,loyalty_points,credit_balance,credit_limit)"
                    " VALUES('Demo Customer','0710001234',37.5,225.50,500)"
                )
                cid = connection.execute(
                    "SELECT id FROM customers WHERE name='Demo Customer'"
                ).fetchone()[0]
            logged = {"allowed": False}
            reader = DraftCustomerReader(database, authorize=lambda: logged["allowed"])
            for call in (lambda: reader.search("Demo"), lambda: reader.get(cid)):
                try:
                    call()
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Customer data leaked without cashier sign-in")
            logged["allowed"] = True
            assert len(reader.search("Demo")) == 1
            assert len(reader.search("0710001234")) == 1
            assert reader.search("%") == []
            assert reader.search("_") == []
            assert reader.get(cid)["loyalty_points"] == Decimal("37.5")
            assert reader.get(cid)["credit_balance"] == Decimal("225.5")
            assert reader.get(cid)["credit_limit"] == Decimal("500")
            assert reader.get(999999) is None
            assert len(reader.search("", limit=100000)) == 1
            for invalid_id in (0, -2, True, "xyz"):
                try:
                    reader.get(invalid_id)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid customer ID accepted")
            with database.db() as connection:
                values = connection.execute(
                    "SELECT loyalty_points,credit_balance,credit_limit "
                    "FROM customers WHERE id=?", (cid,)
                ).fetchone()
                assert tuple(values) == (37.5,225.5,500.0), tuple(values)
                assert connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert connection.execute("SELECT COUNT(*) FROM credit_logs").fetchone()[0] == 0
            logged["allowed"] = False
            try:
                reader.get(cid)
            except PermissionError:
                pass
            else:
                raise AssertionError("Logout must immediately revoke access")
            """
        )

    def test_non_preview_path_is_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.customer_loyalty import DraftCustomerReader
            database.init_db()
            try:
                DraftCustomerReader(database, authorize=lambda: True)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unexpected access to non-preview DB")
            """, folder="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
