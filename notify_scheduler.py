"""
notify_scheduler.py
Inshorts-style scheduled push notifications via ntfy.sh.

How it works:
- Generates a DETERMINISTIC schedule from digest.json at a fixed start time (09:00 IST)
- Each article gets a calculated send_at_epoch, evenly spread to 22:00 IST
- This script is called every 30 min by GitHub Actions cron
- Each run sends only the article(s) whose window falls in [now-35min, now+5min]
- Round-robin across categories so topics vary throughout the day
- No state file needed — schedule is always recomputed from digest.json

Delivery: ntfy.sh (free, open-source push service)
  - Install 'ntfy' app on Android/iOS
  - Subscribe to your NTFY_TOPIC (set as a GitHub Secret)
  - Notifications show headline in notification bar, summary expands on long-press
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib import request as urlreq
from collections import defaultdict

IST         = timezone(timedelta(hours=5, minutes=30))
DIGEST_FILE = Path("docs/digest.json")

# Fixed schedule window
SCHEDULE_START_HOUR   = 9   # 9:00 AM IST (digest finishes well before this)
SCHEDULE_END_HOUR     = 22  # 10:00 PM IST

# Round-robin category priority order
CATEGORY_ORDER = [
    "Politics", "Economy", "India", "World", "Business",
    "Technology", "Science", "Health", "Sports", "Law",
    "Environment", "Infrastructure", "Education", "Culture",
]

CATEGORY_EMOJI = {
    "Politics":       "🏛️",
    "Economy":        "📊",
    "India":          "🇮🇳",
    "World":          "🌍",
    "Business":       "💼",
    "Technology":     "💻",
    "Science":        "🔬",
    "Health":         "🏥",
    "Sports":         "🏆",
    "Law":            "⚖️",
    "Environment":    "🌿",
    "Infrastructure": "🏗️",
    "Education":      "📚",
    "Culture":        "🎭",
}


# ── Article ordering ───────────────────────────────────────────────────────────

def round_robin_articles(articles: list[dict]) -> list[dict]:
    """
    Interleave articles from all categories in round-robin order.
    Within each category, highest-importance articles come first.
    """
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for art in articles:
        cat = art.get("category", "India")
        by_cat[cat].append(art)

    # Sort by importance descending within each category
    for cat in by_cat:
        by_cat[cat].sort(key=lambda a: a.get("importance", 0), reverse=True)

    # Build ordered category list (known order first, then unknowns)
    ordered = [c for c in CATEGORY_ORDER if c in by_cat]
    extra   = [c for c in by_cat         if c not in CATEGORY_ORDER]
    cats    = ordered + extra

    result: list[dict] = []
    while any(by_cat[c] for c in cats):
        for cat in cats:
            if by_cat[cat]:
                result.append(by_cat[cat].pop(0))

    return result


# ── Schedule computation ───────────────────────────────────────────────────────

def build_schedule(articles: list[dict], date_str: str) -> list[dict]:
    """
    Assign a deterministic send_at_epoch to each article.
    Schedule is fixed per date: 09:00 IST → 22:00 IST.
    The epoch is computed purely from the article index — no randomness.
    """
    # Parse the digest date to build IST datetimes
    try:
        base_date = datetime.strptime(date_str, "%d %b %Y")
    except ValueError:
        try:
            base_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            base_date = datetime.now(IST).replace(tzinfo=None)

    start = datetime(base_date.year, base_date.month, base_date.day,
                     SCHEDULE_START_HOUR, 0, 0, tzinfo=IST)
    end   = datetime(base_date.year, base_date.month, base_date.day,
                     SCHEDULE_END_HOUR,   0, 0, tzinfo=IST)

    n = len(articles)
    if n == 0:
        return []

    total_seconds = (end - start).total_seconds()
    interval      = total_seconds / n          # seconds between notifications

    scheduled = []
    for i, art in enumerate(articles):
        send_at = start + timedelta(seconds=i * interval)
        scheduled.append({
            **art,
            "_send_at_epoch": int(send_at.timestamp()),
            "_send_at_ist":   send_at.strftime("%H:%M"),
        })

    return scheduled


# ── ntfy.sh delivery ───────────────────────────────────────────────────────────

def send_ntfy(
    topic:    str,
    title:    str,
    body:     str,
    click:    str = "",
    tags:     list[str] | None = None,
    priority: str = "default",
) -> bool:
    """
    POST a push notification to ntfy.sh.

    On Android the notification shows:
    - Title line  → headline (shown in collapsed notification bar)
    - Body line   → category + summary (visible when expanded / long-pressed)
    - Tap action  → opens the article link
    """
    headers: dict[str, str] = {
        "Title":        title[:200],
        "Priority":     priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if click:
        headers["Click"] = click
    if tags:
        headers["Tags"] = ",".join(tags)

    req = urlreq.Request(
        f"https://ntfy.sh/{topic}",
        data    = body.encode("utf-8"),
        headers = headers,
        method  = "POST",
    )
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"    ntfy error: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not ntfy_topic:
        print("NTFY_TOPIC not set — skipping push notifications")
        return

    if not DIGEST_FILE.exists():
        print("No digest.json found — digest pipeline may not have run yet")
        return

    digest   = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
    articles = digest.get("articles", [])
    date_str = digest.get("date", "")

    if not articles:
        print("Digest has no articles")
        return

    # Build deterministic round-robin schedule
    ordered   = round_robin_articles(articles)
    scheduled = build_schedule(ordered, date_str)

    now_ist = datetime.now(IST)
    print(f"📅 Date: {date_str} | Now IST: {now_ist.strftime('%H:%M')} | "
          f"Articles: {len(scheduled)} | "
          f"Interval: ~{int((SCHEDULE_END_HOUR - SCHEDULE_START_HOUR) * 60 / max(len(scheduled), 1))} min each")

    # Find articles due in this 30-min cron window
    # Window: [now - 35 min, now + 5 min]  (35 min to absorb cron drift)
    window_start = now_ist - timedelta(minutes=35)
    window_end   = now_ist + timedelta(minutes=5)

    due = [
        art for art in scheduled
        if window_start.timestamp() <= art["_send_at_epoch"] <= window_end.timestamp()
    ]

    print(f"⏰ Window: {window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')} IST | "
          f"Due: {len(due)}")

    sent = 0
    for art in due:
        headline = art.get("headline", "")
        summary  = art.get("summary",  "")
        category = art.get("category", "News")
        sources  = art.get("sources",  [])

        # Best link: telegram_url from first source (opens the PDF in Telegram
        # which is the exact page with the article)
        url = ""
        for src in sources:
            u = src.get("telegram_url", "")
            if u:
                url = u
                break
        if not url:
            url = art.get("telegram_url", "")

        emoji = CATEGORY_EMOJI.get(category, "📰")

        # Notification body: category tag + full summary
        # Android expands this when user long-presses / pulls down notification
        body = f"{emoji} {category}\n\n{summary}"

        # Tags for ntfy (used for filtering / muting specific categories)
        ntfy_tags = [category.lower().replace(" ", "_"), "news", "dailybrief"]

        print(f"  [{art['_send_at_ist']}] Sending: {headline[:70]}")
        ok = send_ntfy(
            topic    = ntfy_topic,
            title    = headline,
            body     = body,
            click    = url,
            tags     = ntfy_tags,
            priority = "default",
        )
        if ok:
            sent += 1
            print(f"    ✅ Sent")
        else:
            print(f"    ❌ Failed")

    print(f"\n✅ Sent {sent}/{len(due)} notifications this window")

    # Print upcoming schedule for debugging
    future = [a for a in scheduled if a["_send_at_epoch"] > window_end.timestamp()]
    if future:
        print(f"\nNext 5 in queue:")
        for a in future[:5]:
            print(f"  {a['_send_at_ist']} — [{a.get('category')}] {a.get('headline','')[:60]}")


if __name__ == "__main__":
    main()
