"""Offline end-to-end test with SYNTHETIC fixture feeds (clearly fake data, example.com links).
Proves: validation/autodiscovery, collection, failed-source handling, dedup, date logic, classification,
scoring rules, DB + exports, reports (HTML/MD/PDF/PNG), notifications (mocked SMTP/Telegram), no duplicate sends."""
import importlib, json, shutil, sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{l}</link><pubDate>{format_datetime(d)}</pubDate>"
        f"<description><![CDATA[{desc}]]></description>{img}</item>" for t, l, d, desc, img in items)
    return f'<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>t</title>{body}</channel></rss>'.encode()


class Resp:
    def __init__(self, content, url):
        self.content = content
        self.text = content.decode("utf-8", "ignore")
        self.url = url
        self.status_code = 200


@pytest.fixture()
def env(tmp_path, monkeypatch):
    work = tmp_path / "bi"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("Database", "Reports", "Logs", "tests", ".git", "__pycache__"))
    for d in ("Database", "Reports", "Logs"):
        (work / d).mkdir()
    (work / "Configuration" / "telegram_chat.json").unlink(missing_ok=True)
    # minimal 4-source registry
    (work / "Configuration" / "sources_seed.yaml").write_text("""sources:
- {id: T01, name: Test Branding Mag, url: "https://brandmag.example.com/", category: A_branding_news, geo: Global, topics: x, type: Publication, official: secondary, reliability: 5, frequency: daily}
- {id: T02, name: Test Tool Vendor, url: "https://tool.example.com/news", category: E_tools_ai, geo: Global, topics: x, type: Vendor, official: official, reliability: 5, frequency: daily}
- {id: T03, name: Test Gulf Business, url: "https://gulf.example.com/", category: G_mena, geo: Saudi Arabia, topics: x, type: Publication, official: secondary, reliability: 3, frequency: daily}
- {id: T04, name: Test Dead Site, url: "https://dead.example.com/", category: B_agency, geo: Global, topics: x, type: Agency, official: official, reliability: 5, frequency: daily}
""")
    s = (work / "Configuration" / "settings.yaml").read_text().replace("enabled: true\n  provider: google_news_rss", "enabled: false\n  provider: google_news_rss")
    (work / "Configuration" / "settings.yaml").write_text(s.replace("backoff_seconds: 4", "backoff_seconds: 0"))
    now = datetime.now(timezone.utc)
    img = '<media:content url="https://img.example.com/a.jpg" medium="image"/>'
    feeds = {
        "https://brandmag.example.com/": b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed/"></head><body>newsletter</body></html>',
        "https://brandmag.example.com/feed/": rss([
            ("Acme Bank rebrands with new visual identity by Pentagram", "https://brandmag.example.com/acme?utm_source=x", now - timedelta(hours=3),
             "Acme Bank, a Riyadh-based lender, has unveiled a new logo and brand identity designed by Pentagram. The rebrand follows a strategy review.", img),
            ("Coca-Cola brand value rises 8% to $58 billion in Brand Finance ranking", "https://brandmag.example.com/coke", now - timedelta(hours=5),
             "The Brand Finance Global 500 report says Coca-Cola's brand value rose 8 per cent to $58 billion.", ""),
            ("A look back at 1990s logos", "https://brandmag.example.com/old", now - timedelta(days=9),
             "Nostalgic feature about logos from the 1990s and their typography.", ""),
        ]),
        "https://tool.example.com/news": b"<html><head></head><body>no feed link</body></html>",
        "https://tool.example.com/news/feed/": rss([
            ("Figma launches new AI feature for design systems", "https://tool.example.com/news/ai", now - timedelta(hours=2),
             "Figma introduced a generative AI feature that helps teams maintain design systems. Available in beta.", ""),
        ]),
        "https://gulf.example.com/": b'<html><head><link rel="alternate" type="application/atom+xml" href="https://gulf.example.com/rss.xml"></head></html>',
        "https://gulf.example.com/rss.xml": rss([
            ("Saudi telecom STC reports revenue of SAR 19 billion", "https://gulf.example.com/stc", now - timedelta(hours=6),
             "STC said revenue reached SAR 19 billion in the quarter, up 6% year on year.", ""),
            # same story, different URL -> must be linked as duplicate by title
            ("Acme Bank rebrands with new visual identity by Pentagram", "https://gulf.example.com/acme-copy", now - timedelta(hours=1),
             "Copy of the Acme story.", ""),
        ]),
    }

    def fake_get(url, check_robots=False, **kw):
        if url in feeds:
            return Resp(feeds[url], url), None
        return None, "HTTP 404" if "dead" not in url else "ConnectionError: unreachable"

    monkeypatch.chdir(work)
    for m in [m for m in list(sys.modules) if m.startswith("engine")]:
        del sys.modules[m]
    sys.path.insert(0, str(work))
    import engine.config, engine.net
    importlib.reload(engine.config)
    monkeypatch.setattr(engine.net, "get", fake_get)
    for k in ["SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SHEETS_WEBAPP_URL", "SHEETS_SECRET"]:
        monkeypatch.delenv(k, raising=False)
    yield work
    sys.path.remove(str(work))


