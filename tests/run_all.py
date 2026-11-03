"""Runs every test file + static check + GUI smoke test, each in its own process, and prints a one-screen summary.
    python tests/run_all.py          (exit code 0 = everything passed)"""
import glob, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
jobs = [(os.path.basename(f)[:-3], [sys.executable, "-m", "unittest", f"tests.{os.path.basename(f)[:-3]}"]) for f in sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))]
jobs += [("check_static", [sys.executable, os.path.join("tests", "check_static.py")]), ("gui_smoke", [sys.executable, os.path.join("tests", "gui_smoke.py")])]
rows, failed = [], 0
for name, cmd in jobs:
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"Ran (\d+) tests?", out)
    detail = f"{m.group(1)} tests" if m else ("OK" if r.returncode == 0 else "see output below")
    rows.append((name, "PASS" if r.returncode == 0 else "FAIL", detail, time.time() - t))
    if r.returncode:
        failed += 1
        print(f"\n===== {name} FAILED =====\n{out[-3000:]}")
print("\n" + "=" * 56)
for name, st, detail, secs in rows:
    print(f"  {st:4}  {name:22} {detail:18} {secs:5.1f}s")
print("=" * 56)
print("ALL PASSED" if not failed else f"{failed} JOB(S) FAILED")
sys.exit(1 if failed else 0)
