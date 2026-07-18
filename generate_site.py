"""
generate_site.py — Dual-screen daily brief: browsable Index + swipe Reader.

Index (default landing screen): a scrollable, category-grouped list of every
article — headline, snippet, source, page — with a category chip bar for
quick jumps. Tapping a row opens the Reader at that article.

Reader (unchanged interaction model): the original full-screen, TikTok-style
swipe deck — swipe up for the next article in a category, swipe sideways to
change category. Reached by tapping an Index row, the "Start reading" button,
or a `#article-<id>` deep link (used by push notifications), and closed via
a back button that returns to the Index.

Notification schedule:
  Batch 1 — Fired here, immediately after index.html is written
  Batch 2 — 1:30 PM IST  (via cron → notify_scheduler.py)
  Batch 3 — 4:30 PM IST  (via cron → notify_scheduler.py)
  Batch 4 — 7:30 PM IST  (via cron → notify_scheduler.py)
"""
import json
import hashlib
import subprocess
import sys
from pathlib import Path

CATEGORY_META = {
    "Politics":       {"color": "#e8334a", "icon": "🏛️"},
    "Economy":        {"color": "#f5a623", "icon": "📊"},
    "Business":       {"color": "#f0c040", "icon": "💼"},
    "India":          {"color": "#ff7043", "icon": "🇮🇳"},
    "World":          {"color": "#5c9eff", "icon": "🌍"},
    "Sports":         {"color": "#36c46f", "icon": "🏆"},
    "Science":        {"color": "#a78bfa", "icon": "🔬"},
    "Technology":     {"color": "#38bdf8", "icon": "💻"},
    "Health":         {"color": "#34d399", "icon": "🏥"},
    "Law":            {"color": "#fb923c", "icon": "⚖️"},
    "Environment":    {"color": "#4ade80", "icon": "🌿"},
    "Education":      {"color": "#e879f9", "icon": "📚"},
    "Culture":        {"color": "#f472b6", "icon": "🎭"},
    "Infrastructure": {"color": "#94a3b8", "icon": "🏗️"},
}
DEFAULT_META = {"color": "#636e72", "icon": "📰"}

FAVICON_SVG = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='6' fill='%230c0b0b'/%3E"
    "%3Crect x='4' y='5' width='24' height='22' rx='2' fill='none' stroke='%23c9a66b' stroke-width='1.5'/%3E"
    "%3Crect x='7' y='8' width='18' height='3' rx='1' fill='%23c9a66b'/%3E"
    "%3Crect x='7' y='13' width='10' height='1.5' rx='0.75' fill='%23888'/%3E"
    "%3Crect x='7' y='16' width='10' height='1.5' rx='0.75' fill='%23888'/%3E"
    "%3Crect x='7' y='19' width='7' height='1.5' rx='0.75' fill='%23888'/%3E"
    "%3Crect x='19' y='13' width='6' height='8' rx='1' fill='%23c9a66b' opacity='0.4'/%3E"
    "%3C/svg%3E"
)

def generate_article_id(article):
    """Generate stable 8-char ID from headline + date for deep linking."""
    date = article.get('date', '2026-04-07')
    headline = article.get('headline', '')
    content = f"{date}:{headline}".encode('utf-8')
    return hashlib.md5(content).hexdigest()[:8]

def build_site(data: dict, output_dir: Path):
    (output_dir / "index.html").write_text(generate_html(data), encoding="utf-8")
    _trigger_batch_1()


def _trigger_batch_1():
    """
    Fire Batch 1 notifications immediately after the HTML is written.
    Runs notify_scheduler.py --batch 1 as a subprocess so that any
    import errors in the scheduler don't crash the site builder.
    NTFY_TOPIC must be set in the environment (passed through by digest.py).
    """
    import os
    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not ntfy_topic:
        print("ℹ️  NTFY_TOPIC not set — skipping Batch 1 notifications")
        return

    print("📲 Triggering Batch 1 notifications (immediate)…")
    try:
        result = subprocess.run(
            [sys.executable, "notify_scheduler.py", "--batch", "1"],
            capture_output=False,   # let output stream to the parent's stdout
            timeout=60,
        )
        if result.returncode != 0:
            print(f"⚠️  notify_scheduler.py exited with code {result.returncode}")
    except Exception as e:
        print(f"⚠️  Failed to trigger Batch 1 notifications: {e}")


