"""Normalization, date validation and duplicate detection."""
import hashlib, html, re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from . import db
from .config import settings

TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_|cmpid|ito|sr_share)")


def canonical(url):
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k)]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower().replace("www.", ""), path, "", urlencode(q), ""))


def title_key(title):
    t = re.sub(r"[^\w\s]", " ", title.lower())
    toks = sorted({w for w in t.split() if len(w) > 2})[:12]
    return hashlib.sha1(" ".join(toks).encode()).hexdigest()[:16]


def clean_text(s, limit=None):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


def date_status(pub, now):
    if not pub:
        return "missing publication date"
    d = datetime.fromisoformat(pub)
    if d > now + timedelta(days=1):
        return "invalid (future date)"
    if now - d > timedelta(hours=settings()["fresh_window_hours"]):
        return "older article (not breaking)"
    return "fresh"


def process(con, raw_items, log=print):
    """Returns (new_records, duplicates_prevented)."""
    now = datetime.now(timezone.utc)
    known = {r["duplicate_key"] for r in db.rows(con, "SELECT duplicate_key FROM news")}
    recent_titles = {r["title_key"]: r["news_id"] for r in db.rows(
        con, "SELECT title_key, news_id FROM news WHERE collected_at >= ?",
        ((now - timedelta(days=14)).isoformat(),))}
    new, dupes, batch_keys = [], 0, set()
    for it in raw_items:
        dk = hashlib.sha1(canonical(it["url"]).encode()).hexdigest()[:20]
        if dk in known or dk in batch_keys:
            dupes += 1
            continue
        tk = title_key(it["headline"])
        rec = dict(it)
        rec.update({
            "news_id": "N" + now.strftime("%Y%m%d") + "-" + dk[:8],
            "canonical_url": canonical(it["url"]),
            "duplicate_key": dk, "title_key": tk,
            "collected_at": now.isoformat(timespec="seconds"),
            "date_status": date_status(it.get("published_at"), now),
            "teaser": clean_text(it.get("raw_summary"), 600),
        })
        if tk in recent_titles:
            rec["duplicate_of"] = recent_titles[tk]
            rec["editorial_status"] = "duplicate (linked to original)"
            dupes += 1
        else:
            recent_titles[tk] = rec["news_id"]
        batch_keys.add(dk)
        new.append(rec)
    log(f"[process] {len(new)} new records, {dupes} duplicates prevented/linked")
    return new, dupes
