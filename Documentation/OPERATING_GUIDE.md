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
1. في Telegram افتح **@BotFather** واكتب `/newbot`، واختار اسم. هياخدك لـ **token**.
2. افتح البوت بتاعك واكتب له أي رسالة.
3. افتح في المتصفح: `https://api.telegram.org/bot<TOKEN>/getUpdates` وخد الرقم اللي جنب `"chat":{"id":`. ده الـ **chat id**.

### 3) الإيميل (Gmail SMTP)
1. لازم 2-Step Verification يكون شغال على حساب Google.
2. ادخل myaccount.google.com → Security → **App passwords** واعمل password جديد اسمه "Brand Intelligence" (16 حرف).

### 4) Google Sheet (الداتابيز الأساسية)
1. اعمل Google Sheet جديد باسم "Brand Intelligence DB".
2. Extensions → **Apps Script** ← امسح الموجود والصق محتوى `Documentation/google_apps_script.gs` ← Save.
3. ⚙️ Project Settings → Script properties → Add: `SECRET` = نص عشوائي طويل (اعمل واحد هنا: `python -c "import secrets;print(secrets.token_urlsafe(32))"`، أو اكتب 40 حرف عشوائي).
4. Deploy → New deployment → النوع **Web app** → Execute as: **Me** → Who has access: **Anyone** → Deploy → وافق على الصلاحيات ← انسخ **Web app URL**.
   (الكتابة محمية بالـ SECRET. القراءة بتطلع أعمدة الأخبار بس، للـ Viewer.)

### 5) حط الـ Secrets في GitHub (مش في الشات خالص)
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | القيمة |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token من BotFather |
| `TELEGRAM_CHAT_ID` | الرقم من getUpdates |
| `SMTP_USER` | إيميل Gmail بتاعك |
| `SMTP_PASSWORD` | App Password (16 حرف) |
| `EMAIL_TO` | الإيميل اللي يوصله التقرير |
| `SHEETS_WEBAPP_URL` | Web app URL من Apps Script |
| `SHEETS_SECRET` | نفس قيمة SECRET |
| `GEMINI_API_KEY` | *(اختياري)* لتحليل AI أعمق، ومعاه غيّر `ai.provider: gemini` في settings.yaml |

### 6) أول تشغيل
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
| مفيش رسالة Telegram | اتأكد من TOKEN و CHAT_ID، وإنك بعتّ للبوت رسالة قبل كده. اللوج هيقول `[telegram] skipped/FAILED` |
| مفيش إيميل | App Password غلط أو 2FA مقفول. اللوج: `[email] FAILED` |
| الشيت مش بيتحدث | SHEETS_WEBAPP_URL/SECRET، ولازم الـ deployment يكون Anyone. ولو عدّلت السكريبت، اعمل **New version** من Manage deployments |
| مصدر بيفشل | شوف `Reports/status.json` ← failed_sources. السيستم بيعيد المحاولة كل تشغيلة، وبعد 10 مرات فشل متتالية بيبطّأ لأسبوعي (عمره ما بيعامل الفاشل كأنه فاضي) |
| التشغيلة اتأخرت | جدولة GitHub ممكن تتأخر 5-30 دقيقة في أوقات الزحمة. ده عادي |
| الـ workflow وقف لوحده | GitHub بيوقف الجدولة بعد 60 يوم من غير نشاط على الـ repo. الـ commit اليومي بيمنع ده، ولو حصل اعمل Enable |
