"""
generate_site.py
Dual-filter card site for GitHub Pages.

Category tabs and newspaper pills are INDEPENDENT toggles.
Cards shown = article category is active AND at least one source paper is active.
Both filters default to ALL selected; deselecting narrows results.
"""

import json
from pathlib import Path
from collections import defaultdict

CATEGORY_META = {
    "Politics":       {"color": "#e74c3c", "icon": "🏛"},
    "Economy":        {"color": "#f39c12", "icon": "📊"},
    "Business":       {"color": "#3498db", "icon": "💼"},
    "India":          {"color": "#e67e22", "icon": "🇮🇳"},
    "World":          {"color": "#9b59b6", "icon": "🌍"},
    "Sports":         {"color": "#1abc9c", "icon": "🏆"},
    "Science":        {"color": "#00cec9", "icon": "🔬"},
    "Technology":     {"color": "#6c5ce7", "icon": "💻"},
    "Health":         {"color": "#fd79a8", "icon": "🏥"},
    "Law":            {"color": "#d35400", "icon": "⚖️"},
    "Environment":    {"color": "#27ae60", "icon": "🌿"},
    "Education":      {"color": "#2980b9", "icon": "📚"},
    "Culture":        {"color": "#8e44ad", "icon": "🎭"},
    "Infrastructure": {"color": "#7f8c8d", "icon": "🏗"},
}

# Filled background color for each newspaper pill when active
PAPER_COLORS = {
    "Economic Times":     {"bg": "#c0392b", "fg": "#ffffff"},
    "Times of India":     {"bg": "#c0392b", "fg": "#ffffff"},
    "Mint":               {"bg": "#c9a000", "fg": "#111111"},
    "Financial Express":  {"bg": "#1a5276", "fg": "#ffffff"},
    "Deccan Herald":      {"bg": "#6c3483", "fg": "#ffffff"},
    "Business Standard":  {"bg": "#1e8449", "fg": "#ffffff"},
    "New Indian Express": {"bg": "#d35400", "fg": "#ffffff"},
}
PAPER_DEFAULT = {"bg": "#444444", "fg": "#ffffff"}

DEFAULT_META = {"color": "#636e72", "icon": "📰"}


def build_site(data: dict, output_dir: Path):
    (output_dir / "index.html").write_text(generate_html(data), encoding="utf-8")


