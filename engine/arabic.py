"""Arabic layer: labels, Arabic interpretation templates, and translation of headline/summary.
Translation: Gemini (if GEMINI_API_KEY + ai.provider=gemini) -> best, keeps names/terms in English;
otherwise free Google Translate (deep-translator, no key) with English brand names protected."""
import json, os, re

from . import net
from .config import settings, taxonomy

TYPE_AR = {"N01": "إطلاق علامة جديدة", "N02": "إعادة هوية (Rebranding)", "N03": "تصميم شعار جديد", "N04": "استراتيجية علامة",
           "N05": "Brand Architecture", "N06": "حملة إعلانية", "N07": "نمو أعمال", "N08": "نتائج مالية", "N09": "قيمة العلامة (Brand Value)",
           "N10": "تحديث أداة تصميم", "N11": "ذكاء اصطناعي", "N12": "اتجاه تصميمي (Trend)", "N13": "تقرير بحثي", "N14": "استحواذ",
           "N15": "أخبار الوكالات", "N16": "جوائز", "N17": "Typography وخطوط", "N18": "Packaging", "N19": "سلوك المستهلك", "N20": "توسّع في سوق جديد"}
SECTION_AR = {"Top stories": "أهم الأخبار", "Branding & Rebranding": "البراندنج وإعادة الهوية",
              "Business Impact & Brand Value": "الأثر التجاري وقيمة العلامة", "Tools & AI Updates": "الأدوات والذكاء الاصطناعي",
              "Agency & Studio News": "أخبار الوكالات والاستوديوهات", "Research & Industry Insights": "الأبحاث ورؤى الصناعة",
              "MENA & GCC developments": "الشرق الأوسط والخليج ومصر", "Brand valuation changes": "تغيّرات قيمة العلامات",
              "Major company rebrands": "أبرز عمليات إعادة الهوية"}
PRIORITY_AR = {"High Priority": "أولوية عالية", "Worth Following": "يستحق المتابعة", "Research Only": "للبحث فقط", "Reject": "مرفوض"}
GEO_AR = {"Global": "عالمي", "North America": "أمريكا الشمالية", "Europe": "أوروبا", "Asia Pacific": "آسيا", "Middle East": "الشرق الأوسط",
          "GCC": "الخليج", "Saudi Arabia": "السعودية", "UAE": "الإمارات", "Oman": "عُمان", "Egypt": "مصر", "Other MENA": "شمال أفريقيا والمشرق"}
WHY_AR = {
    "N01": "علامة جديدة بتدخل السوق: فرصة تدرس اختيارات الاسم والـ positioning والهوية من أول يوم.",
    "N02": "إعادة الهوية معناها تحوّل استراتيجي، وأسبابها وتنفيذها case study جاهزة تكلّم بيها عملاءك.",
    "N03": "تغيير الشعار بيعمل جدل وانتباه كبير، ومادة ممتازة لنقد تصميمي (design critique).",
    "N04": "بيوضّح إزاي العلامات بتعيد صياغة استراتيجيتها، ومفيد في نقاشات الاستشارات.",
    "N05": "قرارات الـ Brand Architecture بتأثر على قيمة الـ portfolio ووضوحه، وموضوع قليل اللي بيتكلم فيه بعمق.",
    "N06": "بيوري إزاي الهوية بتتفعّل في السوق من خلال الحملات.",
    "N07": "سياق النمو بيساعد تربط قرارات العلامة بالنتائج التجارية (ارتباط مش إثبات سببية).",
    "N08": "أرقام مالية فعلية للسياق التجاري، من غير ما نفترض إن البراندنج هو السبب.",
    "N09": "تحركات قيمة العلامات محتوى قائم على أرقام، وبيقوّي مصداقيتك كاستشاري.",
    "N10": "تغيير الأدوات بيأثر على شغل المصممين وإنتاجية الاستوديو.",
    "N11": "قدرات الـ AI بتغيّر الإنتاج الإبداعي وتوقعات العملاء.",
    "N12": "إشارات الـ trends بتساعدك تتوقع طلبات العملاء وتخلي شغلك محدّث.",
    "N13": "بيانات بحثية تقدر تستشهد بيها في المحتوى والـ pitches والتعليم.",
    "N14": "الاستحواذات بتغيّر خريطة المنافسة بين الوكالات.",
    "N15": "تحركات الوكالات بتوضّح فين المواهب والعملاء والقدرات رايحة.",
    "N16": "الجوائز بتوري الصناعة بتكافئ إيه دلوقتي، ومعيار للجودة.",
    "N17": "الخط جزء أساسي من الهوية، والـ custom type بقى عامل تميّز متزايد.",
    "N18": "الـ Packaging هو نقطة لقاء العلامة بالرف، وقيمته البصرية عالية للمحتوى.",
    "N19": "تغيّر سلوك المستهلك لازم ينعكس على استراتيجية العلامة ورسائلها.",
    "N20": "دخول أسواق جديدة بيخلق طلب على شغل هوية وتعريب (localization)، وممكن يبقى فرصة عملاء.",
}
ANGLE_AR = {
    "N02": "Before / After: إيه اللي اتغيّر وليه، وهل التغيير ناجح استراتيجياً.",
    "N03": "Carousel نقد شعار: القديم مقابل الجديد و3 قرارات تصميمية.",
    "N09": "بوست أرقام: معنى تغيّر القيمة، مع التفرقة بين Brand Value وقيمة الشركة.",
    "N10": "شرح سريع \"الجديد للمصممين\" مع استخدامات عملية.",
    "N11": "رأي: الخبر ده معناه إيه لاستوديوهات البراندنج وعملائها.",
    "N08": "قصة أعمال بالأرقام، مع توضيح صريح للي البراندنج يقدر ومايقدرش يدّعيه.",
    "N16": "تسليط الضوء على الشغل الفائز والدرس منه.",
    "N20": "زاوية دخول السوق: إزاي العلامة بتتعرّب (Arabic adaptation).",
    "N13": "Carousel أرقام مع ذكر المصدر في كل slide.",
    "N01": "تحليل علامة جديدة: الاسم والـ positioning والهوية.",
}
DEFAULT_WHY = "تطوّر مهم في الصناعة يستحق المتابعة."
DEFAULT_ANGLE = "بوست قصير يشرح الخبر مع لينك المصدر."