# ──────────────────────────────────────────────────────────────────────────
# Page template. Plain string (NOT an f-string) — every brace below is
# literal CSS/JS, nothing needs doubling. Placeholders are %%TOKEN%% markers
# substituted via .replace() in generate_html(), in a deliberate order: safe
# server-controlled values first (DATE_STR, FAVICON), JSON blobs last, with
# DIGEST_JSON absolutely last since article text (Gemini-generated headlines
# and summaries) is the only content that could ever coincidentally contain
# a literal "%%...%%"-shaped substring — putting it last means there is no
# later .replace() call left that could mistake such text for a placeholder.
# ──────────────────────────────────────────────────────────────────────────
PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#0c0c0c">
<title>Daily Brief — %%DATE_STR%%</title>
<link rel="icon" type="image/svg+xml" href="%%FAVICON%%">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
html, body {
  width: 100%; height: 100%;
  overflow: hidden;
  font-family: 'Inter', -apple-system, sans-serif;
  background: #0c0c0c; color: #fff;
}
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
a { color: inherit; }

/* ── Screens ─────────────────────────────────────────────────────────── */
.screen { position: fixed; inset: 0; opacity: 0; pointer-events: none; transition: opacity 0.18s ease; }
.screen.active { opacity: 1; pointer-events: auto; }

/* ── Index screen ────────────────────────────────────────────────────── */
#indexScreen { display: flex; flex-direction: column; background: #0c0c0c; }

