"""DEVELOPER TOOL - never ship this folder. Makes a one-time support code for ONE customer PC.

    python tools/support_code.py POS-XXXX-XXXX-XXXX K7QP-2MXD  [--minutes 30] [--purpose forgot-password] [--customer "Shop name"]

MACHINE-ID and CHALLENGE are shown on the customer's 'Forgot password' screen (choose 'Support code').
Type / paste the printed code into THEIR screen yourself (AnyDesk etc.). Do not send it to the customer.
Purposes: forgot-password (default).  Every code you make is logged in tools/support_log.csv.
"""
import argparse, base64, csv, getpass, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from cryptography.hazmat.primitives import serialization                    # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from velopos import support                                                  # noqa: E402


def load_key(path):
    data = open(path, "rb").read()
    try:
        return serialization.load_pem_private_key(data, password=None)
    except TypeError:
        return serialization.load_pem_private_key(data, password=getpass.getpass("private_key.pem password: ").encode())
    except ValueError:
        raw = base64.urlsafe_b64decode(data.strip() + b"=" * (-len(data.strip()) % 4))      # raw 32-byte seed, base64
        return Ed25519PrivateKey.from_private_bytes(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("machine_id"); ap.add_argument("challenge")
    ap.add_argument("--minutes", type=int, default=support.DEFAULT_MINUTES)
    ap.add_argument("--purpose", default="forgot-password")
    ap.add_argument("--customer", default="")
    ap.add_argument("--key", default=os.path.join(HERE, "private_key.pem"))
    ap.add_argument("--log", default=os.path.join(HERE, "support_log.csv"))
    a = ap.parse_args()
    if not (a.machine_id.startswith("POS-") and len(a.machine_id) == 18):
        sys.exit("Machine ID looks wrong (expected POS-XXXX-XXXX-XXXX).")
    key = load_key(a.key)
    exp = int(time.time()) + max(1, min(a.minutes, 24 * 60)) * 60
    sig = key.sign(support.message(a.purpose, a.machine_id, a.challenge, exp))
    code = f"{exp}." + base64.urlsafe_b64encode(sig).decode().rstrip("=")
    new = not os.path.exists(a.log)
    with open(a.log, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "customer", "machine_id", "challenge", "purpose", "valid_until"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), a.customer, a.machine_id, a.challenge, a.purpose, time.strftime("%H:%M:%S", time.localtime(exp))])
    print(f"\nSupport code (valid {a.minutes} min, this PC + this challenge only):\n\n{code}\n")


if __name__ == "__main__":
    main()
