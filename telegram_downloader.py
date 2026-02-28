"""
telegram_downloader.py
Downloads today's newspaper PDFs from a Telegram group/channel.
Supports private groups (use numeric ID like -1001234567890 as TELEGRAM_CHANNEL).

Edition priority:
  1 = Bengaluru / Bangalore  (preferred)
  2 = Delhi                  (fallback)
  3 = Any / generic          (last resort)

Only the best available edition per newspaper is kept.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename

log = logging.getLogger(__name__)

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
CHANNEL  = os.environ["TELEGRAM_CHANNEL"]   # numeric ID or @username
PDF_DIR  = Path("pdfs")
IST      = timezone(timedelta(hours=5, minutes=30))

# Full list of newspapers we expect each day
EXPECTED_NEWSPAPERS = [
    "The Hindu",
    "Indian Express",
    "Financial Express",
    "Times of India",
    "Hindustan Times",
    "Economic Times",
    "Business Line",
    "Business Standard",
    "Mint",
]

# ── Keyword table ─────────────────────────────────────────────────────────────
# Each entry: (normalised_keyword_substring, newspaper_name, edition_priority)
#   priority 1 = Bengaluru/Bangalore  <- best
#   priority 2 = Delhi
#   priority 3 = any / generic        <- last resort
#
# NOTE: After you run scan_group_history.py and share the output,
# update the keywords below to match the actual filenames in your group.
# ─────────────────────────────────────────────────────────────────────────────
NEWSPAPER_KEYWORDS: list[tuple[str, str, int]] = [

    # ── The Hindu ─────────────────────────────────────────────────────────────
    ("thehindubengaluru",          "The Hindu", 1),
    ("thehindubangalore",          "The Hindu", 1),
    ("hindubengaluru",             "The Hindu", 1),
    ("hindubangalore",             "The Hindu", 1),
    ("thehindudelhi",              "The Hindu", 2),
    ("hindudelhi",                 "The Hindu", 2),
    ("thehindu",                   "The Hindu", 3),

    # ── Indian Express ────────────────────────────────────────────────────────
    ("indianexpressbengaluru",     "Indian Express", 1),
    ("indianexpressbangalore",     "Indian Express", 1),
    ("iebengaluru",                "Indian Express", 1),
    ("iebangalore",                "Indian Express", 1),
    ("indianexpressdelhi",         "Indian Express", 2),
    ("iedelhi",                    "Indian Express", 2),
    ("indianexpress",              "Indian Express", 3),

    # ── Financial Express ─────────────────────────────────────────────────────
    ("financialexpressbengaluru",  "Financial Express", 1),
    ("financialexpressbangalore",  "Financial Express", 1),
    ("febengaluru",                "Financial Express", 1),
    ("febangalore",                "Financial Express", 1),
    ("financialexpressdelhi",      "Financial Express", 2),
    ("fedelhi",                    "Financial Express", 2),
    ("financialexpress",           "Financial Express", 3),

    # ── Times of India ────────────────────────────────────────────────────────
    ("toibengaluru",               "Times of India", 1),
    ("toibangalore",               "Times of India", 1),
    ("bengalurutoi",               "Times of India", 1),
    ("bangaloretoi",               "Times of India", 1),
    ("toidelhi",                   "Times of India", 2),
    ("delhitoi",                   "Times of India", 2),
    ("timeofindia",                "Times of India", 3),
    ("timesofindia",               "Times of India", 3),

    # ── Hindustan Times ───────────────────────────────────────────────────────
    ("htbengaluru",                "Hindustan Times", 1),
    ("htbangalore",                "Hindustan Times", 1),
    ("hindustantimesbengaluru",    "Hindustan Times", 1),
    ("hindustantimesbangalore",    "Hindustan Times", 1),
    ("htdelhi",                    "Hindustan Times", 2),
    ("hindustantimesdelhi",        "Hindustan Times", 2),
    ("hindustantimes",             "Hindustan Times", 3),

    # ── Economic Times ────────────────────────────────────────────────────────
    ("etbengaluru",                "Economic Times", 1),
    ("etbangalore",                "Economic Times", 1),
    ("bengalureet",                "Economic Times", 1),
    ("bangaloreet",                "Economic Times", 1),
    ("etdelhi",                    "Economic Times", 2),
    ("delhiet",                    "Economic Times", 2),
    ("economictimes",              "Economic Times", 3),

    # ── Business Line (The Hindu Business Line) ───────────────────────────────
    ("businesslinebengaluru",      "Business Line", 1),
    ("businesslinebangalore",      "Business Line", 1),
    ("blbengaluru",                "Business Line", 1),
    ("blbangalore",                "Business Line", 1),
    ("thehindubusinesslinebengaluru", "Business Line", 1),
    ("thehindubusinesslinebangalore", "Business Line", 1),
    ("businesslinedelhi",          "Business Line", 2),
    ("bldelhi",                    "Business Line", 2),
    ("businessline",               "Business Line", 3),
    ("thehindubusinessline",       "Business Line", 3),

    # ── Business Standard ─────────────────────────────────────────────────────
    ("businessstandardbengaluru",  "Business Standard", 1),
    ("businessstandardbangalore",  "Business Standard", 1),
    ("bsbengaluru",                "Business Standard", 1),
    ("bsbangalore",                "Business Standard", 1),
    ("businessstandarddelhi",      "Business Standard", 2),
    ("bsdelhi",                    "Business Standard", 2),
    ("businessstandard",           "Business Standard", 3),

    # ── Mint ──────────────────────────────────────────────────────────────────
    ("mintbengaluru",              "Mint", 1),
    ("mintbangalore",              "Mint", 1),
    ("bengalurumint",              "Mint", 1),
    ("bangaloremint",              "Mint", 1),
    ("mintdelhi",                  "Mint", 2),
    ("delhimint",                  "Mint", 2),
    ("livemintdelhi",              "Mint", 2),
    ("livemint",                   "Mint", 3),
    ("mint",                       "Mint", 3),
]


def normalise(text: str) -> str:
    return text.lower().replace(" ", "").replace("-", "").replace("_", "")


def get_newspaper_name(filename: str) -> tuple[str, int] | None:
    """
    Returns (newspaper_name, edition_priority) for the best matching keyword,
    or None if the file should be skipped.
    """
    norm = normalise(filename)

    # Skip supplements / inserts
    if any(skip in norm for skip in ("indulge", "magazine", "epaper_ad", "advertis")):
        return None

    best: tuple[str, int] | None = None
    for keyword, name, priority in NEWSPAPER_KEYWORDS:
        if keyword in norm:
            if best is None or priority < best[1]:
                best = (name, priority)
    return best


def build_telegram_url(channel: str, message_id: int) -> str:
    """
    Build a direct Telegram web URL for the message.
    Handles both public @username channels and private numeric-ID groups.
    """
    channel = channel.strip()

    # Private group / channel: TELEGRAM_CHANNEL is a numeric ID like -1001234567890
    if channel.lstrip("-").isdigit():
        peer_id = int(channel)
        if peer_id < 0:
            # Supergroup/channel IDs start with -100; strip that prefix for the web URL
            raw = str(abs(peer_id))
            channel_id = raw[3:] if raw.startswith("100") else raw
        else:
            channel_id = str(peer_id)
        return f"https://t.me/c/{channel_id}/{message_id}"

    # Public channel: @username or plain username
    channel_clean = channel.lstrip("@")
    return f"https://t.me/{channel_clean}/{message_id}"


async def download_todays_pdfs() -> dict[str, dict]:
    """
    Downloads today's newspapers using edition priority logic.

    Returns dict:
    {
      "Times of India": {
          "path":             Path("pdfs/BangaloreTOI.pdf"),
          "telegram_url":     "https://t.me/c/1234567890/4321",
          "filename":         "BangaloreTOI.pdf",
          "edition_priority": 1,
      }, ...
    }
    """
    PDF_DIR.mkdir(exist_ok=True)
    best_found: dict[str, dict] = {}
    today = datetime.now(IST).date()

    client = TelegramClient("news_session", API_ID, API_HASH)

    async with client:
        log.info(f"Connected. Scanning: {CHANNEL}")
        entity = await client.get_entity(CHANNEL)

        async for message in client.iter_messages(entity, limit=300):
            if message.date.astimezone(IST).date() < today:
                break

            if not message.document:
                continue

            filename = ""
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break

            if not filename.lower().endswith(".pdf"):
                continue

            result = get_newspaper_name(filename)
            if result is None:
                log.debug(f"Skipping: {filename}")
                continue

            newspaper, priority = result

            # Only download if this is a better edition than what we already have
            existing = best_found.get(newspaper)
            if existing and existing["edition_priority"] <= priority:
                log.debug(f"Already have better edition of {newspaper} (priority {existing['edition_priority']})")
                continue

            save_path = PDF_DIR / filename
            log.info(f"Downloading {filename}  [{newspaper}, priority={priority}]...")
            await client.download_media(message, file=str(save_path))

            telegram_url = build_telegram_url(CHANNEL, message.id)
            best_found[newspaper] = {
                "path":             save_path,
                "telegram_url":     telegram_url,
                "filename":         filename,
                "edition_priority": priority,
            }
            log.info(f"  {newspaper} (edition {priority}) -> {telegram_url}")

    found  = [n for n in EXPECTED_NEWSPAPERS if n in best_found]
    absent = [n for n in EXPECTED_NEWSPAPERS if n not in best_found]
    log.info(f"Downloaded {len(best_found)}/{len(EXPECTED_NEWSPAPERS)} newspapers")
    log.info(f"  Present : {', '.join(found)  or 'none'}")
    log.info(f"  Missing : {', '.join(absent) or 'none'}")

    return best_found


def run() -> dict[str, dict]:
    return asyncio.run(download_todays_pdfs())


# ── Lightweight scan (no download) — used by the workflow's early-exit check ──

async def _scan_available_async() -> dict[str, str]:
    """
    Lightweight scan — reads message metadata only, no PDF download.
    Returns as soon as the first matching newspaper is found.
    """
    found: dict[str, str] = {}
    today = datetime.now(IST).date()

    client = TelegramClient("news_session", API_ID, API_HASH)
    async with client:
        entity = await client.get_entity(CHANNEL)
        async for message in client.iter_messages(entity, limit=300):
            if message.date.astimezone(IST).date() < today:
                break
            if not message.document:
                continue
            filename = ""
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
                    break
            if not filename.lower().endswith(".pdf"):
                continue
            result = get_newspaper_name(filename)
            if result:
                newspaper, _ = result
                if newspaper not in found:
                    found[newspaper] = filename
                    log.info(f"  First paper detected: {newspaper} -> {filename}")
                    break   # stop after first detection

    return found


def scan_available() -> dict[str, str]:
    """Synchronous wrapper for the lightweight scan."""
    return asyncio.run(_scan_available_async())