def code(rec):
    return str(rec.get("news_type") or "")[:3]


def protect(text):
    """Wrap Latin brand/proper-noun sequences so the free translator keeps them in English."""
    names = []
    def keep(m):
        names.append(m.group(0))
        return f"[{len(names) - 1}]"
    out = re.sub(r"\b(?:[A-Z][\w&+'’.-]*|[A-Z]{2,})(?:\s+(?:[A-Z][\w&+'’.-]*|&|\+|of|de))*", keep, text)
    return out, names


def restore(text, names):
    for i, n in enumerate(names):
        text = re.sub(rf"\[\s*{i}\s*\]", n, text)
    return text


ERRORS = []


def log_once(msg):
    if msg not in ERRORS:
        ERRORS.append(msg)


def free_translate(texts):
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="auto", target="ar")
    except Exception as e:
        ERRORS.append(f"{type(e).__name__}: {e}"[:160])
        return [None] * len(texts)
    out = []
    for t in texts:
        if not t:
            out.append("")
            continue
        try:
            import time
            time.sleep(0.4)   # free endpoint allows ~5 requests/second
            p, names = protect(t[:1500])
            out.append(restore(tr.translate(p) or "", names))
        except Exception as e:
            ERRORS.append(f"{type(e).__name__}: {e}"[:160])
            out.append(None)
    return out


GEMINI_PROMPT = """ترجم وحلّل الأخبار التالية لمصمم هوية بصرية مصري. لكل خبر رجّع JSON object فيه:
headline_ar (عنوان عربي فصيح بسيط)، summary_ar (جملتين بالعربي من الملخص المتاح فقط)،
why_ar (ليه الخبر مهم لاستوديو براندنج، جملة واحدة)، angle_ar (زاوية محتوى لسوشيال ميديا، جملة واحدة).
قواعد: أسماء الشركات والوكالات والمنتجات والمصطلحات المهنية (rebrand, identity, logo, positioning...) تفضل بالإنجليزي.
لو الملخص فاضي، summary_ar = "" ولا تخترع تفاصيل. رجّع JSON array بنفس الترتيب فقط.
الأخبار:
{items}"""


_working_model = None


