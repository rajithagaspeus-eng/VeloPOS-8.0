"""Admin-only preview report reader tests with disposable database."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReportAccessTests(unittest.TestCase):
    def test_report_reader_respects_role_changes(self):
        script = (
            "from velopos import database\n"
            "from velopos_qt.reports_model import PreviewReportsReader\n"
            "database.init_db()\n"
            "role = {'admin': False}\n"
            "r = PreviewReportsReader(database, authorize=lambda: role['admin'])\n"
            "for operation in (lambda: r.snapshot('2026-11-01','2026-11-04'), r.staff_activity):\n"
            "    try:\n"
            "        operation()\n"
            "    except PermissionError:\n"
            "        pass\n"
            "    else:\n"
            "        raise AssertionError('Expected permission refusal')\n"
            "role['admin'] = True\n"
            "assert r.snapshot('2026-11-01','2026-11-04')['sale_count'] == 0\n"
            "role['admin'] = False\n"
            "try:\n"
            "    r.staff_activity()\n"
            "except PermissionError:\n"
            "    pass\n"
            "else:\n"
            "    raise AssertionError('Sign-out should revoke report access')\n"
        )
        with tempfile.TemporaryDirectory(prefix="v8_report_reader_") as folder:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(folder) / "VeloPOS8PreviewData")
            p = subprocess.run(
                [sys.executable, "-c", script], env=env,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