def generate_html(data: dict) -> str:
    date_str = data.get("date", "Today")
    articles = data.get("articles", [])
    total    = len(articles)

    # Unique newspapers
    all_newspapers = sorted(set(
        src.get("newspaper", "")
        for art in articles
        for src in art.get("sources", [])
        if src.get("newspaper")
    ))

    # Group by category, sorted by count desc
    by_category = defaultdict(list)
    for art in articles:
        by_category[art.get("category", "India")].append(art)
    sorted_cats = sorted(by_category.keys(), key=lambda c: -len(by_category[c]))

    # ── Category tabs (filled when active) ───────────────────────────────────
    nav_tabs = ""
    for cat in sorted_cats:
        meta  = CATEGORY_META.get(cat, DEFAULT_META)
        count = len(by_category[cat])
        nav_tabs += f"""<button class="cat-tab active"
            data-cat="{cat}"
            onclick="toggleCat(this)"
            style="--cc:{meta['color']}">
            <span class="tab-icon">{meta['icon']}</span>
            <span class="tab-label">{cat}</span>
            <span class="tab-count">{count}</span>
        </button>"""

    # ── Newspaper pills (filled with brand color when active) ─────────────────
    paper_pills = ""
    for paper in all_newspapers:
        pc = PAPER_COLORS.get(paper, PAPER_DEFAULT)
        paper_pills += f"""<button class="paper-pill active"
            data-paper="{paper}"
            onclick="togglePaper(this)"
            style="--pb:{pc['bg']};--pf:{pc['fg']}">
            {paper}
        </button>"""

    # ── All cards in a single flat grid (no per-category sections) ───────────
    # Each card carries data-cat and data-papers for client-side filtering.
    all_cards = ""
    for j, art in enumerate(articles):
        headline    = art.get("headline", "")
        summary     = art.get("summary", "")
        sources     = art.get("sources", [])
        cat         = art.get("category", "India")
        meta        = CATEGORY_META.get(cat, DEFAULT_META)
        card_papers = list(dict.fromkeys(
            src.get("newspaper", "") for src in sources if src.get("newspaper")
        ))
        papers_attr = ",".join(card_papers)
        card_id     = f"c{abs(hash(headline + cat)) % 10**9}"

        source_links = ""
        if sources:
            source_links = '<div class="card-sources">'
            for src in sources:
                paper        = src.get("newspaper", "")
                page         = src.get("page", 1)
                pdf_filename = src.get("pdf_filename", "")
                telegram_url = src.get("telegram_url", "")
                href = f"pdfs/{pdf_filename}#page={page}" if pdf_filename else telegram_url
                if href:
                    source_links += f'<a class="source-link" href="{href}" target="_blank">📄 {paper} p.{page}</a>'
            source_links += "</div>"

        all_cards += f"""<article class="card"
            id="{card_id}"
            data-cat="{cat}"
            data-papers="{papers_attr}"
            style="animation-delay:{j * 0.03}s">
            <div class="card-accent" style="background:{meta['color']}"></div>
            <div class="card-body">
                <div class="card-cat-label" style="color:{meta['color']}">{meta['icon']} {cat}</div>
                <h3 class="card-headline">{headline}</h3>
                <p class="card-summary">{summary}</p>
                {source_links}
            </div>
            <button class="read-btn" onclick="toggleRead('{card_id}',this)" title="Mark as read">✓</button>
        </article>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Brief — {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;1,8..60,300&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0c0b0b;--surface:#161414;--surface2:#1e1b1b;
  --border:#272323;--text:#e0dbd5;--muted:#7a736c;--ink:#f5efe6;
}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:'Source Serif 4',Georgia,serif;min-height:100vh}}

/* ── Masthead ── */
.masthead{{background:var(--surface);border-bottom:1px solid var(--border);padding:24px 48px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:300}}
.logo{{font-family:'Playfair Display',serif;font-size:clamp(20px,3vw,34px);font-weight:900;color:var(--ink);letter-spacing:-0.02em}}
.logo em{{color:#c9a66b;font-style:normal}}
.masthead-right{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);line-height:1.8;letter-spacing:0.06em}}

/* ── Stats ── */
.stats-bar{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 48px;display:flex;gap:32px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted);letter-spacing:0.1em;text-transform:uppercase;flex-wrap:wrap}}
.stats-bar b{{color:#c9a66b;font-weight:500}}

/* ── Search ── */
.search-bar{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 48px;display:flex;align-items:center;gap:12px}}
.search-wrap{{position:relative;flex:1;max-width:480px}}
.search-icon{{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:13px;pointer-events:none}}
.search-input{{width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:8px 34px 8px 36px;color:var(--ink);font-family:'Source Serif 4',serif;font-size:13px;outline:none;transition:border-color 0.2s}}
.search-input::placeholder{{color:var(--muted)}}
.search-input:focus{{border-color:#c9a66b}}
.search-clear{{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px;display:none}}
.search-label{{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted);letter-spacing:0.08em;white-space:nowrap}}

/* ── Category tabs — FILLED background when active ── */
.cat-bar{{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:10px 48px;display:flex;gap:6px;overflow-x:auto;
  scrollbar-width:none;position:sticky;top:73px;z-index:200
}}
.cat-bar::-webkit-scrollbar{{display:none}}
.cat-bar-label{{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--muted);letter-spacing:0.15em;text-transform:uppercase;white-space:nowrap;align-self:center;flex-shrink:0;margin-right:4px}}

.cat-tab{{
  display:inline-flex;align-items:center;gap:5px;
  padding:6px 13px;border-radius:20px;
  border:1.5px solid var(--border);
  background:var(--surface2);
  color:var(--muted);
  font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:500;
  letter-spacing:0.1em;text-transform:uppercase;
  cursor:pointer;white-space:nowrap;flex-shrink:0;
  transition:background 0.15s,border-color 0.15s,color 0.15s;
}}
.cat-tab .tab-icon{{font-size:11px;line-height:1}}
.cat-tab .tab-count{{
  font-size:8px;padding:1px 5px;border-radius:8px;
  background:rgba(255,255,255,0.08);
}}
/* Active = filled with category color */
.cat-tab.active{{
  background:var(--cc);
  border-color:var(--cc);
  color:#fff;
}}
.cat-tab.active .tab-count{{background:rgba(0,0,0,0.2);color:rgba(255,255,255,0.85)}}
.reset-cats{{font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:0.08em;padding:6px 12px;border-radius:20px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;white-space:nowrap;flex-shrink:0;transition:color 0.15s,border-color 0.15s}}
.reset-cats:hover{{color:var(--ink);border-color:var(--muted)}}

/* ── Newspaper pills — FILLED with brand color when active ── */
.paper-bar{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 48px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.paper-bar-label{{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--muted);letter-spacing:0.15em;text-transform:uppercase;white-space:nowrap;flex-shrink:0;margin-right:4px}}
.paper-pill{{
  display:inline-block;padding:5px 12px;border-radius:20px;
  border:1.5px solid var(--border);
  background:var(--surface2);color:var(--muted);
  font-family:'JetBrains Mono',monospace;font-size:9px;
  letter-spacing:0.06em;text-transform:uppercase;
  cursor:pointer;white-space:nowrap;flex-shrink:0;
  transition:background 0.15s,border-color 0.15s,color 0.15s;
}}
/* Active = filled with brand color */
.paper-pill.active{{
  background:var(--pb);
  border-color:var(--pb);
  color:var(--pf);
}}
.reset-papers{{font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:0.08em;padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;flex-shrink:0;transition:color 0.15s,border-color 0.15s}}
.reset-papers:hover{{color:var(--ink);border-color:var(--muted)}}

/* ── Empty state ── */
.empty-state{{padding:80px 48px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);letter-spacing:0.12em;line-height:2.2;display:none}}

/* ── Cards grid ── */
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1px;background:var(--border);margin-top:1px}}
.card{{background:var(--surface);display:flex;align-items:stretch;opacity:0;animation:fadeIn 0.35s ease forwards;transition:background 0.15s;position:relative;overflow:hidden}}
.card:hover{{background:var(--surface2)}}
.card.is-read{{opacity:0.32;animation:none}}
.card.is-read .card-headline{{text-decoration:line-through;color:var(--muted)}}
.card.hidden{{display:none!important}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(7px)}}to{{opacity:1;transform:translateY(0)}}}}

/* Left accent strip */
.card-accent{{width:3px;flex-shrink:0}}
.card-body{{flex:1;padding:22px 26px;display:flex;flex-direction:column;gap:10px;min-width:0}}
.card-cat-label{{font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:0.18em;text-transform:uppercase;font-weight:500}}
.card-headline{{font-family:'Playfair Display',serif;font-size:16px;font-weight:700;color:var(--ink);line-height:1.4;letter-spacing:-0.01em}}
.card-summary{{font-size:13.5px;font-weight:300;color:#a09890;line-height:1.75;font-style:italic;flex:1}}
.card-sources{{display:flex;flex-wrap:wrap;gap:6px;padding-top:8px;border-top:1px solid var(--border);margin-top:2px}}
.source-link{{font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:0.08em;color:var(--muted);text-decoration:none;padding:3px 8px;border:1px solid var(--border);border-radius:3px;transition:color 0.15s,border-color 0.15s,background 0.15s;white-space:nowrap}}
.source-link:hover{{color:var(--ink);border-color:var(--muted);background:var(--surface2)}}

.read-btn{{position:absolute;top:12px;right:12px;background:none;border:1px solid var(--border);border-radius:4px;color:var(--muted);font-size:10px;padding:2px 6px;cursor:pointer;font-family:'JetBrains Mono',monospace;transition:all 0.15s;opacity:0}}
.card:hover .read-btn{{opacity:1}}
.card.is-read .read-btn{{opacity:1;background:rgba(201,166,107,0.15);border-color:rgba(201,166,107,0.4);color:#c9a66b}}

/* ── Footer ── */
.footer{{padding:32px 48px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;margin-top:48px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted);letter-spacing:0.08em;flex-wrap:wrap;gap:8px}}

@media(max-width:700px){{
  .masthead,.stats-bar,.search-bar,.cat-bar,.paper-bar{{padding-left:20px;padding-right:20px}}
  .masthead{{flex-direction:column;align-items:flex-start;gap:6px}}
  .cat-bar{{top:88px}}
  .cards-grid{{grid-template-columns:1fr}}
  .card-body{{padding:18px 20px}}
  .footer{{padding:24px 20px;flex-direction:column;text-align:center}}
}}
</style>
</head>
<body>

<header class="masthead">
  <div class="logo">The Daily <em>Brief</em></div>
  <div class="masthead-right">{date_str}<br>Bengaluru Edition</div>
</header>

<div class="stats-bar">
  <div><b id="vis-count">{total}</b> articles</div>
  <div><b>{len(sorted_cats)}</b> categories</div>
  <div><b id="read-count">0</b> read</div>
  <div>duplicates merged · AI summarised</div>
</div>

<div class="search-bar">
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-input" id="searchInput" type="text"
      placeholder="Search headlines and summaries…"
      oninput="onSearch(this.value)">
    <button class="search-clear" id="searchClear" onclick="clearSearch()">✕</button>
  </div>
  <span class="search-label" id="searchLabel"></span>
</div>

<!-- Category tabs — independent toggle, filled when active -->
<div class="cat-bar">
  <span class="cat-bar-label">Category</span>
  {nav_tabs}
  <button class="reset-cats" onclick="resetCats()">All</button>
</div>

<!-- Newspaper pills — independent toggle, filled with brand color when active -->
<div class="paper-bar">
  <span class="paper-bar-label">Newspaper</span>
  {paper_pills}
  <button class="reset-papers" onclick="resetPapers()">All</button>
</div>

<div class="empty-state" id="emptyState">
  No articles match the selected filters.<br>
  Try selecting more categories or newspapers.
</div>

<main>
  <div class="cards-grid" id="cardsGrid">
    {all_cards}
  </div>
</main>

<footer class="footer">
  <div>THE DAILY BRIEF · BENGALURU · GITHUB ACTIONS + GEMINI</div>
  <div>AI summaries — verify with source before acting on news</div>
</footer>

<script>
const RKEY = 'brief-read-{date_str}'.replace(/ /g, '-');
let readSet      = new Set(JSON.parse(localStorage.getItem(RKEY) || '[]'));
let activeCats   = new Set([...document.querySelectorAll('.cat-tab')].map(t => t.dataset.cat));
let activePapers = new Set([...document.querySelectorAll('.paper-pill')].map(p => p.dataset.paper));
let searchQ      = '';

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {{
  readSet.forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.classList.add('is-read');
  }});
  updateReadCount();
  applyFilters();
}}

// ── Read state ────────────────────────────────────────────────────────────────
function toggleRead(id, btn) {{
  const el = document.getElementById(id);
  if (!el) return;
  if (readSet.has(id)) {{ readSet.delete(id); el.classList.remove('is-read'); }}
  else               {{ readSet.add(id);    el.classList.add('is-read');    }}
  localStorage.setItem(RKEY, JSON.stringify([...readSet]));
  updateReadCount();
}}
function updateReadCount() {{
  document.getElementById('read-count').textContent = readSet.size;
}}

// ── Category toggle ───────────────────────────────────────────────────────────
function toggleCat(btn) {{
  const cat = btn.dataset.cat;
  if (activeCats.has(cat)) {{ activeCats.delete(cat); btn.classList.remove('active'); }}
  else                     {{ activeCats.add(cat);    btn.classList.add('active');    }}
  applyFilters();
}}
function resetCats() {{
  document.querySelectorAll('.cat-tab').forEach(t => {{ t.classList.add('active'); activeCats.add(t.dataset.cat); }});
  applyFilters();
}}

// ── Newspaper toggle ──────────────────────────────────────────────────────────
function togglePaper(btn) {{
  const p = btn.dataset.paper;
  if (activePapers.has(p)) {{ activePapers.delete(p); btn.classList.remove('active'); }}
  else                     {{ activePapers.add(p);    btn.classList.add('active');    }}
  applyFilters();
}}
function resetPapers() {{
  document.querySelectorAll('.paper-pill').forEach(p => {{ p.classList.add('active'); activePapers.add(p.dataset.paper); }});
  applyFilters();
}}

// ── Search ────────────────────────────────────────────────────────────────────
function onSearch(val) {{
  searchQ = val.trim().toLowerCase();
  document.getElementById('searchClear').style.display = searchQ ? 'block' : 'none';
  applyFilters();
}}
function clearSearch() {{
  searchQ = '';
  document.getElementById('searchInput').value = '';
  document.getElementById('searchClear').style.display = 'none';
  applyFilters();
}}

// ── Core filter — intersection of ALL three ───────────────────────────────────
// Card is visible when:
//   1. Its category is in activeCats
//   2. At least one of its source papers is in activePapers (or it has no paper tags)
//   3. Headline/summary match searchQ (if non-empty)
function applyFilters() {{
  let visible = 0;
  document.querySelectorAll('#cardsGrid .card').forEach(card => {{
    const catOk = activeCats.has(card.dataset.cat);

    const papers = (card.dataset.papers || '').split(',').filter(Boolean);
    const paperOk = papers.length === 0 || papers.some(p => activePapers.has(p));

    let searchOk = true;
    if (searchQ) {{
      const h = (card.querySelector('.card-headline')?.textContent || '').toLowerCase();
      const s = (card.querySelector('.card-summary')?.textContent  || '').toLowerCase();
      searchOk = h.includes(searchQ) || s.includes(searchQ);
    }}

    const show = catOk && paperOk && searchOk;
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  }});

  document.getElementById('vis-count').textContent = visible;
  document.getElementById('emptyState').style.display = visible === 0 ? 'block' : 'none';
  document.getElementById('searchLabel').textContent = searchQ
    ? visible + ' result' + (visible !== 1 ? 's' : '') : '';
}}

init();
</script>
</body>
</html>"""


