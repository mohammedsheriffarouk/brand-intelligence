"""Notifications: Email (SMTP — Gmail App Password or any SMTP) and Telegram Bot.
Secrets from env only: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
Never sends the same report twice (Logs/notifications_sent.json)."""
import html, json, os, smtplib
from email.message import EmailMessage
from pathlib import Path

from . import net
from .analyze import MENA
from .config import settings

ROOT = Path(__file__).resolve().parent.parent
SENT = ROOT / "Logs" / "notifications_sent.json"
E = html.escape


def _sent():
    return json.loads(SENT.read_text()) if SENT.exists() else {}


def _mark(key):
    d = _sent()
    d[key] = True
    SENT.parent.mkdir(exist_ok=True)
    SENT.write_text(json.dumps(d, indent=1))


def report_url(rep):
    base = settings()["notifications"].get("report_base_url") or os.getenv("PAGES_URL", "")
    return f"{base.rstrip('/')}/{rep['folder']}/{rep['fname']}.html" if base else ""


def _item(n):
    data = "".join(f"<br>• {E(str(f.get('value')))} — {E(str(f.get('metric')))} <i>({E(str(f.get('status')))})</i>" for f in n["financial_data"][:3])
    img = f'<img src="{E(n["image_url"])}" width="100%" style="max-width:560px;border-radius:8px;display:block;margin:0 0 8px">' if n.get("image_url") else ""
    return (f'<div style="border:1px solid #E6E0D8;border-radius:10px;padding:12px 14px;margin:10px 0">{img}'
            f'<div style="font-size:12px;color:#6B645C">{E(n["news_type"])} · {E(n["source_name"])} · {E(n["pub_display"])} · <b>{n["overall_score"]}/100</b></div>'
            f'<div style="font-size:16px;font-weight:600;margin:4px 0" dir="auto"><a href="{E(n["url"])}" style="color:#14110F">{E(n["headline"])}</a></div>'
            f'<div style="font-size:14px" dir="auto">{E(n["short_summary"])}</div>'
            f'<div style="font-size:13px;color:#44403C;margin-top:4px"><b>Why it matters:</b> {E(n["why_it_matters"].split("] ")[-1])}</div>'
            f'{"<div style=font-size:13px;background:#FFF7ED;padding:6px;border-radius:6px;margin-top:6px><b>Data</b>" + data + "</div>" if data else ""}'
            f'<a href="{E(n["url"])}" style="font-size:13px;color:#C2410C;font-weight:600">Read original ↗</a></div>')


def email_html(rep):
    rows, url = rep["rows"], report_url(rep)
    sec = lambda title, items: (f'<h2 style="font-family:Georgia,serif;font-size:19px;border-top:1px solid #E6E0D8;padding-top:12px">{title}</h2>'
                                + ("".join(_item(n) for n in items) if items else '<p style="color:#6B645C;font-size:13px">Nothing significant today.</p>'))
    by = lambda c: [r for r in rows[5:] if r["main_category"] == c][:4]
    execs = [f"<b>{len(rows)}</b> relevant stories · <b>{len(rep['high'])}</b> high priority · <b>{len(rep['mena'])}</b> regional · <b>{len(rep['tools'])}</b> tools/AI"]
    if url:
        execs.append(f'<a href="{url}">Open the full report online</a> (PDF attached)')
    parts = [f'<div style="max-width:640px;margin:auto;font-family:Arial,sans-serif;color:#14110F">',
             f'<div style="font-size:12px;letter-spacing:.12em;color:#C2410C;text-transform:uppercase;font-weight:bold">Brand Intelligence</div>',
             f'<h1 style="font-family:Georgia,serif;margin:4px 0">Daily Brief — {E(rep["label"])}</h1>',
             sec("1. Executive summary", []).replace("Nothing significant today.", "<br>".join(execs)),
             sec("2. Top stories", rows[:5]), sec("3. Branding &amp; rebranding", by("Branding & Rebranding")),
             sec("4. Business impact &amp; brand value", by("Business Impact & Brand Value")),
             sec("5. Tools &amp; AI updates", by("Tools & AI Updates")), sec("6. Agency &amp; studio news", by("Agency & Studio News")),
             sec("7. Research &amp; industry insights", by("Research & Industry Insights")),
             sec("8. MENA &amp; GCC developments", [r for r in rep["mena"] if r not in rows[:5]][:4])]
    opps = "".join(f'<li>{E(r["content_angle"])} — <a href="{E(r["url"])}">{E(r["headline"])}</a></li>' for r in rows[:6] if r.get("content_angle"))
    parts.append(f'<h2 style="font-family:Georgia,serif;font-size:19px">9. Content opportunities</h2><ul style="font-size:13px">{opps}</ul>')
    refs = "".join(f'<li>{E(r["source_name"])} — <a href="{E(r["url"])}">{E(r["url"][:90])}</a></li>' for r in rows[:40])
    parts.append(f'<h2 style="font-family:Georgia,serif;font-size:19px">10. Source references</h2><ol style="font-size:11px;color:#6B645C">{refs}</ol></div>')
    return "".join(parts)


