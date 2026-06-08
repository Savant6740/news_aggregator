"""
notify_scheduler.py - BATCH SCHEDULE VERSION
4 fixed batches delivered via ntfy.sh push notifications:

  Batch 1 — Immediately after HTML is generated  (triggered by generate_site.py)
  Batch 2 — 1:30 PM IST
  Batch 3 — 4:30 PM IST
  Batch 4 — 7:30 PM IST

Each batch delivers exactly 1/4 of the day's articles, drawn equally from
all categories (round-robin). The sent log (docs/.sent_today.json) prevents
double-sends if a cron run overlaps the window.

Cron schedule (UTC):
  '0 8 * * *'    →  1:30 PM IST  (08:00 UTC)
  '0 11 * * *'   →  4:30 PM IST  (11:00 UTC)
  '0 14 * * *'   →  7:30 PM IST  (14:00 UTC)

Batch 1 is triggered by generate_site.py directly — NOT a cron job.

Usage:
  python3 notify_scheduler.py                # normal cron dispatch (reads BATCH_NUM env)
  python3 notify_scheduler.py --batch 1      # force batch (called by generate_site.py)
  BATCH_NUM=2 python3 notify_scheduler.py    # explicit batch via env (set by GH Actions)
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib import request as urlreq
from collections import defaultdict
from zoneinfo import ZoneInfo

IST         = ZoneInfo('Asia/Kolkata')
DIGEST_FILE = Path("docs/digest.json")
SENT_LOG    = Path("docs/.sent_today.json")
SITE_URL    = os.environ.get('SITE_URL', '').rstrip('/')

# ── Fixed batch schedule (IST) ──────────────────────────────────────────────
# Batch 1 is fired immediately by generate_site.py (hour=None signals this).
BATCH_TIMES = [
    {"batch": 1, "hour": None, "minute": None, "label": "Immediate (on HTML generation)"},
    {"batch": 2, "hour": 13,   "minute": 30,   "label": "1:30 PM IST"},
    {"batch": 3, "hour": 16,   "minute": 30,   "label": "4:30 PM IST"},
    {"batch": 4, "hour": 19,   "minute": 30,   "label": "7:30 PM IST"},
]

# Fallback clock-based window (minutes) — used only when BATCH_NUM env is absent.
# Wide enough to survive typical GitHub Actions scheduler delays (~90 min).
WINDOW_MINUTES = 90

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


# ── Sent-log helpers ─────────────────────────────────────────────────────────

def load_sent_log(date_str: str) -> dict:
    """
    Return the sent-log dict for today:
      {
        "date": "07 June 2026",
        "sent": ["id1", "id2", ...],
        "batches_sent": [1, 2]          # which batch numbers have been dispatched
      }
    Resets automatically when the date changes.
    """
    if SENT_LOG.exists():
        try:
            data = json.loads(SENT_LOG.read_text(encoding="utf-8"))
            if data.get("date") == date_str:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"date": date_str, "sent": [], "batches_sent": []}


def save_sent_log(log: dict) -> None:
    SENT_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ── Article helpers ──────────────────────────────────────────────────────────

def ensure_article_ids(articles: list[dict]) -> list[dict]:
    for art in articles:
        if not art.get("article_id"):
            content = f"{art.get('date', '')}:{art.get('headline', '')}".encode()
            art["article_id"] = hashlib.md5(content).hexdigest()[:8]
    return articles


def round_robin_articles(articles: list[dict]) -> list[dict]:
    """
    Sort articles into a round-robin order across categories,
    highest importance first within each category.
    """
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


def split_into_batches(articles: list[dict]) -> dict[int, list[dict]]:
    """
    Split round-robin-ordered articles into 4 equal batches.
    If len(articles) % 4 != 0, extra articles go to batch 1 first,
    then batch 2, etc.
    """
    n = len(articles)
    base = n // 4
    remainder = n % 4        # 0–3 extra articles

    batches = {}
    idx = 0
    for i, slot in enumerate(range(1, 5)):
        size = base + (1 if i < remainder else 0)
        batches[slot] = articles[idx: idx + size]
        idx += size
    return batches


# ── Batch detection ──────────────────────────────────────────────────────────

def detect_batch_from_env() -> int | None:
    """
    Primary: read BATCH_NUM set explicitly by the GitHub Actions workflow.
    Returns None if the env var is absent or invalid.
    """
    raw = os.environ.get("BATCH_NUM", "").strip()
    if raw:
        try:
            val = int(raw)
            if val in (1, 2, 3, 4):
                return val
            print(f"⚠️  BATCH_NUM={raw} is out of range (expected 1-4)")
        except ValueError:
            print(f"⚠️  BATCH_NUM={raw!r} is not an integer — ignoring")
    return None


def detect_batch_from_clock(now_ist: datetime) -> int | None:
    """
    Fallback: infer the batch from the current IST time within a ±WINDOW_MINUTES
    window. Covers typical GitHub Actions scheduler delays.
    Batch 1 is never detected here — it is triggered explicitly.
    """
    best_batch = None
    best_delta = float("inf")
    for slot in BATCH_TIMES[1:]:   # skip batch 1 (no fixed time)
        target = now_ist.replace(
            hour=slot["hour"], minute=slot["minute"],
            second=0, microsecond=0
        )
        delta = abs((now_ist - target).total_seconds())
        if delta <= WINDOW_MINUTES * 60 and delta < best_delta:
            best_batch = slot["batch"]
            best_delta = delta
    return best_batch


# ── ntfy sender ──────────────────────────────────────────────────────────────

def send_ntfy(topic: str, title: str, body: str, click_url: str, tags: list[str]) -> bool:
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


# ── Dispatch ─────────────────────────────────────────────────────────────────

def dispatch_batch(batch_num: int, batch_articles: list[dict],
                   ntfy_topic: str, sent_log: dict) -> int:
    """Send all unsent articles in this batch. Returns count sent."""
    sent_ids = set(sent_log.get("sent", []))
    to_send  = [a for a in batch_articles if a["article_id"] not in sent_ids]

    if not to_send:
        print(f"  ⏭️  Batch {batch_num}: all articles already sent")
        return 0

    print(f"  📦 Batch {batch_num}: {len(to_send)} articles to send")
    sent = 0
    for art in to_send:
        headline   = art["headline"]
        summary    = art.get("summary", "")
        category   = art.get("category", "News")
        article_id = art["article_id"]

        pages_url = f"{SITE_URL}/#article-{article_id}"
        emoji     = CATEGORY_EMOJI.get(category, "📰")
        body      = f"{emoji} {category}\n\n{summary[:350]}..."
        tags      = [category.lower().replace(" ", "_"), "news", "daily"]

        print(f"  📱 [{category}] {headline[:60]}")
        if send_ntfy(ntfy_topic, headline, body, pages_url, tags):
            sent += 1
            sent_ids.add(article_id)
            print(f"     ✅ Sent → {pages_url}")
        else:
            print(f"     ❌ Failed")

    # Update sent log
    sent_log["sent"] = sorted(sent_ids)
    batches_sent = set(sent_log.get("batches_sent", []))
    batches_sent.add(batch_num)
    sent_log["batches_sent"] = sorted(batches_sent)
    save_sent_log(sent_log)
    return sent


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not ntfy_topic:
        print("❌ NTFY_TOPIC not set")
        return

    if not DIGEST_FILE.exists():
        print("❌ digest.json not found")
        return

    digest   = json.loads(DIGEST_FILE.read_text(encoding="utf-8"))
    articles = ensure_article_ids(digest.get("articles", []))
    date_str = digest.get("date", "")

    if not articles:
        print("No articles in digest")
        return

    now_ist  = datetime.now(IST)
    sent_log = load_sent_log(date_str)

    ordered = round_robin_articles(articles)
    batches = split_into_batches(ordered)

    print(f"📅 {date_str} | Now: {now_ist.strftime('%H:%M:%S')} IST")
    print(f"📊 {len(articles)} articles → "
          f"{' | '.join(f'B{k}:{len(v)}' for k,v in sorted(batches.items()))}")

    # ── Determine batch number (3-way priority) ──────────────────────────────
    # 1. --batch CLI arg  (called by generate_site.py for Batch 1)
    # 2. BATCH_NUM env var (set explicitly by GitHub Actions workflow)
    # 3. Clock-based fallback (wide ±90 min window)

    force_batch = None
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        try:
            force_batch = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            pass

    if force_batch is not None:
        batch_num = force_batch
        print(f"\n🚀 Forced batch {batch_num} via --batch flag ({BATCH_TIMES[batch_num-1]['label']})")

    else:
        env_batch = detect_batch_from_env()
        if env_batch is not None:
            batch_num = env_batch
            print(f"\n🎯 Batch {batch_num} from BATCH_NUM env var ({BATCH_TIMES[batch_num-1]['label']})")
        else:
            batch_num = detect_batch_from_clock(now_ist)
            if batch_num is None:
                print("\n— No batch is scheduled right now. Nothing to send.")
                for slot in BATCH_TIMES[1:]:
                    target = now_ist.replace(
                        hour=slot["hour"], minute=slot["minute"],
                        second=0, microsecond=0
                    )
                    if target > now_ist:
                        mins = int((target - now_ist).total_seconds() / 60)
                        print(f"⏭️  Next: Batch {slot['batch']} ({slot['label']}) in ~{mins} min")
                        break
                return
            print(f"\n⏰ Batch {batch_num} from clock fallback ({BATCH_TIMES[batch_num-1]['label']})")

    # Skip if this batch was already fully dispatched
    if batch_num in sent_log.get("batches_sent", []):
        print(f"⏭️  Batch {batch_num} already sent in a prior run — skipping")
        return

    batch_articles = batches.get(batch_num, [])
    if not batch_articles:
        print(f"  No articles assigned to batch {batch_num}")
        return

    sent = dispatch_batch(batch_num, batch_articles, ntfy_topic, sent_log)
    print(f"\n🎉 Batch {batch_num} complete: {sent} notifications sent")


if __name__ == "__main__":
    main()
