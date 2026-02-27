"""
generate_site.py
Builds a category-first card-based static HTML site for GitHub Pages.
- Primary navigation: categories (not newspapers)
- Each card links to source PDF(s) for full article reading
- PDF links use #page=N to open directly at the right page
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

DEFAULT_META = {"color": "#636e72", "icon": "📰"}


def build_site(data: dict, output_dir: Path):
    html = generate_html(data)
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def generate_html(data: dict) -> str:
    date_str = data.get("date", "Today")
    articles  = data.get("articles", [])

    # Group articles by category
    by_category = defaultdict(list)
    for art in articles:
        cat = art.get("category", "India")
        by_category[cat].append(art)

    # Sort categories by article count descending
    sorted_cats = sorted(by_category.keys(), key=lambda c: -len(by_category[c]))

    total = len(articles)

    # ── Build nav tabs ────────────────────────────────────────────────────────
    nav_tabs = ""
    for i, cat in enumerate(sorted_cats):
        meta  = CATEGORY_META.get(cat, DEFAULT_META)
        count = len(by_category[cat])
        active = "active" if i == 0 else ""
        nav_tabs += f"""
        <button class="nav-tab {active}"
                onclick="showCategory({i})"
                data-index="{i}"
                style="--cat-color:{meta['color']}">
            <span class="tab-icon">{meta['icon']}</span>
            <span class="tab-label">{cat}</span>
            <span class="tab-count">{count}</span>
        </button>"""

    # ── Build category sections ───────────────────────────────────────────────
    sections = ""
    for i, cat in enumerate(sorted_cats):
        meta     = CATEGORY_META.get(cat, DEFAULT_META)
        cat_arts = by_category[cat]
        display  = "block" if i == 0 else "none"

        cards = ""
        for j, art in enumerate(cat_arts):
            headline = art.get("headline", "")
            summary  = art.get("summary", "")
            sources  = art.get("sources", [])

            # Build PDF source links
            source_links = ""
            if sources:
                source_links = '<div class="card-sources">'
                for src in sources:
                    paper        = src.get("newspaper", "Source")
                    page         = src.get("page", 1)
                    pdf_filename = src.get("pdf_filename", "")
                    telegram_url = src.get("telegram_url", "")
                    if pdf_filename:
                        # PDF is served from Pages artifact — direct link with page anchor
                        pdf_url = f"pdfs/{pdf_filename}#page={page}"
                        source_links += f'<a class="source-link" href="{pdf_url}" target="_blank" title="Open {paper} at page {page}">📄 {paper} p.{page}</a>'
                    elif telegram_url:
                        # Fallback: link to Telegram message
                        source_links += f'<a class="source-link" href="{telegram_url}" target="_blank" title="View in Telegram">📄 {paper} p.{page}</a>'
                source_links += "</div>"

            # Multi-source badge
            multi_badge = ""
            if len(sources) > 1:
                multi_badge = f'<span class="multi-badge" title="Covered by {len(sources)} newspapers">+{len(sources)} sources</span>'

            cards += f"""
            <article class="card" style="animation-delay:{j * 0.05}s">
                <div class="card-top">
                    <span class="card-category-dot" style="background:{meta['color']}"></span>
                    {multi_badge}
                </div>
                <h3 class="card-headline">{headline}</h3>
                <p class="card-summary">{summary}</p>
                {source_links}
            </article>"""

        sections += f"""
        <section class="cat-section" id="section-{i}" style="display:{display}">
            <div class="section-header" style="--cat-color:{meta['color']}">
                <span class="section-icon">{meta['icon']}</span>
                <h2 class="section-title">{cat}</h2>
                <span class="section-count">{len(cat_arts)} stories</span>
            </div>
            <div class="cards-grid">
                {cards}
            </div>
        </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Brief — {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;1,8..60,300&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:       #0c0b0b;
  --surface:  #161414;
  --surface2: #1e1b1b;
  --border:   #272323;
  --text:     #e0dbd5;
  --muted:    #7a736c;
  --ink:      #f5efe6;
}}

html {{ scroll-behavior: smooth; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'Source Serif 4', Georgia, serif;
  min-height: 100vh;
}}

/* ── Masthead ── */
.masthead {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 24px 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 200;
}}
.logo {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(20px, 3vw, 34px);
  font-weight: 900;
  color: var(--ink);
  letter-spacing: -0.02em;
}}
.logo em {{ color: #c9a66b; font-style: normal; }}
.masthead-right {{
  text-align: right;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
  letter-spacing: 0.06em;
}}

/* ── Stats bar ── */
.stats-bar {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 10px 48px;
  display: flex;
  gap: 32px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}}
.stats-bar span {{ color: #c9a66b; }}

/* ── Nav tabs ── */
.nav-bar {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 48px;
  display: flex;
  gap: 0;
  overflow-x: auto;
  scrollbar-width: none;
  position: sticky;
  top: 73px;
  z-index: 100;
}}
.nav-bar::-webkit-scrollbar {{ display: none; }}

.nav-tab {{
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 18px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.2s, border-color 0.2s;
  position: relative;
  top: 1px;
}}
.nav-tab:hover {{ color: var(--text); }}
.nav-tab.active {{
  color: var(--ink);
  border-bottom-color: var(--cat-color);
}}
.tab-icon {{ font-size: 13px; }}
.tab-count {{
  background: var(--surface2);
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 9px;
  color: var(--muted);
}}
.nav-tab.active .tab-count {{
  background: var(--cat-color);
  color: white;
}}

/* ── Section header ── */
.section-header {{
  padding: 40px 48px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--border);
}}
.section-icon {{ font-size: 32px; }}
.section-title {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(24px, 4vw, 44px);
  font-weight: 900;
  color: var(--cat-color);
  letter-spacing: -0.02em;
  flex: 1;
}}
.section-count {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}}

