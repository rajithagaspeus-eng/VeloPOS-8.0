"""One-time codes (OTP) and their delivery by e-mail (SMTP) or a WhatsApp link. No UI code.

Honest security notes:
* Email OTP (owner's own Gmail + App Password) is the stronger channel.
* WhatsApp OTP here is only a wa.me link opened on THIS PC with the code pre-filled - anyone at the PC
  can read it. It is a convenience, not strong security.
* Offline fallback = the Recovery Code created at first setup.
"""
import hashlib, hmac, secrets, smtplib, socket, ssl, time, urllib.parse
from email.message import EmailMessage

from . import database as dbm, security

OTP_DIGITS, OTP_TTL, OTP_TRIES = 6, 300, 3       # 6 digits, 5 minutes, 3 attempts
_now = time.time


class OtpManager:
    """Codes live in memory only, stored as salted hashes. One active code per purpose."""

    def __init__(self):
        self._s = {}

    @staticmethod
    def _h(salt, code):
        return hashlib.sha256(salt + code.encode()).digest()

    def issue(self, purpose):
        code = f"{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}"
        salt = secrets.token_bytes(8)
        self._s[purpose] = dict(salt=salt, h=self._h(salt, code), exp=_now() + OTP_TTL, left=OTP_TRIES)
        return code

    def cancel(self, purpose):
        self._s.pop(purpose, None)

    def pending(self, purpose):
        s = self._s.get(purpose)
        return bool(s and _now() <= s["exp"] and s["left"] > 0)

    def verify(self, purpose, code):
        """-> (ok, message). A code works once; 3 wrong tries or 5 minutes kill it."""
        s = self._s.get(purpose)
        if not s:
            return False, "No code has been sent. Press 'Send code' first."
        if _now() > s["exp"]:
            del self._s[purpose]
            return False, "The code has expired. Request a new one."
        code = "".join(ch for ch in str(code) if ch.isdigit())
        if hmac.compare_digest(s["h"], self._h(s["salt"], code)):
            del self._s[purpose]
            return True, "OK"
        s["left"] -= 1
        if s["left"] <= 0:
            del self._s[purpose]
            return False, "Wrong code. No attempts left - request a new code."
        return False, f"Wrong code. {s['left']} attempt(s) left."


otp = OtpManager()


# ------------------------------------------------------------------ SMTP (e-mail)
def smtp_config(cfg=None):
    cfg = cfg or dbm.settings
    return dict(host=cfg.get("smtp_host").strip(), port=cfg.int("smtp_port", 465),
                user=cfg.get("smtp_user").strip(), password=security.vault_decrypt(cfg.get("smtp_pass_enc")))


def has_smtp_password(cfg=None):
    return bool(smtp_config(cfg)["password"])


def set_smtp_password(plain):
    """Stores the App Password ENCRYPTED (machine-derived key). Empty string forgets it."""
    dbm.settings.set_many({"smtp_pass_enc": security.vault_encrypt(plain) if plain else ""})


def email_ready(cfg=None):
    cfg = cfg or dbm.settings
    c = smtp_config(cfg)
    return bool(c["host"] and c["user"] and c["password"] and cfg.get("owner_email").strip())


def mask_email(addr):
    name, _, dom = addr.partition("@")
    return (name[:1] + "***@" + dom) if dom else "***"


def send_email(to, subject, body, conf=None, html=None):
    c = conf or smtp_config()
    if not (c["host"] and c["user"] and c["password"]):
        raise ValueError("E-mail is not set up. Enter your Gmail address and App Password in Settings -> 4c.")
    if not to or "@" not in to:
        raise ValueError("Enter a valid owner e-mail address in Settings -> 4c.")
    port = int(c["port"])
    if port not in (465, 587) and c["host"] not in ("localhost", "127.0.0.1"):
        raise ValueError("Use SMTP port 465 (SSL) or 587 (STARTTLS).")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["user"], to, subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    try:
        srv = smtplib.SMTP_SSL(c["host"], port, timeout=15, context=ctx) if port == 465 \
            else smtplib.SMTP(c["host"], port, timeout=15)
        with srv:
            if port == 587:
                srv.starttls(context=ctx)
            srv.login(c["user"], c["password"])
            srv.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("The mail server rejected the login. For Gmail you must use a 16-character App Password "
                           "(Google Account -> Security -> 2-Step Verification -> App passwords), not your normal password.")
    except (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError):
        raise RuntimeError("Cannot reach the mail server. Check the internet connection, SMTP server and port.")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Mail server error: {e}")


def send_otp_email(code, purpose, cfg=None):
    cfg = cfg or dbm.settings
    shop = cfg.get("shop_name")
    send_email(cfg.get("owner_email").strip(), f"{shop} - VeloPOS security code",
               f"Your VeloPOS code for '{purpose}' is:\n\n    {code}\n\n"
               f"It is valid for {OTP_TTL // 60} minutes and works once.\n"
               "If you did not request this, ignore this e-mail and consider changing your passwords.\n")


# ------------------------------------------------------------------ WhatsApp (manual, convenience only)
def normalize_phone(raw):
    ph = "".join(ch for ch in str(raw) if ch.isdigit())
    if ph.startswith("0") and len(ph) == 10:        # Sri Lankan local format 07x xxx xxxx
        ph = "94" + ph[1:]
    return ph


def whatsapp_link(phone, text):
    """wa.me link with the text pre-filled; the owner still has to press Send in WhatsApp."""
    ph = normalize_phone(phone)
    if not ph:
        raise ValueError("Enter the owner's WhatsApp number in Settings -> 4c.")
    return f"https://wa.me/{ph}?text=" + urllib.parse.quote(text)


def whatsapp_otp_url(phone, code, purpose, shop=""):
    return whatsapp_link(phone, f"{shop + ' - ' if shop else ''}VeloPOS {purpose} code: {code} (valid {OTP_TTL // 60} minutes)")
