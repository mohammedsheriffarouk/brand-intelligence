"""Collection engine: RSS first, Google News RSS search discovery second. Failed != empty."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlparse

import feedparser

from . import db, net
from .config import settings

GN = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"


def _dt(struct):
    if not struct:
        return None
    return datetime(*struct[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")


def _image(e):
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in e.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    html = " ".join([e.get("summary", "")] + [c.get("value", "") for c in e.get("content", []) or []])
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)", html, re.I)
    return m.group(1) if m else None


def parse_feed(content, source, via):
    f = feedparser.parse(content)
    items = []
    for e in f.entries[: settings()["max_items_per_feed"]]:
        title = (e.get("title") or "").strip()
        link = e.get("link")
        if not title or not link:
            continue
        publisher = None
        if via == "google_news":
            src = e.get("source") or {}
            publisher = src.get("title")
            if publisher and title.endswith(" - " + publisher):
                title = title[: -len(publisher) - 3]
        items.append({
            "headline": title, "url": link,
            "published_at": _dt(e.get("published_parsed")),
            "updated_at": _dt(e["updated_parsed"]) if "updated" in e and e.get("updated") != e.get("published") else None,
            "raw_summary": e.get("summary", ""),
            "image_url": None if via == "google_news" else _image(e),
            "source_id": source.get("source_id"), "source_name": publisher or source.get("name"),
            "publisher_url": (e.get("source") or {}).get("href") if via == "google_news" else source.get("url"),
            "via": via,
        })
    return items, (None if f.entries or not f.bozo else f"parse error: {f.bozo_exception}"[:200])


def due(source, now):
    """Due if never collected, if last attempt failed (retry every run), or by frequency."""
    if source.get("active") != "yes":
        return False
    last = source.get("last_success")
    if not last or int(source.get("consecutive_failures") or 0) > 0:
        return True
    age = now - datetime.fromisoformat(last)
    if source.get("frequency") == "weekly":
        return age > timedelta(days=6, hours=12)
    return age > timedelta(hours=12)


def gnews(query, lang="en", lookback="2d"):
    hl, gl = ("ar", "EG") if lang == "ar" else ("en-US", "US")
    return GN.format(q=quote_plus(f"{query} when:{lookback}"), hl=hl, gl=gl, lang=lang if lang == "ar" else "en")


def collect(con, run_id, log=print, force=False):
    now = datetime.now(timezone.utc)
    cfg = settings()
    all_items, checked, failed = [], 0, 0
    sources = db.rows(con, "SELECT * FROM sources ORDER BY source_id")
    for s in sources:
        if not force and not due(s, now):
            continue
        checked += 1
        method = s.get("collection_method")
        if method == "rss" and s.get("rss_url"):
            url, via = s["rss_url"], "rss"
        else:
            dom = urlparse(s["url"]).netloc.replace("www.", "")
            path = urlparse(s["url"]).path.strip("/")
            q = f"site:{dom}" + (f"/{path.split('/')[0]}" if path and s["category"] != "B_agency" else "")
            url, via = gnews(q, "en", "7d" if s.get("frequency") == "weekly" else cfg["search_discovery"]["lookback"]), "google_news"
        r, err = net.get(url)
        items, perr = parse_feed(r.content, s, via) if r else ([], None)
        err = err or perr
        status = "ok" if not err else "failed"
        s["last_checked"] = now.isoformat(timespec="seconds")
        if status == "ok":
            s["last_success"] = s["last_checked"]
            s["consecutive_failures"] = "0"
            if via == "google_news":  # keep source attribution even when found via search
                for it in items:
                    it["source_id"] = s["source_id"]
        else:
            failed += 1
            n = int(s.get("consecutive_failures") or 0) + 1
            s["consecutive_failures"] = str(n)
            s["error_notes"] = f"{s['last_checked']} {via}: {err}"[:500]
            if n >= cfg["retry"]["disable_after_consecutive_failures"]:
                s["frequency"] = "weekly"  # back off, never silently drop
        db.upsert(con, "sources", s, "source_id")
        con.execute("INSERT INTO collection_log VALUES (?,?,?,?,?,?,?)",
                    (s["last_checked"], run_id, s["source_id"], via, status, len(items), err))
        log(f"[collect] {s['source_id']} {s['name']} via {via}: {status} ({len(items)} items){' ' + err if err else ''}")
        all_items += items
    # thematic + regional discovery
    sd = cfg["search_discovery"]
    if sd.get("enabled"):
        for qd in sd["queries"]:
            url = gnews(qd["q"], qd.get("lang", "en"), sd["lookback"])
            r, err = net.get(url)
            items, perr = parse_feed(r.content, {"source_id": "SEARCH", "name": "Search discovery"}, "google_news") if r else ([], None)
            err = err or perr
            for it in items:
                it["geo_hint"] = qd.get("geo")
            con.execute("INSERT INTO collection_log VALUES (?,?,?,?,?,?,?)",
                        (now.isoformat(timespec="seconds"), run_id, "SEARCH:" + qd["q"][:40], "google_news",
                         "ok" if not err else "failed", len(items), err))
            log(f"[discover] '{qd['q']}': {len(items)} items{' ' + err if err else ''}")
            all_items += items
    con.commit()
    return all_items, checked, failed
