"""CI gate self-tests: missing test discovery must fail closed.

No POS database, production data, Qt or external services required.
"""
import contextlib
import io
import unittest
from unittest.mock import patch

import run_v8_checks


class V8CheckRunnerTests(unittest.TestCase):
    def test_zero_discovered_tests_cannot_pass(self):
        with patch.object(
            run_v8_checks.unittest.defaultTestLoader,
            "discover",
            return_value=unittest.TestSuite(),
        ):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = run_v8_checks.main([])
        self.assertEqual(code, 1)

    def test_discovered_successful_test_can_pass(self):
        class Passing(unittest.TestCase):
            def runTest(self):
                self.assertTrue(True)

        nested = unittest.TestSuite([unittest.TestSuite([Passing()])])
        with patch.object(
            run_v8_checks.unittest.defaultTestLoader,
            "discover",
            return_value=nested,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                code = run_v8_checks.main([])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
