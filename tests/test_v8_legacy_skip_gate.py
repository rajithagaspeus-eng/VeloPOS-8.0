"""Dependency-free coverage for strict legacy no-skips regression acceptance."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "tests" / "run_all.py"


class LegacySkipAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v8_legacy_skip_contract_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        shutil.copyfile(RUNNER, self.root / "tests" / "run_all.py")
        for name in ("check_static.py", "gui_smoke.py"):
            (self.root / "tests" / name).write_text("pass\n", encoding="utf-8")

    def suite(self, source, *args):
        (self.root / "tests" / "test_sample.py").write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(self.root / "tests" / "run_all.py"), *args],
            cwd=self.root, capture_output=True, text=True, timeout=15,
        )

    def test_strict_mode_rejects_successful_unittest_with_skip(self):
        result = self.suite(
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    @unittest.skip('missing dependency')\n"
            "    def test_not_executed(self): pass\n",
            "--fail-on-skips",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 skipped", result.stdout)
        self.assertIn("REPORTED UNITTEST SKIPS: 1", result.stdout)
        self.assertIn("JOB(S) FAILED", result.stdout)

    def test_strict_mode_accepts_executed_non_skipped_test(self):
        result = self.suite(
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_executed(self): self.assertEqual(2 + 2, 4)\n",
            "--fail-on-skips",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REPORTED UNITTEST SKIPS: 0", result.stdout)
        self.assertIn("ALL PASSED", result.stdout)

    def test_default_legacy_mode_does_not_change_historical_contract(self):
        result = self.suite(
            "import unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    @unittest.skip('historical skip')\n"
            "    def test_not_executed(self): pass\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REPORTED UNITTEST SKIPS: 1", result.stdout)


    def test_hung_unittest_is_a_failure_and_later_checks_still_run(self):
        result = self.suite(
            "import time,unittest\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_hangs(self): time.sleep(3)\n",
            "--fail-on-skips", "--job-timeout", "1",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("timed out", result.stdout)
        self.assertIn("FAILED (subprocess timed out)", result.stdout)
        self.assertNotIn("UnboundLocalError", result.stdout)
        self.assertIn("TIMEOUT: job exceeded 1s", result.stdout)
        self.assertIn("check_static", result.stdout)
        self.assertIn("gui_smoke", result.stdout)
        self.assertIn("JOB(S) FAILED", result.stdout)

    def test_empty_unittest_module_fails_closed(self):
        result = self.suite("pass\n", "--fail-on-skips")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no tests executed", result.stdout)
        self.assertIn("JOB(S) FAILED", result.stdout)

    def test_nonpositive_job_timeout_is_rejected(self):
        result = self.suite("pass\n", "--job-timeout", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--job-timeout must be positive", result.stderr)


if __name__ == "__main__":
    unittest.main()
