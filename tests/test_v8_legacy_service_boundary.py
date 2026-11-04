"""Architecture guard against V8 UI calls into legacy financial services."""
import ast
from pathlib import Path
import unittest

from velopos_qt.service_authorization import _ACTION_ROLES
from velopos_qt.transaction_policy import PreviewTransactionGate
from velopos_qt.transaction_gateway import PreviewTransactionGateway


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "velopos_qt"
LEGACY_MUTATIONS = frozenset({
    "create_sale", "create_return", "void_sale", "create_purchase",
    "void_purchase", "pay_supplier", "settle_credit", "open_shift",
    "close_shift", "cash_move", "add_expense", "delete_expense",
    "adjust_stock", "finalize_count", "receive_batch", "repair_stock_ledger",
})
GATEWAY_ACTIONS = {
    "sale": "sale",
    "return_sale": "return",
    "purchase": "purchase",
    "supplier_payment": "supplier_payment",
    "credit_payment": "credit_payment",
    "redeem_points": "points_redemption",
    "open_shift": "shift_open",
    "close_shift": "shift_close",
    "print_receipt": "receipt_print",
    "void_sale": "sale_void",
    "void_purchase": "purchase_void",
    "cash_move": "cash_move",
    "add_expense": "expense_add",
    "delete_expense": "expense_delete",
    "adjust_stock": "stock_adjustment",
    "finalize_stock_take": "stock_take_finalize",
    "receive_batch": "batch_receive",
}


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return prefix + "." + node.attr if prefix else node.attr
    return None


def _legacy_calls(source):
    tree = ast.parse(source)
    service_prefixes = set()
    imported_mutations = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "velopos":
                    service_prefixes.add((alias.asname or "velopos") + ".services")
                elif alias.name == "velopos.services":
                    service_prefixes.add(alias.asname or "velopos.services")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "velopos":
                for alias in node.names:
                    if alias.name == "services":
                        service_prefixes.add(alias.asname or "services")
            elif node.module == "velopos.services":
                for alias in node.names:
                    if alias.name == "*":
                        imported_mutations.add("wildcard legacy service import")
                    elif alias.name in LEGACY_MUTATIONS:
                        imported_mutations.add(alias.asname or alias.name)

    found = set(imported_mutations)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in imported_mutations:
            found.add(node.func.id)
        path = _dotted(node.func)
        if path:
            tail = path.rsplit(".", 1)[-1]
            if tail in LEGACY_MUTATIONS and any(
                    path.startswith(prefix + ".") for prefix in service_prefixes):
                found.add(path)
        # Catch the common dynamic form getattr(services, "create_sale")(...).
        if (isinstance(node.func, ast.Name) and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in LEGACY_MUTATIONS):
            target = _dotted(node.args[0])
            if target and any(
                    target == prefix or target.startswith(prefix + ".")
                    for prefix in service_prefixes):
                found.add(target + "." + node.args[1].value)
    return found


class V8LegacyServiceBoundaryTests(unittest.TestCase):
    def test_v8_qt_modules_do_not_import_or_call_legacy_mutations(self):
        violations = []
        for path in sorted(APP_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for call in _legacy_calls(source):
                violations.append(f"{path.relative_to(ROOT)}: {call}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_deny_policy_and_gateway_cover_the_same_complete_action_set(self):
        self.assertEqual(set(PreviewTransactionGate.protected), set(_ACTION_ROLES))
        self.assertEqual(set(GATEWAY_ACTIONS.values()), set(_ACTION_ROLES))
        public_methods = {
            name for name in dir(PreviewTransactionGateway)
            if not name.startswith("_") and callable(getattr(PreviewTransactionGateway, name))
        }
        self.assertEqual(public_methods, set(GATEWAY_ACTIONS))

    def test_every_gateway_method_reaches_the_mandatory_deny_gate(self):
        source = (APP_ROOT / "transaction_gateway.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef)
                   and n.name == "PreviewTransactionGateway")
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        block = methods["_block"]
        self.assertTrue(any(
            isinstance(n, ast.Call) and _dotted(n.func) == "self._gate.require"
            for n in ast.walk(block)
        ))
        for method, action in GATEWAY_ACTIONS.items():
            calls = [
                n for n in ast.walk(methods[method])
                if isinstance(n, ast.Call) and _dotted(n.func) == "self._block"
            ]
            self.assertTrue(any(
                n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == action for n in calls
            ), f"{method} must route through the {action} deny gate")


if __name__ == "__main__":
    unittest.main()
