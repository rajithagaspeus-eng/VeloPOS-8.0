"""TEST ONLY: customer-scoped credit charges and repayment declarations.

This is NOT a credit approval service, payment capture, receipt, debt
collection or commercial posting. All writes are restricted to disposable
VeloPOS8PreviewData and main.v8_preview_sandbox_* tables plus the test journal.
No legacy customers.credit_balance, credit_logs or sales are modified.

Only an existing, journal-completed sandbox invoice with NO declared cash,
card or QR tender may be linked to a sandbox credit account. Real returns for
credit-backed invoices remain blocked until credit-note rules are implemented.
"""
from dataclasses import dataclass
from hashlib import sha256

from .atomic_sale_boundary import PreviewAtomicSaleBoundary
from .auth_model import PreviewIdentity
from .combined_authorization import PreviewCombinedAuthorization
from .idempotency_ledger import PreviewIdempotencyLedger, request_fingerprint
from .product_editor import _guard
from .tender_plan import _money


@dataclass(frozen=True)
class SandboxCreditEvidence:
    reference: str
    customer_id: int
    amount_cents: int
    outstanding_cents: int
    replayed: bool
    sandbox_persisted: bool = True
    actual_payment_captured: bool = False
    real_customer_balance_changed: bool = False
    can_execute: bool = False
    can_checkout: bool = False


@dataclass(frozen=True)
class SandboxCreditAudit:
    balanced: bool
    reasons: tuple[str, ...]
    account_count: int
    total_charged_cents: int
    total_repayment_declared_cents: int
    total_outstanding_cents: int
    actual_payment_captured: bool = False
    can_checkout: bool = False


