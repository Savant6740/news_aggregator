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

PDF_DIR      = Path("pdfs")
IST          = timezone(timedelta(hours=5, minutes=30))
# Session file is resolved relative to this source file so it is found
# regardless of the working directory the runner uses.
SESSION_PATH = str(Path(__file__).parent / "news_session")

# Credentials are read lazily inside functions (not at import time) so that
# GitHub Actions secret injection is complete before they are accessed.
def _api_id()   -> int: return int(os.environ["TELEGRAM_API_ID"])
def _api_hash() -> str: return os.environ["TELEGRAM_API_HASH"]
def _channel()  -> str: return os.environ.get("TELEGRAM_CHANNEL", "-1001877410077")

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
# Keywords are matched against the normalised filename, where normalise() lowercases
# the name and replaces hyphens, underscores and tildes with spaces.
# Patterns are derived from 3 months of actual filenames in the source group.
# ─────────────────────────────────────────────────────────────────────────────
NEWSPAPER_KEYWORDS: list[tuple[str, str, int]] = [

    # ── The Hindu ─────────────────────────────────────────────────────────────
    # Observed patterns: "TH Bangalore DD-MM-YYYY", "TH -Bangalore -DD-MM-YYYY",
    # "TH BL HD Bangalore DD~MM~YYYY", "THE HINDU HD Bangalore ...",
    # "th.th_bangalore.DD_MM_YYYY", "TH Bangalore DD~MM~YYYY"
    ("the hindu hd bangalore",    "The Hindu", 1),
    ("th bl hd bangalore",        "The Hindu", 1),   # combo file; also triggers Business Line
    ("th bangalore",              "The Hindu", 1),
    ("th  bangalore",             "The Hindu", 1),   # double-space variant
    ("th.th bangalore",           "The Hindu", 1),   # dot-separated variant normalised
    ("th bl hd delhi",            "The Hindu", 2),
    ("th delhi",                  "The Hindu", 2),
    ("th  delhi",                 "The Hindu", 2),
    ("th mumbai",                 "The Hindu", 3),
    ("th  mumbai",                "The Hindu", 3),

    # ── Indian Express ────────────────────────────────────────────────────────
    # No Bangalore/Bengaluru edition observed in group.
    # Observed patterns: "IE Delhi DD-MM-YYYY", "IE - Delhi-Month-DD-YYYY",
    # "cleaned_IE Delhi DD-MM-YYYY", "cleaned_IE - Delhi-Month-DD-YYYY"
    ("ie delhi",                  "Indian Express", 2),
    ("ie  delhi",                 "Indian Express", 2),
    ("ie - delhi",                "Indian Express", 2),
    ("ie mumbai",                 "Indian Express", 3),
    ("ie  mumbai",                "Indian Express", 3),
    ("ie - mumbai",               "Indian Express", 3),

    # ── Financial Express ─────────────────────────────────────────────────────
    # Observed patterns: "FE_Bengaluru_DD-MM-YYYY", "FE - Bengaluru  - DD-MM-YYYY",
    # "FE-Bengaluru DD-MM", "Bangalore_FE_DD-MM-YYYY", "cleaned_FE - Bengaluru  - ..."
    ("fe bengaluru",              "Financial Express", 1),
    ("fe  bengaluru",             "Financial Express", 1),
    ("bangalore fe",              "Financial Express", 1),
    ("fe - bengaluru",            "Financial Express", 1),
    ("fe delhi",                  "Financial Express", 2),
    ("fe  delhi",                 "Financial Express", 2),
    ("fe - delhi",                "Financial Express", 2),
    ("fe mumbai",                 "Financial Express", 3),
    ("fe  mumbai",                "Financial Express", 3),

    # ── Times of India ────────────────────────────────────────────────────────
    # Observed patterns: "TOI_Bangalore_DD-MM-YYYY", "TOI-Bangalore DD-MM",
    # "Bangalore_TOI_DD-MM-YYYY", "TOIBe - Bengaluru Times  - DD-MM-YYYY",
    # "TOI Bengaluru DD-MM", "ToI Bengaluru DD.MM.YYYY"
    # Note: "TOIBe - Bengaluru Times" is the Bengaluru Times supplement —
    # it is included here as a Bengaluru-edition proxy since no standalone
    # main TOI Bengaluru file was consistently posted without it.
    ("toibe",                     "Times of India", 1),   # Bengaluru Times supplement
    ("toi bangalore",             "Times of India", 1),
    ("bangalore toi",             "Times of India", 1),
    ("toi bengaluru",             "Times of India", 1),
    ("toi  bengaluru",            "Times of India", 1),
    ("toi delhi",                 "Times of India", 2),
    ("delhi toi",                 "Times of India", 2),
    ("toi  delhi",                "Times of India", 2),
    ("toi mumbai",                "Times of India", 3),
    ("toi  mumbai",               "Times of India", 3),

    # ── Hindustan Times ───────────────────────────────────────────────────────
    # Observed patterns: "Bangalore_HT_DD-MM-YYYY", "HT-Bangalore - DD-MM-YYYY",
    # "Bangalore _HT_DD-MM-YYYY", "HT Bengaluru superscript-date",
    # "UHT Bengaluru DD-MM" (UHT = ultra-HD variant of HT)
    ("bangalore ht",              "Hindustan Times", 1),
    ("ht bangalore",              "Hindustan Times", 1),
    ("ht  bangalore",             "Hindustan Times", 1),
    ("ht bengaluru",              "Hindustan Times", 1),
    ("ht  bengaluru",             "Hindustan Times", 1),
    ("uht bengaluru",             "Hindustan Times", 1),   # ultra-HD variant
    ("ht delhi",                  "Hindustan Times", 2),
    ("ht  delhi",                 "Hindustan Times", 2),
    ("ht city delhi",             "Hindustan Times", 2),
    ("ht hd delhi",               "Hindustan Times", 2),
    ("ht mumbai",                 "Hindustan Times", 3),
    ("ht  mumbai",                "Hindustan Times", 3),

    # ── Economic Times ────────────────────────────────────────────────────────
    # Observed patterns: "ET Bengaluru DD-MM-YYYY", "ET- Bengaluru-DD-MM-YYYY",
    # "ET Bengaluru DD.MM.YYYY", "Bangalore_ET_DD-MM-YYYY", "ET_Bangalore_DD-MM-YYYY",
    # "ET-Bangalore DD-MM"
    ("et bengaluru",              "Economic Times", 1),
    ("et  bengaluru",             "Economic Times", 1),
    ("et bangalore",              "Economic Times", 1),
    ("et  bangalore",             "Economic Times", 1),
    ("bangalore et",              "Economic Times", 1),
    ("et delhi",                  "Economic Times", 2),
    ("et  delhi",                 "Economic Times", 2),
    ("delhi et",                  "Economic Times", 2),
    ("et mumbai",                 "Economic Times", 3),
    ("et  mumbai",                "Economic Times", 3),

    # ── Business Line (The Hindu Business Line) ───────────────────────────────
    # Observed patterns: "BL Bangalore DD-MM-YYYY", "BL - Bangalore  - DD-MM-YYYY",
    # "BL- Bangalore DD-MM", "BL_Bangalore_DD-MM-YYYY", "Bangalore_BL_DD-MM-YYYY",
    # "BL Bengaluru DD.MM.YYYY", "TH BL HD Bangalore DD~MM~YYYY" (combo file)
    ("th bl hd bangalore",        "Business Line", 1),   # combo file; also triggers The Hindu
    ("bl bangalore",              "Business Line", 1),
    ("bl  bangalore",             "Business Line", 1),
    ("bl - bangalore",            "Business Line", 1),
    ("bangalore bl",              "Business Line", 1),
    ("bl bengaluru",              "Business Line", 1),
    ("bl  bengaluru",             "Business Line", 1),
    ("th bl hd delhi",            "Business Line", 2),
    ("bl delhi",                  "Business Line", 2),
    ("bl  delhi",                 "Business Line", 2),
    ("bl - delhi",                "Business Line", 2),
    ("bl mumbai",                 "Business Line", 3),
    ("bl  mumbai",                "Business Line", 3),

    # ── Business Standard ─────────────────────────────────────────────────────
    # No Bangalore/Bengaluru edition observed in group.
    # Observed patterns: "BS_Delhi_DD-MM-YYYY", "BS_Delhi_H_DD-MM-YYYY" (HD variant),
    # "BS_Mumbai_DD-MM-YYYY"
    ("bs delhi",                  "Business Standard", 2),
    ("bs  delhi",                 "Business Standard", 2),
    ("bs mumbai",                 "Business Standard", 3),
    ("bs  mumbai",                "Business Standard", 3),
    ("bs ahmedabad",              "Business Standard", 3),

    # ── Mint ──────────────────────────────────────────────────────────────────
    # Observed patterns: "Bengaluru_Mint_DD-MM-YYYY", "BENGALURU_Mint_DD-MM-YYYY",
    # "Mint - Bengaluru DD-MM-YYYY", "Mint Bengaluru DD-MM-YYYY",
    # "cleaned_Mint - Bengaluru DD-MM-YYYY", "cleaned_Bengaluru_Mint_DD-MM-YYYY",
    # "Mint Bangalore DD-MM", "Mint New Delhi DD-MM"
    ("bengaluru mint",            "Mint", 1),
    ("bengaluru  mint",           "Mint", 1),
    ("mint bengaluru",            "Mint", 1),
    ("mint  bengaluru",           "Mint", 1),
    ("mint - bengaluru",          "Mint", 1),
    ("mint bangalore",            "Mint", 1),
    ("mint  bangalore",           "Mint", 1),
    ("mint delhi",                "Mint", 2),
    ("mint  delhi",               "Mint", 2),
    ("mint - delhi",              "Mint", 2),
    ("mint new delhi",            "Mint", 2),
    ("delhi mint",                "Mint", 2),
    ("mint mumbai",               "Mint", 3),
    ("mint  mumbai",              "Mint", 3),
    ("mint - mumbai",             "Mint", 3),
]


