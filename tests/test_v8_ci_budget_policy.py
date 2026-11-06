"""Dependency-free contract: V8 verification must not consume hosted CI on pushes.

Owner opted for zero-spend, manual-only GitHub Actions while the free allowance
is exhausted. A manual invocation is deliberately still available for a future
approved, funded/eligible run. This is policy protection, not execution proof.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    "v8-preview-tests.yml",
    "v8-preview-windows.yml",
    "v8-sandbox-regression.yml",
    "v8-runner-diagnostic.yml",
)


def workflow_events(source):
    """Read only top-level GitHub event keys; do not require PyYAML.

    Reject malformed/missing event blocks rather than implying CI is disabled.
    """
    match = re.search(r"(?m)^on:\s*\n((?:[ \t]+[^\n]*\n|\s*\n)*)", source)
    if match is None:
        raise ValueError("Missing explicit top-level on: event mapping")
    block = match.group(1)
    events = re.findall(r"(?m)^  ([a-z][a-z0-9_]*)\s*:", block)
    if not events:
        raise ValueError("No explicitly configured GitHub Actions events")
    return events


class ZeroSpendActionsPolicyTests(unittest.TestCase):
    def test_all_v8_workflows_are_manual_only(self):
        for name in WORKFLOWS:
            with self.subTest(workflow=name):
                content = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
                self.assertEqual(workflow_events(content), ["workflow_dispatch"],
                                 f"{name} would run without owner-initiated dispatch")

    def test_manual_jobs_are_restricted_to_develop_v8(self):
        for name in WORKFLOWS:
            with self.subTest(workflow=name):
                content = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
                self.assertIn("if: github.ref == 'refs/heads/develop-v8'", content)

    def test_parser_rejects_missing_or_empty_events(self):
        for invalid in ("name: no trigger\n", "on:\n\njobs:\n  example:\n"):
            with self.subTest(source=invalid):
                with self.assertRaises(ValueError):
                    workflow_events(invalid)

    def test_parser_detects_accidental_push_trigger(self):
        self.assertEqual(workflow_events("on:\n  push:\n  workflow_dispatch:\n\njobs:\n"),
                         ["push", "workflow_dispatch"])


if __name__ == "__main__":
    unittest.main()
