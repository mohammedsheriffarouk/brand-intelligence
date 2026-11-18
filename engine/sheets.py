"""Google Sheets sync — the human-facing master database.
Uses a Google Apps Script web app bound to YOUR sheet (no Google Cloud project, no connector, free).
Env: SHEETS_WEBAPP_URL, SHEETS_SECRET. If unset, sync is skipped (logged), never fails the run."""
import json, os

from . import db, net

NEWS_COLS = ["news_id", "collected_at", "published_at", "date_status", "priority", "overall_score", "headline",
             "source_name", "url", "image_url", "main_category", "news_type", "secondary_tags", "industry", "geography",
             "related_companies", "related_agencies", "short_summary", "detailed_summary", "main_development",
             "why_it_matters", "key_facts", "financial_data", "evidence_links", "strategic_insights", "content_angle",
             "research_notes", "rebrand_analysis", "tool_analysis", "relevance_score", "impact_score",
             "credibility_score", "content_score", "score_explanation", "info_status", "editorial_status",
             "duplicate_of", "duplicate_key", "source_id", "analysis_method", "via"]
SOURCE_COLS = db.SOURCE_FIELDS


def _flat(v):
    if v is None:
        return ""
    if isinstance(v, str) and v[:1] in "[{":
        try:
            v = json.loads(v)
        except Exception:
            return v
    if isinstance(v, list):
        return " | ".join(_flat(x) if not isinstance(x, dict) else "; ".join(f"{k}: {x[k]}" for k in x) for x in v)
    if isinstance(v, dict):
        return " | ".join(f"{k}: {x}" for k, x in v.items())
    return str(v)


def push(tab, key, cols, rows, mode="upsert", log=print):
    url, secret = os.getenv("SHEETS_WEBAPP_URL"), os.getenv("SHEETS_SECRET")
    if not url or not secret:
        log(f"[sheets] skipped {tab}: SHEETS_WEBAPP_URL / SHEETS_SECRET not configured")
        return False
    payload = {"secret": secret, "tab": tab, "key": key, "mode": mode, "columns": cols,
               "rows": [[_flat(r.get(c)) for c in cols] for r in rows]}
    try:
        r = net.session().post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                               headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=120)
        ok = r.status_code == 200 and '"ok":true' in r.text.replace(" ", "")
        log(f"[sheets] {tab}: {len(rows)} rows -> {'ok' if ok else 'FAILED ' + r.text[:200]}")
        return ok
    except Exception as e:
        log(f"[sheets] {tab} failed: {e}")
        return False


def sync(con, new_records, log=print):
    push("Sources", "source_id", SOURCE_COLS, db.rows(con, "SELECT * FROM sources ORDER BY source_id"), "replace", log)
    if new_records:
        ids = [r["news_id"] for r in new_records]
        rows = db.rows(con, f"SELECT * FROM news WHERE news_id IN ({','.join('?' * len(ids))})", ids)
        for i in range(0, len(rows), 200):
            push("News", "news_id", NEWS_COLS, rows[i:i + 200], "upsert", log)
    runs = db.rows(con, "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")
    if runs:
        push("Runs", "run_id", list(runs[0].keys()), runs, "upsert", log)
