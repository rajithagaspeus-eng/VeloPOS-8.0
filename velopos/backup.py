"""Backup / restore engine. No UI code, so it is headless-testable.

File names:  velopos_YYYYmmdd_HHMMSS[_tag][_n].db
Tags:  manual | usb | auto | exit | pre-restore | pre-reset
Only 'auto' and 'exit' backups are ever deleted automatically; the rest are never pruned.
"""
import hashlib, os, re, shutil, sqlite3, sys, threading
from datetime import datetime, timedelta
from pathlib import Path

from . import database as dbm

ROTATING = ("auto", "exit")
REQUIRED_TABLES = {"settings", "users", "products", "sales", "sale_items", "customers"}
_NAME = re.compile(r"^velopos_(\d{8})_(\d{6})(?:_([a-z][a-z-]*))?(?:_(\d+))?\.db$")
LOCK = threading.RLock()          # no backup / restore / file swap may overlap


def folder():
    return dbm.p("Backups")


def _rm(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _ro_uri(path):
    return Path(path).resolve().as_uri() + "?mode=ro&immutable=1"


# ------------------------------------------------------------------ listing / verifying
def list_backups(where=None):
    where = where or folder()
    out = []
    for n in os.listdir(where) if os.path.isdir(where) else []:
        m = _NAME.match(n)
        if not m:
            continue
        fp = os.path.join(where, n)
        try:
            st = os.stat(fp)
            ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except (OSError, ValueError):
            continue
        out.append(dict(path=fp, name=n, tag=m.group(3) or "manual", ts=ts, size=st.st_size, mt=st.st_mtime_ns))
    # newest first; the file mtime breaks ties when several backups are made in the same second
    out.sort(key=lambda d: (d["ts"], d["mt"], d["name"]), reverse=True)
    return out


def verify(path):
    """-> (ok, message). Checks it is a real SQLite file, passes integrity_check and has the VeloPOS tables."""
    if not os.path.isfile(path):
        return False, "File not found"
    c = None
    try:
        c = sqlite3.connect(_ro_uri(path), uri=True)
        res = c.execute("PRAGMA integrity_check").fetchone()[0]
        if res != "ok":
            return False, f"Integrity check failed: {res}"
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - have
        if missing:
            return False, "Not a VeloPOS database (missing: " + ", ".join(sorted(missing)) + ")"
        return True, "OK"
    except sqlite3.DatabaseError as e:
        return False, f"Not a valid database: {e}"
    finally:
        if c:
            c.close()


# ------------------------------------------------------------------ create / prune / copy
def _unique(where, tag):
    base = os.path.join(where, f"velopos_{datetime.now():%Y%m%d_%H%M%S}" + ("" if tag == "manual" else f"_{tag}"))
    final, n = base + ".db", 1
    while os.path.exists(final):
        n += 1
        final = f"{base}_{n}.db"
    return final


def create(tag="manual", where=None):
    """Writes to a .part file, verifies it, then renames - a half-written backup never looks valid."""
    where = where or folder()
    os.makedirs(where, exist_ok=True)
    with LOCK:
        final = _unique(where, tag)
        part = final + ".part"
        try:
            dbm.backup_db(part)
            ok, msg = verify(part)
            if not ok:
                raise RuntimeError("Backup verification failed: " + msg)
            os.replace(part, final)
        finally:
            _rm(part)
    return final


def prune(keep, where=None):
    """Delete the oldest automatic ('auto'/'exit') backups beyond `keep`. Returns removed file names."""
    keep, removed = max(1, int(keep)), []
    rot = [b for b in list_backups(where) if b["tag"] in ROTATING]
    for b in rot[keep:]:
        _rm(b["path"])
        removed.append(b["name"])
    return removed


def copy_to(path, target_dir, keep=None, subfolder="VeloPOS_Backups"):
    """Copy a backup to a USB drive / any folder / Google Drive for Desktop folder."""
    if not target_dir or not os.path.isdir(target_dir):
        raise FileNotFoundError(f"Folder not found: {target_dir or '(not set)'}  (is the USB drive / Drive folder available?)")
    dest_dir = os.path.join(target_dir, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    tmp = dest + ".part"
    try:
        shutil.copy2(path, tmp)
        if os.path.getsize(tmp) != os.path.getsize(path):
            raise OSError("Copy is incomplete (disk full or drive removed?)")
        os.replace(tmp, dest)
    finally:
        _rm(tmp)
    if keep:
        prune(keep, dest_dir)
    return dest


# ------------------------------------------------------------------ cloud / network folders (Phase 6.4)
# No login is stored anywhere: "cloud" = a folder that Google Drive for desktop / OneDrive / Dropbox (or a network share) syncs for you.
# A real Google Drive API upload needs OAuth secrets and is deliberately NOT implemented.
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cloud_targets(cfg):
    """Folders every automatic backup is copied to: the 'cloud folders' (feat_cloud_sync) and the older Google Drive folder (feat_backup_gdrive)."""
    out = []
    if cfg.bool("feat_cloud_sync"):
        out += [d.strip() for d in cfg.get("cloud_dirs", "").split("|") if d.strip()]
    if cfg.bool("feat_backup_gdrive") and cfg.get("backup_gdrive_dir").strip():
        out.append(cfg.get("backup_gdrive_dir").strip())
    seen, uniq = set(), []
    for d in out:
        k = os.path.normcase(os.path.normpath(d))
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def copy_verified(path, target_dir, keep=None, subfolder="VeloPOS_Backups"):
    """copy_to + SHA-256 comparison. A copy that does not match the original is deleted and reported."""
    dest = copy_to(path, target_dir, None, subfolder)
    if sha256_file(dest) != sha256_file(path):
        _rm(dest)
        raise OSError("The copy does not match the original (SHA-256 differs) and was removed")
    if keep:
        prune(keep, os.path.dirname(dest))
    return dest


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _queue_add(name, target, err):
    with dbm.db() as c:
        c.execute("INSERT INTO cloud_queue(backup_name, target_dir, attempts, last_error, created_ts, last_try_ts) VALUES (?,?,1,?,?,?) "
                  "ON CONFLICT(backup_name, target_dir) DO UPDATE SET attempts = attempts + 1, last_error=excluded.last_error, last_try_ts=excluded.last_try_ts",
                  (name, target, str(err)[:300], _now_iso(), _now_iso()))


def _queue_remove(name, target):
    with dbm.db() as c:
        c.execute("DELETE FROM cloud_queue WHERE backup_name=? AND target_dir=?", (name, target))


def pending_count():
    with dbm.db() as c:
        return c.execute("SELECT COUNT(*) FROM cloud_queue").fetchone()[0]


def sync_to_clouds(path, cfg):
    """Copy one backup to every cloud folder. A folder that is offline (USB removed, drive not mounted) puts the copy in the retry queue.
    -> dict(ok=[folders], failed=[(folder, error)])"""
    keep, name = max(1, cfg.int("backup_keep", 20)), os.path.basename(path)
    res = dict(ok=[], failed=[])
    for t in cloud_targets(cfg):
        try:
            copy_verified(path, t, keep=keep)
            _queue_remove(name, t)
            res["ok"].append(t)
        except Exception as e:
            _queue_add(name, t, e)
            res["failed"].append((t, str(e)))
    if res["ok"]:
        cfg.set_many({"cloud_last_ok": _now_iso()})
    return res


def process_queue(cfg):
    """Retry the pending copies (called every minute by the app). Backups that were pruned meanwhile, and folders that are no longer
    configured, are dropped from the queue. -> dict(done, pending, dropped)"""
    done = dropped = 0
    targets = {os.path.normcase(os.path.normpath(t)) for t in cloud_targets(cfg)}
    keep = max(1, cfg.int("backup_keep", 20))
    with dbm.db() as c:
        rows = c.execute("SELECT * FROM cloud_queue ORDER BY id").fetchall()
    for r in rows:
        src = os.path.join(folder(), r["backup_name"])
        if os.path.normcase(os.path.normpath(r["target_dir"])) not in targets or not os.path.isfile(src):
            _queue_remove(r["backup_name"], r["target_dir"])
            dropped += 1
            continue
        try:
            copy_verified(src, r["target_dir"], keep=keep)
            _queue_remove(r["backup_name"], r["target_dir"])
            done += 1
        except Exception as e:
            _queue_add(r["backup_name"], r["target_dir"], e)
    if done:
        cfg.set_many({"cloud_last_ok": _now_iso()})
    return dict(done=done, pending=pending_count(), dropped=dropped)


def cloud_status(cfg):
    """For the status panel: last success, pending copies with their last error, and whether each folder is reachable right now."""
    with dbm.db() as c:
        pend = [dict(r) for r in c.execute("SELECT * FROM cloud_queue ORDER BY id")]
    return dict(last_ok=cfg.get("cloud_last_ok"), pending=pend,
                targets=[dict(dir=t, reachable=os.path.isdir(t)) for t in cloud_targets(cfg)])


def list_cloud_backups(target_dir, subfolder="VeloPOS_Backups"):
    """The backups found in one cloud folder (same file names as local backups). Restore them with restore(path)."""
    return list_backups(os.path.join(target_dir, subfolder))


# ------------------------------------------------------------------ restore
def _live_license_rows():
    c = dbm.connect()
    try:
        key = c.execute("SELECT value FROM settings WHERE key='license_key'").fetchone()
        state = c.execute("SELECT id, blob FROM license_state").fetchall()
        return (key[0] if key else None), [(r[0], r[1]) for r in state]
    finally:
        c.close()


def _put_license_rows(conn, key, state):
    if key:
        conn.execute("INSERT INTO settings(key, value) VALUES('license_key', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,))
    conn.execute("CREATE TABLE IF NOT EXISTS license_state (id INTEGER PRIMARY KEY, blob TEXT)")
    for i, blob in state:
        conn.execute("INSERT INTO license_state(id, blob) VALUES(?, ?) "
                     "ON CONFLICT(id) DO UPDATE SET blob=excluded.blob", (i, blob))


def restore(path, user="-"):
    """Safely replace the live database with `path`.
    1) verify the backup  2) safety-backup the CURRENT data  3) build a clean staged copy that keeps
    the CURRENT licence  4) checkpoint + atomic swap  5) remove stale -wal/-shm (a leftover WAL from the
    old database must never be applied to the restored one).  The caller restarts the app afterwards."""
    ok, msg = verify(path)
    if not ok:
        raise ValueError("This backup cannot be restored: " + msg)
    live = dbm.DB_PATH
    with LOCK:
        pre = create("pre-restore")
        staged = live + ".restoring"
        _rm(staged)
        key, state = _live_license_rows()
        src = sqlite3.connect(_ro_uri(path), uri=True)
        dst = sqlite3.connect(staged)
        try:
            src.backup(dst)
            _put_license_rows(dst, key, state)
            dst.commit()
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Staged copy failed the integrity check - nothing was changed")
        except Exception:
            dst.close()
            src.close()
            _rm(staged)
            raise
        dst.close()
        src.close()
        try:
            c = dbm.connect()
            try:
                busy = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
            finally:
                c.close()
            if busy:
                raise RuntimeError("The database is busy. Close other VeloPOS windows and try again - nothing was changed")
            os.replace(staged, live)
        except Exception:
            _rm(staged)
            raise
        for ext in ("-wal", "-shm", "-journal"):
            _rm(live + ext)
        dbm.settings.load()
    dbm.audit(user, "RESTORE", f"from={os.path.basename(path)} safety_copy={os.path.basename(pre)}")
    return dict(pre_backup=pre)


# ------------------------------------------------------------------ automatic schedule
def due(cfg, now=None):
    if not cfg.bool("feat_autobackup"):
        return False
    hrs = cfg.int("backup_interval_hours", 6)
    if hrs <= 0:
        return False
    try:
        last = datetime.fromisoformat(cfg.get("last_auto_backup", ""))
    except ValueError:
        return True
    return (now or datetime.now()) - last >= timedelta(hours=hrs)


def run_auto(cfg, tag="auto", user="system"):
    """Backup + prune + optional Google Drive copy. Never raises; returns {path, copied, pruned, errors}."""
    res = dict(path=None, copied=None, pruned=[], errors=[])
    try:
        res["path"] = create(tag)
    except Exception as e:
        res["errors"].append(f"Backup failed: {e}")
        dbm.audit(user, "BACKUP_FAILED", str(e))
        cfg.set_many({"last_backup_msg": f"{datetime.now():%Y-%m-%d %H:%M} FAILED: {e}"})
        return res
    keep = max(1, cfg.int("backup_keep", 20))
    try:
        res["pruned"] = prune(keep)
    except Exception as e:
        res["errors"].append(f"Cleanup failed: {e}")
    targets = cloud_targets(cfg)
    if targets:
        sync = sync_to_clouds(res["path"], cfg)
        gdrive = cfg.get("backup_gdrive_dir").strip()
        res["copied"] = sync["ok"][0] if sync["ok"] else None
        for t, err in sync["failed"]:
            label = "Google Drive copy" if cfg.bool("feat_backup_gdrive") and gdrive and t == gdrive else f"Cloud copy to {t}"
            res["errors"].append(f"{label} failed: {err}  (queued for retry)")
    msg = f"{datetime.now():%Y-%m-%d %H:%M} OK ({os.path.basename(res['path'])})"
    if res["errors"]:
        msg += " - " + "; ".join(res["errors"])
    cfg.set_many({"last_auto_backup": datetime.now().isoformat(timespec="seconds"), "last_backup_msg": msg})
    dbm.audit(user, "BACKUP_AUTO", msg)
    return res


# ------------------------------------------------------------------ restart helper
def restart_command():
    frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()
    if frozen:
        return [sys.executable] + sys.argv[1:]
    return [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]
