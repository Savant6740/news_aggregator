"""
extractor.py
Extracts ALL articles from a newspaper PDF in a SINGLE Gemini API call.

Why single call?
- Free tier limit: only 20 requests/day (RPD)
- Gemini 2.5 Flash has 1M token context window — entire newspaper fits in one call
- 7 newspapers x 1 call = 7 calls for extraction, leaving budget for deduplication

PDF modes:
- TEXT mode : pdfplumber extracts text → sent as a single text prompt
- IMAGE mode: PDF pages → JPEG images → sent directly to Gemini vision
  (used when text extraction yields < 5 000 chars, i.e. scanned / image-based PDFs)
  This is strictly better than OCR: Gemini reads layout, fonts and columns natively.

Image mode DPI strategy:
  First attempt  : 120 DPI  (~3 MB total, fast)
  Retry on timeout: 80 DPI  (~1.5 MB total, very fast)
  120 DPI is still perfectly sharp for Gemini — text is legible down to ~60 DPI.
  200 DPI (previous default) caused 15-min calls and server-side cancellations.
"""

import io
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

# Text mode: Gemini 2.5 Flash has ~1M token context. 1 token ≈ 4 chars.
MAX_CHARS = 900_000

# Image mode: max pages per call (60 pages × ~258 tokens ≈ 15 K tokens — fine)
MAX_IMAGE_PAGES = 60

# DPI levels tried in order for image mode.
# 120 → fast & sharp; 80 → fallback if 120 times out.
IMAGE_DPI_LEVELS = [120, 80]

# Per-call timeout in seconds for image-mode requests.
# 300 s (5 min) is generous; if it still times out, we retry at lower DPI.
IMAGE_TIMEOUT_SECONDS = 300


# ── Error classification ──────────────────────────────────────────────────────

def _is_timeout_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in (
        "canceled", "cancelled", "timeout", "deadline exceeded",
        "timed out", "operation was canceled",
    ))


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


# ── Image conversion ──────────────────────────────────────────────────────────

def pdf_to_images(pdf_path: Path, dpi: int) -> list:
    """
    Convert PDF pages to PIL Image objects at the given DPI.
    Returns list of PIL.Image instances (capped at MAX_IMAGE_PAGES).
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
            log.warning(f"  PDF has {len(images)} pages — capping at {MAX_IMAGE_PAGES}")
            images = images[:MAX_IMAGE_PAGES]

        # Estimate total JPEG size for logging
        total_kb = 0
        for img in images[:3]:   # sample first 3 pages to estimate
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            total_kb += buf.tell() / 1024
        avg_kb  = total_kb / min(3, len(images))
        est_mb  = avg_kb * len(images) / 1024

        log.info(f"  Converted {len(images)} pages at {dpi} DPI  "
                 f"(est. {est_mb:.1f} MB total)")
        return images

    except Exception as e:
        log.error(f"PDF to image conversion failed: {e}")
        return []


# ── Prompt builder ────────────────────────────────────────────────────────────

def _extraction_prompt(newspaper: str, is_image_mode: bool = False) -> str:
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
- "summary": factual summary in neutral simple English with key facts and figures. HARD LIMIT: 400 characters maximum (including spaces). Do NOT exceed this — the text must fit on a mobile screen without any clipping.
- "category": one category from the list above
- "page": integer page number where article starts
- "importance": integer 1-10 rating of the article's significance

Return ONLY the JSON array. No markdown fences, no explanation, no preamble."""


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_articles(response_text: str, newspaper: str, pdf_path: Path) -> list[dict]:
    """Strip markdown fences and parse JSON array from Gemini response."""
    raw = response_text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    articles = json.loads(raw)
    for art in articles:
        art["newspaper"]    = newspaper
        art["pdf_filename"] = pdf_path.name
    return articles


# ── Extraction entry point ────────────────────────────────────────────────────

def extract_all_articles(newspaper: str, pdf_path: Path, model) -> list[dict]:
    """
    Sends ENTIRE newspaper to Gemini in ONE API call.

    - If the PDF has good embedded text  → TEXT mode
    - If the PDF is scanned / image-based → IMAGE mode (pages as JPEG images)

    `model` may be a raw genai.GenerativeModel or a ModelManager — both expose
    the same generate_content() interface.
    """
    pages = extract_text_by_page(pdf_path)

    if is_low_quality_text(pages):
        log.info(f"  [{newspaper}] Low text quality — switching to IMAGE mode")
        return _extract_via_images(newspaper, pdf_path, model)
    else:
        total_chars = sum(len(p["text"]) for p in pages)
        log.info(f"  [{newspaper}] TEXT mode — {total_chars:,} chars across {len(pages)} pages")
        return _extract_via_text(newspaper, pdf_path, pages, model)


