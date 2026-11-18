"""Sources Registry: seed sync + real validation (homepage reachability, RSS autodiscovery, feed test).
RSS is marked 'working' ONLY after the feed downloads and parses with >=1 entry."""
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser

from . import db, net
from .config import seed_sources

COMMON_FEED_PATHS = ["feed/", "rss/", "feed", "rss", "rss.xml", "feed.xml", "atom.xml", "index.xml"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sync_seed(con):
    """Insert new seed sources; keep validation results of existing ones."""
    existing = {r["source_id"]: r for r in db.rows(con, "SELECT * FROM sources")}
    for s in seed_sources():
        row = existing.get(s["id"], {})
        row.update({"source_id": s["id"], "name": s["name"], "url": s["url"], "category": s["category"],
                    "geo": s["geo"], "topics": s["topics"], "source_type": s["type"], "official": s["official"],
                    "frequency": s["frequency"], "reliability": s["reliability"],
                    "discovered": "yes" if s.get("discovered") else "no"})
        row.setdefault("active", "yes")
        row.setdefault("rss_status", "pending validation")
        row.setdefault("collection_method", "pending")
        row.setdefault("consecutive_failures", "0")
        if s.get("rss") and not row.get("rss_url"):
            row["rss_url"] = s["rss"]
        db.upsert(con, "sources", row, "source_id")
    con.commit()


def test_feed(url):
    r, err = net.get(url, attempts=1)
    if not r:
        return False, err
    f = feedparser.parse(r.content)
    if f.entries:
        return True, f"{len(f.entries)} entries"
    return False, "no entries / not a feed"


def discover_feeds(html, base):
    cands = []
    for m in re.finditer(r"<link[^>]+>", html, re.I):
        tag = m.group(0)
        if re.search(r"type=[\"']application/(rss|atom)\+xml", tag, re.I):
            h = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if h:
                cands.append(urljoin(base, h.group(1)))
    return cands


def validate_source(row):
    notes = []
    url = row["url"]
    r, err = net.get(url, attempts=1)
    homepage_ok = r is not None
    html = r.text if r else ""
    if not homepage_ok:
        notes.append(f"homepage: {err}")
    row["newsletter_status"] = ("detected (manual signup)" if re.search(r"newsletter|subscribe", html, re.I)
                                else ("unknown" if not homepage_ok else "not found"))
    candidates = []
    if row.get("rss_url"):
        candidates.append(row["rss_url"])
    candidates += discover_feeds(html, r.url if r else url)
    p = urlparse(url)
    section = url if url.endswith("/") else url + "/"
    root = f"{p.scheme}://{p.netloc}/"
    for path in COMMON_FEED_PATHS:
        for base in dict.fromkeys([section, root]):
            candidates.append(urljoin(base, path))
    seen, working = set(), None
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        ok, info = test_feed(c)
        if ok:
            working = c
            notes.append(f"rss ok: {info}")
            break
        if len(seen) >= 8:  # stay polite
            break
    if working:
        row.update(rss_url=working, rss_status="working (tested)", collection_method="rss")
    else:
        row.update(rss_url="", rss_status="not found" if homepage_ok else "unverified (site unreachable)",
                   collection_method="search_discovery")
        notes.append("no working RSS; will use Google News site: search")
    row["last_checked"] = now()
    row["active"] = "yes"
    row["error_notes"] = "; ".join(notes)[:500]
    return row


def validate_all(con, only_pending=False, log=print):
    sync_seed(con)
    srcs = db.rows(con, "SELECT * FROM sources ORDER BY source_id")
    for s in srcs:
        if only_pending and s.get("rss_status") not in (None, "", "pending validation"):
            continue
        s = validate_source(s)
        db.upsert(con, "sources", s, "source_id")
        con.commit()
        log(f"[validate] {s['source_id']} {s['name']}: {s['rss_status']} | {s['collection_method']} | {s['error_notes']}")
    return db.rows(con, "SELECT * FROM sources ORDER BY source_id")
