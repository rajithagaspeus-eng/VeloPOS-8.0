"""Launch the VeloPOS 8 Qt UI with persistent, isolated *preview-only* data.

Never use the production VeloPOS data directory or a caller-supplied
VELOPOS_HOME. Do not run this launcher inside the production POS process.
"""
import os
import sys
from pathlib import Path


def preview_data_dir(base=None):
    """Separate preview storage, never the production VeloPOS data folder."""
    base = Path(base if base is not None else (os.getenv("LOCALAPPDATA") or Path.home()))
    location = base / "VeloPOS8PreviewData"
    production = base / "VeloPOS"
    if os.path.normcase(os.path.realpath(location)) == os.path.normcase(os.path.realpath(production)):
        raise RuntimeError("Preview data directory must not be production VeloPOS.")
    return location


def main():
    if "velopos.database" in sys.modules:
        raise RuntimeError("Database already imported: cannot guarantee preview isolation.")
    location = preview_data_dir()
    location.mkdir(parents=True, exist_ok=True)
    # Override any ambient VELOPOS_HOME. Database must be imported afterward.
    os.environ["VELOPOS_HOME"] = str(location)
    from velopos import database
    if os.path.normcase(os.path.realpath(database.DATA_DIR)) != os.path.normcase(os.path.realpath(location)):
        raise RuntimeError("Refusing to run without a dedicated preview database.")
    database.init_db()
    from velopos_qt.app import run
    return run(database.settings, database=database)


if __name__ == "__main__":
    raise SystemExit(main())
