"""
digest.py — Main orchestration
Flow: Telegram → PDF (temp) → Extract ALL → Deduplicate → Build Site → Notify

API call budget (free tier = 20 RPD):
  - 1 test call on startup
  - 7 calls for extraction (1 per newspaper)
  - 1 call for batch deduplication
  = 9 total calls per day — well within 20 RPD limit
"""

import os
import json
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

import google.generativeai as genai

from telegram_downloader import run as download_pdfs
from extractor import extract_all_articles
from deduplicator import deduplicate
from generate_site import build_site
from notify import send as notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("digest.log")],
)
log = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IST = timezone(timedelta(hours=5, minutes=30))

# ── Model selection ───────────────────────────────────────────────────────────
# gemini-3-flash-preview: latest gen, no shutdown date, listed replacement for
# gemini-2.5-flash (shutting down Jun 17 2026). Free: 5 RPM, 250K TPM, 20 RPD.
# Fallback: gemini-2.5-flash-lite (free, 10 RPM, 20 RPD).
# AVOID: gemini-2.0-flash (shuts down Mar 31 2026), gemini-1.5-flash (retired).
genai.configure(api_key=GEMINI_API_KEY)
try:
    model = genai.GenerativeModel("gemini-3-flash-preview")
    model.generate_content("hi")
    log.info("Using gemini-3-flash-preview (5 RPM, 250K TPM, 20 RPD)")
except Exception:
    log.warning("gemini-3-flash-preview unavailable, falling back to gemini-2.5-flash-lite")
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

DOCS_DIR = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)


def main():
    today = datetime.now(IST)
    date_str = today.strftime("%d %B %Y")
    log.info(f"=== News Digest — {date_str} ===")

    # Step 1: Download PDFs from Telegram
    log.info("Downloading from Telegram...")
    newspaper_map = download_pdfs()

    if not newspaper_map:
        log.error("No PDFs downloaded. Check Telegram config and channel keywords.")
        raise SystemExit(1)

    # Step 2: Extract ALL articles (1 API call per newspaper)
    all_articles = []
    for newspaper, info in newspaper_map.items():
        log.info(f"Extracting: {newspaper}")
        articles = extract_all_articles(newspaper, Path(info["path"]), model)
        for art in articles:
            art["telegram_url"] = info["telegram_url"]
        all_articles.extend(articles)
        log.info(f"  {len(articles)} articles extracted")

    log.info(f"Total raw articles: {len(all_articles)}")

    # Step 3: Deduplicate & merge (1 API call total)
    merged_articles = deduplicate(all_articles, model)
    log.info(f"Final unique articles: {len(merged_articles)}")

    # Step 4: Save JSON + Build site
    digest_data = {
        "date":           date_str,
        "generated_at":   today.isoformat(),
        "total_articles": len(merged_articles),
        "newspapers":     list(newspaper_map.keys()),
        "articles":       merged_articles,
    }
    (DOCS_DIR / "digest.json").write_text(
        json.dumps(digest_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    build_site(digest_data, DOCS_DIR)
    log.info("Site built at docs/index.html")

    # Step 5: Stage PDFs for GitHub Pages artifact (not committed to git)
    pdfs_dest = DOCS_DIR / "pdfs"
    pdfs_dest.mkdir(exist_ok=True)
    pdf_dir = Path("pdfs")
    if pdf_dir.exists():
        for pdf in pdf_dir.glob("*.pdf"):
            shutil.copy2(str(pdf), str(pdfs_dest / pdf.name))
            log.info(f"  Staged: {pdf.name}")
        shutil.rmtree(pdf_dir)

    # Step 6: Send Telegram notification (non-fatal)
    notify(digest_data)

    papers = len(newspaper_map)
    log.info(f"Done! {len(merged_articles)} articles, {papers} newspapers, {papers + 2}/20 API calls used.")


if __name__ == "__main__":
    main()