/* ── Cards grid ── */
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1px;
  background: var(--border);
  margin-top: 1px;
}}

.card {{
  background: var(--surface);
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  opacity: 0;
  animation: fadeIn 0.35s ease forwards;
  transition: background 0.15s;
  position: relative;
}}
.card:hover {{ background: var(--surface2); }}

@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

.card-top {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}}
.card-category-dot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.multi-badge {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 0.1em;
  color: #c9a66b;
  background: rgba(201,166,107,0.12);
  padding: 2px 7px;
  border-radius: 10px;
  border: 1px solid rgba(201,166,107,0.25);
}}

.card-headline {{
  font-family: 'Playfair Display', serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.4;
  letter-spacing: -0.01em;
}}

.card-summary {{
  font-size: 13.5px;
  font-weight: 300;
  color: #a09890;
  line-height: 1.75;
  font-style: italic;
  flex: 1;
}}

/* ── Source links (PDF cross-reference) ── */
.card-sources {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
}}
.source-link {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--muted);
  text-decoration: none;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
  white-space: nowrap;
}}
.source-link:hover {{
  color: var(--ink);
  border-color: var(--muted);
  background: var(--surface2);
}}

/* ── Footer ── */
.footer {{
  padding: 32px 48px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 48px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 0.08em;
}}

/* ── Responsive ── */
@media (max-width: 700px) {{
  .masthead  {{ padding: 16px 20px; flex-direction: column; align-items: flex-start; gap: 6px; }}
  .stats-bar {{ padding: 8px 20px; gap: 16px; flex-wrap: wrap; }}
  .nav-bar   {{ padding: 0 20px; top: 100px; }}
  .section-header {{ padding: 28px 20px 16px; }}
  .cards-grid {{ grid-template-columns: 1fr; }}
  .card {{ padding: 20px; }}
  .footer {{ padding: 24px 20px; flex-direction: column; gap: 8px; text-align: center; }}
}}
</style>
</head>
<body>


<header class="masthead">
  <div class="logo">The Daily <em>Brief</em></div>
  <div class="masthead-right">
    {date_str}<br>
    Bengaluru Edition
  </div>
</header>

<div class="stats-bar">
  <div><span>{total}</span> total articles</div>
  <div><span>{len(sorted_cats)}</span> categories</div>
  <div><span>7</span> newspapers</div>
  <div>duplicates merged · AI summarised</div>
</div>

<nav class="nav-bar">
  {nav_tabs}
</nav>

<main>
  {sections}
</main>

<footer class="footer">
  <div>THE DAILY BRIEF · BENGALURU · GITHUB ACTIONS + GEMINI</div>
  <div>AI summaries — verify with source before acting on news</div>
</footer>

<script>
  function showCategory(index) {{
    document.querySelectorAll('.cat-section').forEach((s, i) => {{
      s.style.display = i === index ? 'block' : 'none';
    }});
    document.querySelectorAll('.nav-tab').forEach((t, i) => {{
      t.classList.toggle('active', i === index);
    }});
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }}
</script>

</body>
</html>"""


if __name__ == "__main__":
    # Test render with sample data
    sample = {
        "date": "27 February 2026",
        "articles": [
            {
                "headline": "Bengaluru Metro Phase 3 gets cabinet nod",
                "summary": "The Union Cabinet approved Phase 3 of Namma Metro adding 44.65 km across six new corridors. The project is estimated at Rs 15,611 crore and targets the Electronic City IT corridor. Commissioning is expected by December 2027.",
                "category": "Infrastructure",
                "sources": [
                    {"newspaper": "Times of India", "pdf_file": "Bangalore_TOI_27-02-2026.pdf", "page": 3},
                    {"newspaper": "Deccan Herald",  "pdf_file": "DeccanHerald_Bengaluru_27-02-2026.pdf", "page": 1},
                ]
            },
            {
                "headline": "RBI holds repo rate at 6.25%",
                "summary": "The Reserve Bank of India kept the repo rate unchanged at 6.25% citing sticky food inflation. The MPC voted 4-2 in favour of a hold with two members pushing for a cut. Markets expect a cut in the April meeting.",
                "category": "Economy",
                "sources": [
                    {"newspaper": "Economic Times",   "pdf_file": "Bangalore_ET_27-02-2026.pdf", "page": 1},
                    {"newspaper": "Mint",             "pdf_file": "Bengaluru_Mint_27-02-2026.pdf", "page": 1},
                    {"newspaper": "Business Standard","pdf_file": "BS_Bengaluru_27-02-2026.pdf", "page": 1},
                ]
            },
            {
                "headline": "Karnataka tops ease of doing business rankings",
                "summary": "Karnataka ranked first in the DPIIT ease of doing business assessment for the second consecutive year. Bengaluru's single-window clearance and startup ecosystem were cited as key factors. The state attracted Rs 2.3 lakh crore in investment commitments at Invest Karnataka 2025.",
                "category": "Business",
                "sources": [
                    {"newspaper": "Financial Express","pdf_file": "FE_Bengaluru_27-02-2026.pdf", "page": 5},
                ]
            },
        ]
    }
    build_site(sample, Path("docs"))
    print("Test site generated at docs/index.html")
