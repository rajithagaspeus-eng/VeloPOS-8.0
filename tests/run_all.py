"""Runs every test file + static check + GUI smoke test, each in its own process, and prints a one-screen summary.
    python tests/run_all.py          (exit code 0 = everything passed)"""
import argparse, glob, os, re, subprocess, sys, time

parser = argparse.ArgumentParser(description="Run legacy application checks")
parser.add_argument("--fail-on-skips", action="store_true",
                    help="Fail closed if a unittest subprocess reports skipped tests")
args = parser.parse_args()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
jobs = [(os.path.basename(f)[:-3], [sys.executable, "-m", "unittest", f"tests.{os.path.basename(f)[:-3]}"]) for f in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))]
jobs += [("check_static", [sys.executable, os.path.join("tests", "check_static.py")]), ("gui_smoke", [sys.executable, os.path.join("tests", "gui_smoke.py")])]
rows, failed, total_skips = [], 0, 0
for name, cmd in jobs:
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"Ran (\d+) tests?", out)
    skip_matches = re.findall(r"\bskipped\s*=\s*(\d+)\b", out, flags=re.IGNORECASE)
    skips = sum(int(value) for value in skip_matches)
    total_skips += skips
    detail = f"{m.group(1)} tests" if m else ("OK" if r.returncode == 0 else "see output below")
    if skips:
        detail += f", {skips} skipped"
    job_failed = r.returncode != 0 or (args.fail_on_skips and skips > 0)
    rows.append((name, "FAIL" if job_failed else "PASS", detail, time.time() - t))
    if job_failed:
        failed += 1
        reason = "skipped tests are forbidden in strict mode" if skips and args.fail_on_skips and r.returncode == 0 else "subprocess returned nonzero"
        print(f"\n===== {name} FAILED ({reason}) =====\n{out[-3000:]}")
print("\n" + "=" * 56)
for name, st, detail, secs in rows:
    print(f"  {st:4}  {name:22} {detail:18} {secs:5.1f}s")
print("=" * 56)
print(f"REPORTED UNITTEST SKIPS: {total_skips}")
print("ALL PASSED" if not failed else f"{failed} JOB(S) FAILED")
sys.exit(1 if failed else 0)
