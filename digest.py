"""
digest.py — Main orchestration
Flow: Telegram → PDF (temp) → Extract ALL → Deduplicate → Build Site → Notify

Incremental update mode:
  On the first run of the day, all available papers are downloaded and the site
  is built from scratch. On subsequent runs, only newly arrived papers are
  downloaded and processed; their articles are merged into the existing
  digest.json and the site is rebuilt. A state file (docs/digest_state.json)
  tracks which papers have already been processed today so the workflow can
  skip runs where nothing new has arrived.

Sunday mode:
  Mint and Business Standard are not published on Sundays. The state tracker
  treats 7 papers as "complete" on Sundays rather than 9.

API call budget (free tier = 20 RPD):
  First run : 1 test + N extraction calls (1/paper) + 1 dedup = N+2 calls
  Later runs: N_new extraction calls + 1 dedup = N_new+1 calls
  Worst case across all runs in a day: still ≤ 11 calls (9 papers + 2 overhead)

Model fallback:
  ModelManager tries models in priority order. If any call hits a quota / rate-
  limit error it immediately switches to the next model and retries — even in
  the middle of processing newspapers.  All free-tier models are tried before
  giving up.
"""

import os
import json
import logging
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import google.generativeai as genai

from telegram_downloader import run as download_pdfs, EXPECTED_NEWSPAPERS
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
IST            = timezone(timedelta(hours=5, minutes=30))
DOCS_DIR       = Path("docs")
STATE_FILE     = DOCS_DIR / "digest_state.json"

# Papers not published on Sundays
SUNDAY_SKIP = {"Mint", "Business Standard"}


# ── Model Manager ─────────────────────────────────────────────────────────────

class ModelManager:
    """
    Transparent wrapper around google.generativeai.GenerativeModel that
    automatically falls back to the next available free-tier model whenever a
    quota or rate-limit error is encountered.

    Fallback happens immediately — mid-extraction, mid-dedup, any call —
    so no newspaper is silently skipped due to quota exhaustion.

    Priority order (best → last resort):
      1. gemini-2.5-flash-preview-05-20   (Gemini 2.5 Flash)
      2. gemini-2.5-flash-lite-preview-06-17
      3. gemini-2.0-flash
      4. gemini-1.5-flash
    """

    # (model_id, human-readable label)
    MODEL_CHAIN = [
        ("gemini-3-flash-preview",              "Gemini 3 Flash Preview  (5 RPM / 20 RPD)"),
        ("gemini-2.5-flash",                    "Gemini 2.5 Flash        (5 RPM / 20 RPD)"),
        ("gemini-2.5-flash-lite",               "Gemini 2.5 Flash Lite"),
        ("gemini-2.0-flash",                    "Gemini 2.0 Flash"),
        ("gemini-1.5-flash",                    "Gemini 1.5 Flash"),
    ]

    # Errors that warrant switching to the next model.
    # Quota/rate-limit: switch model immediately.
    # Timeout/cancellation on text mode: also switch (next model may be faster).
    # Note: image-mode timeouts are handled inside extractor.py via DPI reduction first.
    _FALLBACK_SIGNALS = (
        # quota / rate-limit
        "quota", "resource_exhausted", "rate limit",
        "too many requests", "429", "rateerror",
        # timeout / cancellation
        "canceled", "cancelled", "timeout",
        "deadline exceeded", "timed out",
        "operation was canceled",
    )

    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self._index = 0
        self._model = None
        self._lock = threading.Lock()   # guards _index and _model for parallel extraction
        self._load_model(self._index)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_model(self, index: int) -> None:
        model_id, label = self.MODEL_CHAIN[index]
        self._model = genai.GenerativeModel(model_id)
        log.info(f"[ModelManager] Active model: {label}")

    def _is_fallback_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(signal in msg for signal in self._FALLBACK_SIGNALS)

    def _advance(self) -> None:
        """Switch to the next model in the chain. Raises if chain is exhausted."""
        exhausted_id, _ = self.MODEL_CHAIN[self._index]
        self._index += 1
        if self._index >= len(self.MODEL_CHAIN):
            raise RuntimeError(
                "All Gemini free-tier models are quota-exhausted. "
                "Cannot complete extraction today."
            )
        next_id, next_label = self.MODEL_CHAIN[self._index]
        log.warning(
            f"[ModelManager] Quota exceeded on '{exhausted_id}' — "
            f"switching to '{next_id}' ({next_label})"
        )
        self._load_model(self._index)

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def current_model_id(self) -> str:
        return self.MODEL_CHAIN[self._index][0]

    def generate_content(self, *args, **kwargs):
        """
        Drop-in replacement for GenerativeModel.generate_content().
        Retries with the next model on any quota/rate-limit error.
        Thread-safe: multiple newspapers can call this concurrently.
        All other exceptions propagate normally.
        """
        while True:
            with self._lock:
                current_model = self._model
            try:
                return current_model.generate_content(*args, **kwargs)
            except Exception as exc:
                if self._is_fallback_error(exc):
                    log.warning(f"[ModelManager] Quota/rate error: {exc}")
                    with self._lock:
                        self._advance()
                    # Brief pause before retrying to respect new model's RPM
                    time.sleep(2)
                else:
                    raise


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state(today_str: str, force_reset: bool = False) -> dict:
    """
    Load today's state from docs/digest_state.json.
    Returns a fresh state dict if the file is missing, from a previous day,
    or if force_reset is True.
    """
    if not force_reset and STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if state.get("date") == today_str:
                return state
        except Exception:
            pass
    if force_reset:
        log.info("FORCE_RESET: clearing all state for today.")
    return {
        "date":        today_str,
        "downloaded":  [],
        "articles":    [],
        "newspapers":  [],
        "is_complete": False,
    }


