"""Runs every test file + static check + GUI smoke test, each in its own process, and prints a one-screen summary.
    python tests/run_all.py          (exit code 0 = everything passed)"""
import argparse, glob, os, re, subprocess, sys, time

parser = argparse.ArgumentParser(description="Run legacy application checks")
parser.add_argument("--fail-on-skips", action="store_true",
                    help="Fail closed if a unittest subprocess reports skipped tests")
parser.add_argument("--job-timeout", type=int, default=600,
                    help="maximum seconds for each legacy test/static/GUI subprocess (default: 600)")
args = parser.parse_args()
if args.job_timeout <= 0:
    parser.error("--job-timeout must be positive")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
jobs = [(os.path.basename(f)[:-3], [sys.executable, "-m", "unittest", f"tests.{os.path.basename(f)[:-3]}"]) for f in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))]
jobs += [("check_static", [sys.executable, os.path.join("tests", "check_static.py")]), ("gui_smoke", [sys.executable, os.path.join("tests", "gui_smoke.py")])]
rows, failed, total_skips = [], 0, 0
for name, cmd in jobs:
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=args.job_timeout)
        out = (r.stdout or "") + (r.stderr or "")
        returncode = r.returncode
    except subprocess.TimeoutExpired as exc:
        # A hung subprocess is a failed check, never an implicit pass.
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        out = stdout + stderr + f"\nTIMEOUT: job exceeded {args.job_timeout}s\n"
        returncode = 124
    m = re.search(r"Ran (\d+) tests?", out)
    skip_matches = re.findall(r"\bskipped\s*=\s*(\d+)\b", out, flags=re.IGNORECASE)
    skips = sum(int(value) for value in skip_matches)
    total_skips += skips
    detail = f"{m.group(1)} tests" if m else ("OK" if returncode == 0 else "see output below")
    if skips:
        detail += f", {skips} skipped"
    if returncode == 124:
        detail += ", timed out"
    # A test module with zero discovered tests must not silently pass release QA.
    no_tests = name.startswith("test_") and (m is None or int(m.group(1)) == 0)
    if no_tests:
        detail += ", no tests executed"
    job_failed = returncode != 0 or no_tests or (args.fail_on_skips and skips > 0)
    rows.append((name, "FAIL" if job_failed else "PASS", detail, time.time() - t))
    if job_failed:
        failed += 1
        reason = ("subprocess timed out" if returncode == 124 else
                  "no unittest tests executed" if no_tests else
                  "skipped tests are forbidden in strict mode" if skips and args.fail_on_skips and returncode == 0 else
                  "subprocess returned nonzero")
        print(f"\n===== {name} FAILED ({reason}) =====\n{out[-3000:]}")
print("\n" + "=" * 56)
for name, st, detail, secs in rows:
    print(f"  {st:4}  {name:22} {detail:18} {secs:5.1f}s")
print("=" * 56)
print(f"REPORTED UNITTEST SKIPS: {total_skips}")
print("ALL PASSED" if not failed else f"{failed} JOB(S) FAILED")
sys.exit(1 if failed else 0)
