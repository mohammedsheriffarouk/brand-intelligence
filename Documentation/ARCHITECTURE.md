# Architecture, Audit & Limitations

## Environment audit (2026-11-18)
| Capability | Finding | Decision |
|---|---|---|
| Claude cloud workspace | Python 3.13, Node 22, pandoc, wkhtmltopdf; **outbound web blocked** (only package registries) | Build + offline tests here; cannot run collection here |
| GitHub | Account `mohammedsheriffarouk` with push rights; Actions = free cron + full internet | **Execution engine** |
| Claude scheduled tasks | Available, but each run is a fresh session (no persistent files) and the user asked for no connectors | Not used for core pipeline |
| AI API | None; Claude subscription ≠ API credits | Rule-based default; optional Gemini free tier / paid Claude API, hard-capped |
| Email / Telegram | Not configured | SMTP + Telegram Bot API from Actions (user adds secrets) |

## Components (`engine/`)
| Module | Role |
|---|---|
| `sources.py` | Registry sync from `Configuration/sources_seed.yaml`; validation = homepage check → RSS autodiscovery (`<link rel=alternate>`) → testing common feed paths. A feed is "working" only after it downloads and parses with ≥1 entry |
| `collect.py` | Per-source frequency; RSS first, else Google News RSS `site:` search; thematic + regional (EN/AR) discovery queries; failures logged + retried next run |
| `process.py` | URL canonicalisation (tracking params stripped) → `duplicate_key`; title fingerprint → cross-source `duplicate_of` linking; publication-date validation (fresh / older / missing / future) |
| `analyze.py` | Taxonomy N01–N20, industry, geography, companies, agencies; financial figure extraction labelled by metric; 7-criterion score /100 with explanation; editorial status; rebrand & tool analysis (missing = "Not Disclosed") |
| `enrich.py` | og:image for top stories (robots.txt respected); optional LLM analysis from article text (never from headline alone) |
| `db.py` | SQLite (`sources`, `news`, `runs`, `collection_log`), CSV/JSON export, plain SQL → easy migration |
| `sheets.py` + `google_apps_script.gs` | Push Sources/News/Runs to Google Sheet (upsert, secret-protected); doGet serves news JSON for the viewer |
| `report.py` | Daily/Weekly/Monthly HTML (mobile, images, links), Markdown, PDF, PNG brief card (Playwright Chromium; wkhtmltopdf fallback) |
| `notify.py` | Email (sections 1–10, PDF attached), Telegram (PNG card + top stories + PDF), critical alerts ≥92; de-duplicated sends |
| `pipeline.py` | Orchestration, backups (14 daily SQLite snapshots + git history), run log, status dashboard (`Reports/index.html`, `status.json`), viewer |

## Scoring (out of 100)
Relevance 20 · Business impact 20 · Innovation 15 · Source credibility 15 (reliability × 3; unknown publishers 6) · Evidence 15 · Content potential 10 · Regional 5.
Rules: regional points only added if base ≥ 50 · older articles −10 · financial claims from non-official sources with reliability < 4 capped at evidence 8 and marked **"Needs verification — not approved for publication"** · duplicates linked, not re-scored.
Bands: 85+ High Priority · 70–84 Worth Following · 55–69 Research Only · <55 Reject.

## Information labels
Verified (from feed: headline, URL, source, publication date) · Publisher claims (summaries, figures) · Third-party analysis (rankings) · AI-generated interpretation (why it matters, implications, angles: always prefixed).

## Cost
GitHub Actions (public repo: free; private: 2,000 free min/month, this uses ~150) · Pages free (public repo) · Telegram free · Gmail SMTP free · Google Sheets/Apps Script free · Gemini optional free tier (rate-limited; Google may use free-tier data) · Claude API optional **paid**. Default configuration = **$0**.

## Known limitations (honest list)
1. **Rule-based analysis is shallow.** Without an AI key, "why it matters" and content angles are templates per news type, and summaries are publisher excerpts. Classification works from headline + feed summary, so expect some misclassification. Enable Gemini for real per-article analysis.
2. **Google News links** are Google redirect URLs: they open the right article, but images can't be fetched for them.
3. **Paywalled sources** (WARC, MEED, parts of HBR/Marketing Week) yield headlines only. Never bypassed.
4. **Agency sites often have no RSS**; they're covered through `site:` search, which only finds pages Google News indexes (weaker for case-study pages).
5. **Company/agency extraction** uses keyword lists + headline patterns. It will miss names not in `taxonomy.yaml`.
6. **Financial verification** is rule-based (source officialness + reliability). It flags claims; it doesn't cross-check numbers against filings.
7. GitHub cron can be delayed up to ~30 min. Public repo means reports on Pages are public.
8. Viewer PNG export skips images whose host blocks cross-origin use (PDF export keeps them).
