# VeloPOS 8.0 — Phase 0 baseline and migration plan

Status: **Initial static review completed; implementation and runtime validation pending.**

## Source and scope

- Base: `develop-v8` branch, preserving `main` as the original baseline.
- Inspected: `README.md`, `DEVELOPER_HANDOFF.md`, `requirements.txt`, `velopos/main.py`, `velopos/database.py`, `velopos/screens/settings.py`, `velopos/license.py`.
- Existing entry point: `run.py` -> `velopos.main.run`.
- Current desktop UI: CustomTkinter; proposed experimental modern UI: PySide6.
- Current persistent data: SQLite, with `VELOPOS_HOME` override and otherwise user-local `VeloPOS` data directory.

## Key observations

1. `SettingsScreen.__init__` creates a large scrollable form synchronously. It invokes `svc.list_printers()` during widget construction. These are **plausible** causes of slow first render, not measured root causes.
2. Business logic is documented as largely headless in `velopos/services.py`. Preserve that boundary and do not call long-running services from a GUI event handler.
3. Existing SQLite storage and database initialization must be preserved. Never run test or migration operations against a live shop database.
4. The existing license module verifies Ed25519 signatures. Do **not** regenerate key pairs or alter license checks as part of the UI migration.
5. Repository has a `tools/` directory. **Audit it for private signing keys, credentials, and issued license records before any redistribution.** Never include private material in installers, screenshots, or release archives.
6. README and developer handoff refer to earlier project phases; confirm the exact delivered baseline before labeling anything VeloPOS 8.0.

## Safe implementation sequence

### Phase 0A — baseline validation

- Record project structure and feature matrix.
- Ensure `.gitignore` excludes `.venv/`, `__pycache__/`, `*.pyc`, local `*.db` databases, backups, `*.pem` private keys, secrets and generated binaries. Review already tracked files separately: ignore rules do not remove tracked secrets.
- Create dedicated disposable `VELOPOS_HOME` for every test run.
- Run existing static, headless and GUI smoke tests; capture the results without implying a real Windows render test.
- Verify backup and restore on a **copy** of representative sample data.
- Record current Settings/Inventory/Reports timing on actual Windows hardware.

### Phase 1 — modern UI vertical slice

- Build a separate `velopos_qt/` experimental package without replacing the existing `run.py`.
- Check PySide6/Qt licensing obligations before distribution.
- Implement a real, functional Settings vertical slice: shop identity and appearance backed by existing settings APIs.
- Use native Qt model/view controls, bounded page construction, and signals/slots; background workers must never change widgets directly.
- Use dependency adapters so existing business logic remains available.
- Ensure the experimental UI uses a separate test data directory, not the real shop's live data.
- Compare measured startup, navigation and scroll performance to the old UI.

### Phase 2 onward

- Move billing, inventory, reports and remaining modules behind preserved service contracts, one validated feature at a time.
- Add business-specific optional modules, locale/currency support and optional offline-first cloud architecture only after the stable core is validated.
- Prepare licensing, installer, documentation, customer support and commercial readiness checks before sale.

## Release gates

- No destructive database migrations, overwriting of `main`, or production data access.
- Full functionality parity documented before old UI removal.
- Transactional integrity of billing, returns and stock changes verified.
- Tests executed and results recorded; no claims of zero bugs.
- Real Windows UI/device tests still required.
- Target countries' privacy, tax and pharmacy requirements must be checked individually.

## Immediate next task

**Implement the isolated PySide6 Settings prototype with existing settings service integration, automated tests and a safe test launcher.** Do not call it a completed commercial application.

Budget: **zero mandatory paid subscriptions/services**. Commercial redistribution obligations for dependencies still require review.
