# Brand Intelligence — دليل التشغيل

## الفكرة في سطرين
GitHub Actions بيشغّل السيستم كل يوم الصبح (مجاناً). بيجمع الأخبار ويصنّفها ويديها درجات، ويحفظها في SQLite وفي **Google Sheet**، ويطلع تقرير HTML و PDF و PNG، ويبعتلك **Telegram** (صورة + PDF + لينكات) و**إيميل**.

```
Sources Registry ─► Collector (RSS → Google News search) ─► Dedup + date check ─► Classify ─► Score
     ─► (optional AI) ─► SQLite + CSV/JSON ─► Google Sheet ─► Reports (HTML/MD/PDF/PNG) ─► Telegram + Email + GitHub Pages
```

## الإعداد لأول مرة (حوالي 20 دقيقة، مرة واحدة)

### 1) الـ repo
- اعمل repo جديد على GitHub باسم `brand-intelligence` (مقترح Public، عشان GitHub Pages ببلاش. التقارير فيها أخبار منشورة أصلاً).
- Claude بيعمل push للكود.
- **Settings → Pages → Source: GitHub Actions**.

### 2) Telegram (الإشعارات على الموبايل)
1. في Telegram افتح **@BotFather** واكتب `/newbot` واختار اسم، هيديك **token**.
2. ابعت للبوت بتاعك أي رسالة. السيستم هيجيب الـ chat id لوحده في أول تشغيلة.

### 3) Google Sheet (الداتابيز + إرسال الإيميل)
1. اعمل Google Sheet جديد باسم "Brand Intelligence DB".
2. Extensions → **Apps Script**: امسح الموجود والصق محتوى `Documentation/google_apps_script.gs` وبعدين Save.
3. ⚙️ Project Settings → Script properties → Add: `SECRET` = نص عشوائي طويل.
4. Deploy → New deployment → **Web app** → Execute as: **Me** → Who has access: **Anyone** → Deploy → وافق على الصلاحيات (كتابة في الشيت + إرسال إيميل من حسابك) → انسخ **Web app URL**.
   الإيميل اليومي بيتبعت من Gmail بتاعك عن طريق السكريبت ده، فمش محتاج App Password ولا SMTP.

### 4) الـ Secrets في GitHub (3 بس)
Repo → Settings → Secrets and variables → Actions:

| Secret | القيمة |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token من BotFather |
| `SHEETS_WEBAPP_URL` | Web app URL |
| `SHEETS_SECRET` | نفس قيمة SECRET |
| *(اختياري)* `EMAIL_TO` | لو عايز التقرير يروح لإيميل غير حساب Google بتاع الشيت |
| *(اختياري)* `GEMINI_API_KEY` | تحليل AI أعمق، ومعاه غيّر `ai.provider: gemini` |
| *(اختياري)* `SMTP_USER`/`SMTP_PASSWORD`/`EMAIL_TO` | لو حبيت SMTP بدل السكريبت |

### 5) أول تشغيل
Actions → **Validate all sources (manual)** → Run workflow (بيختبر الـ 100 مصدر كلهم، حوالي 10-15 دقيقة). بعدها **Daily collection & brief** → Run workflow.

## التشغيل اليومي
| عايز | تعمل إيه |
|---|---|
| **تشغّل** | مفيش حاجة، شغال لوحده كل يوم 06:17 بتوقيت القاهرة (07:17 في التوقيت الصيفي) |
| **تشغيل فوري** | Actions → Daily collection & brief → Run workflow |
| **توقّف** | Actions → اختار الـ workflow → ⋯ → **Disable workflow** |
| **تعيد التشغيل** | نفس المكان → **Enable workflow** (أو Re-run لتشغيلة فاشلة) |
| **تراقب** | Actions (كل تشغيلة بلوجها) · `Reports/index.html` على Pages (لوحة الحالة) · فولدر `Logs/` |
| **تشوف التقارير** | Telegram / الإيميل · `https://<user>.github.io/brand-intelligence/` · فولدر `Reports/` · **viewer.html** (بيقرأ من الشيت، وفيه فلاتر وتصدير PDF/PNG) |
| **تضيف/تشيل مصدر** | عدّل `Configuration/sources_seed.yaml` (من GitHub نفسه ← ✏️) ← commit. المصدر الجديد بيتعمله validate أوتوماتيك في التشغيلة الجاية |
| **تغيّر التردد** | لكل مصدر: `frequency: daily/weekly`. لميعاد التشغيل: سطر `cron` في `.github/workflows/daily.yml` (بتوقيت UTC) |
| **تغيّر كلمات البحث/الإقليم** | `search_discovery.queries` في `Configuration/settings.yaml` |
| **تعدّل التصنيف** | `Configuration/taxonomy.yaml` (كلمات لكل نوع خبر/صناعة/منطقة/وكالات) |
| **تشغّل محلياً** | `pip install -r requirements.txt && python run.py daily --no-notify` |

## حل المشاكل
| العَرَض | السبب والحل |
|---|---|
| مفيش رسالة Telegram | ابعت للبوت أي رسالة (عشان الـ chat id يتجاب) واتأكد من الـ TOKEN. اللوج: `[telegram] ...` |
| مفيش إيميل | اتأكد إن الـ Deployment اتعمله New version بعد آخر تعديل، وإنك وافقت على صلاحية الإيميل. اللوج: `[email] FAILED` |
| الشيت مش بيتحدث | SHEETS_WEBAPP_URL/SECRET، ولازم الـ deployment يكون Anyone. ولو عدّلت السكريبت، اعمل **New version** من Manage deployments |
| مصدر بيفشل | شوف `Reports/status.json` ← failed_sources. السيستم بيعيد المحاولة كل تشغيلة، وبعد 10 مرات فشل متتالية بيبطّأ لأسبوعي (عمره ما بيعامل الفاشل كأنه فاضي) |
| التشغيلة اتأخرت | جدولة GitHub ممكن تتأخر 5-30 دقيقة في أوقات الزحمة. ده عادي |
| الـ workflow وقف لوحده | GitHub بيوقف الجدولة بعد 60 يوم من غير نشاط على الـ repo. الـ commit اليومي بيمنع ده، ولو حصل اعمل Enable |
