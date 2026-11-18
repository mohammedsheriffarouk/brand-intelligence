"""Daily / Weekly / Monthly reports: HTML (self-contained, mobile), Markdown, PDF, PNG brief card."""
import collections, shutil, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db
from .analyze import MENA
from .config import settings

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "Reports"
env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())
SECTIONS = ["Branding & Rebranding", "Business Impact & Brand Value", "Tools & AI Updates",
            "Agency & Studio News", "Research & Industry Insights"]
LIST_FIELDS = ["secondary_tags", "industry", "geography", "related_companies", "related_agencies", "key_facts",
               "financial_data", "evidence_links"]


def tz():
    return ZoneInfo(settings()["timezone"])


def load(con, since, until):
    rows = db.rows(con, "SELECT * FROM news WHERE collected_at >= ? AND collected_at < ? AND (duplicate_of IS NULL OR duplicate_of='')"
                        " ORDER BY CAST(overall_score AS INTEGER) DESC", (since.isoformat(), until.isoformat()))
    for r in rows:
        for f in LIST_FIELDS:
            r[f] = db.loads(r.get(f), [])
        r["overall_score"] = int(r["overall_score"] or 0)
        p = r.get("published_at")
        r["pub_display"] = datetime.fromisoformat(p).astimezone(tz()).strftime("%d %b %Y") if p else "date not provided"
    return rows


def keep(rows):
    return [r for r in rows if r["priority"] != "Reject"]


def build(con, kind="daily", day=None):
    now = datetime.now(timezone.utc)
    local = (day or now.astimezone(tz())).replace(tzinfo=tz())
    if kind == "daily":
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        since, until = start - timedelta(hours=6), now + timedelta(minutes=1)   # catches the early-morning run
        label, fname = local.strftime("%A %d %B %Y"), f"Brand_Intelligence_Daily_{local:%Y-%m-%d}"
        title, kicker, folder, per = "Brand Intelligence Daily Brief", "Daily", "Daily", 6
    elif kind == "weekly":
        since, until = now - timedelta(days=7), now
        y, w, _ = local.isocalendar()
        label, fname = f"Week {w}, {y}", f"Brand_Intelligence_Weekly_{y}-{w:02d}"
        title, kicker, folder, per = "Brand Intelligence Weekly", "Weekly intelligence", "Weekly", 6
    else:
        first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev = (first - timedelta(days=1)).replace(day=1)
        since, until = prev.astimezone(timezone.utc), first.astimezone(timezone.utc)
        label, fname = prev.strftime("%B %Y"), f"Brand_Intelligence_Monthly_{prev:%Y-%m}"
        title, kicker, folder, per = "Brand Intelligence Monthly", "Monthly industry report", "Monthly", 8
    allrows = load(con, since, until)
    rows = keep(allrows)
    high = [r for r in rows if r["priority"] == "High Priority"]
    mena = [r for r in rows if set(r["geography"]) & MENA]
    tools = [r for r in rows if r["main_category"] == "Tools & AI Updates"]
    sections = [{"title": "Top stories", "stories": rows[:5], "images": True}]
    for s in SECTIONS:
        sections.append({"title": s, "stories": [r for r in rows[5:] if r["main_category"] == s][:per], "images": kind != "daily"})
    sections.append({"title": "MENA & GCC developments", "stories": [r for r in mena if r not in rows[:5]][:per], "images": False,
                     "note": "Egypt · Saudi Arabia · UAE · Oman · wider GCC & MENA"})
    if kind == "monthly":
        sections.insert(1, {"title": "Brand valuation changes", "stories": [r for r in rows if r["news_type"].startswith("N09")][:8], "images": False})
        sections.insert(2, {"title": "Major company rebrands", "stories": [r for r in rows if r["news_type"][:3] in ("N02", "N03")][:10], "images": True})
    tables = []
    if kind != "daily":
        types = collections.Counter(r["news_type"] for r in rows).most_common(8)
        tags = collections.Counter(t for r in rows for t in r["secondary_tags"] + r["industry"]).most_common(8)
        agencies = collections.Counter(a for r in rows for a in r["related_agencies"]).most_common(10)
        tables += [{"title": "Emerging trends (most frequent topics)", "head": ["Topic", "Stories"], "rows": types + tags},
                   {"title": "Agencies & competitors in the news", "head": ["Agency / studio", "Mentions"], "rows": agencies}]
    executive = [f"{len(rows)} relevant stories ({len(high)} high priority) out of {len(allrows)} collected."]
    if rows:
        executive.append(f"Lead story: {rows[0]['headline']} — {rows[0]['source_name']}.")
    if mena:
        executive.append(f"Top regional story: {mena[0]['headline']} ({', '.join(mena[0]['geography'][:2])}).")
    if tools:
        executive.append(f"Top tool/AI update: {tools[0]['headline']}.")
    verify = [r for r in rows if r["editorial_status"].startswith("Needs verification")]
    if verify:
        executive.append(f"{len(verify)} stories carry unverified financial claims — not approved for publication.")
    stats = [("Stories", len(rows)), ("High priority", len(high)), ("Regional", len(mena)), ("Tools & AI", len(tools))]
    opps = [{"angle": r["content_angle"], "headline": r["headline"], "url": r["url"]} for r in rows[:8] if r.get("content_angle")]
    ctx = dict(title=title, kicker=kicker, period=label, generated=now.astimezone(tz()).strftime("%d %b %Y %H:%M"),
               stats=stats, executive=executive, sections=sections, tables=tables, opportunities=opps, refs=rows[:60])
    out = REPORTS / folder
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"{fname}.html"
    html_path.write_text(env.get_template("report.html.j2").render(**ctx), encoding="utf-8")
    (out / f"{fname}.md").write_text(markdown(ctx), encoding="utf-8")
    pdf = to_pdf(html_path, out / f"{fname}.pdf")
    card = None
    if kind == "daily":
        card = brief_card(rows, stats, local, out / f"{fname}_brief.png")
    return {"kind": kind, "html": html_path, "pdf": pdf, "png": card, "rows": rows, "high": high, "mena": mena,
            "tools": tools, "label": label, "fname": fname, "folder": folder, "collected": len(allrows)}


