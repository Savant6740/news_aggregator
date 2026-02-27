"""
deduplicator.py

Deduplicates articles across all newspapers in ONE single Gemini API call.
This is critical to stay within the 20 RPD free tier limit.

Approach:
1. Stage 1 (local, free): TF-IDF cosine similarity to cluster similar stories — no API call
2. Stage 2 (1 API call): Send ALL clusters to Gemini in one prompt for merging
"""

import json
import logging
from collections import defaultdict

log = logging.getLogger(__name__)


def cosine_cluster(articles: list[dict], threshold: float = 0.35) -> list[list[int]]:
    """
    Groups article indices by similarity using TF-IDF. No API call — runs locally.
    Returns list of clusters (each cluster = list of article indices).
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        texts = [f"{a['headline']} {a['summary']}" for a in articles]
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf = vec.fit_transform(texts)
        sim = cosine_similarity(tfidf).tolist()

        visited = set()
        clusters = []
        for i in range(len(articles)):
            if i in visited:
                continue
            cluster = [i]
            visited.add(i)
            for j in range(i + 1, len(articles)):
                if j not in visited and sim[i][j] >= threshold:
                    cluster.append(j)
                    visited.add(j)
            clusters.append(cluster)
        return clusters

    except ImportError:
        log.warning("sklearn not available — skipping cosine clustering")
        return [[i] for i in range(len(articles))]


def deduplicate(all_articles: list[dict], model) -> list[dict]:
    """
    Deduplicates all articles across all newspapers using exactly 1 Gemini API call.

    Steps:
    1. Group by category
    2. Within each category, find duplicate clusters via TF-IDF (free, local)
    3. Build one big prompt with ALL multi-source clusters
    4. Single Gemini call merges them all at once
    5. Reconstruct final article list

    Each final article has:
    - headline, summary, category
    - sources: [{newspaper, pdf_filename, page}, ...]  for cross-referencing
    """
    log.info(f"Deduplicating {len(all_articles)} articles (1 API call total)...")

    by_category = defaultdict(list)
    for art in all_articles:
        by_category[art.get("category", "India")].append(art)

    # Stage 1: Local TF-IDF clustering (free, no API)
    single_source = []     # Articles that appear in only one paper — keep as-is
    multi_source_clusters = []  # Groups that need merging

    for category, articles in by_category.items():
        clusters = cosine_cluster(articles)
        for cluster_indices in clusters:
            cluster_arts = [articles[i] for i in cluster_indices]

            # Build source list
            sources = []
            seen = set()
            for art in cluster_arts:
                paper = art.get("newspaper", "")
                if paper not in seen:
                    sources.append({
                        "newspaper":    paper,
                        "pdf_filename": art.get("pdf_filename", ""),
                        "page":         art.get("page", 1),
                        "telegram_url": art.get("telegram_url", ""),
                    })
                    seen.add(paper)

            if len(cluster_arts) == 1:
                # No deduplication needed
                art = cluster_arts[0].copy()
                art["sources"] = sources
                art.pop("newspaper", None)
                art.pop("pdf_filename", None)
                single_source.append(art)
            else:
                multi_source_clusters.append({
                    "category": category,
                    "sources":  sources,
                    "articles": [
                        {"headline": a["headline"], "summary": a["summary"], "newspaper": a["newspaper"]}
                        for a in cluster_arts
                    ]
                })

    log.info(f"  {len(single_source)} unique articles, {len(multi_source_clusters)} clusters to merge")

    # Stage 2: Merge ALL clusters in a single API call
    merged = []
    if multi_source_clusters:
        merged = merge_all_clusters(multi_source_clusters, model)

    final = single_source + merged
    log.info(f"Deduplication complete: {len(all_articles)} → {len(final)} articles (used 1 API call)")
    return final


def merge_all_clusters(clusters: list[dict], model) -> list[dict]:
    """
    Merges all multi-source duplicate clusters in ONE Gemini API call.
    """
    clusters_json = json.dumps(clusters, ensure_ascii=False, indent=2)

    prompt = f"""You are a news editor. Multiple newspapers covered the same stories.
Below are {len(clusters)} groups of duplicate articles. Each group has articles from different newspapers about the same event.

For EACH group, produce a single merged article that:
- Combines unique facts from all sources into one richer summary (3-4 sentences)
- Uses the best/most informative headline
- Preserves the category

Return ONLY a valid JSON array with exactly {len(clusters)} objects, one per group, in the same order.
Each object must have:
- "headline": best headline (max 12 words)
- "summary": merged 3-4 sentence summary combining all unique facts
- "category": same category as the group

Groups:
{clusters_json}

Return ONLY the JSON array. No markdown, no explanation."""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        merged_list = json.loads(raw)

        # Attach source metadata back
        result = []
        for i, merged_art in enumerate(merged_list):
            merged_art["sources"] = clusters[i]["sources"]
            result.append(merged_art)

        log.info(f"  Merged {len(clusters)} clusters in 1 API call")
        return result

    except Exception as e:
        log.error(f"Batch merge failed: {e}. Falling back to best-source per cluster.")
        # Fallback: pick the article with the longest summary from each cluster
        result = []
        for cluster in clusters:
            best = max(cluster["articles"], key=lambda a: len(a.get("summary", "")))
            best["sources"] = cluster["sources"]
            best.pop("newspaper", None)
            result.append(best)
        return result
