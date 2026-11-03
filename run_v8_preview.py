"""Run the VeloPOS 8 UI preview with a disposable SQLite database.

This command NEVER accesses the regular VeloPOS shop database.
"""
import os
import tempfile


def main():
    if "velopos.database" in __import__("sys").modules:
        raise RuntimeError("Database already imported; cannot guarantee safe data isolation.")
    with tempfile.TemporaryDirectory(prefix="velopos8_ui_preview_") as isolated:
        os.environ["VELOPOS_HOME"] = isolated
        from velopos import database
        database.init_db()
        from velopos_qt.app import run
        return run(database.settings)


if __name__ == "__main__":
    raise SystemExit(main())
