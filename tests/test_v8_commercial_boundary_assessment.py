"""Commercial boundary proof inventory never authorizes financial posting."""
import unittest
from dataclasses import FrozenInstanceError

from velopos_qt.commercial_boundary_assessment import assess_commercial_boundary


class CommercialBoundaryAssessmentTests(unittest.TestCase):
    def test_missing_proofs_are_reported_without_authorization(self):
        for action in ("sale", "return", "purchase"):
            with self.subTest(action=action):
                result = assess_commercial_boundary(action)
                self.assertEqual(result.missing_proofs, result.required_proofs)
                self.assertFalse(result.can_execute)
                self.assertFalse(result.production_ready)
                self.assertEqual(result.unverified_proofs, ())

    def test_all_forged_proofs_remain_unverified_and_denied(self):
        for action in ("sale", "return", "purchase"):
            required = assess_commercial_boundary(action).required_proofs
            for forged in (True, "verified", {"signed": True}, object()):
                with self.subTest(action=action, forged=type(forged).__name__):
                    result = assess_commercial_boundary(
                        action, {key: forged for key in required}
                    )
                    self.assertEqual(result.missing_proofs, ())
                    self.assertEqual(result.unverified_proofs, required)
                    self.assertFalse(result.can_execute)
                    self.assertFalse(result.production_ready)

    def test_unknown_actions_and_proof_keys_are_rejected(self):
        for action in ("checkout", "sale_void", "", None, 7):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    assess_commercial_boundary(action)
        for evidence in ([], "verified", {"secret_bypass": True}, {1: True}):
            with self.subTest(evidence=type(evidence).__name__):
                with self.assertRaises(ValueError):
                    assess_commercial_boundary("sale", evidence)

    def test_assessment_is_immutable(self):
        result = assess_commercial_boundary("sale")
        with self.assertRaises(FrozenInstanceError):
            result.can_execute = True


if __name__ == "__main__":
    unittest.main()