def markdown(c):
    L = [f"# {c['title']}", f"*{c['period']} · generated {c['generated']} (Cairo)*", "",
         " · ".join(f"**{v}** {k}" for k, v in c["stats"]), "", "## Executive summary"] + [f"- {e}" for e in c["executive"]]
    for s in c["sections"]:
        L += ["", f"## {s['title']} ({len(s['stories'])})"]
        for n in s["stories"]:
            L += ["", f"### [{n['headline']}]({n['url']})",
                  f"*{n['news_type']} · {n['source_name']} · published {n['pub_display']} · {n['priority']} {n['overall_score']}/100*",
                  "", f"- **Summary:** {n['short_summary']}", f"- **Why it matters:** {n['why_it_matters']}"]
            for f in n["financial_data"][:4]:
                L.append(f"- **Data:** {f['value']} — {f['metric']} ({f['status']})")
            L.append(f"- **Strategic implication:** {n['strategic_insights']}")
    for t in c["tables"]:
        L += ["", f"## {t['title']}", "", "| " + " | ".join(t["head"]) + " |", "|" + "---|" * len(t["head"])]
        L += ["| " + " | ".join(str(x) for x in r) + " |" for r in t["rows"]]
    L += ["", "## Source references"] + [f"{i}. {n['source_name']} — {n['url']}" for i, n in enumerate(c["refs"], 1)]
    return "\n".join(L) + "\n"


def _render(html_path, out, kind):
    """PDF/PNG export: Playwright Chromium if installed (best), else wkhtmltopdf/wkhtmltoimage."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1080 if kind == "png" else 900, "height": 1200}, device_scale_factor=1 if kind == "pdf" else 2)
            pg.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=60000)
            if kind == "pdf":
                pg.pdf(path=str(out), format="A4", print_background=True, margin={"top": "12mm", "bottom": "12mm"})
            else:
                pg.screenshot(path=str(out), full_page=True)
            b.close()
        return out
    except Exception:
        pass
    tool = shutil.which("wkhtmltopdf" if kind == "pdf" else "wkhtmltoimage")
    if not tool:
        return None
    args = [tool, "--quiet", "--enable-local-file-access"]
    args += ["--encoding", "utf-8", "--print-media-type", "-s", "A4"] if kind == "pdf" else ["--width", "1080", "--quality", "85"]
    try:
        subprocess.run(args + [str(html_path), str(out)], timeout=180, check=False, capture_output=True)
    except Exception:
        return None
    return out if out.exists() and out.stat().st_size > 1000 else None


def to_pdf(html_path, out):
    return _render(html_path, out, "pdf")


LABEL = {"Branding & Rebranding": "Branding", "Business Impact & Brand Value": "Business", "Tools & AI Updates": "Tools & AI",
         "Agency & Studio News": "Agencies", "Research & Industry Insights": "Research"}


def brief_card(rows, stats, local, out, link=None):
    top = [dict(r, label=LABEL.get(r["main_category"], "News")) for r in rows[:5]]
    tmp = out.with_suffix(".card.html")
    tmp.write_text(env.get_template("brief_card.html.j2").render(top=top, stats=stats, link=link,
                                                                  date_long=local.strftime("%A %d %B %Y")), encoding="utf-8")
    res = _render(tmp, out, "png")
    tmp.unlink(missing_ok=True)
    return res
