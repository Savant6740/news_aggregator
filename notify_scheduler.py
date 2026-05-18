"""
notify_scheduler.py - REVISED VERSION
Inshorts-style scheduled push notifications via ntfy.sh with EVEN intervals + GitHub Pages links.

FIXES vs previous version:
✅ Dead zone eliminated: window widened to ±3 min (6 min total) to cover 5-min cron gaps
✅ Double-send protection: sent log (docs/.sent_today.json) deduplicates within the day
✅ Sent log auto-resets daily (keyed by digest date)
✅ Dynamic intervals: interval = 13hrs / article_count
✅ GitHub Pages deep links: https://your-site.github.io/#article-id
✅ zoneinfo (stdlib) — no pip install needed

IMPORTANT — sent log persistence:
  The sent log is written to docs/.sent_today.json.
  For it to work across GitHub Actions runs, your workflow must commit it back
  to the repo after this script runs. Add these steps to your workflow:

    - name: Commit sent log
      run: |
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add docs/.sent_today.json
        git diff --staged --quiet || git commit -m "chore: update sent log [skip ci]"
        git push

  The [skip ci] tag prevents the commit from re-triggering your workflow.

Usage: GitHub cron should be '*/5 3-17 * * *' (every 5 min, 8:30 AM–11:30 PM IST)
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib import request as urlreq
from collections import defaultdict
from zoneinfo import ZoneInfo  # stdlib since Python 3.9 — no pip install needed

IST         = ZoneInfo('Asia/Kolkata')
DIGEST_FILE = Path("docs/digest.json")
SENT_LOG    = Path("docs/.sent_today.json")
SITE_URL    = os.environ.get('SITE_URL', '').rstrip('/')

# Fixed schedule window: 9 AM to 10 PM IST (13 hours)
SCHEDULE_START_HOUR = 9
SCHEDULE_END_HOUR   = 22

# Send window: ±3 min around each article's scheduled time.
# Must be >= half the cron interval to eliminate dead zones.
# With 5-min cron → use 3 min (covers the full 5-min gap with 1 min overlap each side).
WINDOW_MINUTES = 3

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

CATEGORY_ORDER = list(CATEGORY_EMOJI.keys())


# ---------------------------------------------------------------------------
# Sent-log helpers
# ---------------------------------------------------------------------------

def load_sent_log(date_str: str) -> set:
    """
    Return the set of article_ids already sent today.
    If the log is for a different date (new day), treat it as empty.
    """
    if SENT_LOG.exists():
        try:
            data = json.loads(SENT_LOG.read_text(encoding="utf-8"))
            if data.get("date") == date_str:
                return set(data.get("sent", []))
        except (json.JSONDecodeError, KeyError):
            pass  # Corrupt log — start fresh
    return set()


def save_sent_log(date_str: str, sent_ids: set) -> None:
    """Persist the sent log for today."""
    SENT_LOG.write_text(
        json.dumps({"date": date_str, "sent": sorted(sent_ids)}, ensure_ascii=False),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Scheduling helpers
# ---------------------------------------------------------------------------

def round_robin_articles(articles: list[dict]) -> list[dict]:
    """Round-robin across categories by importance score."""
    by_cat = defaultdict(list)
    for art in articles:
        cat = art.get("category", "India")
        by_cat[cat].append(art)

    for cat in by_cat:
        by_cat[cat].sort(key=lambda a: a.get("importance", 0), reverse=True)

    ordered = [c for c in CATEGORY_ORDER if c in by_cat]
    extra   = [c for c in by_cat if c not in CATEGORY_ORDER]
    cats    = ordered + extra

    result = []
    while any(by_cat[c] for c in cats):
        for cat in cats:
            if by_cat[cat]:
                result.append(by_cat[cat].pop(0))
    return result


def build_precise_schedule(articles: list[dict], date_str: str) -> list[dict]:
    """Assign EXACT send times: 09:00 + (i * interval_seconds)."""
    try:
        base_date = datetime.strptime(date_str, "%d %B %Y").replace(tzinfo=IST)
    except ValueError:
        try:
            base_date = datetime.strptime(date_str, "%d %b %Y").replace(tzinfo=IST)
        except ValueError:
            base_date = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)

    start = base_date.replace(hour=SCHEDULE_START_HOUR, minute=0, second=0, microsecond=0)
    end   = base_date.replace(hour=SCHEDULE_END_HOUR,   minute=0, second=0, microsecond=0)

    n = len(articles)
    if n == 0:
        return []

    total_seconds    = int((end - start).total_seconds())
    interval_seconds = total_seconds // n

    scheduled = []
    for i, art in enumerate(articles):
        send_at    = start + timedelta(seconds=i * interval_seconds)
        article_id = art.get('article_id') or hashlib.md5(
            f"{art.get('date', '')}:{art['headline']}".encode()
        ).hexdigest()[:8]
        scheduled.append({
            **art,
            'article_id':     article_id,
            '_send_at':       send_at,
            '_send_at_epoch': int(send_at.timestamp()),
            '_send_at_ist':   send_at.strftime("%H:%M:%S"),
            '_interval_min':  f"{interval_seconds // 60}:{interval_seconds % 60:02d}",
        })
    return scheduled


# ---------------------------------------------------------------------------
# Notification sender
# ---------------------------------------------------------------------------

def send_ntfy(topic: str, title: str, body: str, click_url: str, tags: list[str]) -> bool:
    """Send an ntfy notification with a GitHub Pages deep link."""
    headers = {
        "Title":        title[:200],
        "Priority":     "default",
        "Click":        click_url,
        "Tags":         ",".join(tags),
        "Content-Type": "text/plain; charset=utf-8",
    }
    req = urlreq.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers=headers,
        method="POST"
    )
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  ntfy error: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not ntfy_topic:
        print("❌ NTFY_TOPIC not set")
        return

    if not DIGEST_FILE.exists():
        print("❌ digest.json not found")
        return

    digest   = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
    articles = digest.get("articles", [])
    date_str = digest.get("date", "")

    if not articles:
        print("No articles in digest")
        return

    # Build precise schedule
    ordered      = round_robin_articles(articles)
    scheduled    = build_precise_schedule(ordered, date_str)
    interval_min = int((SCHEDULE_END_HOUR - SCHEDULE_START_HOUR) * 60 / max(len(scheduled), 1))

    now_ist = datetime.now(IST)
    print(f"📅 {date_str} | Now: {now_ist.strftime('%H:%M:%S')} IST")
    print(f"📊 {len(scheduled)} articles | Interval: ~{interval_min} min")

    # -----------------------------------------------------------------------
    # REVISED WINDOW: ±WINDOW_MINUTES (default ±3 min = 6 min total)
    # This fully covers a 5-min cron cycle with no dead zones.
    # The sent log below prevents double-sends from overlapping windows.
    # -----------------------------------------------------------------------
    window_start = now_ist - timedelta(minutes=WINDOW_MINUTES)
    window_end   = now_ist + timedelta(minutes=WINDOW_MINUTES)

    due = [
        art for art in scheduled
        if window_start.timestamp() <= art["_send_at_epoch"] <= window_end.timestamp()
    ]

    print(f"⏰ Window: {window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')} "
          f"({WINDOW_MINUTES * 2} min) | Due: {len(due)}")

    # -----------------------------------------------------------------------
    # Load sent log — skip articles already delivered this run or a prior run
    # -----------------------------------------------------------------------
    sent_ids = load_sent_log(date_str)
    already_sent = [a for a in due if a["article_id"] in sent_ids]
    due          = [a for a in due if a["article_id"] not in sent_ids]

    if already_sent:
        print(f"⏭️  Skipping {len(already_sent)} already-sent article(s)")

    # -----------------------------------------------------------------------
    # Send
    # -----------------------------------------------------------------------
    sent = 0
    for art in due:
        headline   = art["headline"]
        summary    = art["summary"]
        category   = art.get("category", "News")
        article_id = art["article_id"]

        pages_url = f"{SITE_URL}/#article-{article_id}"
        emoji     = CATEGORY_EMOJI.get(category, "📰")
        body      = f"{emoji} {category}\n\n{summary[:350]}..."
        tags      = [category.lower().replace(" ", "_"), "news", "daily"]

        print(f"📱 [{art['_send_at_ist']}] {headline[:60]}")
        if send_ntfy(ntfy_topic, headline, body, pages_url, tags):
            sent += 1
            sent_ids.add(article_id)
            print(f"   ✅ Sent → {pages_url}")
        else:
            print(f"   ❌ Failed")

    # Persist updated sent log (only if something changed)
    if sent > 0:
        save_sent_log(date_str, sent_ids)
        print(f"\n🎉 Sent {sent}/{len(due)} notifications | Log updated")
    else:
        print(f"\n— Nothing new to send this run")

    # -----------------------------------------------------------------------
    # Debug: show next 3 upcoming articles
    # -----------------------------------------------------------------------
    future = [a for a in scheduled if a["_send_at_epoch"] > now_ist.timestamp()]
    future = [a for a in future if a["article_id"] not in sent_ids]
    if future:
        print("\n⏭️  Next up:")
        for a in future[:3]:
            print(f"   {a['_send_at_ist']} [{a.get('category')}] {a.get('headline', '')[:55]}")


if __name__ == "__main__":
    main()
