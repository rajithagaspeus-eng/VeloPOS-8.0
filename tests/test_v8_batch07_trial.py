"""Batch 07: trial continuity regression cases with NO network calls or real license mutations.

Mocks never touch the real signing key, registry, cache or customer database.
They exercise the existing trial decision logic in a fresh process.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class TrialContinuityTests(unittest.TestCase):
    def run_case(self, script):
        with tempfile.TemporaryDirectory(prefix="v8_trial_test_") as root:
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(Path(root) / "VeloPOS8PreviewData")
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(script)],
                env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_remote_first_seen_prevents_simple_local_reset(self):
        self.run_case(
            """
            from datetime import date, timedelta
            from velopos import license as lic
            from velopos.branding import TRIAL_DAYS
            saved = []
            lic.machine_id = lambda: "POS-PREVIEW"
            lic._load_key = lambda: ""
            lic._read_raw = lambda: []
            lic._write_all = lambda state: saved.append(state)
            lic._remote_first_seen = lambda mid: (
                date.today() - timedelta(days=TRIAL_DAYS + 2)
            ).isoformat()
            status, days, mid = lic.check_status()
            assert status == "EXPIRED" and days == 0 and mid == "POS-PREVIEW"
            assert saved
            decoded = lic._unseal(saved[-1], "POS-PREVIEW")
            assert decoded["i"] == (date.today() -
                                   timedelta(days=TRIAL_DAYS + 2)).isoformat()
            """,
        )

    def test_clock_rollback_tampering_is_rejected(self):
        self.run_case(
            """
            from datetime import date, timedelta
            from velopos import license as lic
            mid = "POS-PREVIEW"
            lic.machine_id = lambda: mid
            lic._load_key = lambda: ""
            lic._remote_first_seen = lambda _: None
            previous = {
                "i": (date.today() - timedelta(days=3)).isoformat(),
                "l": (date.today() + timedelta(days=4)).isoformat(),
            }
            lic._read_raw = lambda: [lic._seal(previous, mid)]
            lic._write_all = lambda state: (_ for _ in ()).throw(
                AssertionError("Tampered state must never be written")
            )
            assert lic.check_status()[:2] == ("TAMPERED", 0)
            """,
        )

    def test_corrupted_local_store_is_not_clean_trial(self):
        self.run_case(
            """
            from velopos import license as lic
            lic.machine_id = lambda: "POS-PREVIEW"
            lic._load_key = lambda: ""
            lic._read_raw = lambda: ["damaged-state"]
            lic._remote_first_seen = lambda _: None
            assert lic.check_status()[:2] == ("TAMPERED", 0)
            """,
        )


if __name__ == "__main__":
    unittest.main()
