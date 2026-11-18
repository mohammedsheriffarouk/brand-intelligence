"""Orchestration + logging + status dashboard."""
import json, shutil, sqlite3, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import analyze, arabic, collect, db, enrich, notify, process, report, sheets, sources
from .config import settings

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "Logs"


class Logger:
    def __init__(self, kind):
        LOGS.mkdir(exist_ok=True)
        self.path = LOGS / f"{kind}_{datetime.now(timezone.utc):%Y-%m-%d}.log"
        self.f = open(self.path, "a", encoding="utf-8")

    def __call__(self, msg):
        line = f"{datetime.now(timezone.utc):%H:%M:%S} {msg}"
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def _source_for(item, by_id, by_domain):
    if item.get("source_id") in by_id:
        return by_id[item["source_id"]]
    dom = urlparse(item.get("publisher_url") or "").netloc.replace("www.", "")
    if dom in by_domain:
        item["source_id"] = by_domain[dom]["source_id"]
        return by_domain[dom]
    return {"source_id": "SEARCH", "name": item.get("source_name") or "Unknown", "reliability": 0,
            "official": "secondary", "category": None, "geo": "Global"}


def backup():
    src = db.DB_PATH
    if not src.exists():
        return
    bdir = ROOT / "Database" / "backups"
    bdir.mkdir(exist_ok=True)
    dst = bdir / f"news_{datetime.now(timezone.utc):%Y-%m-%d}.sqlite"
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    for old in sorted(bdir.glob("news_*.sqlite"))[:-14]:   # keep 14 daily backups (+ full git history)
        old.unlink()


def run_daily(notify_on=True, force=False):
    log = Logger("daily")
    con = db.connect()
    run_id = "R" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = {"sources_checked": 0, "sources_failed": 0, "items_seen": 0, "items_new": 0, "duplicates_prevented": 0}
    status, notes, recs = "ok", [], []
    try:
        backup()
        sources.validate_all(con, only_pending=True, log=log)   # validates new sources once
        raw, stats["sources_checked"], stats["sources_failed"] = collect.collect(con, run_id, log, force=force)
        stats["items_seen"] = len(raw)
        recs, stats["duplicates_prevented"] = process.process(con, raw, log)
        srcs = db.rows(con, "SELECT * FROM sources")
        by_id = {s["source_id"]: s for s in srcs}
        by_domain = {urlparse(s["url"]).netloc.replace("www.", ""): s for s in srcs}
        for r in recs:
            analyze.analyze(r, _source_for(r, by_id, by_domain))
        enrich.enrich(recs, log)
        for r in recs:
            if r.pop("_enriched", False):   # publisher summary found -> re-classify/score with the richer text
                analyze.analyze(r, _source_for(r, by_id, by_domain))
        arabic.arabize(recs, log)
        for r in recs:
            r.pop("_type", None)
            db.upsert(con, "news", r, "news_id")
        con.commit()
        stats["items_new"] = len([r for r in recs if not r.get("duplicate_of")])
        log(f"[score] {sum(r['priority']=='High Priority' for r in recs)} high, "
            f"{sum(r['priority']=='Worth Following' for r in recs)} follow, {sum(r['priority']=='Reject' for r in recs)} rejected")
        rep = report.build(con, "daily")
        log(f"[report] {rep['html'].name} | pdf={'yes' if rep['pdf'] else 'no'} | png={'yes' if rep['png'] else 'no'}")
        db.export(con)
        if notify_on:
            notes.append("email:" + notify.send_email(rep, log))
            notes.append("telegram:" + notify.send_telegram(rep, log))
            notes.append(f"alerts:{notify.critical_alerts(recs, log)}")
    except Exception as e:
        status = "error"
        notes.append(f"{type(e).__name__}: {e}")
        log(traceback.format_exc())
    con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "daily", started, datetime.now(timezone.utc).isoformat(timespec="seconds"), status,
                 stats["sources_checked"], stats["sources_failed"], stats["items_seen"], stats["items_new"],
                 stats["duplicates_prevented"], "; ".join(notes)))
    con.commit()
    try:
        sheets.sync(con, recs if status == "ok" else [], log)
    except Exception as e:
        log(f"[sheets] error {e}")
    db.export(con)
    dashboard(con)
    log(f"[done] {status} {json.dumps(stats)} {notes}")
    return status


def rescore(log=None, resend=False):
    """Re-apply current classification/scoring rules to every stored article (after rule changes) and resync the Sheet."""
    log = log or Logger("rescore")
    con = db.connect()
    srcs = db.rows(con, "SELECT * FROM sources")
    by_id = {s["source_id"]: s for s in srcs}
    by_domain = {urlparse(s["url"]).netloc.replace("www.", ""): s for s in srcs}
    rows = db.rows(con, "SELECT * FROM news")
    junk = 0
    for row in rows:
        if process.is_junk(row["headline"]):
            row.update(priority="Reject", editorial_status="Rejected (non-article page)", overall_score="0")
            junk += 1
        else:
            old_geo = db.loads(row.get("geography"), [])
            rec = {k: row.get(k) for k in ("news_id", "headline", "url", "published_at", "image_url", "source_id",
                                           "source_name", "date_status", "duplicate_of", "via")}
            rec["teaser"] = row.get("teaser") or (row.get("detailed_summary") or "").replace("[Publisher excerpt] ", "").replace("Not Disclosed", "")
            rec["geo_hint"] = next((g for g in old_geo if g in analyze.MENA), None)
            analyze.analyze(rec, _source_for(rec, by_id, by_domain))
            rec.pop("_type", None)
            row.update({k: v for k, v in rec.items() if k != "geo_hint"})
            if row.get("duplicate_of"):
                row["editorial_status"] = "duplicate (linked to original)"
    arabic.arabize(rows, log)
    for row in rows:
        db.upsert(con, "news", row, "news_id")
    con.commit()
    log(f"[rescore] {len(rows)} articles re-scored, {junk} marked as non-article pages")
    db.export(con)
    sheets.sync(con, rows, log)
    rep = report.build(con, "daily")
    if resend:   # re-send today's brief after a rebuild (clears today's "already sent" marks)
        sent = json.loads(notify.SENT.read_text()) if notify.SENT.exists() else {}
        sent = {k: v for k, v in sent.items() if rep["fname"] not in k}
        notify.SENT.write_text(json.dumps(sent, indent=1))
        notify.send_email(rep, log)
        notify.send_telegram(rep, log)
    dashboard(con)