class PreviewSandboxCreditLedger:
    """Locked customer credit accounting *simulation*, never commercial use."""

    _FAILPOINTS = frozenset({"after_claim", "after_post", "after_complete"})

    def __init__(self, database, *, license_public_key_b64):
        _guard(database)
        self.database = database
        self.auth = PreviewCombinedAuthorization(
            database, public_key_b64=license_public_key_b64
        )
        self.journal = PreviewIdempotencyLedger(database)

    @staticmethod
    def _cents(value):
        amount = _money(value)
        return int(amount * 100)

    @staticmethod
    def _tables(connection):
        # executescript would commit the caller's SQLite transaction.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_credit_accounts ("
            "customer_id INTEGER PRIMARY KEY, branch_id TEXT NOT NULL, "
            "limit_cents INTEGER NOT NULL CHECK(limit_cents>0), "
            "active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_credit_charges ("
            "reference TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, "
            "invoice_ref TEXT NOT NULL UNIQUE, customer_id INTEGER NOT NULL, "
            "branch_id TEXT NOT NULL, amount_cents INTEGER NOT NULL "
            "CHECK(amount_cents>0))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS main.v8_preview_sandbox_credit_repayments ("
            "reference TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, "
            "customer_id INTEGER NOT NULL, branch_id TEXT NOT NULL, "
            "amount_cents INTEGER NOT NULL CHECK(amount_cents>0), "
            "method TEXT NOT NULL CHECK(method='Cash'))"
        )

    @staticmethod
    def _customer(customer_id):
        if type(customer_id) is not int or customer_id <= 0:
            raise ValueError("Positive persisted customer id required")
        return customer_id

    @staticmethod
    def _require_tables(connection, names):
        found = {row[0] for row in connection.execute(
            "SELECT name FROM main.sqlite_master WHERE type='table'"
        )}
        if not set(names).issubset(found):
            raise PermissionError("Required sandbox credit records unavailable")

    def _authorized(self, connection, *, identity, shift_id,
                    expected_branch_id, license_id, machine_id, license_key,
                    server_public_key_b64, previous_status, current_status,
                    today, now, max_offline_hours):
        actor = (
            PreviewIdentity(
                getattr(identity, "username", None),
                getattr(identity, "role", None),
                getattr(identity, "credential_tag", None)
            ) if identity is not None else None
        )
        decision = self.auth.inspect_with_activation_chain(
            connection, action="credit_payment", identity=actor,
            shift_id=shift_id, expected_branch_id=expected_branch_id,
            license_id=license_id, machine_id=machine_id,
            license_key=license_key,
            server_public_key_b64=server_public_key_b64,
            previous_status=previous_status, current_status=current_status,
            today=PreviewAtomicSaleBoundary._day(today),
            now=now, max_offline_hours=max_offline_hours,
        )
        if not decision.policy_consistent:
            raise PermissionError("Sandbox credit session/license/branch denied")
        return decision.authorization.actor, decision.authorization.role, (
            actor, PreviewAtomicSaleBoundary._day(today).isoformat()
        )

    def _balance(self, connection, customer_id):
        charged = connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM "
            "main.v8_preview_sandbox_credit_charges WHERE customer_id=?",
            (customer_id,)
        ).fetchone()[0]
        repaid = connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM "
            "main.v8_preview_sandbox_credit_repayments WHERE customer_id=?",
            (customer_id,)
        ).fetchone()[0]
        if (type(charged) is not int or type(repaid) is not int
                or repaid > charged or charged < 0):
            raise RuntimeError("Sandbox credit balance needs reconciliation")
        return charged - repaid

    def _account(self, connection, customer_id, branch):
        self._require_tables(connection, (
            "v8_preview_sandbox_credit_accounts",
            "v8_preview_sandbox_credit_charges",
            "v8_preview_sandbox_credit_repayments",
        ))
        account = connection.execute(
            "SELECT branch_id,limit_cents,active FROM "
            "main.v8_preview_sandbox_credit_accounts WHERE customer_id=?",
            (customer_id,)
        ).fetchone()
        if account is None or account["branch_id"] != branch or account["active"] != 1:
            raise PermissionError("Active customer credit account not in branch")
        original = connection.execute(
            "SELECT id FROM main.customers WHERE id=?", (customer_id,)
        ).fetchone()
        if original is None:
            raise PermissionError("Persisted customer no longer exists")
        return account

    def open_test_account(self, *, customer_id, credit_limit, identity,
                          shift_id, expected_branch_id, license_id, machine_id,
                          license_key, server_public_key_b64, previous_status,
                          current_status, today=None, now=None,
                          max_offline_hours=24):
        """One-time Admin-only sandbox limit registration, no V7 balance write.

        Repeating the SAME account+limit is idempotent. Any different limit
        requires a future audited Admin amendment protocol, not silent UPDATE.
        """
        self._customer(customer_id)
        limit = self._cents(credit_limit)
        _guard(self.database)
        c = self.database.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            actor, role, _ = self._authorized(
                c, identity=identity, shift_id=shift_id,
                expected_branch_id=expected_branch_id, license_id=license_id,
                machine_id=machine_id, license_key=license_key,
                server_public_key_b64=server_public_key_b64,
                previous_status=previous_status, current_status=current_status,
                today=today, now=now, max_offline_hours=max_offline_hours,
            )
            if role != "Admin":
                raise PermissionError("Only verified Admin can set sandbox credit limits")
            if c.execute(
                "SELECT 1 FROM main.customers WHERE id=?", (customer_id,)
            ).fetchone() is None:
                raise PermissionError("Persisted customer required")
            self._tables(c)
            existing = c.execute(
                "SELECT branch_id,limit_cents FROM "
                "main.v8_preview_sandbox_credit_accounts WHERE customer_id=?",
                (customer_id,)
            ).fetchone()
            if existing is not None:
                if existing["branch_id"] != expected_branch_id or existing["limit_cents"] != limit:
                    raise PermissionError("Sandbox credit limit/branch is immutable")
                c.rollback()
                return limit
            c.execute(
                "INSERT INTO main.v8_preview_sandbox_credit_accounts "
                "(customer_id,branch_id,limit_cents) VALUES (?,?,?)",
                (customer_id,expected_branch_id,limit)
            )
            c.commit()
            return limit
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def attach_unpaid_invoice(self, *, customer_id, invoice_ref, request_id,
                              identity, shift_id, expected_branch_id, license_id,
                              machine_id, license_key, server_public_key_b64,
                              previous_status, current_status, today=None,
                              now=None, max_offline_hours=24,
                              inject_failure_at=None):
        """Declare credit for an unpaid sandbox invoice; exact-once and limited."""
        self._customer(customer_id)
        self.journal._validate_identity("credit_charge", request_id)
        if (type(invoice_ref) is not str or len(invoice_ref) != 28
                or not invoice_ref.startswith("SBX-")):
            raise ValueError("Original sandbox invoice reference required")
        if inject_failure_at is not None and inject_failure_at not in self._FAILPOINTS:
            raise ValueError("Invalid credit failpoint")
        _guard(self.database)
        c = self.database.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            actor, role, (frozen_actor, day) = self._authorized(
                c, identity=identity, shift_id=shift_id,
                expected_branch_id=expected_branch_id, license_id=license_id,
                machine_id=machine_id, license_key=license_key,
                server_public_key_b64=server_public_key_b64,
                previous_status=previous_status, current_status=current_status,
                today=today, now=now, max_offline_hours=max_offline_hours,
            )
            account = self._account(c, customer_id, expected_branch_id)
            self._require_tables(c, (
                "v8_preview_sandbox_sales", "v8_preview_sandbox_settlements",
                "v8_preview_request_journal",
            ))
            sale = c.execute(
                "SELECT request_id,branch_id,subtotal_cents FROM "
                "main.v8_preview_sandbox_sales WHERE reference=?",
                (invoice_ref,)
            ).fetchone()
            if sale is None or sale["branch_id"] != expected_branch_id:
                raise PermissionError("Sandbox invoice not in authorized branch")
            if sale["subtotal_cents"] <= 0:
                raise PermissionError("Invoice has no credit-eligible amount")
            original = c.execute(
                "SELECT status,result_ref FROM main.v8_preview_request_journal "
                "WHERE scope='sale' AND request_id=?", (sale["request_id"],)
            ).fetchone()
            if original is None or original["status"] != "COMPLETED" or original["result_ref"] != invoice_ref:
                raise PermissionError("Unverified original sandbox invoice journal")
            settlement = c.execute(
                "SELECT declared,cash_cents,noncash_cents,change_cents,due_cents "
                "FROM main.v8_preview_sandbox_settlements WHERE reference=?",
                (invoice_ref,)
            ).fetchone()
            if (settlement is None or settlement["declared"] != 0
                    or any(settlement[field] != 0 for field in
                           ("cash_cents","noncash_cents","change_cents"))
                    or settlement["due_cents"] != sale["subtotal_cents"]):
                raise PermissionError("Only wholly unpaid, non-tendered sandbox invoices may be charged")
            # Credit-note/refund adjustment against credit balance is not yet
            # defined. Refuse a previously returned invoice, not a guess.
            names = {row[0] for row in c.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table'"
            )}
            if "v8_preview_sandbox_returns" in names and c.execute(
                "SELECT 1 FROM main.v8_preview_sandbox_returns "
                "WHERE original_ref=?", (invoice_ref,)
            ).fetchone() is not None:
                raise PermissionError("Returned invoices require credit-note policy")
            payload = {
                "v":1, "action":"sandbox_credit_charge", "request_id":request_id,
                "customer_id":customer_id, "invoice_ref":invoice_ref,
                "amount_cents":sale["subtotal_cents"],
                "actor":actor, "branch_id":expected_branch_id,
                "shift_id":shift_id, "license_id":license_id,
                "machine_id":machine_id, "day":day,
            }
            fingerprint = request_fingerprint(payload)
            ref = "CRC-" + sha256(
                (request_id + ":" + fingerprint).encode("utf-8")
            ).hexdigest()[:24]
            journal = self.journal.inspect_request(
                c, "credit_charge", request_id, payload
            )
            existing = c.execute(
                "SELECT reference,request_id,customer_id,amount_cents FROM "
                "main.v8_preview_sandbox_credit_charges WHERE invoice_ref=?",
                (invoice_ref,)
            ).fetchone()
            if journal.state == "journal_completed_unverified":
                if (existing is None or existing["reference"] != ref
                        or existing["request_id"] != request_id
                        or existing["customer_id"] != customer_id
                        or existing["amount_cents"] != sale["subtotal_cents"]
                        or journal.result_ref != ref):
                    raise RuntimeError("Sandbox credit charge replay needs reconciliation")
                balance = self._balance(c, customer_id)
                c.rollback()
                return SandboxCreditEvidence(ref,customer_id,sale["subtotal_cents"],balance,True)
            if journal.state != "not_recorded":
                raise PermissionError("Sandbox credit charge journal needs reconciliation")
            if existing is not None:
                raise PermissionError("Invoice already assigned to another credit request")
            remaining = self._balance(c, customer_id)
            amount = sale["subtotal_cents"]
            if remaining + amount > account["limit_cents"]:
                raise PermissionError("Customer sandbox credit limit exceeded")
            claim = self.journal.claim(c,"credit_charge",request_id,payload)
            if not claim.is_new:
                raise RuntimeError("Unexpected credit-charge request replay")
            if inject_failure_at == "after_claim":
                raise RuntimeError("Injected credit failure after claim")
            c.execute(
                "INSERT INTO main.v8_preview_sandbox_credit_charges "
                "(reference,request_id,invoice_ref,customer_id,branch_id,amount_cents) "
                "VALUES (?,?,?,?,?,?)",
                (ref,request_id,invoice_ref,customer_id,expected_branch_id,amount)
            )
            if inject_failure_at == "after_post":
                raise RuntimeError("Injected credit failure after post")
            self.journal.complete(c,"credit_charge",request_id,ref)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected credit failure after complete")
            c.commit()
            return SandboxCreditEvidence(ref,customer_id,amount,remaining+amount,False)
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def declare_repayment(self, *, customer_id, amount, method="Cash", request_id,
                          identity, shift_id, expected_branch_id, license_id,
                          machine_id, license_key, server_public_key_b64,
                          previous_status, current_status, today=None, now=None,
                          max_offline_hours=24, inject_failure_at=None):
        """Declare a cash repayment, NOT receipt of money; cannot overpay debt."""
        self._customer(customer_id)
        cents = self._cents(amount)
        self.journal._validate_identity("credit_payment",request_id)
        if type(method) is not str or method != "Cash":
            raise PermissionError("Only unverified Cash repayment declaration supported")
        if inject_failure_at is not None and inject_failure_at not in self._FAILPOINTS:
            raise ValueError("Invalid repayment failure point")
        _guard(self.database)
        c = self.database.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            actor, role, (frozen_actor, day) = self._authorized(
                c, identity=identity, shift_id=shift_id,
                expected_branch_id=expected_branch_id, license_id=license_id,
                machine_id=machine_id, license_key=license_key,
                server_public_key_b64=server_public_key_b64,
                previous_status=previous_status, current_status=current_status,
                today=today, now=now, max_offline_hours=max_offline_hours,
            )
            self._account(c,customer_id,expected_branch_id)
            payload = {
                "v":1, "action":"sandbox_credit_repayment",
                "customer_id":customer_id, "amount_cents":cents,
                "method":"Cash", "actor":actor,
                "branch_id":expected_branch_id, "shift_id":shift_id,
                "license_id":license_id, "machine_id":machine_id,"day":day,
            }
            fingerprint = request_fingerprint(payload)
            ref = "CRP-" + sha256(
                (request_id + ":" + fingerprint).encode("utf-8")
            ).hexdigest()[:24]
            journal = self.journal.inspect_request(
                c,"credit_payment",request_id,payload
            )
            if journal.state == "journal_completed_unverified":
                row = c.execute(
                    "SELECT customer_id,branch_id,amount_cents,method "
                    "FROM main.v8_preview_sandbox_credit_repayments "
                    "WHERE reference=? AND request_id=?",
                    (ref,request_id)
                ).fetchone()
                if (journal.result_ref != ref or row is None
                        or row["customer_id"] != customer_id
                        or row["branch_id"] != expected_branch_id
                        or row["amount_cents"] != cents or row["method"] != method):
                    raise RuntimeError("Sandbox repayment replay needs reconciliation")
                remaining = self._balance(c,customer_id)
                c.rollback()
                return SandboxCreditEvidence(ref,customer_id,cents,remaining,True)
            if journal.state != "not_recorded":
                raise PermissionError("Prior sandbox repayment requires reconciliation")
            outstanding = self._balance(c,customer_id)
            if cents > outstanding:
                raise PermissionError("Repayment exceeds outstanding sandbox credit")
            claim = self.journal.claim(c,"credit_payment",request_id,payload)
            if not claim.is_new:
                raise RuntimeError("Unexpected repayment replay")
            if inject_failure_at == "after_claim":
                raise RuntimeError("Injected credit failure after claim")
            c.execute(
                "INSERT INTO main.v8_preview_sandbox_credit_repayments "
                "(reference,request_id,customer_id,branch_id,amount_cents,method) "
                "VALUES (?,?,?,?,?,?)",
                (ref,request_id,customer_id,expected_branch_id,cents,method)
            )
            if inject_failure_at == "after_post":
                raise RuntimeError("Injected credit failure after post")
            self.journal.complete(c,"credit_payment",request_id,ref)
            if inject_failure_at == "after_complete":
                raise RuntimeError("Injected credit failure after complete")
            c.commit()
            return SandboxCreditEvidence(ref,customer_id,cents,outstanding-cents,False)
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def reconcile(self):
        """Read-only audit of customer accounts, invoice bindings and journals."""
        _guard(self.database)
        c = self.database.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            self.journal._check_connection(c)
            names = {row[0] for row in c.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table'"
            )}
            required = {
                "v8_preview_sandbox_credit_accounts",
                "v8_preview_sandbox_credit_charges",
                "v8_preview_sandbox_credit_repayments",
                "v8_preview_sandbox_sales",
                "v8_preview_sandbox_settlements",
                "v8_preview_request_journal",
            }
            if not required.issubset(names):
                return SandboxCreditAudit(
                    False,("sandbox_credit_schema_missing",),0,0,0,0
                )
            issues = []
            accounts = {
                row["customer_id"]:row for row in c.execute(
                    "SELECT customer_id,branch_id,limit_cents,active "
                    "FROM main.v8_preview_sandbox_credit_accounts"
                )
            }
            charges = c.execute(
                "SELECT reference,request_id,invoice_ref,customer_id,"
                "branch_id,amount_cents FROM main.v8_preview_sandbox_credit_charges"
            ).fetchall()
            payments = c.execute(
                "SELECT reference,request_id,customer_id,branch_id,"
                "amount_cents,method FROM main.v8_preview_sandbox_credit_repayments"
            ).fetchall()
            totals = {customer_id:[0,0] for customer_id in accounts}
            charge_refs = {row["reference"] for row in charges}
            payment_refs = {row["reference"] for row in payments}
            for row in charges:
                cid = row["customer_id"]
                account = accounts.get(cid)
                if (account is None or account["branch_id"] != row["branch_id"]):
                    issues.append("credit_charge_branch_mismatch")
                invoice = c.execute(
                    "SELECT request_id,branch_id,subtotal_cents "
                    "FROM main.v8_preview_sandbox_sales WHERE reference=?",
                    (row["invoice_ref"],)
                ).fetchone()
                settlement = c.execute(
                    "SELECT declared,cash_cents,noncash_cents,change_cents "
                    "FROM main.v8_preview_sandbox_settlements WHERE reference=?",
                    (row["invoice_ref"],)
                ).fetchone()
                if (invoice is None or invoice["branch_id"] != row["branch_id"]
                        or invoice["subtotal_cents"] != row["amount_cents"]
                        or settlement is None or settlement["declared"] != 0
                        or any(settlement[x] for x in (
                            "cash_cents","noncash_cents","change_cents"
                        ))):
                    issues.append("credit_invoice_link_mismatch")
                else:
                    sale_journal = c.execute(
                        "SELECT status,result_ref FROM main.v8_preview_request_journal "
                        "WHERE scope='sale' AND request_id=?", (invoice["request_id"],)
                    ).fetchone()
                    if (sale_journal is None or sale_journal["status"] != "COMPLETED"
                            or sale_journal["result_ref"] != row["invoice_ref"]):
                        issues.append("credit_invoice_journal_mismatch")
                journal = c.execute(
                    "SELECT status,result_ref FROM main.v8_preview_request_journal "
                    "WHERE scope='credit_charge' AND request_id=?",
                    (row["request_id"],)
                ).fetchone()
                if (journal is None or journal["status"] != "COMPLETED"
                        or journal["result_ref"] != row["reference"]):
                    issues.append("credit_charge_journal_mismatch")
                totals.setdefault(cid,[0,0])[0] += row["amount_cents"]
            for row in payments:
                cid = row["customer_id"]
                account = accounts.get(cid)
                if (account is None or account["branch_id"] != row["branch_id"]
                        or row["method"] != "Cash"):
                    issues.append("credit_payment_account_mismatch")
                journal = c.execute(
                    "SELECT status,result_ref FROM main.v8_preview_request_journal "
                    "WHERE scope='credit_payment' AND request_id=?",
                    (row["request_id"],)
                ).fetchone()
                if (journal is None or journal["status"] != "COMPLETED"
                        or journal["result_ref"] != row["reference"]):
                    issues.append("credit_payment_journal_mismatch")
                totals.setdefault(cid,[0,0])[1] += row["amount_cents"]
            for cid, (charged, repaid) in totals.items():
                account = accounts.get(cid)
                if (account is None or charged < 0 or repaid < 0
                        or repaid > charged):
                    issues.append("credit_balance_invalid")
                elif (charged - repaid > account["limit_cents"]):
                    issues.append("credit_limit_exceeded")
            for scope, refs in (("credit_charge",charge_refs),
                                ("credit_payment",payment_refs)):
                for journal in c.execute(
                    "SELECT status,result_ref FROM main.v8_preview_request_journal "
                    "WHERE scope=?", (scope,)
                ):
                    if journal["status"] != "COMPLETED" or journal["result_ref"] not in refs:
                        issues.append("orphan_credit_journal")
            charged = sum(row["amount_cents"] for row in charges)
            repaid = sum(row["amount_cents"] for row in payments)
            return SandboxCreditAudit(
                not issues,tuple(dict.fromkeys(issues)),len(accounts),
                charged,repaid,charged-repaid
            )
        finally:
            c.rollback()
            c.close()

    def require_real_credit(self, **_kwargs):
        raise PermissionError(
            "Sandbox customer credit and repayment declarations are not commercial payments"
        )
