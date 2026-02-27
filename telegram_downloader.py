"""
telegram_downloader.py
Downloads today's newspaper PDFs from a public Telegram channel.
Also captures the Telegram message URL for PDF cross-referencing
(avoids storing PDFs in the GitHub repo — saves storage).
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
CHANNEL  = os.environ["TELEGRAM_CHANNEL"]
PDF_DIR  = Path("pdfs")
IST      = timezone(timedelta(hours=5, minutes=30))

NEWSPAPER_KEYWORDS = {
    # Financial Express
    "febengaluru":               "Financial Express",
    "febangalore":               "Financial Express",
    "financialexpressbengaluru": "Financial Express",
    "financialexpressbangalore": "Financial Express",

    # Deccan Herald
    "deccanheraldbengaluru":     "Deccan Herald",
    "deccanheraldbangalore":     "Deccan Herald",

    # Business Standard
    "bsbengaluru":               "Business Standard",
    "bsbangalore":               "Business Standard",
    "businessstandardbengaluru": "Business Standard",
    "businessstandardbangalore": "Business Standard",

    # Mint
    "bengalurumint":             "Mint",
    "bangaloremint":             "Mint",
    "mintbengaluru":             "Mint",
    "mintbangalore":             "Mint",

    # Economic Times
    "bangaloreet":               "Economic Times",
    "bengalureet":               "Economic Times",
    "etbangalore":               "Economic Times",
    "etbengaluru":               "Economic Times",

    # Times of India
    "bangaloretoi":              "Times of India",
    "bengalurutoi":              "Times of India",
    "toibangalore":              "Times of India",
    "toibengaluru":              "Times of India",

    # New Indian Express
    "bengalurunie":              "New Indian Express",
    "bangalorenie":              "New Indian Express",
    "niebengaluru":              "New Indian Express",
    "niebangalore":              "New Indian Express",
    "newindianexpressbengaluru": "New Indian Express",
    "newindianexpressbangalore": "New Indian Express",
}


def normalise(text: str) -> str:
    return text.lower().replace(" ", "").replace("-", "").replace("_", "")


def get_newspaper_name(filename: str) -> str | None:
    norm = normalise(filename)
    for keyword, name in NEWSPAPER_KEYWORDS.items():
        if keyword in norm:
            return name
    return None


def build_telegram_url(channel: str, message_id: int) -> str:
    """Build a direct Telegram web URL for the message."""
    # Strip @ if present
    channel_clean = channel.lstrip("@")
    return f"https://t.me/{channel_clean}/{message_id}"


async def download_todays_pdfs() -> dict[str, dict]:
    """
    Downloads today's newspapers and captures Telegram message URLs.

    Returns dict:
    {
      "Times of India": {
          "path": Path("pdfs/Bangalore_TOI_27-02-2026.pdf"),
          "telegram_url": "https://t.me/channelname/12345"
      }, ...
    }
    """
    PDF_DIR.mkdir(exist_ok=True)
    downloaded: dict[str, dict] = {}
    today = datetime.now(IST).date()

    client = TelegramClient("news_session", API_ID, API_HASH)

    async with client:
        log.info(f"Connected to Telegram. Scanning: {CHANNEL}")
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

            newspaper = get_newspaper_name(filename)
            if newspaper is None:
                log.debug(f"Skipping: {filename}")
                continue

            if newspaper in downloaded:
                continue

            save_path = PDF_DIR / filename
            log.info(f"Downloading {filename}...")
            await client.download_media(message, file=str(save_path))

            telegram_url = build_telegram_url(CHANNEL, message.id)

            downloaded[newspaper] = {
                "path":         save_path,
                "telegram_url": telegram_url,
                "filename":     filename,
            }
            log.info(f"  {newspaper} → {telegram_url}")

    log.info(f"Downloaded {len(downloaded)}/7 newspapers")
    return downloaded


def run() -> dict[str, dict]:
    return asyncio.run(download_todays_pdfs())


# ── Lightweight scan (no download) — used by the workflow's early-exit check ──

async def _scan_available_async() -> dict[str, str]:
    """
    Lightweight scan — reads message metadata only, no PDF download.

    Returns as soon as the FIRST matching newspaper is found.
    This is intentional: the workflow only needs to know whether posting
    has started. Once it has, it waits 30 mins and then runs the full
    pipeline (which downloads all papers at that point).

    Returns dict of {newspaper_name: filename} — will contain just 1 entry
    on first detection, or all available papers if called from full pipeline.
    """
    found = {}
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
            newspaper = get_newspaper_name(filename)
            if newspaper and newspaper not in found:
                found[newspaper] = filename
                log.info(f"  First paper detected: {newspaper} → {filename}")
                # Stop immediately — we only need first detection
                # Full pipeline will download all papers 30 mins later
                break

    return found


def scan_available() -> dict[str, str]:
    """Synchronous wrapper for the lightweight scan."""
    return asyncio.run(_scan_available_async())