def test_end_to_end(env, monkeypatch):
    from engine import db, pipeline, notify
    sent = {"email": 0, "tg": []}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, u, p): pass
        def send_message(self, m):
            sent["email"] += 1
            assert m["Subject"].startswith("Brand Intelligence · النشرة اليومية · ")
            assert any(p.get_filename() and p.get_filename().endswith(".pdf") for p in m.iter_attachments())

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(notify, "_tg", lambda method, data=None, files=None: sent["tg"].append(method))
    for k, v in {"SMTP_USER": "me@example.com", "SMTP_PASSWORD": "x", "EMAIL_TO": "me@example.com",
                 "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}.items():
        monkeypatch.setenv(k, v)

    assert pipeline.run_daily(notify_on=True) == "ok"
    con = db.connect(env / "Database" / "news.sqlite")
    src = {s["source_id"]: s for s in db.rows(con, "SELECT * FROM sources")}
    # --- source validation: tested feeds only
    assert src["T01"]["collection_method"] == "rss" and src["T01"]["rss_url"].endswith("/feed/")
    assert src["T02"]["rss_status"] == "working (tested)"            # found by testing common path, not invented
    assert src["T03"]["rss_url"] == "https://gulf.example.com/rss.xml"
    assert src["T04"]["collection_method"] == "search_discovery"      # dead site -> fallback, flagged
    assert int(src["T04"]["consecutive_failures"]) >= 1               # failed != empty: logged
    assert src["T01"]["newsletter_status"].startswith("detected")
    news = {n["headline"][:20]: n for n in db.rows(con, "SELECT * FROM news WHERE duplicate_of IS NULL")}
    acme = news["Acme Bank rebrands w"]
    # --- classification
    assert acme["news_type"].startswith("N02") and "Saudi Arabia" in acme["geography"]
    assert "Pentagram" in acme["related_agencies"] and acme["image_url"] == "https://img.example.com/a.jpg"
    assert "utm_source" not in acme["canonical_url"]
    coke = news["Coca-Cola brand valu"]
    assert coke["news_type"].startswith("N09") and "Brand Value" in coke["financial_data"]
    assert news["Figma launches new A"]["main_category"] == "Tools & AI Updates"
    assert news["Saudi telecom STC re"]["news_type"].startswith("N08")
    # --- date logic: old article is not breaking
    old = news["A look back at 1990s"]
    assert old["date_status"] == "older article (not breaking)"
    # --- duplicate linking across sources
    dups = [n for n in db.rows(con, "SELECT * FROM news") if n["duplicate_of"]]
    assert len(dups) == 1 and dups[0]["duplicate_of"] == acme["news_id"]
    # --- scoring: explanation present, bands valid
    for n in news.values():
        assert 0 <= int(n["overall_score"]) <= 100 and "Relevance" in n["score_explanation"]
    assert int(acme["overall_score"]) > int(old["overall_score"])
    # --- rebrand fields never fabricated
    assert "Not Disclosed" in acme["rebrand_analysis"]
    # --- exports + reports
    for f in ["news.csv", "news.json", "sources.csv", "sources.json"]:
        assert (env / "Database" / f).exists()
    daily = list((env / "Reports" / "Daily").glob("Brand_Intelligence_Daily_*.html"))
    assert daily and "Acme Bank" in daily[0].read_text() and "ليه مهم" in daily[0].read_text()
    assert daily[0].with_suffix(".md").exists()
    assert (env / "Reports" / "index.html").exists()
    # --- notifications sent once
    assert sent["email"] == 1 and "sendMessage" in sent["tg"]

    # --- second run: everything already known -> duplicates prevented, no re-send
    assert pipeline.run_daily(notify_on=True, force=True) == "ok"
    runs = db.rows(con, "SELECT * FROM runs ORDER BY started_at")
    assert int(runs[-1]["items_new"]) == 0 and int(runs[-1]["duplicates_prevented"]) >= 5
    assert sent["email"] == 1
    status = json.loads((env / "Reports" / "status.json").read_text())["status"]
    assert status["Working RSS feeds"] == 3 and status["Total registered sources"] == 4


def test_weekly_monthly(env):
    from engine import pipeline
    assert pipeline.run_daily(notify_on=False) == "ok"
    assert pipeline.run_periodic("weekly", notify_on=False) == "ok"
    assert list((env / "Reports" / "Weekly").glob("*.html"))


def test_email_via_apps_script_and_chat_autodetect(env, monkeypatch):
    from engine import notify, pipeline
    calls = {"post": [], "tg": []}

    class R:
        def __init__(self, t): self.text = t
        def json(self): return json.loads(self.text)

    class S:
        def post(self, url, data=None, **k):
            calls["post"].append(json.loads(data))
            return R('{"ok": true, "emailed": true}')
        def get(self, url, **k):
            return R('{"ok": true, "result": [{"message": {"chat": {"id": 4242}}}]}')

    monkeypatch.setattr(notify.net, "session", lambda: S())
    monkeypatch.setattr(notify, "_tg", lambda m, data=None, files=None: calls["tg"].append(data["chat_id"]))
    monkeypatch.setenv("SHEETS_WEBAPP_URL", "https://script.example.com/exec")
    monkeypatch.setenv("SHEETS_SECRET", "s3cret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    import engine.sheets
    monkeypatch.setattr(engine.sheets, "push", lambda *a, **k: True)
    assert pipeline.run_daily(notify_on=True) == "ok"
    mail = [c for c in calls["post"] if c.get("action") == "email"]
    assert len(mail) == 1 and mail[0]["secret"] == "s3cret" and mail[0]["pdf_base64"]
    assert calls["tg"] and set(calls["tg"]) == {"4242"}
    assert json.loads((env / "Configuration" / "telegram_chat.json").read_text())["chat_id"] == "4242"
