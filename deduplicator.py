"""
deduplicator.py

Deduplicates articles across all newspapers in ONE single Gemini API call.
Improvements over previous version:
  1. Cross-category clustering — same story covered under different categories is now caught
  2. Better TF-IDF: headline triple-weighted, bigram+trigram ngrams, higher threshold (0.30)
  3. Named-entity overlap check as a second-pass filter (person names, org names, places)
  4. Headline normalisation strips newspaper prefix labels like "ET:", "HT:", "BSE:"
  5. Importance preserved from the highest-importance source in each cluster
"""

import json
import re
import logging
from collections import defaultdict

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

_PREFIX_RE = re.compile(
    r"^(?:ET|HT|TOI|IE|TH|FE|BS|BL|MINT|Mint|Hindu|Express|Times)[:\-]\s*",
    flags=re.IGNORECASE,
)

def _normalise_headline(h: str) -> str:
    h = _PREFIX_RE.sub("", h).strip()
    return re.sub(r"\s+", " ", h)


def _extract_entities(text: str) -> set:
    skip = {
        "The","This","That","These","Those","There","Their",
        "India","Indian","New","Delhi","Mumbai","Bengaluru",
        "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday",
        "January","February","March","April","May","June",
        "July","August","September","October","November","December",
    }
    tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
    return {t for t in tokens if t not in skip}


def _entity_overlap(a: dict, b: dict) -> float:
    text_a = f"{a['headline']} {a.get('summary','')}"
    text_b = f"{b['headline']} {b.get('summary','')}"
    ea, eb = _extract_entities(text_a), _extract_entities(text_b)
    if not ea or not eb:
        return 0.0
    return len(ea & eb) / len(ea | eb)


# ── Stage 1: cross-category TF-IDF + entity clustering ────────────────────────

def cosine_cluster(
    articles:        list,
    tfidf_threshold: float = 0.30,
    entity_boost:    float = 0.20,
) -> list:
    """
    Groups article indices by similarity across ALL categories.
    A pair is merged if:
      - cosine(TF-IDF) >= tfidf_threshold, OR
      - entity_overlap >= entity_boost AND cosine >= 0.18 (weak signal + entity match)
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [
            f"{_normalise_headline(a['headline'])} " * 3 + a.get("summary", "")
            for a in articles
        ]

        vec   = TfidfVectorizer(stop_words="english", ngram_range=(1, 3), min_df=1)
        tfidf = vec.fit_transform(texts)
        sim   = cosine_similarity(tfidf)

        n       = len(articles)
        visited = set()
        clusters = []

        for i in range(n):
            if i in visited:
                continue
            cluster = [i]
            visited.add(i)
            for j in range(i + 1, n):
                if j in visited:
                    continue
                s = float(sim[i, j])
                if s >= tfidf_threshold:
                    cluster.append(j)
                    visited.add(j)
                elif s >= 0.18 and _entity_overlap(articles[i], articles[j]) >= entity_boost:
                    cluster.append(j)
                    visited.add(j)
            clusters.append(cluster)

        return clusters

    except ImportError:
        log.warning("sklearn not available — skipping cosine clustering")
        return [[i] for i in range(len(articles))]


# ── Stage 2: batch merge via Gemini ───────────────────────────────────────────

def merge_all_clusters(clusters: list, model) -> list:
    clusters_json = json.dumps(clusters, ensure_ascii=False, indent=2)

    prompt = f"""You are a senior news editor. Multiple newspapers covered the same stories.
Below are {len(clusters)} groups of duplicate articles from different newspapers about the same event.

For EACH group, produce a single merged article that:
- Combines ALL unique facts from every source into one richer summary. HARD LIMIT: 400 characters.
- Picks the most informative, specific headline (max 12 words, no publication name prefix).
- Picks the BEST category that fits the merged story (may differ from individual articles).

Return ONLY a valid JSON array with exactly {len(clusters)} objects, one per group, in the same order.
Each object MUST have exactly these keys:
  "headline" — best headline (max 12 words)
  "summary"  — merged summary, max 400 chars
  "category" — best category label

Groups:
{clusters_json}

Return ONLY the JSON array. No markdown fences, no explanation."""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        merged_list = json.loads(raw)

        if len(merged_list) != len(clusters):
            raise ValueError(f"Gemini returned {len(merged_list)} for {len(clusters)} clusters")

        result = []
        for i, art in enumerate(merged_list):
            art["sources"] = clusters[i]["sources"]
            result.append(art)

        log.info(f"  Merged {len(clusters)} clusters in 1 API call")
        return result

    except Exception as e:
        log.error(f"Batch merge failed: {e} — falling back to best-source per cluster")
        result = []
        for cluster in clusters:
            best = max(cluster["articles"], key=lambda a: len(a.get("summary", "")))
            best["sources"] = cluster["sources"]
            best.pop("newspaper", None)
            result.append(best)
        return result


# ── Public API ─────────────────────────────────────────────────────────────────

def deduplicate(all_articles: list, model) -> list:
    """
    Deduplicates all articles across all newspapers using exactly 1 Gemini API call.

    Key improvements:
    - Clusters ACROSS all categories (not just within-category)
    - Named-entity overlap used as secondary signal
    - Headline normalisation strips publication prefixes before clustering
    - Importance preserved from the highest-importance source in each cluster
    """
    log.info(f"Deduplicating {len(all_articles)} articles across all categories (1 API call)...")

    if not all_articles:
        return []

    clusters_indices = cosine_cluster(all_articles)

    single_source      = []
    multi_source_clusters = []

    for cluster_idx_list in clusters_indices:
        cluster_arts = [all_articles[i] for i in cluster_idx_list]

        sources = []
        seen_papers = set()
        for art in cluster_arts:
            paper = art.get("newspaper", "")
            if paper and paper not in seen_papers:
                sources.append({
                    "newspaper":    paper,
                    "pdf_filename": art.get("pdf_filename", ""),
                    "page":         art.get("page", 1),
                    "telegram_url": art.get("telegram_url", ""),
                })
                seen_papers.add(paper)

        if len(cluster_arts) == 1:
            art = cluster_arts[0].copy()
            art["sources"] = sources
            for k in ("newspaper", "pdf_filename"):
                art.pop(k, None)
            single_source.append(art)
        else:
            best_importance = max((a.get("importance", 0) for a in cluster_arts), default=0)
            multi_source_clusters.append({
                "category":   cluster_arts[0].get("category", "India"),
                "importance": best_importance,
                "sources":    sources,
                "articles": [
                    {
                        "headline":  a.get("headline", ""),
                        "summary":   a.get("summary", ""),
                        "newspaper": a.get("newspaper", ""),
                        "category":  a.get("category", ""),
                    }
                    for a in cluster_arts
                ],
            })

    log.info(
        f"  Stage 1: {len(single_source)} unique, "
        f"{len(multi_source_clusters)} clusters to merge"
    )

    merged = []
    if multi_source_clusters:
        merged = merge_all_clusters(multi_source_clusters, model)
        for i, art in enumerate(merged):
            if "importance" not in art:
                art["importance"] = multi_source_clusters[i].get("importance", 5)

    final = single_source + merged
    log.info(
        f"Deduplication complete: {len(all_articles)} → {len(final)} articles "
        f"(removed {len(all_articles) - len(final)} duplicates)"
    )
    return final
