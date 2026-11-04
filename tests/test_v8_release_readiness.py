"""Release-readiness reports must never be mistaken for checkout permission."""
import json
import subprocess
import sys
import unittest

from velopos_qt.release_readiness import release_readiness, release_readiness_report


class ReleaseReadinessTests(unittest.TestCase):
    def test_all_commercial_gates_remain_blocked(self):
        report = release_readiness_report()
        self.assertEqual(report["branch"], "develop-v8")
        self.assertTrue(report["preview_only"])
        self.assertFalse(report["can_checkout"])
        self.assertFalse(report["production_ready"])
        self.assertEqual({gate["key"] for gate in report["gates"]},
                         {"A", "B", "C", "D", "E"})
        self.assertEqual(report["gate_counts"]["total"], 5)
        self.assertEqual(report["gate_counts"]["passed"], 0)
        self.assertEqual(report["gate_counts"]["blocked"], 2)
        self.assertEqual(report["gate_counts"]["not_ready"], 3)
        self.assertTrue(all(gate["outstanding"] for gate in report["gates"]))

    def test_immutable_gate_definitions_and_fresh_serialization(self):
        first = release_readiness()
        self.assertIsInstance(first, tuple)
        with self.assertRaises((AttributeError, TypeError)):
            first[0].status = "PASSED"
        report = release_readiness_report()
        report["gates"][0]["status"] = "PASSED"
        report["gates"][0]["outstanding"] = []
        self.assertEqual(release_readiness_report()["gates"][0]["status"],
                         "BLOCKED")
        self.assertTrue(release_readiness_report()["gates"][0]["outstanding"])

    def test_cli_json_can_be_consumed_by_release_checks(self):
        result = subprocess.run(
            [sys.executable, "-m", "velopos_qt.release_readiness"],
            capture_output=True, text=True, timeout=20, check=True,
        )
        payload = json.loads(result.stdout)
        self.assertFalse(payload["production_ready"])
        self.assertFalse(payload["can_checkout"])
        self.assertEqual(payload["gate_counts"]["passed"], 0)


if __name__ == "__main__":
    unittest.main()