def save_state(state: dict) -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"State saved — processed so far today: {state['downloaded']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    DOCS_DIR.mkdir(exist_ok=True)

    today_override = os.environ.get("TARGET_DATE")
    if today_override:
        from datetime import date as _date
        today = datetime.combine(datetime.strptime(today_override, "%Y-%m-%d").date(),
                                 datetime.min.time()).replace(tzinfo=IST)
        log.info(f"TARGET_DATE override: using {today_override}")
    else:
        today = datetime.now(IST)
    today_str   = today.strftime("%Y-%m-%d")
    date_str    = today.strftime("%d %B %Y")
    is_sunday   = today.weekday() == 6

    expected_papers = (
        [p for p in EXPECTED_NEWSPAPERS if p not in SUNDAY_SKIP]
        if is_sunday else list(EXPECTED_NEWSPAPERS)
    )

    log.info(f"=== News Digest — {date_str} {'(Sunday mode)' if is_sunday else ''} ===")
    log.info(f"Expected papers ({len(expected_papers)}): {expected_papers}")

    # ── Initialise model manager (single shared instance for the whole run) ───
    model = ModelManager()
    log.info(f"Model manager ready — starting with '{model.current_model_id}'")

    # ── Load state from previous runs today ───────────────────────────────────
    force_reset  = os.environ.get("FORCE_RESET", "no").lower() in ("yes", "true", "1")
    state        = load_state(today_str, force_reset=force_reset)
    already_done = set(state["downloaded"])

    if state["is_complete"] and not force_reset and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        log.info("All papers already processed today — nothing to do.")
        return

    log.info(f"Already processed today: {sorted(already_done) or 'none'}")

    # ── Step 1: Download only papers not yet processed ────────────────────────
    log.info("Downloading new papers from Telegram...")
    newspaper_map = download_pdfs()

    new_papers = {k: v for k, v in newspaper_map.items() if k not in already_done}

    if not new_papers:
        log.info("No new papers available since last run — exiting.")
        return

    log.info(f"New papers this run: {list(new_papers.keys())}")

    # ── Step 2: Extract articles from new papers in parallel ──────────────────
    # Up to 5 papers run concurrently (matches Gemini's 5 RPM free-tier limit).
    # Each extraction call takes 1–5 min, so 5 parallel calls stay well within RPM.
    # ModelManager is thread-safe and shared across all workers.
    def _extract_one(newspaper: str, info: dict) -> tuple[str, list[dict]]:
        log.info(f"Extracting: {newspaper}  [model: {model.current_model_id}]")
        articles = extract_all_articles(newspaper, Path(info["path"]), model)
        for art in articles:
            art["telegram_url"] = info["telegram_url"]
        log.info(f"  {len(articles)} articles extracted from {newspaper}")
        return newspaper, articles

    new_articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_extract_one, np, info): np for np, info in new_papers.items()}
        for future in as_completed(futures):
            try:
                _, articles = future.result()
                new_articles.extend(articles)
            except Exception as exc:
                log.error(f"Extraction failed for {futures[future]}: {exc}")

    log.info(f"New raw articles this run: {len(new_articles)}")

    # ── Step 3: Merge with existing articles from earlier runs today ──────────
    combined_articles = state["articles"] + new_articles
    combined_newspapers = state["newspapers"] + [
        n for n in new_papers.keys() if n not in state["newspapers"]
    ]
    log.info(f"Combined article pool: {len(combined_articles)} articles from {combined_newspapers}")

    # ── Step 4: Deduplicate the full combined pool ────────────────────────────
    log.info(f"Deduplicating  [model: {model.current_model_id}]")
    merged_articles = deduplicate(combined_articles, model)
    log.info(f"Final unique articles after dedup: {len(merged_articles)}")

    # ── Step 5: Save digest JSON + build site ─────────────────────────────────
    digest_data = {
        "date":           date_str,
        "generated_at":   today.isoformat(),
        "total_articles": len(merged_articles),
        "newspapers":     combined_newspapers,
        "articles":       merged_articles,
    }
    (DOCS_DIR / "digest.json").write_text(
        json.dumps(digest_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    build_site(digest_data, DOCS_DIR)
    log.info("Site rebuilt at docs/index.html")

    # ── Step 6: Stage PDFs for GitHub Pages artifact ──────────────────────────
    pdfs_dest = DOCS_DIR / "pdfs"
    pdfs_dest.mkdir(exist_ok=True)
    pdf_dir = Path("pdfs")
    if pdf_dir.exists():
        for pdf in pdf_dir.glob("*.pdf"):
            shutil.copy2(str(pdf), str(pdfs_dest / pdf.name))
            log.info(f"  Staged: {pdf.name}")
        shutil.rmtree(pdf_dir)

    # ── Step 7: Update and persist state ──────────────────────────────────────
    updated_done = sorted(already_done | set(new_papers.keys()))
    is_complete  = set(updated_done) >= set(expected_papers)

    state.update({
        "downloaded":  updated_done,
        "articles":    merged_articles,
        "newspapers":  combined_newspapers,
        "is_complete": is_complete,
    })
    save_state(state)

    if is_complete:
        log.info(f"All {len(expected_papers)} expected papers processed — "
                 "workflow will skip remaining schedule triggers today.")
    else:
        remaining = [p for p in expected_papers if p not in updated_done]
        log.info(f"Still waiting for: {remaining}")

    # ── Step 8: Send Telegram notification ───────────────────────────────────
    if os.environ.get("MORNING_NOTIFY", "true").lower() == "false":
        notify(digest_data)
    else:
        log.info("Notification deferred to morning_notify job (9 AM IST)")

    api_calls_used = len(new_papers) + 2
    log.info(
        f"Done! {len(merged_articles)} articles, "
        f"{len(combined_newspapers)} newspapers so far today, "
        f"~{api_calls_used} API calls this run. "
        f"Final model used: {model.current_model_id}"
    )


if __name__ == "__main__":
    main()
