"""VeloPOS Admin - developer-only helper window (NEVER ship this folder to customers).

Tab 1  Dashboard code : makes an invite / renewal code on YOUR Cloudflare Worker (replaces the curl command).
Tab 2  Licence key    : calls your own tools/keygen.py (it is not part of this package) to issue a licence key.

Run:  double-click VeloPOS_Admin.bat      (needs Python; uses only the standard library)
CLI (for testing / scripts):  python velopos_admin.py invite 30 [--url https://...] [--key ADMINKEY]
"""
import csv, json, os, subprocess, sys, urllib.error, urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
KEY_FILE = os.path.join(HERE, "admin_key.txt")          # only written if you tick "Remember"
LOG_FILE = os.path.join(HERE, "invites_log.csv")


def default_url():
    try:
        from velopos import branding
        return (getattr(branding, "TRIAL_SERVER_URL", "") or getattr(branding, "DEFAULT_DASH_URL", "")).strip()
    except Exception:
        return ""


def make_invite(url, admin_key, days, timeout=15):
    """-> code string like 'AB12-CD34-EF56'. Raises RuntimeError with a readable message."""
    url = (url or "").strip().rstrip("/")
    if not url.lower().startswith("https://"):
        raise RuntimeError("The Worker address must start with https://")
    if not admin_key.strip():
        raise RuntimeError("Enter your ADMIN_KEY password.")
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise RuntimeError("Days must be a whole number.") from None
    if not 1 <= days <= 3660:
        raise RuntimeError("Days must be between 1 and 3660.")
    req = urllib.request.Request(url + "/admin/invite", data=json.dumps({"days": days}).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + admin_key.strip(), "Content-Type": "application/json",
                                          "User-Agent": "VeloPOS-Admin/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError("Wrong ADMIN_KEY password (the server said 'forbidden').") from None
        raise RuntimeError(f"The server answered with error {e.code}.") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"Cannot reach the server. Check the internet and the address.\n({e})") from None
    code = data.get("code")
    if not code:
        raise RuntimeError("The server did not return a code.")
    return code


def log_invite(customer, days, code):
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "customer", "days", "code"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), customer, days, code])


def whatsapp_text(code, days):
    return (f"Your VeloPOS owner-dashboard code: {code}\nValid for {days} days.\n"
            "In VeloPOS open Settings -> 4h, tick 'Owner phone dashboard', type this code in 'Invite / renewal code', "
            "save and press 'Upload now'.")


def issue_licence(machine_id, customer):
    """Runs YOUR tools/keygen.py (not included here). -> its printed output."""
    kg = os.path.join(HERE, "keygen.py")
    if not os.path.isfile(kg):
        raise RuntimeError("tools/keygen.py was not found next to this program.\nCopy velopos_admin.py and VeloPOS_Admin.bat into your own tools folder (where keygen.py is).")
    mid = machine_id.strip().upper()
    if not mid.startswith("POS-"):
        raise RuntimeError("The Machine ID looks like POS-XXXX-XXXX-XXXX.")
    cmd = [sys.executable, kg, "issue", mid] + (["--customer", customer.strip()] if customer.strip() else [])
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=60)
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        raise RuntimeError((r.stderr or out or "keygen failed").strip()[-600:])
    return out


