"""
extractor.py
Extracts ALL articles from a newspaper PDF in a SINGLE Gemini API call.

Why single call?
- Free tier limit: only 20 requests/day (RPD)
- Gemini 2.5 Flash has 1M token context window — entire newspaper fits in one call
- 7 newspapers x 1 call = 7 calls for extraction, leaving budget for deduplication

PDF modes:
- TEXT mode : pdfplumber extracts text → sent as a single text prompt
- IMAGE mode: PDF pages → high-quality JPEG images → sent directly to Gemini vision
  (used when text extraction yields < 5 000 chars, i.e. scanned / image-based PDFs)
  This is strictly better than OCR: Gemini reads layout, fonts and columns natively.
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
MAX_CHARS = 900_000

# Image mode: max pages sent in one call.
# Each image ≈ 258 tokens; 60 pages ≈ 15 480 tokens — well within the 1M limit.
MAX_IMAGE_PAGES = 60

# DPI for PDF-to-image conversion. 200 gives sharp text without huge memory use.
IMAGE_DPI = 200


# ── Text extraction ───────────────────────────────────────────────────────────

def extract_text_by_page(pdf_path: Path) -> list[dict]:
    """Returns list of {page, text} dicts via pdfplumber. No OCR fallback."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if len(text.strip()) > 50:
                    pages.append({"page": i, "text": text.strip()})
    except Exception as e:
        log.warning(f"pdfplumber failed: {e}")
    return pages


def is_low_quality_text(pages: list[dict]) -> bool:
    """Return True if the extracted text is too sparse to be useful."""
    total_chars = sum(len(p["text"]) for p in pages)
    return len(pages) < 2 or total_chars < 5_000


# ── Image extraction ──────────────────────────────────────────────────────────

def pdf_to_images(pdf_path: Path, dpi: int = IMAGE_DPI) -> list:
    """
    Convert PDF pages to PIL Image objects for direct Gemini vision input.
    Returns list of PIL.Image instances (up to MAX_IMAGE_PAGES).
    """
    try:
        from pdf2image import convert_from_path
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None  # suppress DecompressionBombWarning

        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            fmt="jpeg",
            thread_count=2,
        )

        if len(images) > MAX_IMAGE_PAGES:
            log.warning(
                f"  PDF has {len(images)} pages — capping at {MAX_IMAGE_PAGES} for API limits"
            )
            images = images[:MAX_IMAGE_PAGES]

        log.info(f"  Converted {len(images)} pages to images at {dpi} DPI")
        return images

    except Exception as e:
        log.error(f"PDF to image conversion failed: {e}")
        return []


# ── Prompt builder ────────────────────────────────────────────────────────────

def _extraction_prompt(newspaper: str, is_image_mode: bool = False) -> str:
    """Build the extraction prompt for both text and image modes."""
    mode_note = (
        "You are given the newspaper as a series of page images. "
        "Read every page carefully.\n"
        if is_image_mode
        else "Full newspaper text is appended below.\n"
    )

    return f"""You are a senior news editor. Extract EVERY distinct news article from today's {newspaper}.

{mode_note}
Rules:
- Extract ALL news articles — include every story, not just major ones.
- SKIP: advertisements, stock tables, weather forecasts, TV schedules, classifieds, obituaries, horoscopes, crosswords.
- Identify the page number (1-based) for each article.
- Category must be exactly one of: {', '.join(CATEGORIES)}
- Importance: rate each article 1-10 based on national/global significance and reader impact. Front-page lead stories = 8-10. Minor local briefs = 1-3.

Return ONLY a valid JSON array. Each item must have exactly these fields:
- "headline": clear factual headline, max 12 words
- "summary": 5-6 sentences in neutral simple English with key facts and figures
- "category": one category from the list above
- "page": integer page number where article starts
- "importance": integer 1-10 rating of the article's significance

Return ONLY the JSON array. No markdown fences, no explanation, no preamble."""


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_articles(response_text: str, newspaper: str, pdf_path: Path) -> list[dict]:
    """Strip fences and parse JSON from Gemini response."""
    raw = response_text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    articles = json.loads(raw)
    for art in articles:
        art["newspaper"] = newspaper
        art["pdf_filename"] = pdf_path.name
    return articles


