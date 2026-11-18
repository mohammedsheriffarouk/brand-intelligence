"""Classification, scoring and structured analysis.
Rule-based by default (free, deterministic, auditable). Optional LLM enrichment in llm.py.
Labels: Verified Information / Publisher Claim / Third-party Analysis / AI-generated Interpretation."""
import re

from .config import taxonomy
from .process import clean_text

ND = "Not Disclosed"
SECTION_OF = {**{k: "Branding & Rebranding" for k in ["N01", "N02", "N03", "N04", "N05", "N06", "N12", "N17", "N18"]},
              **{k: "Business Impact & Brand Value" for k in ["N07", "N08", "N09", "N14", "N20"]},
              **{k: "Tools & AI Updates" for k in ["N10", "N11"]},
              **{k: "Agency & Studio News" for k in ["N15", "N16"]},
              **{k: "Research & Industry Insights" for k in ["N13", "N19"]}}
CATEGORY_DEFAULT = {"A_branding_news": "N02", "B_agency": "N15", "C_business": "N09", "D_design_trends": "N12",
                    "E_tools_ai": "N10", "F_research": "N13", "G_mena": "N06", "H_awards": "N16"}
BRANDING_CORE = ["rebrand", "brand identity", "visual identity", "identity", "logo", "wordmark", "branding", "brand",
                 "typeface", "typography", "packaging", "design system", "هوية", "شعار", "علامة"]
REGIONAL_PTS = {"Egypt": 5, "Saudi Arabia": 5, "UAE": 5, "Oman": 5, "GCC": 4, "Middle East": 3, "Other MENA": 3}
MENA = set(REGIONAL_PTS)

WHY = {
    "N01": "A new brand entering the market — useful to study naming, positioning and launch identity choices.",
    "N02": "A rebrand signals a strategic shift; the rationale and execution are a ready case study for clients.",
    "N03": "Logo changes draw high public attention and debate — strong material for design critique content.",
    "N04": "Shows how brands are re-framing strategy and positioning; relevant to consulting conversations.",
    "N05": "Architecture decisions affect portfolio value and clarity — a less-covered, high-expertise topic.",
    "N06": "Campaign work shows how identity is activated in market.",
    "N07": "Business growth context helps link brand decisions to commercial outcomes (correlation, not proof).",
    "N08": "Financial results give hard numbers for commercial context; causality to branding must not be assumed.",
    "N09": "Brand valuation movements are strong evidence-led content and credibility builders for consulting.",
    "N10": "Tool changes affect designers' workflows and studio productivity.",
    "N11": "AI capabilities are reshaping creative production and client expectations.",
    "N12": "Trend signals help anticipate client requests and keep the studio's work current.",
    "N13": "Research provides citable data for content, pitches and education.",
    "N14": "Consolidation changes the competitive landscape for agencies and studios.",
    "N15": "Agency moves reveal where talent, clients and capabilities are shifting.",
    "N16": "Awards show what the industry currently rewards — a benchmark for quality.",
    "N17": "Typography is a core identity asset; custom type is a growing differentiator.",
    "N18": "Packaging is where brand meets shelf — high visual content value.",
    "N19": "Consumer behaviour shifts should inform brand strategy and messaging.",
    "N20": "Market entries create demand for localisation and new brand work — potential leads.",
}
ANGLE = {
    "N02": "Before/after breakdown: what changed, why, and whether it works strategically.",
    "N03": "Logo critique carousel: old vs new, 3 design decisions explained.",
    "N09": "Data post: what the valuation movement means — clearly separating brand value from company value.",
    "N10": "'What's new for designers' quick explainer with practical use cases.",
    "N11": "Opinion: what this AI development means for branding studios and clients.",
    "N08": "Business story: the numbers, with an honest note on what branding can and cannot claim.",
    "N16": "Spotlight on winning work and the lesson behind it.",
    "N20": "Market-entry angle: how the brand is localising (watch for Arabic adaptation).",
    "N13": "Key stats carousel with the source cited on every slide.",
}


def _hits(text, kws):
    n = 0
    for k in kws:
        if len(k) <= 3 and k.isascii():
            n += len(re.findall(rf"\b{re.escape(k)}\b", text))
        else:
            n += text.count(k)
    return n


