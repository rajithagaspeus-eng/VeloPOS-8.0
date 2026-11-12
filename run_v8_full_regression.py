"""Run both V8 preview checks and legacy application regressions.

This script never launches commercial checkout. Use a disposable VELOPOS_HOME.
Exit nonzero if either suite fails, times out, or cannot start.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description="VeloPOS full regression gate")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="per-suite timeout in seconds (default: 1800)")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    root = Path(__file__).resolve().parent
    commands = [
        ("V8 preview", [sys.executable, "run_v8_checks.py", "--verbose"]),
        ("Legacy application", [sys.executable, "tests/run_all.py", "--fail-on-skips"]),
    ]
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Never allow inherited real customer paths into test subprocesses.
    for name in ("VELOPOS_DB", "VELOPOS_DATABASE", "VELOPOS_DATA_DIR",
                 "VELOPOS_PRODUCTION_HOME"):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="velopos-full-regression-") as home:
        env["VELOPOS_HOME"] = home
        failures = []
        for label, command in commands:
            print(f"=== {label}: START ===", flush=True)
            try:
                completed = subprocess.run(
                    command, cwd=root, env=env, timeout=args.timeout,
                    check=False,
                )
                passed = completed.returncode == 0
                print(f"=== {label}: {'PASS' if passed else 'FAIL'} "
                      f"(exit {completed.returncode}) ===", flush=True)
            except (subprocess.TimeoutExpired, OSError) as exc:
                passed = False
                print(f"=== {label}: ERROR {exc} ===", flush=True)
            if not passed:
                failures.append(label)
        if failures:
            print("FULL REGRESSION FAILED: " + ", ".join(failures), flush=True)
            return 1
        print("FULL REGRESSION PASSED: both suites executed", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