# ----------------------------------------------------------------------------- window
def gui():
    import tkinter as tk
    from tkinter import messagebox, ttk
    root = tk.Tk()
    root.title("VeloPOS Admin (developer only)")
    root.geometry("640x560")
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=True, padx=10, pady=10)

    def copy(text):
        root.clipboard_clear(); root.clipboard_append(text)

    # ---- tab 1
    t1 = ttk.Frame(nb, padding=14); nb.add(t1, text="  Dashboard code  ")
    v_url, v_key, v_cust, v_days, v_rem = tk.StringVar(value=default_url()), tk.StringVar(), tk.StringVar(), tk.StringVar(value="30"), tk.BooleanVar()
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            v_key.set(f.read().strip()); v_rem.set(True)
    except OSError:
        pass
    for r, (lab, var, show) in enumerate((("Worker address", v_url, ""), ("ADMIN_KEY password", v_key, "*"), ("Customer / shop name", v_cust, ""))):
        ttk.Label(t1, text=lab).grid(row=r, column=0, sticky="w", pady=5)
        ttk.Entry(t1, textvariable=var, width=52, show=show).grid(row=r, column=1, sticky="w", padx=8)
    ttk.Label(t1, text="Days of access").grid(row=3, column=0, sticky="w", pady=5)
    ttk.Combobox(t1, textvariable=v_days, values=("30", "90", "180", "365"), width=10).grid(row=3, column=1, sticky="w", padx=8)
    ttk.Checkbutton(t1, text="Remember the ADMIN_KEY on this PC (saved as plain text in tools\\admin_key.txt)", variable=v_rem).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
    out = tk.StringVar()
    box = ttk.Entry(t1, textvariable=out, font=("Consolas", 22, "bold"), justify="center", state="readonly", width=18)
    msg = tk.Text(t1, height=7, width=62, wrap="word")

    def generate():
        try:
            code = make_invite(v_url.get(), v_key.get(), v_days.get())
        except RuntimeError as e:
            return messagebox.showerror("Could not make the code", str(e))
        try:
            if v_rem.get():
                with open(KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(v_key.get().strip())
            elif os.path.exists(KEY_FILE):
                os.remove(KEY_FILE)
            log_invite(v_cust.get().strip(), v_days.get(), code)
        except OSError:
            pass
        out.set(code)
        msg.delete("1.0", "end"); msg.insert("1.0", whatsapp_text(code, v_days.get()))
        copy(code)

    ttk.Button(t1, text="MAKE DASHBOARD CODE", command=generate).grid(row=5, column=0, columnspan=2, pady=10, ipadx=20, ipady=6)
    box.grid(row=6, column=0, columnspan=2, pady=4)
    ttk.Label(t1, text="(the code is copied automatically; every code is logged in tools\\invites_log.csv)", foreground="#666").grid(row=7, column=0, columnspan=2)
    msg.grid(row=8, column=0, columnspan=2, pady=8)
    ttk.Button(t1, text="Copy WhatsApp message", command=lambda: copy(msg.get("1.0", "end").strip())).grid(row=9, column=0, columnspan=2)

    # ---- tab 2
    t2 = ttk.Frame(nb, padding=14); nb.add(t2, text="  Licence key  ")
    v_mid, v_c2 = tk.StringVar(), tk.StringVar()
    ttk.Label(t2, text="Customer's Machine ID").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(t2, textvariable=v_mid, width=34).grid(row=0, column=1, sticky="w", padx=8)
    ttk.Label(t2, text="Customer / shop name").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Entry(t2, textvariable=v_c2, width=34).grid(row=1, column=1, sticky="w", padx=8)
    res = tk.Text(t2, height=10, width=66, wrap="word")

    def issue():
        try:
            text = issue_licence(v_mid.get(), v_c2.get())
        except (RuntimeError, subprocess.SubprocessError) as e:
            return messagebox.showerror("Could not issue the key", str(e))
        res.delete("1.0", "end"); res.insert("1.0", text); copy(text)

    ttk.Button(t2, text="ISSUE LICENCE KEY", command=issue).grid(row=2, column=0, columnspan=2, pady=10, ipadx=20, ipady=6)
    res.grid(row=3, column=0, columnspan=2)
    ttk.Label(t2, text="Uses your own tools\\keygen.py. The output is copied to the clipboard.", foreground="#666").grid(row=4, column=0, columnspan=2, pady=6)
    root.mainloop()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "invite":
        def opt(n, d=""):
            return a[a.index(n) + 1] if n in a else d
        try:
            print(make_invite(opt("--url", default_url()), opt("--key", os.environ.get("ADMIN_KEY", "")), a[1] if len(a) > 1 and not a[1].startswith("--") else 30))
        except RuntimeError as e:
            sys.exit(str(e))
    else:
        gui()
