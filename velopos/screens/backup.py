import os
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .. import backup as bk, database as dbm
from ..theme import C
from . import Screen

INTERVALS = {"Off (only on exit)": "0", "Every 1 hour": "1", "Every 2 hours": "2", "Every 4 hours": "4",
             "Every 6 hours": "6", "Every 12 hours": "12", "Every 24 hours": "24"}
TAG_LABEL = {"manual": "Manual", "usb": "USB / folder", "auto": "Automatic", "exit": "On exit",
             "pre-restore": "Safety (before restore)", "pre-reset": "Safety (before reset)"}


def _size(n):
    return f"{n / 1024:,.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:,.1f} MB"


class BackupScreen(Screen):
    def __init__(self, app, parent):
        super().__init__(app, parent)
        a = app
        self.heading(self, "Backup & Restore").pack(anchor="w", pady=(4, 8))
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        # ---- actions
        f = a.card(sc)
        f.pack(fill="x", pady=6)
        ctk.CTkLabel(f, text="Back up now", font=a.f(2, "bold"), text_color=a.accent).pack(anchor="w", padx=16, pady=(10, 4))
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        a.btn(row, "Backup now", "green", self.backup_now, width=150).pack(side="left", padx=4)
        a.btn(row, "Backup to USB / folder...", "blue", self.backup_usb, width=210).pack(side="left", padx=4)
        a.btn(row, "Open backup folder", "gray", self.open_folder, width=170).pack(side="left", padx=4)
        self.lbl_last = ctk.CTkLabel(f, text="", font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left")
        self.lbl_last.pack(anchor="w", padx=16, pady=(0, 10))

        # ---- list
        f = a.card(sc)
        f.pack(fill="x", pady=6)
        ctk.CTkLabel(f, text="Saved backups", font=a.f(2, "bold"), text_color=a.accent).pack(anchor="w", padx=16, pady=(10, 4))
        self.tree = ttk.Treeview(f, columns=("when", "type", "size"), show="headings", height=9)
        for c, t, w in (("when", "Date & time", 220), ("type", "Type", 240), ("size", "Size", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="x", padx=16, pady=6)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        a.btn(row, "RESTORE selected...", "red", self.restore_selected, width=190).pack(side="left", padx=4)
        a.btn(row, "Restore from file...", "amber", self.restore_file, width=190).pack(side="left", padx=4)
        a.btn(row, "Verify selected", "teal", self.verify_selected, width=150).pack(side="left", padx=4)
        a.btn(row, "Delete selected", "gray", self.delete_selected, width=150).pack(side="right", padx=4)
        self.paths = {}

        # ---- schedule
        f = a.card(sc)
        f.pack(fill="x", pady=6)
        ctk.CTkLabel(f, text="Automatic backup schedule", font=a.f(2, "bold"), text_color=a.accent).grid(
            row=0, column=0, columnspan=4, padx=16, pady=(10, 4), sticky="w")
        self.w = {}
        for i, (k, label) in enumerate((("feat_autobackup", "Back up automatically on a schedule"),
                                        ("feat_backup_on_exit", "Back up when the program is closed"),
                                        ("feat_backup_gdrive", "Also copy automatic backups to the Google Drive folder below"))):
            cb = ctk.CTkCheckBox(f, text=label, text_color=C["text"], font=a.f(0))
            cb.grid(row=1 + i, column=0, columnspan=4, padx=16, pady=3, sticky="w")
            if a.s.bool(k):
                cb.select()
            self.w[k] = cb
        ctk.CTkLabel(f, text="Schedule:", text_color=C["text"]).grid(row=4, column=0, padx=16, pady=6, sticky="w")
        cur_h = a.s.get("backup_interval_hours")
        cur_lbl = next((k for k, v in INTERVALS.items() if v == cur_h), "Every 6 hours")
        self.interval = ctk.CTkOptionMenu(f, values=list(INTERVALS), width=220)
        self.interval.grid(row=4, column=1, padx=8, pady=6, sticky="w")
        self.interval.set(cur_lbl)
        ctk.CTkLabel(f, text="Keep last (automatic):", text_color=C["text"]).grid(row=4, column=2, padx=16, pady=6, sticky="w")
        self.keep = ctk.CTkEntry(f, width=90)
        self.keep.grid(row=4, column=3, padx=8, pady=6, sticky="w")
        self.keep.insert(0, a.s.get("backup_keep"))
        ctk.CTkLabel(f, text="Google Drive folder:", text_color=C["text"]).grid(row=5, column=0, padx=16, pady=6, sticky="w")
        self.drive = ctk.CTkEntry(f, width=420)
        self.drive.grid(row=5, column=1, columnspan=2, padx=8, pady=6, sticky="w")
        self.drive.insert(0, a.s.get("backup_gdrive_dir"))
        a.btn(f, "Browse...", "gray", self.pick_drive, width=110).grid(row=5, column=3, padx=8, pady=6, sticky="w")
        ctk.CTkLabel(f, text="How Google Drive works here: install 'Google Drive for desktop', choose a folder inside it above, and "
                             "VeloPOS simply copies each automatic backup there (Drive then uploads it). No Google login is stored in VeloPOS. "
                             "Manual, safety and USB backups are never deleted automatically.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=6, column=0, columnspan=4, padx=16, pady=4, sticky="w")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=7, column=0, columnspan=4, padx=16, pady=(6, 12), sticky="w")
        a.btn(row, "Save schedule", "green", self.save_schedule, width=160).pack(side="left", padx=4)
        a.btn(row, "Copy latest backup to Drive now", "blue", self.copy_to_drive, width=260).pack(side="left", padx=4)

        # ---- cloud / network folders (Phase 6.4)
        f = a.card(sc)
        f.pack(fill="x", pady=6)
        ctk.CTkLabel(f, text="Cloud / network folders", font=a.f(2, "bold"), text_color=a.accent).grid(row=0, column=0, columnspan=4, padx=16, pady=(10, 4), sticky="w")
        cb = ctk.CTkCheckBox(f, text="Copy every automatic backup to these folders (each copy is verified with SHA-256)", text_color=C["text"], font=a.f(0))
        cb.grid(row=1, column=0, columnspan=4, padx=16, pady=3, sticky="w")
        if a.s.bool("feat_cloud_sync"):
            cb.select()
        self.w["feat_cloud_sync"] = cb
        self.cloud = ctk.CTkEntry(f, width=620, placeholder_text="Folders separated by |   e.g.  C:\\Users\\You\\OneDrive\\Backups | D:\\Dropbox | \\\\server\\share")
        self.cloud.grid(row=2, column=0, columnspan=3, padx=16, pady=6, sticky="w")
        self.cloud.insert(0, a.s.get("cloud_dirs"))
        row = ctk.CTkFrame(f, fg_color="transparent"); row.grid(row=3, column=0, columnspan=4, padx=12, pady=4, sticky="w")
        a.btn(row, "Add folder...", "gray", self.add_cloud, width=120, height=30).pack(side="left", padx=4)
        a.btn(row, "Sync latest now", "green", self.sync_now, width=140, height=30).pack(side="left", padx=4)
        a.btn(row, "Retry pending", "amber", self.retry_cloud, width=130, height=30).pack(side="left", padx=4)
        a.btn(row, "Cloud backups / restore...", "blue", self.open_cloud_list, width=200, height=30).pack(side="left", padx=4)
        self.lbl_cloud = ctk.CTkLabel(f, text="", font=a.f(-1), text_color=C["muted"], wraplength=900, justify="left")
        self.lbl_cloud.grid(row=4, column=0, columnspan=4, padx=16, pady=(2, 4), sticky="w")
        ctk.CTkLabel(f, text="No login is stored: install Google Drive for desktop / OneDrive / Dropbox, or use a network share, and choose a folder inside it. "
                             "If a folder is offline (USB removed, drive not mounted) the copy waits in a queue and is retried every minute. "
                             "Press 'Save schedule' above to keep these settings. A real Google Drive API upload needs OAuth secrets and is NOT implemented.",
                     font=a.f(-2), text_color=C["muted"], wraplength=900, justify="left").grid(row=5, column=0, columnspan=4, padx=16, pady=(0, 10), sticky="w")
        self.refresh()

    # ------------------------------------------------------------------ helpers
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.paths = {}
        rows = bk.list_backups()
        for b in rows:
            iid = self.tree.insert("", "end", values=(b["ts"].strftime("%Y-%m-%d  %H:%M:%S"), TAG_LABEL.get(b["tag"], b["tag"]), _size(b["size"])))
            self.paths[iid] = b
        msg = self.app.s.get("last_backup_msg") or "No automatic backup has run yet."
        self.lbl_last.configure(text=f"{len(rows)} backup(s) in {bk.folder()}\nLast automatic backup: {msg}")
        self.refresh_cloud()

    def refresh_cloud(self):
        st = bk.cloud_status(self.app.s)
        if not st["targets"]:
            return self.lbl_cloud.configure(text="No cloud folder is active.", text_color=C["muted"])
        lines = [f"{len(st['targets'])} folder(s), {sum(1 for t in st['targets'] if t['reachable'])} reachable now.  Last successful copy: {st['last_ok'].replace('T', ' ') or 'never'}"]
        if st["pending"]:
            lines.append(f"{len(st['pending'])} copy(ies) waiting for retry. Last problem: {st['pending'][0]['last_error']}")
        self.lbl_cloud.configure(text="\n".join(lines), text_color=C["danger"] if st["pending"] else C["success"])

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select a backup in the list first.")
            return None
        return self.paths[sel[0]]

    # ------------------------------------------------------------------ actions
    def backup_now(self):
        try:
            path = bk.create("manual")
            dbm.audit(self.app.user, "BACKUP_MANUAL", os.path.basename(path))
        except Exception as e:
            return messagebox.showerror("Backup failed", str(e))
        self.refresh()
        messagebox.showinfo("Backup", f"Saved and verified:\n{path}")

    def backup_usb(self):
        d = filedialog.askdirectory(title="Choose the USB drive / folder")
        if not d:
            return
        try:
            path = bk.create("usb")
            dest = bk.copy_to(path, d)
            dbm.audit(self.app.user, "BACKUP_USB", dest)
        except Exception as e:
            return messagebox.showerror("Backup failed", str(e))
        self.refresh()
        messagebox.showinfo("Backup", f"Backup saved here and copied to:\n{dest}\n\nSafely eject the USB drive before removing it.")

    def open_folder(self):
        if os.name == "nt":
            os.startfile(bk.folder())
        else:
            messagebox.showinfo("Backup folder", bk.folder())

    def verify_selected(self):
        b = self.selected()
        if b:
            ok, msg = bk.verify(b["path"])
            (messagebox.showinfo if ok else messagebox.showerror)("Verify backup", f"{b['name']}\n\n" + ("Backup is healthy." if ok else msg))

    def delete_selected(self):
        b = self.selected()
        if b and messagebox.askyesno("Delete backup", f"Delete this backup file?\n{b['name']}"):
            try:
                os.remove(b["path"])
                dbm.audit(self.app.user, "BACKUP_DELETED", b["name"])
            except OSError as e:
                messagebox.showerror("Delete failed", str(e))
            self.refresh()

    def restore_selected(self):
        b = self.selected()
        if b:
            self.do_restore(b["path"])

    def restore_file(self):
        p = filedialog.askopenfilename(title="Choose a VeloPOS backup (.db)", filetypes=[("VeloPOS backup", "*.db")])
        if p:
            self.do_restore(p)

    def do_restore(self, path):
        a = self.app
        ok, msg = bk.verify(path)
        if not ok:
            return messagebox.showerror("Cannot restore", f"This file is not a usable VeloPOS backup:\n{msg}")
        if not messagebox.askyesno(
                "Restore backup",
                f"Restore this backup?\n{os.path.basename(path)}\n\n"
                "ALL current data (products, bills, customers, users, settings) will be replaced by the contents of this backup.\n"
                "Your current data is backed up automatically first, and your software licence is kept.\n\n"
                "VeloPOS will restart afterwards. Continue?", icon="warning"):
            return
        try:
            res = bk.restore(path, a.user)
        except Exception as e:
            return messagebox.showerror("Restore failed", f"Your data was not changed.\n\n{e}")
        messagebox.showinfo("Restore complete", f"Done. A safety copy of your previous data:\n{res['pre_backup']}\n\nVeloPOS will now restart.")
        a.restart()

    def pick_drive(self):
        d = filedialog.askdirectory(title="Choose a folder inside Google Drive")
        if d:
            self.drive.delete(0, "end")
            self.drive.insert(0, d)

    def add_cloud(self):
        d = filedialog.askdirectory(title="Choose a cloud / network folder")
        if d:
            cur = self.cloud.get().strip()
            self.cloud.delete(0, "end")
            self.cloud.insert(0, (cur + "|" if cur else "") + d)

    def sync_now(self):
        self.save_schedule(quiet=True)
        rows = bk.list_backups()
        if not rows:
            return messagebox.showinfo("Cloud", "Make a backup first.")
        if not bk.cloud_targets(self.app.s):
            return messagebox.showinfo("Cloud", "Tick the box and add at least one folder first.")
        res = bk.sync_to_clouds(rows[0]["path"], self.app.s)
        self.refresh_cloud()
        msg = f"Copied (and verified) to {len(res['ok'])} folder(s)."
        if res["failed"]:
            msg += "\n\nNot copied (queued for retry):\n" + "\n".join(f"{t}: {e}" for t, e in res["failed"])
        messagebox.showinfo("Cloud", msg)

    def retry_cloud(self):
        r = bk.process_queue(self.app.s)
        self.refresh_cloud()
        messagebox.showinfo("Cloud", f"Copied: {r['done']}   Still waiting: {r['pending']}   Dropped: {r['dropped']}")

    def open_cloud_list(self):
        targets = bk.cloud_targets(self.app.s)
        if not targets:
            return messagebox.showinfo("Cloud", "No cloud folder is configured yet (save the schedule first).")
        d = ctk.CTkToplevel(self); d.title("Backups in the cloud folder"); d.geometry("640x460"); d.configure(fg_color=C["bg"]); d.transient(self.winfo_toplevel())
        menu = ctk.CTkOptionMenu(d, values=targets, width=560); menu.pack(pady=10); menu.set(targets[0])
        tree = ttk.Treeview(d, columns=("w", "t", "s"), show="headings", height=12)
        for c, t, w in (("w", "Date & time", 200), ("t", "Type", 200), ("s", "Size", 100)):
            tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
        tree.pack(fill="both", expand=True, padx=12)
        found = {}

        def load(*_):
            for i in tree.get_children():
                tree.delete(i)
            found.clear()
            for b in bk.list_cloud_backups(menu.get()):
                iid = tree.insert("", "end", values=(b["ts"].strftime("%Y-%m-%d  %H:%M:%S"), TAG_LABEL.get(b["tag"], b["tag"]), _size(b["size"])))
                found[iid] = b
        menu.configure(command=load)

        def restore():
            sel = tree.selection()
            if sel:
                d.destroy()
                self.do_restore(found[sel[0]]["path"])
        row = ctk.CTkFrame(d, fg_color="transparent"); row.pack(pady=10)
        self.app.btn(row, "RESTORE selected...", "red", restore, width=180).pack(side="left", padx=5)
        self.app.btn(row, "Close", "gray", d.destroy, width=100).pack(side="left", padx=5)
        load()

    def save_schedule(self, quiet=False):
        try:
            keep = int(self.keep.get())
            if not 1 <= keep <= 365:
                raise ValueError
        except ValueError:
            return messagebox.showwarning("Check", "'Keep last' must be a whole number between 1 and 365.")
        vals = {k: ("1" if w.get() else "0") for k, w in self.w.items()}
        vals.update(backup_interval_hours=INTERVALS[self.interval.get()], backup_keep=str(keep), backup_gdrive_dir=self.drive.get().strip(),
                    cloud_dirs="|".join(p.strip() for p in self.cloud.get().split("|") if p.strip()))
        self.app.s.set_many(vals)
        dbm.audit(self.app.user, "BACKUP_SETTINGS", str(vals))
        if quiet:
            return
        if vals["feat_backup_gdrive"] == "1" and not os.path.isdir(vals["backup_gdrive_dir"]):
            return messagebox.showwarning("Saved", "Saved, but the Google Drive folder was not found. Choose it with 'Browse...'.")
        self.refresh_cloud()
        messagebox.showinfo("Saved", "Backup schedule saved.")

    def copy_to_drive(self):
        rows = bk.list_backups()
        if not rows:
            return messagebox.showinfo("Drive", "Make a backup first.")
        try:
            dest = bk.copy_to(rows[0]["path"], self.drive.get().strip(), keep=self.app.s.int("backup_keep", 20))
        except Exception as e:
            return messagebox.showerror("Copy failed", str(e))
        messagebox.showinfo("Drive", f"Copied to:\n{dest}")