.masthead { flex-shrink: 0; padding: 22px 20px 14px; }
.masthead-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.masthead-kicker { font-size: 10.5px; font-weight: 800; letter-spacing: 0.16em; color: #c9a66b; text-transform: uppercase; margin-bottom: 5px; }
.masthead-date { font-size: 25px; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }
.masthead-meta { margin-top: 9px; font-size: 12.5px; font-weight: 500; color: #666; }
.start-btn {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; white-space: nowrap;
  background: #c9a66b; color: #14110a; font-weight: 700; font-size: 12.5px;
  padding: 10px 14px; border-radius: 100px; letter-spacing: 0.005em;
}

.chip-nav {
  flex-shrink: 0; display: flex; gap: 8px; padding: 12px 20px;
  overflow-x: auto; scrollbar-width: none; border-bottom: 1px solid #1a1a1a;
}
.chip-nav::-webkit-scrollbar { display: none; }
.chip {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; white-space: nowrap;
  background: #141414; border: 1px solid #232323; border-radius: 100px;
  padding: 7px 13px 7px 11px; font-size: 12.5px; font-weight: 600; color: #999;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.chip-count { color: #555; font-weight: 500; }
.chip.active { color: #fff; border-color: var(--cc); background: color-mix(in srgb, var(--cc) 18%, #141414); }
.chip.active .chip-count { color: color-mix(in srgb, var(--cc) 65%, #fff); }

.index-list { flex: 1; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 32px; }
.cat-section { display: flex; flex-direction: column; }

.section-head { display: flex; align-items: center; gap: 8px; padding: 20px 20px 8px; }
.sh-icon { font-size: 14px; }
.sh-name { font-size: 12.5px; font-weight: 800; letter-spacing: 0.07em; text-transform: uppercase; color: var(--cc); }
.sh-count { margin-left: auto; font-size: 11.5px; font-weight: 600; color: #444; }

.row {
  display: flex; flex-direction: column; width: 100%; text-align: left; gap: 5px;
  padding: 13px 20px; border-bottom: 1px solid #131313; position: relative;
}
.row::before { content: ''; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; border-radius: 2px; background: var(--cc); opacity: 0.6; }
.row:active { background: #111; }
.row-top { display: flex; align-items: center; gap: 6px; min-height: 14px; }
.row-flame { font-size: 11px; line-height: 1; }
.row-source { margin-left: auto; font-size: 11.5px; font-weight: 600; color: #5e5e5e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 70%; }
.row-more { color: #444; font-weight: 500; }
.row-headline { font-size: 15px; font-weight: 700; line-height: 1.32; color: #eee; letter-spacing: -0.01em; }
.row-summary { font-size: 12.5px; line-height: 1.5; color: #666; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 6px; padding: 40px 24px; text-align: center; }
.empty-state-icon { font-size: 34px; opacity: 0.55; margin-bottom: 6px; }
.empty-state-title { font-size: 14.5px; font-weight: 700; color: #888; }
.empty-state-sub { font-size: 12px; color: #454545; }

/* ── Reader screen (swipe cards) — unchanged from the original design ──── */
.outer { position: fixed; inset: 0; overflow: hidden; touch-action: none; }
.h-track { display: flex; height: 100%; will-change: transform; }
.cat-panel { flex-shrink:0; width:100vw; height:100%; display:flex; flex-direction:column; overflow:hidden; }
.progress-row { flex-shrink:0; display:flex; gap:4px; padding:14px 16px 10px; background:#0c0c0c; position:relative; z-index:5; overflow:visible; }
.progress-row::after { content:''; position:absolute; top:0; left:50%; transform:translateX(-50%); width:80%; height:120px; background:radial-gradient(ellipse at top,color-mix(in srgb,var(--cc) 30%,transparent) 0%,transparent 70%); pointer-events:none; z-index:-1; }
.pseg { flex:1; height:2px; border-radius:1px; background:rgba(255,255,255,0.12); position:relative; overflow:hidden; }
.pseg::after { content:''; position:absolute; inset:0; background:var(--cc,#e8334a); transform:scaleX(0); transform-origin:left; transition:transform 0.25s ease; }
.pseg.done::after, .pseg.active::after { transform:scaleX(1); }
.v-feed { flex:1; overflow:hidden; position:relative; clip-path:inset(0); }
.v-track { display:flex; flex-direction:column; will-change:transform; }
.card {
  width:100%; flex-shrink:0; background:#0c0c0c; display:flex; flex-direction:column;
  overflow:hidden; position:relative;
  scroll-margin-top: 80px;
}
.card.target-highlight {
  background: linear-gradient(135deg, #fff3cd22 0%, #ffeaa722 100%) !important;
  box-shadow: 0 0 30px rgba(255, 193, 7, 0.4);
  border: 2px solid #f39c12;
  animation: pulse-highlight 2s ease-in-out;
}
@keyframes pulse-highlight {
  0%, 100% { box-shadow: 0 0 30px rgba(255, 193, 7, 0.4); }
  50% { box-shadow: 0 0 50px rgba(255, 193, 7, 0.6); }
}
.card-content { flex:1; display:flex; flex-direction:column; padding:36px 20px 22px; min-height:0; position:relative; z-index:1; }
.card-toprow { display:flex; align-items:center; justify-content:space-between; margin-bottom:28px; flex-shrink:0; }
.cat-pill { display:inline-flex; align-items:center; gap:7px; background:#1c1c1e; border-radius:8px; padding:7px 12px 7px 10px; font-size:11.5px; font-weight:700; letter-spacing:0.07em; color:#d0d0d0; text-transform:uppercase; line-height:1; }
.pill-icon { width:16px; height:16px; background:#2e2e30; border-radius:3px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.pill-icon svg { display:block; }
.card-date { display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:500; color:#666; letter-spacing:0.01em; }
.card-headline { font-size:28px; font-weight:800; line-height:1.18; color:#fff; letter-spacing:-0.03em; margin-bottom:20px; flex-shrink:0; }
.card-summary { font-size:15.5px; font-weight:400; line-height:1.62; color:#6b6b6b; flex:1; overflow:hidden; display:-webkit-box; -webkit-line-clamp:7; -webkit-box-orient:vertical; }
.card-divider { height:1px; background:#1e1e1e; margin:20px 0 16px; flex-shrink:0; }
.card-footer { display:flex; align-items:center; justify-content:space-between; flex-shrink:0; }
.src-chip { display:inline-flex; align-items:center; gap:6px; background:#181818; border:1px solid #282828; border-radius:9px; padding:8px 13px; font-size:12.5px; font-weight:600; color:#c0c0c0; text-decoration:none; letter-spacing:0.005em; line-height:1; }
.src-chip-sep { color:#3a3a3a; font-weight:400; }
.src-chip-pg { color:#555; font-weight:500; }
.src-chip-ext { margin-left:2px; }
.src-chip-ext svg { display:block; }
.info-btn { width:36px; height:36px; border-radius:50%; border:1.5px solid #252525; background:#141414; display:flex; align-items:center; justify-content:center; color:#555; flex-shrink:0; }

.back-btn {
  position: fixed; top: 16px; left: 16px; z-index: 500;
  width: 38px; height: 38px; border-radius: 50%;
  background: rgba(20,20,20,0.72); backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,0.08);
  display: flex; align-items: center; justify-content: center; color: #ddd;
}

.cat-flash { position:fixed; inset:0; z-index:600; pointer-events:none; opacity:0; transition:opacity 0.12s; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:8px; }
.cat-flash.on { opacity:1; }
.cf-icon { font-size:34px; }
.cf-name { font-size:22px; font-weight:900; letter-spacing:-0.03em; text-transform:uppercase; }
.hint { position:fixed; display:flex; flex-direction:column; align-items:center; gap:5px; pointer-events:none; z-index:400; opacity:0; transition:opacity 0.6s ease; }
.hint.visible { opacity:1; }
.hint.gone { opacity:0 !important; transition:opacity 0.4s; }
.hint-pill { font-size:10px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:rgba(255,255,255,0.55); background:rgba(255,255,255,0.07); backdrop-filter:blur(10px); padding:5px 13px; border-radius:100px; border:1px solid rgba(255,255,255,0.09); }
.hint-arr { font-size:16px; color:rgba(255,255,255,0.4); }
.h-up { bottom:28px; left:50%; transform:translateX(-50%); animation:bUp 2s ease-in-out infinite; }
.h-right { top:50%; right:14px; transform:translateY(-50%); animation:bRight 2s ease-in-out infinite 0.6s; }
@keyframes bUp { 0%,100% { bottom:28px; opacity:.65; } 50% { bottom:36px; opacity:1; } }
@keyframes bRight { 0%,100% { right:14px; opacity:.65; } 50% { right:6px; opacity:1; } }

/* ── Accessibility & responsive ──────────────────────────────────────── */
button:focus-visible, a:focus-visible { outline: 2px solid #c9a66b; outline-offset: 2px; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }
}

@media (min-width: 640px) {
  .masthead, .chip-nav, .cat-section { max-width: 640px; margin-inline: auto; }
}
</style>
</head>
<body>

<!-- INDEX SCREEN — default landing page: browsable, category-grouped list -->
<div class="screen" id="indexScreen">
  <header class="masthead">
    <div class="masthead-row">
      <div>
        <div class="masthead-kicker">Daily Brief</div>
        <h1 class="masthead-date" id="mastheadDate"></h1>
      </div>
      <button class="start-btn" id="startBtn" type="button">
        Start reading
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6h8M6 2l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
    <div class="masthead-meta" id="mastheadMeta"></div>
  </header>
  <nav class="chip-nav" id="chipNav" aria-label="Categories"></nav>
  <main class="index-list" id="indexList"></main>
</div>

<!-- READER SCREEN — full-screen swipe deck, opened from the Index -->
<div class="screen" id="readerScreen">
  <button class="back-btn" id="backBtn" type="button" aria-label="Back to index">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 3L4 8l6 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </button>
  <div class="outer" id="outer"><div class="h-track" id="hTrack"></div></div>
  <div class="hint h-up" id="hintUp"><span class="hint-arr">↑</span><span class="hint-pill">Swipe up</span></div>
  <div class="hint h-right" id="hintRight"><span class="hint-arr">→</span><span class="hint-pill">Next category</span></div>
  <div class="cat-flash" id="catFlash"><span class="cf-icon" id="cfIcon"></span><span class="cf-name" id="cfName"></span></div>
</div>

<script>
const DIGEST = %%DIGEST_JSON%%;
const CAT_META = %%CAT_META_JSON%%;
const DEFAULT_META = { color: "#636e72", icon: "📰" };

// ── Safety helpers ───────────────────────────────────────────────────────
// Article text comes from Gemini's reading of the newspaper PDFs, so it is
// technically external content (e.g. "AT&T", "R&D", or worse). Escape every
// dynamic string before it goes into innerHTML.
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str == null ? '' : String(str);
  return d.innerHTML;
}
function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'cat';
}

// ── Shared data (used by both Index and Reader) ─────────────────────────
const allArts = [...DIGEST.articles].sort((a, b) => (b.importance || 0) - (a.importance || 0));
const byCategory = {};
for (const art of allArts) {
  const c = art.category || "India";
  (byCategory[c] || (byCategory[c] = [])).push(art);
}
const sortedCats = Object.keys(byCategory).sort(
  (a, b) => (byCategory[b][0].importance || 0) - (byCategory[a][0].importance || 0)
);

// ── Screen switching ─────────────────────────────────────────────────────
const indexScreen  = document.getElementById('indexScreen');
const readerScreen = document.getElementById('readerScreen');

function showIndex() {
  readerScreen.classList.remove('active');
  indexScreen.classList.add('active');
}
function showReader() {
  indexScreen.classList.remove('active');
  readerScreen.classList.add('active');
  initHintsOnce();
}

// ── Index screen ─────────────────────────────────────────────────────────
function buildIndex() {
  const chipNav      = document.getElementById('chipNav');
  const indexList    = document.getElementById('indexList');
  const mastheadDate = document.getElementById('mastheadDate');
  const mastheadMeta = document.getElementById('mastheadMeta');
  const startBtn     = document.getElementById('startBtn');

  mastheadDate.textContent = DIGEST.date || 'Today';
  const totalArticles = DIGEST.total_articles ?? allArts.length;
  const totalPapers   = (DIGEST.newspapers || []).length;
  mastheadMeta.textContent = totalArticles
    ? `${totalArticles} article${totalArticles === 1 ? '' : 's'} · ${totalPapers} newspaper${totalPapers === 1 ? '' : 's'}`
    : 'No articles yet';

  if (!allArts.length) {
    startBtn.style.display = 'none';
  } else {
    startBtn.addEventListener('click', () => openReader(allArts[0].article_id));
  }

  chipNav.innerHTML = '';
  indexList.innerHTML = '';

  if (!sortedCats.length) {
    indexList.innerHTML =
      '<div class="empty-state">' +
        '<div class="empty-state-icon">📭</div>' +
        '<div class="empty-state-title">No articles yet</div>' +
        '<div class="empty-state-sub">Check back after the next digest run</div>' +
      '</div>';
    return;
  }

  const chips = [];
  sortedCats.forEach((cat, ci) => {
    const m    = CAT_META[cat] || DEFAULT_META;
    const arts = byCategory[cat];
    const slug = 'sec-' + slugify(cat);

    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip' + (ci === 0 ? ' active' : '');
    chip.style.setProperty('--cc', m.color);
    chip.innerHTML = `<span>${m.icon}</span><span>${esc(cat)}</span><span class="chip-count">${arts.length}</span>`;
    chip.addEventListener('click', () => {
      const sec = document.getElementById(slug);
      if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    chipNav.appendChild(chip);
    chips.push(chip);

    const section = document.createElement('section');
    section.className = 'cat-section';
    section.id = slug;

    const head = document.createElement('div');
    head.className = 'section-head';
    head.style.setProperty('--cc', m.color);
    head.innerHTML = `<span class="sh-icon">${m.icon}</span><span class="sh-name">${esc(cat)}</span><span class="sh-count">${arts.length}</span>`;
    section.appendChild(head);

    arts.forEach(art => section.appendChild(buildRow(art, m)));
    indexList.appendChild(section);
  });

  setupChipObserver(chips);
}

function buildRow(art, m) {
  const src   = art.sources && art.sources[0];
  const extra = (art.sources && art.sources.length > 1) ? art.sources.length - 1 : 0;
  const srcLabel = src
    ? `${esc(src.newspaper || '')} · Pg ${src.page || 1}${extra ? ` <span class="row-more">+${extra} more</span>` : ''}`
    : '';
  const flame = (art.importance || 0) >= 8 ? '<span class="row-flame">🔥</span>' : '';

  const row = document.createElement('button');
  row.type = 'button';
  row.className = 'row';
  row.style.setProperty('--cc', m.color);
  row.dataset.articleId = art.article_id;
  row.innerHTML = `
    <div class="row-top">
      ${flame}
      <span class="row-source">${srcLabel}</span>
    </div>
    <div class="row-headline">${esc(art.headline)}</div>
    <div class="row-summary">${esc(art.summary)}</div>
  `;
  row.addEventListener('click', () => openReader(art.article_id));
  return row;
}

let chipObserver = null;
function setupChipObserver(chips) {
  const indexList = document.getElementById('indexList');
  const sections  = sortedCats.map(cat => document.getElementById('sec-' + slugify(cat)));
  if (chipObserver) chipObserver.disconnect();
  chipObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const idx = sections.indexOf(entry.target);
      if (idx === -1) return;
      chips.forEach(c => c.classList.remove('active'));
      chips[idx].classList.add('active');
      chips[idx].scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    });
  }, { root: indexList, rootMargin: '-10% 0px -75% 0px', threshold: 0 });
  sections.forEach(s => s && chipObserver.observe(s));
}

// ── Reader screen (swipe-based; logic unchanged from the original) ──────
let catIdx = 0, vpW = 0, vpH = 0;
const panels    = [];
const outer     = document.getElementById('outer');
const hTrack    = document.getElementById('hTrack');
const hintUp    = document.getElementById('hintUp');
const hintRight = document.getElementById('hintRight');
const catFlash  = document.getElementById('catFlash');
const cfIcon    = document.getElementById('cfIcon');
const cfName    = document.getElementById('cfName');
const backBtn   = document.getElementById('backBtn');

function buildAllReaderPanels() {
  vpW = outer.offsetWidth; vpH = outer.offsetHeight;
  hTrack.innerHTML = ''; panels.length = 0;

  sortedCats.forEach((cat, ci) => {
    const m    = CAT_META[cat] || DEFAULT_META;
    const arts = byCategory[cat];
    const panel = document.createElement('div');
    panel.className = 'cat-panel';
    panel.id = `cat-panel-${ci}`;
    panel.style.setProperty('--cc', m.color);
    panel.innerHTML = `<div class="progress-row" id="prow-${ci}" style="--cc:${m.color}"></div><div class="v-feed" id="vfeed-${ci}"><div class="v-track" id="vtrack-${ci}"></div></div>`;
    hTrack.appendChild(panel);

    const pRow   = panel.querySelector(`#prow-${ci}`);
    const vFeed  = panel.querySelector(`#vfeed-${ci}`);
    const vTrack = panel.querySelector(`#vtrack-${ci}`);
    const cardH  = vFeed.getBoundingClientRect().height || vpH;

    arts.forEach((art, ai) => {
      const card = buildCard(art, cardH, m, cat, ai);
      card.id = `article-${art.article_id}`;
      vTrack.appendChild(card);
    });

    panels.push({ pRow, vFeed, vTrack, articles: arts, artIdx: 0 });
    buildPRow(ci);
  });

  hTrack.style.transition = 'none';
  hTrack.style.transform = 'translateX(0)';
  if (panels.length) syncV(0, false);
}

function buildCard(art, h, m, cat, articleIndex) {
  const src = art.sources && art.sources[0];
  // Direct PDF link with #page=N - respected by all modern browser PDF viewers
  // when the file is opened via a link click (Chrome, Firefox, Safari, Edge).
  // Falls back to the Telegram source URL if no PDF is available.
  const href = (src && src.pdf_filename)
    ? ('pdfs/' + src.pdf_filename + '#page=' + (src.page || 1))
    : ((src && src.telegram_url) || '#');
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.articleId = art.article_id;
  card.style.height = h + 'px';
  card.style.setProperty('--cc', m.color);
  card.innerHTML = `
    <div class="card-content">
      <div class="card-toprow">
        <div class="cat-pill">
          <div class="pill-icon"><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="1" y="1" width="8" height="2" rx="0.6" fill="#888"/><rect x="1" y="4.5" width="5" height="1.5" rx="0.6" fill="#666"/><rect x="1" y="7" width="6" height="1.5" rx="0.6" fill="#666"/></svg></div>
          ${esc(cat.toUpperCase())}
        </div>
        <div class="card-date">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="2.5" width="11" height="9.5" rx="1.8" stroke="#555" stroke-width="1.2"/><path d="M4.5 1v3M8.5 1v3" stroke="#555" stroke-width="1.2" stroke-linecap="round"/><path d="M1 6h11" stroke="#555" stroke-width="1.2"/></svg>
          ${esc(DIGEST.date)}
        </div>
      </div>
      <div class="card-headline">${esc(art.headline)}</div>
      <div class="card-summary">${esc(art.summary)}</div>
      <div class="card-divider"></div>
      <div class="card-footer">
        ${src ? `<a class="src-chip" href="${href}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${esc(src.newspaper)}<span class="src-chip-sep">&middot;</span><span class="src-chip-pg">Pg ${src.page || 1}</span><span class="src-chip-ext"><svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M3.5 7.5L7.5 3.5M7.5 3.5H5M7.5 3.5V6" stroke="#555" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span></a>` : '<div></div>'}
        <div class="info-btn"><svg width="15" height="15" viewBox="0 0 15 15" fill="none"><circle cx="7.5" cy="7.5" r="6.5" stroke="#444" stroke-width="1.3"/><circle cx="7.5" cy="4.5" r="0.8" fill="#555"/><path d="M7.5 7v4" stroke="#555" stroke-width="1.5" stroke-linecap="round"/></svg></div>
      </div>
    </div>`;
  return card;
}

function buildPRow(ci) {
  const p = panels[ci], ai = p.artIdx;
  p.pRow.innerHTML = '';
  p.articles.forEach((_, i) => {
    const seg = document.createElement('div');
    seg.className = 'pseg' + (i < ai ? ' done' : i === ai ? ' active' : '');
    p.pRow.appendChild(seg);
  });
}

function syncV(ci, animated) {
  const p = panels[ci], h = p.vFeed.getBoundingClientRect().height;
  p.vTrack.style.transition = animated ? 'transform 0.35s cubic-bezier(0.4,0,0.2,1)' : 'none';
  p.vTrack.style.transform = `translateY(${-p.artIdx * h}px)`;
  buildPRow(ci);
}

// General-purpose jump: used by row taps, the Start button, and deep links.
function openReader(articleId, isDeepLink) {
  const ci = sortedCats.findIndex(cat => byCategory[cat].some(a => a.article_id === articleId));
  if (ci === -1) return;
  const ai = byCategory[sortedCats[ci]].findIndex(a => a.article_id === articleId);
  if (ai === -1) return;

  catIdx = ci;
  hTrack.style.transition = 'none';
  hTrack.style.transform = `translateX(${-ci * vpW}px)`;
  panels[ci].artIdx = ai;
  syncV(ci, false);

  showReader();
  history.replaceState(null, '', '#article-' + articleId);

  if (isDeepLink) {
    const card = document.getElementById('article-' + articleId);
    if (card) {
      card.classList.add('target-highlight');
      setTimeout(() => card.classList.remove('target-highlight'), 3000);
    }
  }
}

function closeReader() {
  showIndex();
  history.replaceState(null, '', window.location.pathname + window.location.search);
}

function goArt(d) {
  const p = panels[catIdx];
  if (!p) return;
  const n = Math.max(0, Math.min(p.artIdx + d, p.articles.length - 1));
  if (n === p.artIdx && d !== 0) return;
  p.artIdx = n; syncV(catIdx, true); dismiss();
}

function goCat(idx, animated = true) {
  idx = Math.max(0, Math.min(idx, sortedCats.length - 1));
  if (idx === catIdx && animated) return;
  const prev = catIdx; catIdx = idx;
  hTrack.style.transition = animated ? 'transform 0.38s cubic-bezier(0.4,0,0.2,1)' : 'none';
  hTrack.style.transform = `translateX(${-catIdx * vpW}px)`;
  if (animated && idx !== prev) {
    const m = CAT_META[sortedCats[idx]] || DEFAULT_META;
    catFlash.style.background = m.color + '18';
    cfIcon.textContent = m.icon; cfName.textContent = sortedCats[idx]; cfName.style.color = m.color;
    catFlash.classList.add('on'); setTimeout(() => catFlash.classList.remove('on'), 500);
  }
  dismiss();
}

let dismissed = false;
function dismiss() {
  if (dismissed) return; dismissed = true;
  hintUp.classList.remove('visible'); hintRight.classList.remove('visible');
  hintUp.classList.add('gone'); hintRight.classList.add('gone');
}

// Hints are scheduled once, the first time the reader ever opens (not on
// page load) — the parent #readerScreen sits at opacity:0 while inactive,
// so even if this timer fires while the index is showing, the hint stays
// invisible; it will simply appear next time the reader is open.
let hintsInitialized = false;
function initHintsOnce() {
  if (hintsInitialized) return;
  hintsInitialized = true;
  const KEY = 'dailyBriefHintSeen';
  try {
    if (!localStorage.getItem(KEY)) {
      localStorage.setItem(KEY, '1');
      setTimeout(() => { if (!dismissed) { hintUp.classList.add('visible'); hintRight.classList.add('visible'); } }, 2500);
    }
  } catch (e) { /* localStorage unavailable (e.g. private browsing) — skip hints */ }
}

backBtn.addEventListener('click', closeReader);

// ── Gestures — scoped to #outer, so they're automatically inert whenever
// the reader screen is inactive (pointer-events:none redirects hit-testing
// to the Index screen beneath it; no extra guard needed). ──────────────────
let tsX = 0, tsY = 0, tcX = 0, tcY = 0, axis = null, drag = false;
outer.addEventListener('touchstart', e => {
  tsX = e.touches[0].clientX; tsY = e.touches[0].clientY; tcX = 0; tcY = 0; axis = null; drag = true;
  hTrack.style.transition = 'none';
  const p = panels[catIdx]; if (p) p.vTrack.style.transition = 'none';
}, { passive: true });

outer.addEventListener('touchmove', e => {
  if (!drag) return;
  const dx = e.touches[0].clientX - tsX, dy = e.touches[0].clientY - tsY;
  tcX = dx; tcY = dy;
  if (!axis && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) axis = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v';
  if (!axis) return;
  e.preventDefault();
  if (axis === 'h') {
    const edge = (catIdx === 0 && dx > 0) || (catIdx === sortedCats.length - 1 && dx < 0);
    hTrack.style.transform = `translateX(${-catIdx * vpW + dx * (edge ? 0.14 : 1)}px)`;
  } else {
    const p = panels[catIdx], h = p.vFeed.getBoundingClientRect().height;
    const edge = (p.artIdx === 0 && dy > 0) || (p.artIdx === p.articles.length - 1 && dy < 0);
    p.vTrack.style.transform = `translateY(${-p.artIdx * h + dy * (edge ? 0.14 : 1)}px)`;
  }
}, { passive: false });

outer.addEventListener('touchend', () => {
  if (!drag) return; drag = false;
  if (axis === 'h') {
    const t = vpW * .2;
    if (tcX < -t) goCat(catIdx + 1);
    else if (tcX > t) goCat(catIdx - 1);
    else { hTrack.style.transition = 'transform 0.3s cubic-bezier(.4,0,.2,1)'; hTrack.style.transform = `translateX(${-catIdx * vpW}px)`; }
  } else if (axis === 'v') {
    const t = vpH * .2;
    if (tcY < -t) goArt(1);
    else if (tcY > t) goArt(-1);
    else { const p = panels[catIdx], h = p.vFeed.getBoundingClientRect().height; p.vTrack.style.transition = 'transform 0.3s cubic-bezier(.4,0,.2,1)'; p.vTrack.style.transform = `translateY(${-p.artIdx * h}px)`; }
  }
  axis = null;
}, { passive: true });

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (readerScreen.classList.contains('active')) { e.preventDefault(); closeReader(); }
    return;
  }
  if (!readerScreen.classList.contains('active')) return;
  if (e.key === 'ArrowDown' || e.key === ' ') { e.preventDefault(); goArt(1); }
  if (e.key === 'ArrowUp') { e.preventDefault(); goArt(-1); }
  if (e.key === 'ArrowRight') { e.preventDefault(); goCat(catIdx + 1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); goCat(catIdx - 1); }
});

let wl = false;
outer.addEventListener('wheel', e => {
  e.preventDefault(); if (wl) return; wl = true;
  Math.abs(e.deltaX) > Math.abs(e.deltaY) ? goCat(catIdx + (e.deltaX > 0 ? 1 : -1)) : goArt(e.deltaY > 0 ? 1 : -1);
  setTimeout(() => wl = false, 500);
}, { passive: false });

window.addEventListener('resize', () => {
  vpW = outer.offsetWidth; vpH = outer.offsetHeight;
  hTrack.style.transition = 'none';
  hTrack.style.transform = `translateX(${-catIdx * vpW}px)`;
  panels.forEach(p => {
    const h = p.vFeed.getBoundingClientRect().height;
    p.vTrack.querySelectorAll('.card').forEach(c => c.style.height = h + 'px');
    p.vTrack.style.transition = 'none';
    p.vTrack.style.transform = `translateY(${-p.artIdx * h}px)`;
  });
});

// ── Init ──────────────────────────────────────────────────────────────────
// No hash → show the Index immediately. A #article-<id> hash (from a push
// notification) → skip the Index entirely and jump straight into the
// Reader once layout has settled (200ms, same as the original deep-link
// timing) so card heights are measured correctly before the jump.
function init() {
  buildIndex();
  buildAllReaderPanels();

  const hash  = window.location.hash;
  const rawId = hash.startsWith('#article-') ? hash.slice(9) : (hash ? hash.slice(1) : '');
  const target = rawId && DIGEST.articles.find(a => a.article_id === rawId);

  if (target) {
    setTimeout(() => openReader(target.article_id, true), 200);
  } else {
    showIndex();
  }
}

init();
</script>
</body>
</html>
'''


def generate_html(data: dict) -> str:
    date_str        = data.get("date", "Today")
    articles        = data.get("articles", [])
    newspapers      = data.get("newspapers", [])
    total_articles  = data.get("total_articles", len(articles))

    # Add article IDs to the digest for notify_scheduler.py's deep links.
    for article in articles:
        article['article_id'] = generate_article_id(article)

    digest_payload = {
        "date":           date_str,
        "articles":       articles,
        "newspapers":     newspapers,
        "total_articles": total_articles,
    }

    html = PAGE_TEMPLATE
    html = html.replace("%%DATE_STR%%", date_str)
    html = html.replace("%%FAVICON%%", FAVICON_SVG)
    html = html.replace("%%CAT_META_JSON%%", json.dumps(CATEGORY_META, ensure_ascii=False))
    html = html.replace("%%DIGEST_JSON%%", json.dumps(digest_payload, ensure_ascii=False))
    return html