def classify(rec, source):
    tx = taxonomy()
    head = rec["headline"].lower()
    body = (rec.get("teaser") or "").lower()
    scores = {}
    for code, t in tx["news_types"].items():
        s = 2 * _hits(head, t["kw"]) + _hits(body, t["kw"])
        if s:
            scores[code] = s
    primary = max(scores, key=scores.get) if scores else CATEGORY_DEFAULT.get(source.get("category"), "N04")
    secondary = [c for c in sorted(scores, key=scores.get, reverse=True) if c != primary][:4]
    text = f" {head} {body} "
    inds = [i for i, kws in tx["industries"].items() if _hits(text, kws)][:3]
    geos = [g for g, kws in tx["geography"].items() if _hits(text, kws)]
    for hint in (rec.get("geo_hint"), source.get("geo")):
        if hint and hint not in ("Global",) and hint not in geos:
            geos.append(hint)
    if any(g in geos for g in ("Saudi Arabia", "UAE", "Oman")) and "GCC" not in geos:
        geos.append("GCC")
    companies = [b.title() if b.islower() else b for b in tx["big_brands"] if _hits(text, [b])]
    m = re.search(r"([A-Z][\w&'’.-]+(?:\s[A-Z][\w&'’.-]+){0,3})\s+(?:rebrands|unveils|launches|reveals|debuts|gets a new|introduces|refreshes)", rec["headline"])
    if m and m.group(1) not in companies and m.group(1).split()[0] not in ("The", "A", "An", "New", "How", "Why"):
        companies.insert(0, m.group(1))
    agencies = [a.title() if a.islower() and len(a) > 4 else a.upper() if len(a) <= 4 else a for a in tx["agencies"] if _hits(text, [a])]
    if source.get("category") == "B_agency":
        agencies.insert(0, source["name"])
    rec.update(news_type=f"{primary} — {tx['news_types'][primary]['name']}",
               _type=primary, main_category=SECTION_OF[primary],
               secondary_tags=[f"{c} — {tx['news_types'][c]['name']}" for c in secondary],
               industry=inds or ["Unclassified"], geography=geos or ["Global"],
               related_companies=list(dict.fromkeys(companies))[:6], related_agencies=list(dict.fromkeys(agencies))[:4])
    return rec


MONEY = re.compile(r"((?:US)?\$|£|€|SAR|AED|EGP|OMR|USD)\s?\d[\d,.]*\s?(?:bn|billion|m|million|k)?|\d[\d,.]*\s?(?:bn|billion|million)\s?(?:dollars|riyals|dirhams|pounds)?|\d+(?:\.\d+)?\s?(?:%|per cent|percent)", re.I)
METRICS = [("Brand Value", ["brand value", "brand valuation", "worth"]), ("Company Valuation", ["valuation", "valued at"]),
           ("Market Capitalization", ["market cap"]), ("Revenue", ["revenue", "sales", "turnover"]),
           ("Profit", ["profit", "net income", "earnings"]), ("Market Share", ["market share"]),
           ("Marketing ROI", ["roi", "return on"]), ("Brand Awareness", ["awareness"]),
           ("Customer Acquisition", ["customers", "users", "subscribers"])]


def financial(rec, source):
    text = f"{rec['headline']}. {rec.get('teaser') or ''}"
    out = []
    for m in MONEY.finditer(text):
        ctx = text[max(0, m.start() - 80): m.end() + 40].lower()
        metric = next((name for name, kws in METRICS if any(k in ctx for k in kws)), "Unlabelled figure")
        out.append({"value": m.group(0).strip(), "metric": metric,
                    "status": "Publisher claim — official source" if source.get("official") == "official"
                    else "Publisher claim — not independently verified",
                    "context": clean_text(text[max(0, m.start() - 60): m.end() + 30])})
    return out[:6]


def score(rec, source):
    t = rec["_type"]
    head = rec["headline"].lower()
    body = (rec.get("teaser") or "").lower()
    tx = taxonomy()
    rel = min(20, 6 * _hits(head, BRANDING_CORE) + 2 * _hits(body, BRANDING_CORE)
              + (4 if source.get("category") in ("A_branding_news", "B_agency", "D_design_trends", "H_awards") else 0))
    big = any(_hits(f" {head} {body} ", [b]) for b in tx["big_brands"])
    nums = bool(rec.get("financial_data"))
    base_imp = {"N09": 14, "N14": 13, "N08": 12, "N02": 12, "N01": 10, "N03": 10, "N20": 10, "N11": 9, "N07": 9,
                "N13": 9, "N10": 8}.get(t, 6)
    rel_rating_ = int(source.get("reliability") or 0)
    quality_branding = rel >= 16 and rel_rating_ >= 4 and t in ("N01", "N02", "N03", "N05", "N17", "N18")
    imp = min(20, base_imp + (4 if big else 0) + (2 if nums else 0) + (3 if quality_branding else 0))
    inn = min(15, 6 + (4 if re.search(r"\b(first|new|launch|unveil|introduc|debut|rebrand|refresh|reveal)", head) else 0)
              + (3 if t in ("N10", "N11", "N17") else 0) + (2 if rec.get("date_status") == "fresh" else 0))
    rel_rating = int(source.get("reliability") or 0)
    cred = rel_rating * 3 if rel_rating else 6
    ev = 6 + (4 if source.get("official") == "official" else 0) + (3 if nums else 0) \
        + (3 if rec.get("related_companies") else 0) + (2 if len(body) > 200 else 0) + (2 if rel_rating >= 4 else 0)
    flags = []
    if nums and source.get("official") != "official" and rel_rating < 4:
        ev = min(ev, 8)
        flags.append("financial claim from non-official, lower-reliability source")
    ev = min(15, ev)
    con = min(10, (6 if _hits(head, ["logo", "identity", "rebrand", "packaging", "typeface", "campaign", "هوية", "شعار"]) else 1)
              + (3 if big else 0) + (2 if t in ("N10", "N11") else 0) + (1 if rec.get("image_url") else 0)
              + (1 if any(g in MENA for g in rec["geography"]) else 0))
    subtotal = rel + imp + inn + cred + ev + con
    reg = max([REGIONAL_PTS.get(g, 0) for g in rec["geography"]] or [0])
    reg_applied = reg if subtotal >= 50 else 0
    penalty = 10 if rec.get("date_status") == "older article (not breaking)" else 0
    total = max(0, min(100, subtotal + reg_applied - penalty))
    bands = {"high": 85, "follow": 70, "research": 55}
    prio = ("High Priority" if total >= bands["high"] else "Worth Following" if total >= bands["follow"]
            else "Research Only" if total >= bands["research"] else "Reject")
    expl = (f"Relevance {rel}/20, Impact {imp}/20, Innovation {inn}/15, Credibility {cred}/15, Evidence {ev}/15, "
            f"Content {con}/10, Regional {reg_applied}/5" + (f" (regional {reg} withheld: weak base)" if reg and not reg_applied else "")
            + (f", −{penalty} older article" if penalty else "") + (". Flags: " + "; ".join(flags) if flags else ""))
    if rec.get("duplicate_of"):
        status = "duplicate (linked to original)"
    elif flags and prio in ("High Priority", "Worth Following"):
        status = "Needs verification — not approved for publication"
    else:
        status = {"High Priority": "Ready for editorial review", "Worth Following": "Worth following",
                  "Research Only": "Research only", "Reject": "Rejected (low score)"}[prio]
    rec.update(relevance_score=rel, impact_score=imp, credibility_score=cred, content_score=con,
               overall_score=total, priority=prio, score_explanation=expl, editorial_status=status)
    return rec