def normalise(text: str) -> str:
    """
    Lowercase and replace separators with spaces so keyword matching works
    against the real filenames (e.g. 'TH_Bangalore' -> 'th bangalore',
    'TH -Bangalore' -> 'th  bangalore', 'TH~Bangalore' -> 'th bangalore').
    Dots are also replaced so 'th.th_bangalore' -> 'th th bangalore'.
    """
    return (
        text.lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("~", " ")
        .replace(".", " ")
    )


def get_newspaper_name(filename: str) -> tuple[str, int] | None:
    """
    Returns (newspaper_name, edition_priority) for the best matching keyword,
    or None if the file should be skipped.
    """
    norm = normalise(filename)

    # Skip supplements / inserts / non-newspaper files
    skip_tokens = (
        "indulge", "magazine", "epaper ad", "advertis",
        "school", "combo edit",
        "all english editorial",
        "all hindi editorial",
        "daily vocabulary",
        "hindi ",
        "times supplement",
        "bombay times", "pune times", "madras times",
        "kolkata times", "hyderabad times",
        "chandigarh times", "ahmedabad times",
        "bengaluru times",   # TOIBe supplement — remove if you want it included
    )
    if any(skip in norm for skip in skip_tokens):
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
          "path":             Path("pdfs/TOI_Bangalore_28-02-2026.pdf"),
          "telegram_url":     "https://t.me/c/1877410077/4321",
          "filename":         "TOI_Bangalore_28-02-2026.pdf",
          "edition_priority": 1,
      }, ...
    }
    """
    PDF_DIR.mkdir(exist_ok=True)
    best_found: dict[str, dict] = {}
    today = datetime.now(IST).date()

    client = TelegramClient(SESSION_PATH, _api_id(), _api_hash())

    async with client:
        channel = _channel()
        log.info(f"Connected. Scanning: {channel}")
        log.info(f"Session path: {SESSION_PATH}.session  exists={Path(SESSION_PATH + '.session').exists()}")
        me = await client.get_me()
        if me is None:
            log.error("Telegram session is not authorised — re-generate news_session.session locally and update the TELEGRAM_SESSION secret.")
            return best_found
        log.info(f"Authorised as: {getattr(me, 'username', None) or getattr(me, 'phone', 'unknown')}")

        entity = await client.get_entity(channel)

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
                log.debug(
                    f"Already have better edition of {newspaper} "
                    f"(priority {existing['edition_priority']})"
                )
                continue

            save_path = PDF_DIR / filename
            log.info(f"Downloading {filename}  [{newspaper}, priority={priority}]...")
            await client.download_media(message, file=str(save_path))

            telegram_url = build_telegram_url(channel, message.id)
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


# ── Lightweight scan (no download) ────────────────────────────────────────────

async def _scan_available_async() -> dict[str, str]:
    """
    Lightweight scan — reads message metadata only, no PDF download.
    Returns as soon as the first matching newspaper is found.
    """
    found: dict[str, str] = {}
    today = datetime.now(IST).date()

    client = TelegramClient(SESSION_PATH, _api_id(), _api_hash())
    async with client:
        channel = _channel()
        me = await client.get_me()
        if me is None:
            log.error("Telegram session is not authorised.")
            return found
        entity = await client.get_entity(channel)
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
                    break

    return found


def scan_available() -> dict[str, str]:
    """Synchronous wrapper for the lightweight scan."""
    return asyncio.run(_scan_available_async())