def gemini_generate(prompt):
    """Calls the first Gemini model that exists for this key (model names change over time). Returns parsed JSON."""
    global _working_model
    cfg = settings()["ai"]
    models = [_working_model] if _working_model else list(dict.fromkeys(available_models() + [cfg.get("model")] + cfg.get("model_fallbacks", [])))
    import time
    last = None
    tried = []
    for m in [x for x in models if x]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        r = None
        for attempt in range(3):
            # key goes in a header, never in the URL, so it can't leak into logs or error messages
            try:
                r = net.session().post(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}, timeout=(10, 180), json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}})
            except Exception as e:
                tried.append(f"{m}=timeout/{type(e).__name__}")
                r = None
                break
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"{m}: HTTP {r.status_code}"
                time.sleep(8 * (attempt + 1))
                continue
            break
        if r is None:
            continue
        if r.status_code in (404, 429, 500, 502, 503, 504):
            last = f"{m}: HTTP {r.status_code}"
            tried.append(f"{m}={r.status_code}:{_err(r)}")
            continue
        if r.status_code != 200:
            raise RuntimeError(f"{m}: HTTP {r.status_code} {r.text[:150]}")
        _working_model = m
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    raise RuntimeError("all models failed: " + " | ".join(tried)[:600] if tried else (last or "no Gemini model configured"))


def _err(r):
    try:
        return str(r.json().get("error", {}).get("message", ""))[:90]
    except Exception:
        return r.text[:90]


_models_cache = None


def available_models():
    """Ask the API which flash models this key can call (names change over time), best first."""
    global _models_cache
    if _models_cache is not None:
        return _models_cache
    _models_cache = []
    try:
        r = net.session().get("https://generativelanguage.googleapis.com/v1beta/models", timeout=30,
                              headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}, params={"pageSize": 200})
        names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in names if re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?|gemini-flash(-lite)?-latest", n)]
        def rank(n):
            v = re.match(r"gemini-(\d+(?:\.\d+)?)", n)
            return (("lite" in n), -(float(v.group(1)) if v else 0.5))
        _models_cache = sorted(flash, key=rank)[:5]
        log_once(f"available flash models: {_models_cache}")
    except Exception as e:
        log_once(f"model list failed: {type(e).__name__}")
    return _models_cache


def gemini_enabled():
    return settings()["ai"].get("provider") == "gemini" and bool(os.getenv("GEMINI_API_KEY"))


def gemini_batch(recs):
    if not gemini_enabled():
        log_once("Gemini not enabled (provider or GEMINI_API_KEY missing)")
        return None
    items = json.dumps([{"headline": r["headline"], "summary": r.get("teaser") or "", "type": TYPE_AR.get(code(r), "")}
                        for r in recs], ensure_ascii=False)
    data = gemini_generate(GEMINI_PROMPT.format(items=items))
    return data if isinstance(data, list) and len(data) == len(recs) else None


def arabize(recs, log=print, limit=60):
    """Adds headline_ar, summary_ar, why_ar, angle_ar to the top `limit` records (others get templates only)."""
    ranked = sorted([r for r in recs if not r.get("duplicate_of") and r.get("priority") != "Reject"],
                    key=lambda r: -int(r.get("overall_score") or 0))
    for r in recs:
        c = code(r)
        if not r.get("why_ar"):
            r["why_ar"] = WHY_AR.get(c, DEFAULT_WHY)
        if not r.get("angle_ar"):
            r["angle_ar"] = ANGLE_AR.get(c, DEFAULT_ANGLE)
    top = ranked[:limit]
    if not top:
        return recs
    done = False
    try:
        for i in range(0, len(top), 10):
            chunk = top[i:i + 10]
            res = gemini_batch(chunk)
            if res is None:
                break
            for r, d in zip(chunk, res):
                r.update(headline_ar=d.get("headline_ar") or "", summary_ar=d.get("summary_ar") or "",
                         why_ar=d.get("why_ar") or r["why_ar"], angle_ar=d.get("angle_ar") or r["angle_ar"], translation="gemini")
            done = i + 10 >= len(top)
        if done:
            log(f"[arabic] {len(top)} stories translated + analysed by Gemini")
            return recs
    except Exception as e:
        log(f"[arabic] Gemini failed, falling back to free translation: {e}"[:700])
        log(f"[arabic] diagnostics: {[x for x in ERRORS if 'model' in x]}"[:400])
    pending = [r for r in top if not r.get("headline_ar")]
    if not pending:
        return recs
    heads = free_translate([r["headline"] for r in pending])
    sums = free_translate([r.get("teaser") or "" for r in pending])
    ok = 0
    for r, h, s in zip(pending, heads, sums):
        if h:
            ok += 1
            r.update(headline_ar=h, summary_ar=s or "", translation="google-translate")
    log(f"[arabic] {ok}/{len(pending)} stories machine-translated (free)" + (f" | first error: {ERRORS[0]}" if ERRORS else ""))
    return recs
