# Test Results

## Phase 5a — Offline end-to-end tests (2026-11-18, Claude workspace) — **PASSED (2/2)**
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
| Notifications | Email (subject format, PDF attached) and Telegram (photo/message/document) called once; **no duplicate send** on re-run (mocked transports) |

`Documentation/test_output.txt` has the raw pytest output.

## Phase 5b — Live test on GitHub Actions — **PENDING**
Blocked until the repository and secrets exist (see OPERATING_GUIDE §Setup). The first `validate` run will produce the real RSS status for all 102 sources in `Database/sources.csv`. Results will be appended here.
