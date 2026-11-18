"""SQLite storage (engine cache + history). Google Sheets is the human-facing master copy (see sheets.py).
Schema is plain SQL so it can migrate to Postgres/Supabase later."""
import csv, json, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "Database" / "news.sqlite"

SOURCE_FIELDS = ["source_id", "name", "url", "category", "geo", "topics", "source_type", "official",
                 "rss_url", "rss_status", "newsletter_status", "collection_method", "frequency",
                 "reliability", "active", "discovered", "last_checked", "last_success", "consecutive_failures",
                 "error_notes"]

NEWS_FIELDS = ["news_id", "headline", "source_id", "source_name", "url", "canonical_url", "image_url",
               "published_at", "updated_at", "collected_at", "date_status", "main_category", "news_type",
               "secondary_tags", "industry", "geography", "related_companies", "related_agencies",
               "short_summary", "detailed_summary", "main_development", "why_it_matters", "key_facts",
               "financial_data", "evidence_links", "strategic_insights", "content_angle", "research_notes",
               "rebrand_analysis", "tool_analysis", "info_status", "credibility_score", "relevance_score",
               "impact_score", "content_score", "overall_score", "score_explanation", "priority",
               "duplicate_key", "title_key", "duplicate_of", "editorial_status", "analysis_method", "via"]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sources ({", ".join(f + (" TEXT PRIMARY KEY" if f == "source_id" else " TEXT") for f in SOURCE_FIELDS)});
CREATE TABLE IF NOT EXISTS news ({", ".join(f + (" TEXT PRIMARY KEY" if f == "news_id" else " TEXT") for f in NEWS_FIELDS)});
CREATE UNIQUE INDEX IF NOT EXISTS ux_news_dupkey ON news(duplicate_key);
CREATE INDEX IF NOT EXISTS ix_news_title ON news(title_key);
CREATE INDEX IF NOT EXISTS ix_news_pub ON news(published_at);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, kind TEXT, started_at TEXT, finished_at TEXT,
    status TEXT, sources_checked INTEGER, sources_failed INTEGER, items_seen INTEGER, items_new INTEGER,
    duplicates_prevented INTEGER, notes TEXT);
CREATE TABLE IF NOT EXISTS collection_log (ts TEXT, run_id TEXT, source_id TEXT, method TEXT, status TEXT,
    items INTEGER, error TEXT);
"""


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert(con, table, row, key):
    fields = SOURCE_FIELDS if table == "sources" else NEWS_FIELDS
    vals = {f: _s(row.get(f)) for f in fields}
    cols = ",".join(fields)
    ph = ",".join("?" for _ in fields)
    upd = ",".join(f"{f}=excluded.{f}" for f in fields if f != key)
    con.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT({key}) DO UPDATE SET {upd}",
                [vals[f] for f in fields])


def _s(v):
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def export(con):
    """CSV + JSON exports of both databases (Database/ folder)."""
    out = ROOT / "Database"
    for table, fields, name in (("sources", SOURCE_FIELDS, "sources"), ("news", NEWS_FIELDS, "news")):
        data = rows(con, f"SELECT * FROM {table} ORDER BY 1")
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(data)
        (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def loads(v, default=None):
    if v in (None, ""):
        return default if default is not None else []
    try:
        return json.loads(v)
    except Exception:
        return v