def send_email(rep, log=print):
    cfg = settings()["notifications"]
    key = f"email:{rep['fname']}"
    smtp_ok = all(os.getenv(k) for k in ["SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"])
    script_ok = os.getenv("SHEETS_WEBAPP_URL") and os.getenv("SHEETS_SECRET")
    if not cfg["email_enabled"] or not (smtp_ok or script_ok):
        log("[email] skipped: disabled, or neither SMTP nor Apps Script (SHEETS_WEBAPP_URL/SECRET) configured")
        return "skipped"
    if _sent().get(key):
        log("[email] already sent for this report — no duplicate")
        return "duplicate-prevented"
    if not rep["rows"] and not cfg["send_empty_status_email"]:
        log("[email] nothing meaningful; status email disabled")
        return "skipped-empty"
    kind = rep["kind"].capitalize()
    subject = f"Brand Intelligence {kind} Brief — {rep['label']}"
    if not smtp_ok:   # send through the Google Apps Script web app (MailApp, from the user's own Gmail)
        import base64
        pdf = rep.get("pdf")
        payload = {"secret": os.environ["SHEETS_SECRET"], "action": "email", "to": os.getenv("EMAIL_TO", ""),
                   "subject": subject, "html": email_html(rep), "text": f"{len(rep['rows'])} stories. {report_url(rep)}",
                   "pdf_name": Path(pdf).name if pdf and Path(pdf).exists() else None,
                   "pdf_base64": base64.b64encode(Path(pdf).read_bytes()).decode() if pdf and Path(pdf).exists() else None}
        try:
            r = net.session().post(os.environ["SHEETS_WEBAPP_URL"], data=json.dumps(payload).encode(),
                                   headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=120)
            if '"emailed":true' not in r.text.replace(" ", ""):
                raise RuntimeError(r.text[:200])
            _mark(key)
            log("[email] sent via Apps Script")
            return "sent"
        except Exception as e:
            log(f"[email] FAILED (Apps Script): {e}")
            return f"failed: {e}"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"], msg["To"] = os.environ["SMTP_USER"], os.environ["EMAIL_TO"]
    msg.set_content(f"Brand Intelligence {kind} — {rep['label']}\n{len(rep['rows'])} stories. Full report: {report_url(rep) or 'attached'}")
    msg.add_alternative(email_html(rep), subtype="html")
    for p in (rep.get("pdf"),):
        if p and Path(p).exists():
            msg.add_attachment(Path(p).read_bytes(), maintype="application", subtype="pdf", filename=Path(p).name)
    try:
        host, port = os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "465"))
        with smtplib.SMTP_SSL(host, port, timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        _mark(key)
        log("[email] sent")
        return "sent"
    except Exception as e:
        log(f"[email] FAILED: {e}")
        return f"failed: {e}"


CHAT_FILE = ROOT / "Configuration" / "telegram_chat.json"


def chat_id(log=print):
    """TELEGRAM_CHAT_ID secret, else saved file, else auto-detect from the last message sent to the bot."""
    if os.getenv("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    if CHAT_FILE.exists():
        return json.loads(CHAT_FILE.read_text())["chat_id"]
    try:
        r = net.session().get(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/getUpdates", timeout=30).json()
        chats = [u[k]["chat"]["id"] for u in r.get("result", []) for k in ("message", "my_chat_member") if k in u]
        if chats:
            CHAT_FILE.write_text(json.dumps({"chat_id": str(chats[-1])}))
            log(f"[telegram] chat id auto-detected and saved")
            return str(chats[-1])
    except Exception as e:
        log(f"[telegram] chat id detection failed: {e}")
    log("[telegram] no chat id yet: send any message to your bot, then it will be detected next run")
    return None


def _tg(method, data=None, files=None):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    r = net.session().post(f"https://api.telegram.org/bot{tok}/{method}", data=data, files=files, timeout=60)
    if not r.json().get("ok"):
        raise RuntimeError(r.text[:200])


def telegram_text(rep):
    rows, url = rep["rows"], report_url(rep)
    t = [f"<b>Brand Intelligence — {E(rep['label'])}</b>",
         f"{len(rows)} stories · {len(rep['high'])} high priority · {rep['collected']} collected", ""]
    for i, n in enumerate(rows[:5], 1):
        t.append(f"{i}. <a href=\"{E(n['url'])}\">{E(n['headline'][:110])}</a> — {E(n['source_name'])} ({n['overall_score']})")
    if rep["mena"]:
        m = rep["mena"][0]
        t += ["", f"🌍 Regional: <a href=\"{E(m['url'])}\">{E(m['headline'][:110])}</a>"]
    if rep["tools"]:
        m = rep["tools"][0]
        t += [f"🛠 Tool/AI: <a href=\"{E(m['url'])}\">{E(m['headline'][:110])}</a>"]
    if url:
        t += ["", f"📄 <a href=\"{url}\">Full report</a>"]
    return "\n".join(t)


def send_telegram(rep, log=print):
    cfg = settings()["notifications"]
    key = f"telegram:{rep['fname']}"
    if not cfg["telegram_enabled"] or not os.getenv("TELEGRAM_BOT_TOKEN"):
        log("[telegram] skipped: TELEGRAM_BOT_TOKEN not set")
        return "skipped"
    if _sent().get(key):
        log("[telegram] already sent — no duplicate")
        return "duplicate-prevented"
    chat = chat_id(log)
    if not chat:
        return "skipped-no-chat"
    try:
        text = telegram_text(rep)
        if rep.get("png") and Path(rep["png"]).exists():
            with open(rep["png"], "rb") as f:
                _tg("sendPhoto", {"chat_id": chat, "caption": f"Daily Brief — {rep['label']}"}, {"photo": f})
        _tg("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        if rep.get("pdf") and Path(rep["pdf"]).exists():
            with open(rep["pdf"], "rb") as f:
                _tg("sendDocument", {"chat_id": chat}, {"document": f})
        _mark(key)
        log("[telegram] sent")
        return "sent"
    except Exception as e:
        log(f"[telegram] FAILED: {e}")
        return f"failed: {e}"


def critical_alerts(records, log=print):
    cfg = settings()["notifications"]
    if not (cfg["telegram_enabled"] and os.getenv("TELEGRAM_BOT_TOKEN")):
        return 0
    chat = chat_id(log)
    if not chat:
        return 0
    n = 0
    for r in records:
        if int(r.get("overall_score") or 0) >= cfg["critical_alert_score"] and r.get("date_status") == "fresh" \
                and not r.get("duplicate_of") and not _sent().get("alert:" + r["news_id"]):
            try:
                _tg("sendMessage", {"chat_id": chat, "parse_mode": "HTML",
                                    "text": f"🚨 <b>High-impact:</b> <a href=\"{E(r['url'])}\">{E(r['headline'])}</a>\n{E(r['source_name'])} · {r['overall_score']}/100"})
                _mark("alert:" + r["news_id"])
                n += 1
            except Exception as e:
                log(f"[alert] failed: {e}")
    return n
