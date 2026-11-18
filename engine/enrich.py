"""Optional enrichment for top items: og:image (for report visuals) and LLM analysis.
LLM providers: gemini (free tier, rate limited) or anthropic (PAID API). Hard daily cap. Falls back to rules on any error."""
import json, os, re

from . import net
from .config import settings

PROMPT = """You are a branding-industry analyst. Using ONLY the article text below, return JSON with keys:
short_summary (<=40 words, your own words), detailed_summary (<=120 words, own words, no quotes over 15 words),
main_development, why_it_matters, key_facts (list, max 4), important_numbers (list of {{value, metric, as_stated}}),
strategic_implications, content_opportunities, research_opportunities, suggested_content_angle,
rebrand (object or null: previous_identity, new_identity, company, agency, launch_date, strategic_reason, target_audience,
main_visual_changes, architecture_implications, positioning_changes, case_study, business_context),
tool (object or null: product, company, feature, release_date, capabilities, what_changed, design_use_cases, pricing, availability).
Rules: any detail not in the text = "Not Disclosed". Never invent numbers, quotes, agencies or dates.
metric must be one of: Brand Value, Company Valuation, Revenue, Profit, Market Capitalization, Market Share, Marketing ROI,
Brand Awareness, Customer Acquisition, Other — never mix them up. Never state branding CAUSED a financial result unless
the text gives evidence; if it doesn't, say correlation is not causation.
HEADLINE: {headline}
SOURCE: {source}
TEXT:
{text}"""


RESOLVE_ERRORS = []


def resolve_google_news(url):
    """Google News RSS links are redirects; decode to the publisher's original article URL."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        res = gnewsdecoder(url, interval=0.3)
        if res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
        RESOLVE_ERRORS.append(str(res.get("message") or res)[:160])
    except Exception as e:
        RESOLVE_ERRORS.append(f"{type(e).__name__}: {e}"[:160])
    return None


def article_html(url):
    if not url or "news.google.com" in url:
        return None
    r, _ = net.get(url, check_robots=True, attempts=1)
    return r.text if r else None


def og_description(html):
    for pat in (r'<meta[^>]+(?:property|name)=["\'](?:og:description|description|twitter:description)["\'][^>]+content=["\']([^"\']{40,})',
                r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+(?:property|name)=["\'](?:og:description|description)'):
        m = re.search(pat, html or "", re.I)
        if m:
            import html as h
            return h.unescape(m.group(1)).strip()
    return None


def og_image(html):
    m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', html or "", re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image', html or "", re.I)
    return m.group(1) if m else None


def extract_text(html):
    try:
        import trafilatura
        t = trafilatura.extract(html)
        if t:
            return t[:9000]
    except Exception:
        pass
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html or "", re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", " ".join(paras)))[:9000]


def call_llm(prompt):
    cfg = settings()["ai"]
    p = cfg["provider"]
    s = net.session()
    if p == "gemini" and os.getenv("GEMINI_API_KEY"):
        from .arabic import gemini_generate
        return gemini_generate(prompt)
    if p == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        r = s.post("https://api.anthropic.com/v1/messages", timeout=90, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
            json={"model": cfg["model"], "max_tokens": 1500, "messages": [{"role": "user", "content": prompt + "\nReturn JSON only."}]})
        r.raise_for_status()
        txt = r.json()["content"][0]["text"]
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    return None


def apply_llm(rec, data):
    lab = "[AI-generated interpretation] "
    rec["short_summary"] = data.get("short_summary") or rec["short_summary"]
    rec["detailed_summary"] = data.get("detailed_summary") or rec["detailed_summary"]
    rec["main_development"] = data.get("main_development") or rec["main_development"]
    rec["why_it_matters"] = lab + (data.get("why_it_matters") or "")
    rec["key_facts"] = data.get("key_facts") or rec["key_facts"]
    rec["strategic_insights"] = lab + str(data.get("strategic_implications") or "")
    rec["content_angle"] = data.get("suggested_content_angle") or rec["content_angle"]
    rec["research_notes"] = f"Content: {data.get('content_opportunities')} | Research: {data.get('research_opportunities')}"
    if data.get("important_numbers"):
        rec["financial_data"] = [dict(n, status="Publisher claim — extracted by AI from article text") for n in data["important_numbers"]]
    if data.get("rebrand"):
        rec["rebrand_analysis"] = data["rebrand"]
    if data.get("tool"):
        rec["tool_analysis"] = data["tool"]
    rec["analysis_method"] = f"llm:{settings()['ai']['provider']}"


def enrich(records, log=print, image_limit=40):
    """For the top stories: resolve original URL, add image + publisher summary (og tags). Optional deep LLM analysis."""
    cfg = settings()["ai"]
    ranked = sorted([r for r in records if not r.get("duplicate_of") and r.get("priority") != "Reject"],
                    key=lambda r: -int(r["overall_score"]))
    llm_budget = cfg["max_articles_per_day"] if cfg.get("deep_analysis") and cfg["provider"] != "none" else 0
    resolved = enriched = 0
    for i, rec in enumerate(ranked[:max(image_limit, llm_budget)]):
        need_img = not rec.get("image_url") and i < image_limit
        need_sum = len(rec.get("teaser") or "") < 60 and i < image_limit
        need_llm = llm_budget > 0 and int(rec["overall_score"]) >= cfg["only_if_score_at_least"]
        if not (need_img or need_sum or need_llm):
            continue
        if "news.google.com" in rec["url"]:
            orig = resolve_google_news(rec["url"])
            if orig:
                rec["evidence_links"] = list(dict.fromkeys((rec.get("evidence_links") or []) + [rec["url"]]))
                rec["url"] = orig
                resolved += 1
        html = article_html(rec["url"])
        if not html:
            continue
        if need_img:
            rec["image_url"] = og_image(html) or rec.get("image_url")
        if need_sum:
            d = og_description(html)
            if d:
                rec["teaser"] = d[:600]
                rec["_enriched"] = True
                enriched += 1
        if need_llm and cfg.get("fetch_article_text", True):
            text = extract_text(html)
            if len(text) < 300:
                continue  # inaccessible/paywalled -> never fabricate from headline
            try:
                data = call_llm(PROMPT.format(headline=rec["headline"], source=rec["source_name"], text=text))
                if data:
                    apply_llm(rec, data)
                    llm_budget -= 1
            except Exception as e:
                log(f"[ai] {rec['news_id']} failed, kept rule analysis: {e}"[:200])
    log(f"[enrich] {resolved} Google News links resolved to original articles, {enriched} publisher summaries added"
        + (f" | first decode error: {RESOLVE_ERRORS[0]}" if RESOLVE_ERRORS else ""))
    return records
