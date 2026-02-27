"""
notify.py
Sends a Telegram notification to your personal chat when the digest is ready.
Uses only Python's built-in urllib — no extra dependencies.

Required environment variables:
  NOTIFY_BOT_TOKEN  — token from @BotFather for your notification bot
  NOTIFY_CHAT_ID    — your personal Telegram chat/user ID
  SITE_URL          — your GitHub Pages URL (e.g. https://user.github.io/repo)
"""

import os
import json
import logging
import urllib.request
import urllib.error
from collections import Counter

log = logging.getLogger(__name__)


def send(digest_data: dict) -> bool:
    """
    Sends a rich Telegram notification summarising today's digest.
    Returns True on success, False on failure (non-fatal — digest still succeeded).
    """
    bot_token = os.environ.get("NOTIFY_BOT_TOKEN", "").strip()
    chat_id   = os.environ.get("NOTIFY_CHAT_ID", "").strip()
    site_url  = os.environ.get("SITE_URL", "").strip()

    if not bot_token or not chat_id:
        log.warning("NOTIFY_BOT_TOKEN or NOTIFY_CHAT_ID not set — skipping notification")
        return False

    date       = digest_data.get("date", "Today")
    total      = digest_data.get("total_articles", 0)
    newspapers = digest_data.get("newspapers", [])
    articles   = digest_data.get("articles", [])

    # Top 5 categories by article count
    cat_counts  = Counter(a.get("category", "Other") for a in articles)
    cat_lines   = "\n".join(
        f"  › {cat} ({count})" for cat, count in cat_counts.most_common(5)
    )

    site_line = f"\n\n[📖 Read today's digest]({site_url})" if site_url else ""

    message = (
        f"📰 *Daily Brief is ready\\!*\n\n"
        f"📅 {escape(date)}\n"
        f"📊 {total} articles · {len(newspapers)} newspapers\n\n"
        f"*Top categories:*\n{escape(cat_lines)}"
        f"{site_line}"
    )

    payload = json.dumps({
        "chat_id":                  chat_id,
        "text":                     message,
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
            if result.get("ok"):
                log.info("✅ Telegram notification sent successfully")
                return True
            else:
                log.error(f"Telegram API error: {result}")
                return False

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.error(f"Telegram HTTP {e.code}: {body}")
        return False
    except Exception as e:
        log.error(f"Notification failed: {e}")
        return False


def escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
