# Brand Intelligence Automation System

Automated daily intelligence on branding, design, marketing & creative industries: Global · Middle East · GCC · Egypt.

- **Runs on:** GitHub Actions (free), daily 06:17 Cairo, weekly Saturday, monthly on the 1st
- **Stores in:** Google Sheet (master view) + `Database/news.sqlite` + CSV/JSON
- **Delivers:** Telegram (image brief + PDF + links), email (full brief + PDF), GitHub Pages (HTML reports, live viewer, status dashboard)
- **Costs:** $0 by default

Start here → [`Documentation/OPERATING_GUIDE.md`](Documentation/OPERATING_GUIDE.md) · Design & limits → [`Documentation/ARCHITECTURE.md`](Documentation/ARCHITECTURE.md)

```
python run.py validate   # test every source, discover real RSS feeds
python run.py daily      # full daily pipeline
python run.py weekly | monthly | status
```
