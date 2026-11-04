"""Run the entire VeloPOS 8 preview regression suite with one short command.

Usage:
    python run_v8_checks.py
    python run_v8_checks.py --verbose

Only tests matching test_v8_*.py are collected. Other legacy POS tests are
intentionally not mixed into this fast preview gate. No production launch.
"""
import argparse
import os
import sys
import unittest
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="VeloPOS 8 combined preview checks")
    parser.add_argument("--verbose", action="store_true",
                        help="print every test instead of a compact summary")
    args = parser.parse_args(argv)

    # Must precede importing any PySide6 test modules; no Windows UI appears.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(root / "tests"),
        pattern="test_v8_*.py",
        top_level_dir=str(root),
    )
    discovered = suite.countTestCases()
    print("VeloPOS 8 | Combined preview checks | test data only", flush=True)
    print(f"Discovered V8 tests: {discovered}", flush=True)
    # A renamed/missing tests directory must never produce a green CI gate.
    if discovered == 0:
        print("ERROR: No V8 preview tests discovered; refusing green CI.", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        stream=sys.stdout,
    ).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
