"""
notify.py
Sends a Telegram notification when the digest is ready.
Now includes which newspapers are PRESENT and which are ABSENT for the day.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from collections import Counter

from telegram_downloader import EXPECTED_NEWSPAPERS

log = logging.getLogger(__name__)

EDITION_LABEL = {1: "Bengaluru", 2: "Delhi", 3: "Generic"}


def send(digest_data: dict, downloaded: dict | None = None) -> bool:
    """
    Sends a rich Telegram notification summarising today's digest.
    downloaded: the dict returned by telegram_downloader.run() — used to show
                which edition was downloaded. Pass None if not available.
    Returns True on success, False on failure (non-fatal).
    """
    bot_token = os.environ.get("NOTIFY_BOT_TOKEN", "").strip()
    chat_id   = os.environ.get("NOTIFY_CHAT_ID",   "").strip()
    site_url  = os.environ.get("SITE_URL",          "").strip()

    if not bot_token or not chat_id:
        log.warning("NOTIFY_BOT_TOKEN or NOTIFY_CHAT_ID not set — skipping notification")
        return False

    date       = digest_data.get("date", "Today")
    total      = digest_data.get("total_articles", 0)
    articles   = digest_data.get("articles", [])

    # ── Newspaper present / absent ────────────────────────────────────────────
    present_in_digest = set(
        src.get("newspaper", "")
        for art in articles
        for src in art.get("sources", [])
        if src.get("newspaper")
    )

    present_lines = []
    absent_lines  = []
    for paper in EXPECTED_NEWSPAPERS:
        if paper in present_in_digest:
            edition_info = ""
            if downloaded and paper in downloaded:
                p = downloaded[paper].get("edition_priority", 3)
                edition_info = f" \\({escape(EDITION_LABEL.get(p, ''))}" + " ed\\.\\)"
            present_lines.append(f"  ✅ {escape(paper)}{edition_info}")
        else:
            absent_lines.append(f"  ❌ {escape(paper)}")

    papers_block = ""
    if present_lines:
        papers_block += "*Present:*\n" + "\n".join(present_lines) + "\n"
    if absent_lines:
        papers_block += "*Absent:*\n" + "\n".join(absent_lines) + "\n"

    # ── Top categories ────────────────────────────────────────────────────────
    cat_counts = Counter(a.get("category", "Other") for a in articles)
    cat_lines  = "\n".join(
        f"  › {escape(cat)} \\({count}\\)" for cat, count in cat_counts.most_common(5)
    )

    site_line = f"\n\n[📖 Read today's digest]({site_url})" if site_url else ""

    message = (
        f"📰 *Daily Brief is ready\\!*\n\n"
        f"📅 {escape(date)}\n"
        f"📊 {total} articles · {len(present_in_digest)} newspapers\n\n"
        f"{papers_block}\n"
        f"*Top categories:*\n{cat_lines}"
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
                log.info("Telegram notification sent successfully")
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