if __name__ == "__main__":
    sample = {
        "date": "27 February 2026",
        "articles": [
            {"headline": "Bengaluru Metro Phase 3 gets cabinet nod", "summary": "The Union Cabinet approved Phase 3 of Namma Metro adding 44.65 km across six new corridors. Estimated at Rs 15,611 crore, commissioning expected by December 2027.", "category": "Infrastructure",
              "sources": [{"newspaper": "Times of India", "pdf_filename": "TOI.pdf", "page": 1, "telegram_url": ""}, {"newspaper": "Deccan Herald", "pdf_filename": "DH.pdf", "page": 1, "telegram_url": ""}]},
            {"headline": "RBI holds repo rate at 6.25%", "summary": "The Reserve Bank kept the repo rate at 6.25% citing food inflation. The MPC voted 4-2; markets expect a cut in April.", "category": "Economy",
              "sources": [{"newspaper": "Economic Times", "pdf_filename": "ET.pdf", "page": 1, "telegram_url": ""}, {"newspaper": "Mint", "pdf_filename": "Mint.pdf", "page": 1, "telegram_url": ""}]},
            {"headline": "Karnataka tops ease of doing business", "summary": "Karnataka retained DPIIT top rank for the second consecutive year. Rs 2.3 lakh crore pledged at Invest Karnataka 2025.", "category": "Business",
              "sources": [{"newspaper": "Times of India", "pdf_filename": "TOI.pdf", "page": 5, "telegram_url": ""}]},
            {"headline": "SEBI tightens F&O trading rules", "summary": "SEBI raised minimum contract sizes and mandated risk disclosures for F&O trades from April 1.", "category": "Economy",
              "sources": [{"newspaper": "Mint", "pdf_filename": "Mint.pdf", "page": 2, "telegram_url": ""}, {"newspaper": "Economic Times", "pdf_filename": "ET.pdf", "page": 3, "telegram_url": ""}]},
            {"headline": "India wins SA test series 3-1", "summary": "India clinched the series with an innings win in Johannesburg. Jaiswal was player of the series.", "category": "Sports",
              "sources": [{"newspaper": "Times of India", "pdf_filename": "TOI.pdf", "page": 17, "telegram_url": ""}]},
            {"headline": "HAL delivers 12 Tejas Mk1A jets to IAF", "summary": "HAL handed over 12 Tejas Mk1A jets at Bengaluru. HAL has a total order of 83 aircraft.", "category": "India",
              "sources": [{"newspaper": "Deccan Herald", "pdf_filename": "DH.pdf", "page": 4, "telegram_url": ""}, {"newspaper": "New Indian Express", "pdf_filename": "NIE.pdf", "page": 2, "telegram_url": ""}]},
        ]
    }
    from pathlib import Path
    Path("docs").mkdir(exist_ok=True)
    build_site(sample, Path("docs"))
    print("Preview at docs/index.html")
