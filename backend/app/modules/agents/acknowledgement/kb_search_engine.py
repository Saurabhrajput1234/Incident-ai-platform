"""
Knowledge Base Search Engine.

Evaluates ticket query text against corporate KB articles dataset and returns
top relevant self-service help guides for INFORMATION_REQUEST tickets.
"""
import logging
from app.modules.agents.acknowledgement.dummy_data.dummy_kb_articles import DUMMY_KB_ARTICLES
from app.modules.agents.acknowledgement.schemas import KBArticle

logger = logging.getLogger(__name__)


class KBSearchEngine:
    def __init__(self, kb_catalog: list[dict] | None = None):
        self.catalog = kb_catalog or DUMMY_KB_ARTICLES

    def search_kb(self, query: str, top_k: int = 2) -> list[KBArticle]:
        """
        Computes composite relevance score for each KB article based on
        keyword matching, title token overlap, and category relevance.
        """
        query_words = set(query.lower().split())
        scored_articles: list[tuple[float, dict]] = []

        for article in self.catalog:
            score = 0.0
            keywords = [k.lower() for k in article.get("keywords", [])]
            title = article.get("title", "").lower()
            category = article.get("category", "").lower()

            # 1. Direct Keyword Match
            for kw in keywords:
                if kw in query.lower():
                    score += 3.0

            # 2. Title Word Overlap
            title_words = set(title.split())
            overlap = query_words.intersection(title_words)
            score += len(overlap) * 1.5

            # 3. Category match
            if any(word in category for word in query_words):
                score += 1.0

            if score > 0.5:
                scored_articles.append((score, article))

        # Sort by score descending
        scored_articles.sort(key=lambda x: x[0], reverse=True)
        top_results = [KBArticle(**item[1]) for item in scored_articles[:top_k]]

        logger.info(f"[KBSearchEngine] Found {len(top_results)} KB articles matching query: '{query}'")
        return top_results
