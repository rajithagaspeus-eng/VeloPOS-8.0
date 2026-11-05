"""Dependency-free contract tests for the V8 full regression launcher."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "run_v8_full_regression.py"


class FullRunnerContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tests").mkdir()
        shutil.copyfile(RUNNER, self.root / RUNNER.name)

    def stub(self, path, code):
        (self.root / path).write_text(code, encoding="utf-8")

    def gate(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / RUNNER.name), *args],
            cwd=self.root, capture_output=True, text=True, timeout=20,
        )

    def test_both_suites_share_isolated_home(self):
        self.stub("run_v8_checks.py", "import os,pathlib; p=pathlib.Path(os.environ['VELOPOS_HOME']); assert p.is_dir(); (p/'marker').write_text('ok')")
        self.stub("tests/run_all.py", "import os,pathlib; p=pathlib.Path(os.environ['VELOPOS_HOME']); assert (p/'marker').read_text()=='ok'; assert os.environ['QT_QPA_PLATFORM']=='offscreen'")
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FULL REGRESSION PASSED", result.stdout)

    def test_preview_failure_still_runs_legacy(self):
        self.stub("run_v8_checks.py", "raise SystemExit(7)")
        self.stub("tests/run_all.py", "from pathlib import Path; Path('legacy-ran').write_text('yes')")
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.root / "legacy-ran").exists())
        self.assertIn("V8 preview: FAIL", result.stdout)

    def test_legacy_failure_fails_closed(self):
        self.stub("run_v8_checks.py", "pass")
        self.stub("tests/run_all.py", "raise SystemExit(9)")
        result = self.gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Legacy application: FAIL", result.stdout)

    def test_missing_suite_fails_closed(self):
        self.stub("run_v8_checks.py", "pass")
        self.assertEqual(self.gate().returncode, 1)

    def test_timeout_fails_closed_and_continues(self):
        self.stub("run_v8_checks.py", "import time; time.sleep(3)")
        self.stub("tests/run_all.py", "from pathlib import Path; Path('legacy-ran').write_text('yes')")
        result = self.gate("--timeout", "1")
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.root / "legacy-ran").exists())
        self.assertIn("V8 preview: ERROR", result.stdout)

    def test_invalid_timeout_rejected(self):
        result = self.gate("--timeout", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be positive", result.stderr)


if __name__ == "__main__":
    unittest.main()
