"""Every web request VeloPOS makes carries a real User-Agent ("VeloPOS/<version>") instead of Python's default "Python-urllib/3.x".

Why: Cloudflare (and many hosts) refuse the default Python User-Agent with a 403 before the request reaches our Worker. That made the
owner-dashboard upload and the online trial check fail silently. licence.py must not be edited, so the header is set here, once, for
every urllib opener in the program."""
import urllib.request


def install():
    cls = urllib.request.OpenerDirector
    if getattr(cls, "_velopos_ua", False):
        return
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        from . import __version__
        self.addheaders = [("User-Agent", f"VeloPOS/{__version__}")]
    cls.__init__ = init
    cls._velopos_ua = True
