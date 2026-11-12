"""V8 preview transaction authorization must fail closed, with isolated paths."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from velopos_qt.auth_model import PreviewIdentity
from velopos_qt.transaction_policy import PreviewTransactionGate


class TransactionPolicyIntegrationTests(unittest.TestCase):
    def isolated(self, code, dirname="VeloPOS8PreviewData"):
        with tempfile.TemporaryDirectory(prefix="v8_transaction_policy_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / dirname)
            p = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(code)],
                env=env, text=True, capture_output=True, timeout=35,
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_all_protected_transactions_remain_denied_even_for_admin(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.auth_model import PreviewIdentity
            from velopos_qt.transaction_policy import PreviewTransactionGate
            database.init_db()
            policy = PreviewTransactionGate(database)
            identities = [None, PreviewIdentity("staff", "Cashier"),
                          PreviewIdentity("owner", "Admin")]
            for action in sorted(policy.protected):
                for identity in identities:
                    verdict = policy.evaluate(action, identity)
                    assert verdict.action == action
                    assert verdict.allowed is False
                    assert verdict.reasons
                    try:
                        policy.require(action, identity)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("Preview transaction allowed")
            for action in ("", "license_sign", "admin_override", "UNKNOWN"):
                try:
                    policy.require(action, identities[-1])
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unrecognized action accepted")
            with database.db() as c:
                assert c.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] == 0
                assert c.execute("SELECT COUNT(*) FROM supplier_payments").fetchone()[0] == 0
            """
        )

    def test_nonpreview_path_rejected(self):
        self.isolated(
            """
            from velopos import database
            from velopos_qt.transaction_policy import PreviewTransactionGate
            database.init_db()
            try:
                PreviewTransactionGate(database)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Nonpreview storage permitted")
            """, dirname="VeloPOS"
        )


if __name__ == "__main__":
    unittest.main()
