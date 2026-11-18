# Test Results

## Phase 5a — Offline end-to-end tests (2026-11-18, Claude workspace) — **PASSED (3/3)**
Run with `python -m pytest -v tests` against **synthetic fixture feeds** (example.com, clearly fake), because the build workspace has no outbound web access.

| Area | Verified |
|---|---|
| Source validation | RSS found via `<link rel=alternate>` (RSS & Atom) and via testing common paths; unreachable site → `search_discovery` + error logged; newsletter detection |
| Collection | 4 sources, multiple categories incl. a regional (Saudi) source, an official tool vendor, a business story |
| Failed sources | Dead source logged as failed (`consecutive_failures`), retried next run, never treated as empty |
| Dedup | Tracking params stripped; same story from 2 sources linked via `duplicate_of`; 2nd run → 0 new, all prevented |
| Dates | 9-day-old article marked "older article (not breaking)" and penalised |
| Classification | Rebrand → N02 + Saudi Arabia + Pentagram; brand value → N09 with "Brand Value" metric; Figma → Tools & AI; telecom results → N08 |
| Scoring | All scores 0–100 with explanation; unverified financial claim flagged; regional points withheld for weak story |
| No fabrication | Rebrand fields not in source = "Not Disclosed" |
| Database | SQLite + news/sources CSV & JSON exports |
| Reports | Daily HTML + MD + **PDF + PNG brief card** generated; weekly report generated; status dashboard + viewer + data JSON |
| Notifications | Email via SMTP and via Apps Script (PDF attached), Telegram chat-id auto-detect, and Telegram (photo/message/document) called once; **no duplicate send** on re-run (mocked transports) |

`Documentation/test_output.txt` has the raw pytest output.

## Phase 5b — Live test on GitHub Actions (2026-11-18) — **PASSED**
| Check | Result |
|---|---|
| Source validation (all 102) | 29 working RSS feeds (tested), 73 via Google News `site:` search. Bot-blocked (HTTP 403): Design Week, Creative Review, The Drum, Marketing Week, Adobe, Canva, OpenAI, Arab News, Khaleej Times, Ahram Online, others |
| Collection | 102 sources checked, 0 failed; 1,345 items seen on first run |
| Dedup | 43 duplicates on run 1; run 2 → 139 prevented, 1 new |
| Non-article filter | 238 agency office/contact/login pages removed after real-data review |
| Reports | Daily HTML + MD + PDF + PNG generated in Actions (Playwright Chromium) |
| Email | Sent via Apps Script (MailApp); re-runs → "no duplicate" |
| Telegram | Chat id auto-detected; brief image + top stories + PDF delivered |
| Google Sheet | Sources (102), News (1,339), Runs synced |
| Viewer | Live on GitHub Pages, reads the Sheet via Apps Script; filters render, no console errors |
| Scoring after tuning | First-day fresh stories: 4 Worth Following, ~55 Research Only, rest rejected as off-topic business news. 0 High Priority (expected for rule-based scoring without article text) |
