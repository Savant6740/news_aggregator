"""
extractor.py
Extracts ALL articles from a newspaper PDF in a SINGLE Gemini API call.

Why single call?
- Free tier limit: only 20 requests/day (RPD)
- Gemini 2.5 Flash has 1M token context window — entire newspaper fits in one call
- 7 newspapers x 1 call = 7 calls for extraction, leaving budget for deduplication
"""

import json
import logging
from pathlib import Path

import pdfplumber

log = logging.getLogger(__name__)

CATEGORIES = [
    "Politics", "Economy", "Business", "India", "World",
    "Sports", "Science", "Technology", "Health", "Law",
    "Environment", "Education", "Culture", "Infrastructure"
]

# Gemini 2.5 Flash: ~1M token context. 1 token ~ 4 chars.
# 900K tokens x 4 = ~3.6M chars safe limit. Full newspaper is typically 200K-600K chars.
MAX_CHARS = 900_000


def extract_text_by_page(pdf_path: Path) -> list[dict]:
    """Returns list of {page, text} dicts. OCR fallback for scanned PDFs."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if len(text.strip()) > 50:
                    pages.append({"page": i, "text": text.strip()})
    except Exception as e:
        log.warning(f"pdfplumber failed: {e}")

    # If total extracted text is suspiciously low, assume scanned PDF
    total_chars = sum(len(p["text"]) for p in pages)
    if len(pages) < 2 or total_chars < 5000:
        log.info(f"Falling back to OCR for {pdf_path.name}")
        pages = ocr_by_page(pdf_path)

    return pages


def ocr_by_page(pdf_path: Path) -> list[dict]:
    try:
        from pdf2image import convert_from_path
        import pytesseract
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None  # Suppress DecompressionBombWarning for large newspaper scans
        images = convert_from_path(str(pdf_path), dpi=150)  # Lowered DPI to reduce memory usage
        results = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 3")
            if len(text.strip()) > 50:
                results.append({"page": i + 1, "text": text.strip()})
        return results
    except Exception as e:
        log.error(f"OCR failed: {e}")
        return []


def extract_all_articles(newspaper: str, pdf_path: Path, model) -> list[dict]:
    """
    Sends ENTIRE newspaper to Gemini in ONE API call.
    Uses the 1M token context window — no chunking needed.
    Returns list of article dicts with headline, summary, category, page, newspaper.
    """
    pages = extract_text_by_page(pdf_path)
    if not pages:
        log.error(f"No text extracted from {pdf_path.name}")
        return []

    # Build single page-tagged text block for the entire newspaper
    full_text = ""
    for p in pages:
        full_text += f"\n\n[PAGE {p['page']}]\n{p['text']}"

    # Trim if somehow exceeds safe limit (very unlikely for a single newspaper)
    if len(full_text) > MAX_CHARS:
        log.warning(f"Text truncated from {len(full_text):,} to {MAX_CHARS:,} chars")
        full_text = full_text[:MAX_CHARS]

    log.info(f"  [{newspaper}] Sending {len(full_text):,} chars in single API call...")

    prompt = f"""You are a senior news editor. Extract EVERY distinct news article from today's {newspaper}.

Rules:
- Extract ALL news articles — include every story, not just major ones.
- SKIP: advertisements, stock tables, weather forecasts, TV schedules, classifieds, obituaries, horoscopes, crosswords.
- Identify the page number from [PAGE N] markers in the text.
- Category must be exactly one of: {', '.join(CATEGORIES)}
- Importance: rate each article 1-10 based on national/global significance and reader impact. Front-page lead stories = 8-10. Minor local briefs = 1-3.

Return ONLY a valid JSON array. Each item must have exactly these fields:
- "headline": clear factual headline, max 12 words
- "summary": 2-3 sentences in neutral simple English with key facts and figures
- "category": one category from the list above
- "page": integer page number where article starts
- "importance": integer 1-10 rating of the article's significance

Full newspaper text:
{full_text}

Return ONLY the JSON array. No markdown fences, no explanation, no preamble."""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        articles = json.loads(raw)

        for art in articles:
            art["newspaper"] = newspaper
            art["pdf_filename"] = pdf_path.name

        log.info(f"  [{newspaper}] Extracted {len(articles)} articles in 1 API call")
        return articles

    except json.JSONDecodeError as e:
        log.error(f"  [{newspaper}] JSON parse error: {e}")
        log.debug(f"Raw response snippet: {response.text[:300]}")
        return []
    except Exception as e:
        log.error(f"  [{newspaper}] Gemini error: {e}")
        return []
