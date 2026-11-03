"""Preview storage regression tests. No production database access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from run_v8_preview import preview_data_dir


class PreviewStorageTests(unittest.TestCase):
    def test_preview_path_distinct_from_production(self):
        with tempfile.TemporaryDirectory() as base:
            expected = Path(base) / "VeloPOS8PreviewData"
            self.assertEqual(preview_data_dir(base), expected)
            self.assertNotEqual(expected, Path(base) / "VeloPOS")

    def test_preview_database_survives_restart_and_skips_live_data(self):
        """Separate Python processes simulate exiting and reopening the preview."""
        with tempfile.TemporaryDirectory(prefix="velopos8_storage_test_") as base:
            directory = preview_data_dir(base)
            directory.mkdir()
            live = Path(base) / "VeloPOS"
            live.mkdir()
            sentinel = live / "DO_NOT_TOUCH.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            env = os.environ.copy()
            env["VELOPOS_HOME"] = str(directory)

            write_code = (
                "from velopos import database as db; "
                "db.init_db(); "
                "db.settings.set_many({'paper_size': 'A5', "
                "'print_copies': '2', 'shop_name': 'Preview Demo'})"
            )
            read_code = (
                "from velopos import database as db; "
                "db.init_db(); "
                "assert db.settings.get('paper_size') == 'A5'; "
                "assert db.settings.get('print_copies') == '2'; "
                "assert db.settings.get('shop_name') == 'Preview Demo'"
            )
            root = str(Path(__file__).resolve().parents[1])
            for snippet in (write_code, read_code):
                subprocess.run(
                    [sys.executable, "-c", snippet],
                    env=env, cwd=root, check=True, capture_output=True, text=True,
                    timeout=25,
                )
            self.assertTrue((directory / "velopos.db").is_file())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse((live / "velopos.db").exists())


if __name__ == "__main__":
    unittest.main()