# ── TEXT mode ─────────────────────────────────────────────────────────────────

def _extract_via_text(
    newspaper: str,
    pdf_path: Path,
    pages: list[dict],
    model,
) -> list[dict]:
    full_text = "".join(f"\n\n[PAGE {p['page']}]\n{p['text']}" for p in pages)

    if len(full_text) > MAX_CHARS:
        log.warning(f"  Text truncated from {len(full_text):,} to {MAX_CHARS:,} chars")
        full_text = full_text[:MAX_CHARS]

    log.info(f"  [{newspaper}] Sending {len(full_text):,} chars...")

    prompt = (
        _extraction_prompt(newspaper, is_image_mode=False)
        + f"\n\nFull newspaper text:\n{full_text}"
    )

    try:
        response = model.generate_content(prompt)
        articles = _parse_articles(response.text, newspaper, pdf_path)

        if len(articles) == 0:
            # 0 articles usually means Gemini returned something non-JSON or an
            # error message.  Log the raw response to help diagnose.
            log.warning(f"  [{newspaper}] 0 articles returned. Raw response (first 500 chars):")
            log.warning(f"  {response.text[:500]}")

        log.info(f"  [{newspaper}] Extracted {len(articles)} articles (TEXT mode)")
        return articles

    except json.JSONDecodeError as e:
        log.error(f"  [{newspaper}] JSON parse error: {e}")
        try:
            log.error(f"  [{newspaper}] Response start : {response.text[:400]}")
            log.error(f"  [{newspaper}] Response end   : {response.text[-400:]}")
        except Exception:
            pass
        return []
    except Exception as e:
        log.error(f"  [{newspaper}] Gemini error (text mode): {e}")
        return []


# ── IMAGE mode ────────────────────────────────────────────────────────────────

def _extract_via_images(
    newspaper: str,
    pdf_path: Path,
    model,
) -> list[dict]:
    """
    IMAGE mode: convert PDF pages to JPEGs and send directly to Gemini vision.

    Retries automatically at a lower DPI if the call times out or is canceled:
      Attempt 1 : IMAGE_DPI_LEVELS[0]  (120 DPI, ~3 MB)
      Attempt 2 : IMAGE_DPI_LEVELS[1]  (80 DPI,  ~1.5 MB)
    """
    prompt = _extraction_prompt(newspaper, is_image_mode=True)

    for attempt, dpi in enumerate(IMAGE_DPI_LEVELS, start=1):
        images = pdf_to_images(pdf_path, dpi=dpi)
        if not images:
            log.error(f"  [{newspaper}] Could not convert PDF to images at {dpi} DPI")
            return []

        log.info(
            f"  [{newspaper}] IMAGE attempt {attempt}/{len(IMAGE_DPI_LEVELS)} "
            f"— {len(images)} pages at {dpi} DPI, "
            f"timeout={IMAGE_TIMEOUT_SECONDS}s"
        )

        content = [prompt] + images

        try:
            response = model.generate_content(
                content,
                request_options={"timeout": IMAGE_TIMEOUT_SECONDS},
            )
            articles = _parse_articles(response.text, newspaper, pdf_path)

            if len(articles) == 0:
                log.warning(f"  [{newspaper}] 0 articles returned (image mode). Raw response:")
                log.warning(f"  {response.text[:500]}")

            log.info(
                f"  [{newspaper}] Extracted {len(articles)} articles "
                f"(IMAGE mode, {dpi} DPI)"
            )
            return articles

        except json.JSONDecodeError as e:
            log.error(f"  [{newspaper}] JSON parse error (image, {dpi} DPI): {e}")
            try:
                log.error(f"  [{newspaper}] Response start: {response.text[:400]}")
            except Exception:
                pass
            # JSON error is not a timeout — don't retry at lower DPI
            return []

        except Exception as e:
            if _is_timeout_error(e) and attempt < len(IMAGE_DPI_LEVELS):
                log.warning(
                    f"  [{newspaper}] Timeout/cancellation at {dpi} DPI: {e}\n"
                    f"  Retrying at {IMAGE_DPI_LEVELS[attempt]} DPI..."
                )
                continue   # next DPI level
            else:
                log.error(f"  [{newspaper}] Gemini error (image, {dpi} DPI): {e}")
                return []

    # All DPI levels exhausted
    log.error(f"  [{newspaper}] IMAGE mode failed after {len(IMAGE_DPI_LEVELS)} attempts")
    return []
