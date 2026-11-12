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
        for action in ("checkout", "unknown_action", "", None, 7):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    assess_commercial_boundary(action)
        for evidence in ([], "verified", {"secret_bypass": True}, {1: True}):
            with self.subTest(evidence=type(evidence).__name__):
                with self.assertRaises(ValueError):
                    assess_commercial_boundary("sale", evidence)

    def test_financial_mutations_require_action_specific_accounting_proofs(self):
        expectations = {
            "credit_payment": ("customer_revalidation", "receivable_reconciliation",
                               "tender_reconciliation"),
            "supplier_payment": ("supplier_revalidation", "payable_reconciliation",
                                 "tender_reconciliation"),
            "sale_void": ("original_invoice", "reversal_reconciliation",
                          "stock_revalidation"),
            "stock_adjustment": ("stock_revalidation", "batch_reconciliation",
                                 "audit_reason"),
        }
        for action, required in expectations.items():
            with self.subTest(action=action):
                assessment = assess_commercial_boundary(action)
                self.assertTrue(set(required).issubset(assessment.required_proofs))
                self.assertIn("atomic_commit", assessment.required_proofs)
                self.assertIn("idempotent_recovery", assessment.required_proofs)
                self.assertFalse(assessment.can_execute)
                forged = assess_commercial_boundary(
                    action, dict.fromkeys(assessment.required_proofs, True)
                )
                self.assertFalse(forged.production_ready)
                self.assertEqual(forged.unverified_proofs, assessment.required_proofs)

    def test_assessment_is_immutable(self):
        result = assess_commercial_boundary("sale")
        with self.assertRaises(FrozenInstanceError):
            result.can_execute = True


if __name__ == "__main__":
    unittest.main()