def rule_analysis(rec, source):
    t = rec["_type"]
    teaser = rec.get("teaser") or ""
    if len(teaser) < 40 or teaser.lower().startswith(rec["headline"].lower()[:30]):
        teaser = ""
    company = rec["related_companies"][0] if rec["related_companies"] else ND
    agency = rec["related_agencies"][0] if rec["related_agencies"] else ND
    rec["short_summary"] = clean_text(teaser, 220) if teaser else "No summary provided by the feed — open the original article."
    rec["detailed_summary"] = ("[Publisher excerpt] " + clean_text(teaser, 600)) if teaser else ND
    rec["main_development"] = f"{rec['news_type'].split(' — ')[1]} — {company}" + (f" (agency: {agency})" if agency != ND else "")
    rec["why_it_matters"] = "[AI-generated interpretation · rule template] " + WHY.get(t, "Relevant industry development.")
    rec["content_angle"] = ANGLE.get(t, "Short explainer post linking to the original source.")
    sents = re.split(r"(?<=[.!?])\s+", teaser)
    rec["key_facts"] = [s for s in sents if re.search(r"\d|[A-Z][a-z]+ [A-Z]", s)][:3]
    rec["evidence_links"] = [rec["url"]] + ([rec["publisher_url"]] if rec.get("publisher_url") else [])
    rec["strategic_insights"] = ("[AI-generated interpretation] Commercial figures are reported by the publisher; "
                                 "no causal link between branding and results is claimed.") if rec.get("financial_data") else \
        "[AI-generated interpretation] " + WHY.get(t, "")
    rec["research_notes"] = "Open the original article to confirm details before publishing."
    if t in ("N01", "N02", "N03"):
        rec["rebrand_analysis"] = {"Company / Brand": company, "Branding Agency": agency,
                                   "Project Launch Date": (rec.get("published_at") or ND)[:10] + " (article date)",
                                   **{k: ND for k in ["Previous Brand Identity", "New Brand Identity", "Strategic Reason for Change",
                                                      "Target Audience", "Main Visual Changes", "Brand Architecture Implications",
                                                      "Positioning Changes", "Available Case Study", "Business Context"]}}
    if t in ("N10", "N11"):
        text = (rec["headline"] + " " + teaser).lower()
        prod = next((p.title() for p in taxonomy()["tools"] if re.search(rf"\b{re.escape(p)}\b", text)), ND)
        rec["tool_analysis"] = {"Product Name": prod, "Company": source.get("name") if source.get("category") == "E_tools_ai" else ND,
                                "Feature Name": ND, "Release Date": (rec.get("published_at") or ND)[:10],
                                "Main Capabilities": ND, "What Changed?": ND, "Branding / Design Use Cases": ND,
                                "Pricing": ND, "Availability": ND,
                                "Official Documentation Link": rec["url"] if source.get("official") == "official" else ND}
    rec["info_status"] = ("Verified: headline, URL, source, publication date (from feed) · Publisher claims: summary & figures · "
                          "AI-generated interpretation: why it matters, insights, angle")
    rec["analysis_method"] = "rules"
    return rec


def analyze(rec, source):
    classify(rec, source)
    rec["financial_data"] = financial(rec, source)
    score(rec, source)
    rule_analysis(rec, source)
    return rec
