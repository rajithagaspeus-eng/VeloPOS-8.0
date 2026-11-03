"""Update checker (headless). The owner hosts a tiny JSON file at an HTTPS link, e.g.
    {"version": "7.2.0", "notes": "What is new ...", "download": "https://example.com/velopos_v6_5.zip"}
VeloPOS only TELLS the owner that a newer version exists and opens the download link in the browser when asked.
It NEVER downloads, installs or runs anything. HTTPS only, short timeout, size limit, strict validation, once a day, silent when offline."""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from . import __version__

MAX_BYTES = 64 * 1024
_VER = re.compile(r"^v?(\d+(?:\.\d+){0,3})([-+][0-9A-Za-z.\-+]*)?$")


def parse_version(s):
    """'6.4.0' -> (6, 4, 0, 0, 1). A '-beta' style suffix makes it OLDER than the plain release; '+build' metadata is ignored."""
    m = _VER.match(str(s).strip())
    if not m:
        raise ValueError(f"Not a version number: {str(s)[:30]!r}")
    nums = [int(x) for x in m.group(1).split(".")]
    nums += [0] * (4 - len(nums))
    return tuple(nums) + (0 if (m.group(2) or "").startswith("-") else 1,)


def is_newer(remote, local=__version__):
    return parse_version(remote) > parse_version(local)


def validate_manifest(obj):
    if not isinstance(obj, dict):
        raise ValueError("The update file is not a JSON object")
    ver, notes, dl = obj.get("version"), obj.get("notes", ""), obj.get("download", "")
    if not isinstance(ver, str):
        raise ValueError("The update file has no version")
    parse_version(ver)
    if not isinstance(notes, str):
        raise ValueError("The update notes must be text")
    if not isinstance(dl, str) or not dl.lower().startswith("https://") or len(dl) > 500 or any(c in dl for c in " \t\r\n<>\"'"):
        raise ValueError("The download link must be a plain https:// link")
    notes = "".join(ch for ch in notes if ch == "\n" or ch >= " ")[:2000]
    return dict(version=ver.strip(), notes=notes, download=dl)


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("Refusing a redirect to a non-https address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_manifest(url, opener=None, timeout=6):
    if not str(url).lower().startswith("https://"):
        raise ValueError("The update link must start with https://")
    op = opener or urllib.request.build_opener(_HttpsOnly)
    req = urllib.request.Request(url, headers={"User-Agent": f"VeloPOS/{__version__}", "Accept": "application/json"})
    with op.open(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("The update file is too large")
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("The update file is not valid JSON")
    return validate_manifest(obj)


def check(cfg, now=None, opener=None, force=False):
    """-> dict(status = off | no_url | skipped | error | current | newer, ...).  At most one real check per 24 hours unless force=True.
    The time of the attempt is stored even when it fails, so an offline PC is not retried every minute."""
    if not force and not cfg.bool("feat_update_check"):
        return dict(status="off")
    url = cfg.get("update_url").strip()
    if not url:
        return dict(status="no_url")
    now = now or datetime.now()
    if not force:
        try:
            if now - datetime.fromisoformat(cfg.get("last_update_check")) < timedelta(hours=24):
                return dict(status="skipped")
        except ValueError:
            pass
    cfg.set_many({"last_update_check": now.isoformat(timespec="seconds")})
    try:
        m = fetch_manifest(url, opener)
    except Exception as e:                                  # offline, DNS, timeout, bad file ... never raised to the caller
        return dict(status="error", error=str(e))
    if is_newer(m["version"]):
        cfg.set_many({"update_info": json.dumps(m)})
        return dict(status="newer", **m)
    cfg.set_many({"update_info": ""})
    return dict(status="current", version=m["version"])