# ── Extraction entry point ────────────────────────────────────────────────────

def extract_all_articles(newspaper: str, pdf_path: Path, model) -> list[dict]:
    """
    Sends ENTIRE newspaper to Gemini in ONE API call.

    - If the PDF has good embedded text  → TEXT mode
    - If the PDF is scanned / image-based → IMAGE mode (pages as JPEG images)

    `model` must expose a generate_content() method compatible with
    google.generativeai.GenerativeModel — a ModelManager instance works too.

    Returns list of article dicts: headline, summary, category, page, newspaper,
    pdf_filename, importance.
    """
    pages = extract_text_by_page(pdf_path)

    if is_low_quality_text(pages):
        log.info(f"  [{newspaper}] Low text quality — switching to IMAGE mode (direct vision)")
        return _extract_via_images(newspaper, pdf_path, model)
    else:
        total_chars = sum(len(p["text"]) for p in pages)
        log.info(f"  [{newspaper}] TEXT mode — {total_chars:,} chars across {len(pages)} pages")
        return _extract_via_text(newspaper, pdf_path, pages, model)


def _extract_via_text(
    newspaper: str,
    pdf_path: Path,
    pages: list[dict],
    model,
) -> list[dict]:
    """TEXT mode: send the full extracted text to Gemini."""
    full_text = ""
    for p in pages:
        full_text += f"\n\n[PAGE {p['page']}]\n{p['text']}"

    if len(full_text) > MAX_CHARS:
        log.warning(f"  Text truncated from {len(full_text):,} to {MAX_CHARS:,} chars")
        full_text = full_text[:MAX_CHARS]

    log.info(f"  [{newspaper}] Sending {len(full_text):,} chars in single API call...")

    prompt = (
        _extraction_prompt(newspaper, is_image_mode=False)
        + f"\n\nFull newspaper text:\n{full_text}"
    )

    try:
        response = model.generate_content(prompt)
        articles = _parse_articles(response.text, newspaper, pdf_path)
        log.info(f"  [{newspaper}] Extracted {len(articles)} articles (TEXT mode)")
        return articles

    except json.JSONDecodeError as e:
        log.error(f"  [{newspaper}] JSON parse error: {e}")
        log.error(f"  [{newspaper}] Response start: {response.text[:300]}")
        log.error(f"  [{newspaper}] Response end:   {response.text[-300:]}")
        return []
    except Exception as e:
        log.error(f"  [{newspaper}] Gemini error (text mode): {e}")
        return []


def _extract_via_images(
    newspaper: str,
    pdf_path: Path,
    model,
) -> list[dict]:
    """
    IMAGE mode: convert PDF pages to high-quality JPEGs and send them directly
    to Gemini's vision API. No OCR involved — Gemini reads layout natively,
    handling multi-column formats and mixed scripts accurately.
    """
    images = pdf_to_images(pdf_path)
    if not images:
        log.error(f"  [{newspaper}] IMAGE mode failed: could not convert PDF to images")
        return []

    log.info(f"  [{newspaper}] Sending {len(images)} page images in single API call...")

    prompt = _extraction_prompt(newspaper, is_image_mode=True)

    # Gemini generate_content accepts a list: [text_prompt, pil_img1, pil_img2, ...]
    content = [prompt] + images

    try:
        response = model.generate_content(content)
        articles = _parse_articles(response.text, newspaper, pdf_path)
        log.info(f"  [{newspaper}] Extracted {len(articles)} articles (IMAGE mode)")
        return articles

    except json.JSONDecodeError as e:
        log.error(f"  [{newspaper}] JSON parse error (image mode): {e}")
        log.error(f"  [{newspaper}] Response start: {response.text[:300]}")
        return []
    except Exception as e:
        log.error(f"  [{newspaper}] Gemini error (image mode): {e}")
        return []
