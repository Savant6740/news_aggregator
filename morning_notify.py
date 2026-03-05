"""
morning_notify.py
Runs at 9 AM IST every day. Reads last night's digest_state.json and sends
a Telegram message with a summary and link to the digest site.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST        = timezone(timedelta(hours=5, minutes=30))
STATE_FILE = Path("docs/digest_state.json")
DIGEST_FILE = Path("docs/digest.json")


def escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    payload = json.dumps({
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "MarkdownV2",
        "disable_web_page_preview": False,
    }).encode("utf-8")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    req = urllib.request.Request(
        url,
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"Telegram HTTP {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Notification failed: {e}")
        return False


def main():
    bot_token = os.environ.get("NOTIFY_BOT_TOKEN", "").strip()
    chat_id   = os.environ.get("NOTIFY_CHAT_ID",   "").strip()
    site_url  = os.environ.get("SITE_URL",          "").strip()

    if not bot_token or not chat_id:
        print("NOTIFY_BOT_TOKEN or NOTIFY_CHAT_ID not set — skipping")
        return

    # Read digest data
    if not DIGEST_FILE.exists():
        print("No digest.json found — digest may not have run yet")
        msg = (
            "⚠️ *Good Morning\\!*\n\n"
            "No digest was found for today\\. "
            "The nightly pipeline may not have completed yet\\."
        )
        send_message(bot_token, chat_id, msg)
        return

    digest = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
    date         = digest.get("date", "Today")
    total        = digest.get("total_articles", 0)
    newspapers   = digest.get("newspapers", [])
    articles     = digest.get("articles", [])

    # Top 3 most important articles
    top_articles = sorted(articles, key=lambda a: a.get("importance", 0), reverse=True)[:3]

    top_lines = []
    for i, art in enumerate(top_articles, 1):
        headline = escape(art.get("headline", ""))
        category = escape(art.get("category", ""))
        top_lines.append(f"{i}\\. *{headline}* _{category}_")

    top_block = "\n".join(top_lines) if top_lines else "_No articles found_"

    papers_block = escape(", ".join(newspapers)) if newspapers else "_None_"

    site_line = f"\n\n[📖 Read full digest]({site_url})" if site_url else ""

    message = (
        f"☀️ *Good Morning\\! Here's your Daily Brief*\n\n"
        f"📅 {escape(date)}\n"
        f"📊 {escape(str(total))} articles from {escape(str(len(newspapers)))} newspapers\n\n"
        f"*Top stories:*\n{top_block}\n\n"
        f"*Newspapers:* {papers_block}"
        f"{site_line}"
    )

    success = send_message(bot_token, chat_id, message)
    if success:
        print("✅ Morning notification sent successfully")
    else:
        print("❌ Failed to send morning notification")


if __name__ == "__main__":
    main()
