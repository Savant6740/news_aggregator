"""
generate_site.py - FIXED with ARTICLE IDs for deep linking
Swipe-based TikTok-style daily brief + GitHub Pages deep links.
"""
import json
import hashlib
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

def generate_html(data: dict) -> str:
    date_str = data.get("date", "Today")
    articles = data.get("articles", [])
    
    # ✅ ADD ARTICLE IDs TO DIGEST for notify_scheduler.py
    for article in articles:
        article['article_id'] = generate_article_id(article)

    digest_json  = json.dumps({"date": date_str, "articles": articles}, ensure_ascii=False)
    cat_meta_json = json.dumps(CATEGORY_META, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Daily Brief — {date_str}</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON_SVG}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
html, body {{
  width: 100%; height: 100%;
  overflow: hidden;
  font-family: 'Inter', -apple-system, sans-serif;
  background: #0c0c0c; color: #fff; touch-action: none;
}}
.outer {{ position: fixed; inset: 0; overflow: hidden; }}
.h-track {{ display: flex; height: 100%; will-change: transform; }}
.cat-panel {{ flex-shrink:0; width:100vw; height:100%; display:flex; flex-direction:column; overflow:hidden; }}
.progress-row {{ flex-shrink:0; display:flex; gap:4px; padding:14px 16px 10px; background:#0c0c0c; position:relative; z-index:5; overflow:visible; }}
.progress-row::after {{ content:''; position:absolute; top:0; left:50%; transform:translateX(-50%); width:80%; height:120px; background:radial-gradient(ellipse at top,color-mix(in srgb,var(--cc) 30%,transparent) 0%,transparent 70%); pointer-events:none; z-index:-1; }}
.pseg {{ flex:1; height:2px; border-radius:1px; background:rgba(255,255,255,0.12); position:relative; overflow:hidden; }}
.pseg::after {{ content:''; position:absolute; inset:0; background:var(--cc,#e8334a); transform:scaleX(0); transform-origin:left; transition:transform 0.25s ease; }}
.pseg.done::after, .pseg.active::after {{ transform:scaleX(1); }}
.v-feed {{ flex:1; overflow:hidden; position:relative; clip-path:inset(0); }}
.v-track {{ display:flex; flex-direction:column; will-change:transform; }}
.card {{ 
  width:100%; flex-shrink:0; background:#0c0c0c; display:flex; flex-direction:column; 
  overflow:hidden; position:relative; 
  scroll-margin-top: 80px;
}}
.card.target-highlight {{
  background: linear-gradient(135deg, #fff3cd22 0%, #ffeaa722 100%) !important;
  box-shadow: 0 0 30px rgba(255, 193, 7, 0.4);
  border: 2px solid #f39c12;
  animation: pulse-highlight 2s ease-in-out;
}}
@keyframes pulse-highlight {{
  0%, 100% {{ box-shadow: 0 0 30px rgba(255, 193, 7, 0.4); }}
  50% {{ box-shadow: 0 0 50px rgba(255, 193, 7, 0.6); }}
}}
.card-content {{ flex:1; display:flex; flex-direction:column; padding:36px 20px 22px; min-height:0; position:relative; z-index:1; }}
.card-toprow {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:28px; flex-shrink:0; }}
.cat-pill {{ display:inline-flex; align-items:center; gap:7px; background:#1c1c1e; border-radius:8px; padding:7px 12px 7px 10px; font-size:11.5px; font-weight:700; letter-spacing:0.07em; color:#d0d0d0; text-transform:uppercase; line-height:1; }}
.pill-icon {{ width:16px; height:16px; background:#2e2e30; border-radius:3px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.pill-icon svg {{ display:block; }}
.card-date {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:500; color:#666; letter-spacing:0.01em; }}
.card-headline {{ font-size:28px; font-weight:800; line-height:1.18; color:#fff; letter-spacing:-0.03em; margin-bottom:20px; flex-shrink:0; }}
.card-summary {{ font-size:15.5px; font-weight:400; line-height:1.62; color:#6b6b6b; flex:1; overflow:hidden; display:-webkit-box; -webkit-line-clamp:7; -webkit-box-orient:vertical; }}
.card-divider {{ height:1px; background:#1e1e1e; margin:20px 0 16px; flex-shrink:0; }}
.card-footer {{ display:flex; align-items:center; justify-content:space-between; flex-shrink:0; }}
.src-chip {{ display:inline-flex; align-items:center; gap:6px; background:#181818; border:1px solid #282828; border-radius:9px; padding:8px 13px; font-size:12.5px; font-weight:600; color:#c0c0c0; text-decoration:none; letter-spacing:0.005em; line-height:1; }}
.src-chip-sep {{ color:#3a3a3a; font-weight:400; }}
.src-chip-pg {{ color:#555; font-weight:500; }}
.src-chip-ext {{ margin-left:2px; }}
.src-chip-ext svg {{ display:block; }}
.info-btn {{ width:36px; height:36px; border-radius:50%; border:1.5px solid #252525; background:#141414; display:flex; align-items:center; justify-content:center; color:#555; cursor:pointer; flex-shrink:0; }}
.cat-flash {{ position:fixed; inset:0; z-index:600; pointer-events:none; opacity:0; transition:opacity 0.12s; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:8px; }}
.cat-flash.on {{ opacity:1; }}
.cf-icon {{ font-size:34px; }}
.cf-name {{ font-size:22px; font-weight:900; letter-spacing:-0.03em; text-transform:uppercase; }}
.hint {{ position:fixed; display:flex; flex-direction:column; align-items:center; gap:5px; pointer-events:none; z-index:400; opacity:0; transition:opacity 0.6s ease; }}
.hint.visible {{ opacity:1; }}
.hint.gone {{ opacity:0 !important; transition:opacity 0.4s; }}
.hint-pill {{ font-size:10px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:rgba(255,255,255,0.55); background:rgba(255,255,255,0.07); backdrop-filter:blur(10px); padding:5px 13px; border-radius:100px; border:1px solid rgba(255,255,255,0.09); }}
.hint-arr {{ font-size:16px; color:rgba(255,255,255,0.4); }}
.h-up {{ bottom:28px; left:50%; transform:translateX(-50%); animation:bUp 2s ease-in-out infinite; }}
.h-right {{ top:50%; right:14px; transform:translateY(-50%); animation:bRight 2s ease-in-out infinite 0.6s; }}
@keyframes bUp {{ 0%,100% {{ bottom:28px; opacity:.65; }} 50% {{ bottom:36px; opacity:1; }} }}
@keyframes bRight {{ 0%,100% {{ right:14px; opacity:.65; }} 50% {{ right:6px; opacity:1; }} }}
</style>
</head>
<body>
<div class="outer" id="outer"><div class="h-track" id="hTrack"></div></div>
<div class="hint h-up" id="hintUp"><span class="hint-arr">↑</span><span class="hint-pill">Swipe up</span></div>
<div class="hint h-right" id="hintRight"><span class="hint-arr">→</span><span class="hint-pill">Next category</span></div>
<div class="cat-flash" id="catFlash"><span class="cf-icon" id="cfIcon"></span><span class="cf-name" id="cfName"></span></div>

<script>
const DIGEST   = {digest_json};
const CAT_META = {cat_meta_json};

// FIXED: Pre-build data structures IMMEDIATELY for deep linking
const allArts = [...DIGEST.articles].sort((a,b)=>(b.importance||0)-(a.importance||0));
const byCategory = {{}};
for (const art of allArts) {{
  const c = art.category||"India";
  if (!byCategory[c]) byCategory[c]=[];
  byCategory[c].push(art);
}}
const sortedCats = Object.keys(byCategory).sort(
  (a,b)=>(byCategory[b][0].importance||0)-(byCategory[a][0].importance||0)
);

// FIXED DEEP LINK HANDLER - Runs IMMEDIATELY
let deepLinkTarget = null;
function handleDeepLink() {{
  const hash = window.location.hash;
  if (!hash || !sortedCats.length) return;
  
  const cleanHash = hash.startsWith('#article-') ? hash.slice(9) : hash.slice(1);
  const targetArticle = DIGEST.articles.find(art => art.article_id === cleanHash);
  
  if (targetArticle) {{
    deepLinkTarget = {{article: targetArticle, hash: cleanHash}};
  }}
}}
handleDeepLink();

let catIdx=0,vpW=0,vpH=0;
const panels=[];
const outer=document.getElementById('outer');
const hTrack=document.getElementById('hTrack');
const hintUp=document.getElementById('hintUp');
const hintRight=document.getElementById('hintRight');
const catFlash=document.getElementById('catFlash');
const cfIcon=document.getElementById('cfIcon');
const cfName=document.getElementById('cfName');

function buildAll() {{
  vpW=outer.offsetWidth; vpH=outer.offsetHeight;
  hTrack.innerHTML=''; panels.length=0;
  sortedCats.forEach((cat,ci)=>{{
    const m=CAT_META[cat]||{{color:"#e8334a",icon:"📰"}};
    const arts=byCategory[cat];
    const panel=document.createElement('div');
    panel.className='cat-panel';
    panel.id=`cat-panel-${{ci}}`;
    panel.style.setProperty('--cc',m.color);
    panel.innerHTML=`<div class="progress-row" id="prow-${{ci}}" style="--cc:${{m.color}}"></div><div class="v-feed" id="vfeed-${{ci}}"><div class="v-track" id="vtrack-${{ci}}"></div></div>`;
    hTrack.appendChild(panel);
    const pRow=panel.querySelector(`#prow-${{ci}}`);
    const vFeed=panel.querySelector(`#vfeed-${{ci}}`);
    const vTrack=panel.querySelector(`#vtrack-${{ci}}`);
    const cardH=vFeed.getBoundingClientRect().height||vpH;
    
    arts.forEach((art,ai)=>{{
      const card = buildCard(art, cardH, m, cat, ai);
      card.id = `article-${{art.article_id}}`;
      card.dataset.articleId = art.article_id;
      vTrack.appendChild(card);
    }});
    
    panels.push({{pRow,vFeed,vTrack,articles:arts,artIdx:0}});
    buildPRow(ci);
  }});
  
  hTrack.style.transition='none';
  hTrack.style.transform='translateX(0)';
  syncV(0,false);
  
  // FIXED: Apply deep link after build
  if (deepLinkTarget) {{
    setTimeout(() => applyDeepLink(deepLinkTarget), 100);
  }}
}}

function buildCard(art,h,m,cat,articleIndex) {{
  const src=art.sources?.[0];
  const href=src?.pdf_filename?`pdfs/${{src.pdf_filename}}#page=${{src.page}}`:(src?.telegram_url||'#');
  const card=document.createElement('div');
  card.className='card';
  card.dataset.articleId = art.article_id;
  card.style.height=h+'px';
  card.style.setProperty('--cc',m.color);
  card.innerHTML=`
    <div class="card-content">
      <div class="card-toprow">
        <div class="cat-pill">
          <div class="pill-icon"><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="1" y="1" width="8" height="2" rx="0.6" fill="#888"/><rect x="1" y="4.5" width="5" height="1.5" rx="0.6" fill="#666"/><rect x="1" y="7" width="6" height="1.5" rx="0.6" fill="#666"/></svg></div>
          ${{cat.toUpperCase()}}
        </div>
        <div class="card-date">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="2.5" width="11" height="9.5" rx="1.8" stroke="#555" stroke-width="1.2"/><path d="M4.5 1v3M8.5 1v3" stroke="#555" stroke-width="1.2" stroke-linecap="round"/><path d="M1 6h11" stroke="#555" stroke-width="1.2"/></svg>
          ${{DIGEST.date}}
        </div>
      </div>
      <div class="card-headline">${{art.headline}}</div>
      <div class="card-summary">${{art.summary}}</div>
      <div class="card-divider"></div>
      <div class="card-footer">
        ${{src?`<a class="src-chip" href="${{href}}" target="_blank" onclick="event.stopPropagation()">${{src.newspaper}}<span class="src-chip-sep">&middot;</span><span class="src-chip-pg">Pg ${{src.page}}</span><span class="src-chip-ext"><svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M3.5 7.5L7.5 3.5M7.5 3.5H5M7.5 3.5V6" stroke="#555" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></span></a>`:'<div></div>'}}
        <div class="info-btn"><svg width="15" height="15" viewBox="0 0 15 15" fill="none"><circle cx="7.5" cy="7.5" r="6.5" stroke="#444" stroke-width="1.3"/><circle cx="7.5" cy="4.5" r="0.8" fill="#555"/><path d="M7.5 7v4" stroke="#555" stroke-width="1.5" stroke-linecap="round"/></svg></div>
      </div>
    </div>`;
  return card;
}}

function buildPRow(ci) {{
  const p=panels[ci],ai=p.artIdx;
  p.pRow.innerHTML='';
  p.articles.forEach((_,i)=>{{
    const seg=document.createElement('div');
    seg.className='pseg'+(i<ai?' done':i===ai?' active':'');
    p.pRow.appendChild(seg);
  }});
}}

function syncV(ci,animated) {{
  const p=panels[ci],h=p.vFeed.getBoundingClientRect().height;
  p.vTrack.style.transition=animated?'transform 0.35s cubic-bezier(0.4,0,0.2,1)':'none
  ';
  p.vTrack.style.transform=`translateY(${{-p.artIdx*h}}px)`;
  buildPRow(ci);
}}

function applyDeepLink(target) {{
  const ci = sortedCats.findIndex(cat =>
    byCategory[cat].some(art => art.article_id === target.hash)
  );
  if (ci === -1) return;
  goCat(ci, false);
  const ai = byCategory[sortedCats[ci]].findIndex(art => art.article_id === target.hash);
  if (ai === -1) return;
  panels[ci].artIdx = ai;
  syncV(ci, false);
  const card = document.getElementById('article-' + target.hash);
  if (card) {{ card.classList.add('target-highlight'); setTimeout(() => card.classList.remove('target-highlight'), 3000); }}
}}

function goArt(d) {{
  const p=panels[catIdx];
  const n=Math.max(0,Math.min(p.artIdx+d,p.articles.length-1));
  if(n===p.artIdx&&d!==0)return;
  p.artIdx=n; syncV(catIdx,true); dismiss();
}}

function goCat(idx,animated=true) {{
  idx=Math.max(0,Math.min(idx,sortedCats.length-1));
  if(idx===catIdx&&animated)return;
  const prev=catIdx; catIdx=idx;
  hTrack.style.transition=animated?'transform 0.38s cubic-bezier(0.4,0,0.2,1)':'none';
  hTrack.style.transform=`translateX(${{-catIdx*vpW}}px)`;
  if(animated&&idx!==prev) {{
    const m=CAT_META[sortedCats[idx]]||{{color:"#e8334a",icon:"📰"}};
    catFlash.style.background=m.color+'18';
    cfIcon.textContent=m.icon; cfName.textContent=sortedCats[idx]; cfName.style.color=m.color;
    catFlash.classList.add('on'); setTimeout(()=>catFlash.classList.remove('on'),500);
  }}
  dismiss();
}}

let dismissed=false;
function dismiss() {{
  if(dismissed)return; dismissed=true;
  hintUp.classList.remove('visible'); hintRight.classList.remove('visible');
  hintUp.classList.add('gone'); hintRight.classList.add('gone');
}}

(function initHints() {{
  const KEY='dailyBriefHintSeen';
  if(!localStorage.getItem(KEY)) {{
    localStorage.setItem(KEY,'1');
    setTimeout(()=>{{ if(!dismissed){{ hintUp.classList.add('visible'); hintRight.classList.add('visible'); }} }},2500);
  }}
}})();

let tsX=0,tsY=0,tcX=0,tcY=0,axis=null,drag=false;
outer.addEventListener('touchstart',e=>{{ tsX=e.touches[0].clientX; tsY=e.touches[0].clientY; tcX=0; tcY=0; axis=null; drag=true; hTrack.style.transition='none'; const p=panels[catIdx]; if(p)p.vTrack.style.transition='none'; }},{{passive:true}});
outer.addEventListener('touchmove',e=>{{ if(!drag)return; const dx=e.touches[0].clientX-tsX,dy=e.touches[0].clientY-tsY; tcX=dx; tcY=dy; if(!axis&&(Math.abs(dx)>8||Math.abs(dy)>8))axis=Math.abs(dx)>Math.abs(dy)?'h':'v'; if(!axis)return; e.preventDefault(); if(axis==='h'){{ const edge=(catIdx===0&&dx>0)||(catIdx===sortedCats.length-1&&dx<0); hTrack.style.transform=`translateX(${{-catIdx*vpW+dx*(edge?.14:1)}}px)`; }}else{{ const p=panels[catIdx],h=p.vFeed.getBoundingClientRect().height; const edge=(p.artIdx===0&&dy>0)||(p.artIdx===p.articles.length-1&&dy<0); p.vTrack.style.transform=`translateY(${{-p.artIdx*h+dy*(edge?.14:1)}}px)`; }} }},{{passive:false}});
outer.addEventListener('touchend',()=>{{ if(!drag)return; drag=false; if(axis==='h'){{ const t=vpW*.2; if(tcX<-t)goCat(catIdx+1); else if(tcX>t)goCat(catIdx-1); else{{hTrack.style.transition='transform 0.3s cubic-bezier(.4,0,.2,1)';hTrack.style.transform=`translateX(${{-catIdx*vpW}}px)`;}} }}else if(axis==='v'){{ const t=vpH*.2; if(tcY<-t)goArt(1); else if(tcY>t)goArt(-1); else{{const p=panels[catIdx],h=p.vFeed.getBoundingClientRect().height;p.vTrack.style.transition='transform 0.3s cubic-bezier(.4,0,.2,1)';p.vTrack.style.transform=`translateY(${{-p.artIdx*h}}px)`;}} }} axis=null; }},{{passive:true}});
document.addEventListener('keydown',e=>{{ if(e.key==='ArrowDown'||e.key===' '){{e.preventDefault();goArt(1);}} if(e.key==='ArrowUp'){{e.preventDefault();goArt(-1);}} if(e.key==='ArrowRight'){{e.preventDefault();goCat(catIdx+1);}} if(e.key==='ArrowLeft'){{e.preventDefault();goCat(catIdx-1);}} }});
let wl=false;
outer.addEventListener('wheel',e=>{{ e.preventDefault();if(wl)return;wl=true; Math.abs(e.deltaX)>Math.abs(e.deltaY)?goCat(catIdx+(e.deltaX>0?1:-1)):goArt(e.deltaY>0?1:-1); setTimeout(()=>wl=false,500); }},{{passive:false}});
window.addEventListener('resize',()=>{{ vpW=outer.offsetWidth;vpH=outer.offsetHeight; hTrack.style.transition='none'; hTrack.style.transform=`translateX(${{-catIdx*vpW}}px)`; panels.forEach(p=>{{ const h=p.vFeed.getBoundingClientRect().height; p.vTrack.querySelectorAll('.card').forEach(c=>c.style.height=h+'px'); p.vTrack.style.transition='none'; p.vTrack.style.transform=`translateY(${{-p.artIdx*h}}px)`; }}); }});

buildAll();
</script>
</body>
</html>
'''
