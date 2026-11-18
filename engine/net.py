"""Polite HTTP: timeouts, retries with backoff, robots.txt respect, no paywall bypass."""
import time, urllib.robotparser
from urllib.parse import urlparse
import requests

from .config import settings

_session = None
_robots = {}


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": settings()["user_agent"],
                                 "Accept-Language": "en,ar;q=0.8"})
    return _session


def allowed_by_robots(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = session().get(base + "/robots.txt", timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(settings()["user_agent"], url)


def get(url, check_robots=False, **kw):
    """Returns (response|None, error|None). Never raises."""
    cfg = settings()
    if check_robots and not allowed_by_robots(url):
        return None, "blocked by robots.txt"
    err = None
    for i in range(cfg["retry"]["attempts_per_run"]):
        try:
            r = session().get(url, timeout=cfg["request_timeout"], allow_redirects=True, **kw)
            if r.status_code == 200:
                return r, None
            err = f"HTTP {r.status_code}"
            if r.status_code in (401, 402, 403, 404, 410):
                break  # no point retrying now; logged and retried next run
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
        time.sleep(cfg["retry"]["backoff_seconds"] * (i + 1))
    return None, err