def run_periodic(kind, notify_on=True):
    log = Logger(kind)
    con = db.connect()
    rep = report.build(con, kind)
    log(f"[report] {rep['html'].name} ({len(rep['rows'])} stories) pdf={'yes' if rep['pdf'] else 'no'}")
    if notify_on:
        notify.send_email(rep, log)
        notify.send_telegram(rep, log)
    dashboard(con)
    return "ok"


def dashboard(con):
    s = db.rows(con, "SELECT * FROM sources")
    n_total = db.rows(con, "SELECT COUNT(*) c FROM news")[0]["c"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n_today = db.rows(con, "SELECT COUNT(*) c FROM news WHERE collected_at LIKE ? AND (duplicate_of IS NULL OR duplicate_of='')", (today + "%",))[0]["c"]
    n_high = db.rows(con, "SELECT COUNT(*) c FROM news WHERE priority='High Priority'")[0]["c"]
    dup = db.rows(con, "SELECT COALESCE(SUM(duplicates_prevented),0) c FROM runs")[0]["c"]
    last = db.rows(con, "SELECT * FROM runs WHERE status='ok' ORDER BY started_at DESC LIMIT 1")
    failed = [x for x in s if int(x.get("consecutive_failures") or 0) > 0]
    nxt = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=4, minute=17, second=0)
    data = {"Total registered sources": len(s), "Active sources": sum(x.get("active") == "yes" for x in s),
            "Working RSS feeds": sum(x.get("collection_method") == "rss" for x in s),
            "Sources using other methods": sum(x.get("collection_method") not in ("rss",) for x in s),
            "Pending validation": sum(x.get("collection_method") == "pending" for x in s),
            "Total collected articles": n_total, "New articles today": n_today, "High priority articles (all time)": n_high,
            "Duplicate articles prevented": dup, "Failed sources (current)": len(failed),
            "Last successful execution (UTC)": last[0]["finished_at"] if last else "never",
            "Next scheduled execution (UTC, approx.)": nxt.strftime("%Y-%m-%d %H:%M")}
    (ROOT / "Reports").mkdir(exist_ok=True)
    (ROOT / "Reports" / "status.json").write_text(json.dumps({"status": data, "failed_sources": [
        {"id": x["source_id"], "name": x["name"], "error": x.get("error_notes")} for x in failed]}, indent=1, ensure_ascii=False))
    # live viewer (reads Google Sheet via Apps Script doGet; falls back to published JSON copy)
    import os
    api = os.getenv("SHEETS_WEBAPP_URL", "")
    v = (Path(__file__).parent / "templates" / "viewer.html").read_text(encoding="utf-8")
    (ROOT / "Reports" / "viewer.html").write_text(v.replace('<script>\nconst API', f'<script>window.BI_API={json.dumps(api)};</script>\n<script>\nconst API', 1), encoding="utf-8")
    (ROOT / "Reports" / "data").mkdir(exist_ok=True)
    keep = ["news_id", "collected_at", "published_at", "priority", "overall_score", "headline", "headline_ar", "summary_ar",
            "source_name", "url", "image_url", "main_category", "news_type", "geography", "short_summary", "duplicate_of"]
    recent = db.rows(con, "SELECT * FROM news WHERE collected_at >= ?", ((datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),))
    (ROOT / "Reports" / "data" / "news.json").write_text(json.dumps([{k: r.get(k) for k in keep} for r in recent], ensure_ascii=False), encoding="utf-8")
    reps = sorted((ROOT / "Reports").glob("*/Brand_Intelligence_*.html"), reverse=True)[:40]
    li = "".join(f'<li><a href="{p.parent.name}/{p.name}">{p.stem.replace("Brand_Intelligence_", "").replace("_", " ")}</a>'
                 + (f' · <a href="{p.parent.name}/{p.stem}.pdf">PDF</a>' if p.with_suffix(".pdf").exists() else "") + "</li>" for p in reps)
    rows = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in data.items())
    fl = "".join(f"<li>{x['source_id']} {x['name']}: {x.get('error_notes') or ''}</li>" for x in failed) or "<li>None</li>"
    (ROOT / "Reports" / "index.html").write_text(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brand Intelligence — Status</title><style>body{{font:15px/1.5 system-ui,sans-serif;max-width:760px;margin:auto;padding:24px;background:#FBF8F4;color:#14110F}}
h1{{font-family:Georgia,serif}}table{{border-collapse:collapse;width:100%;background:#fff}}td{{border:1px solid #E6E0D8;padding:7px 10px}}a{{color:#C2410C}}
.btn{{display:inline-block;background:#14110F;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;margin:8px 0}}</style></head><body>
<h1>Brand Intelligence</h1><a class="btn" href="viewer.html">Open the live viewer (Google Sheet) →</a>
<h2>System status</h2><table>{rows}</table><h2>Reports</h2><ul>{li}</ul><h2>Failing sources</h2><ul>{fl}</ul></body></html>""", encoding="utf-8")
    return data
