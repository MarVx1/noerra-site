# ============================================================
#  parsers/arxiv.py — парсер arXiv через RSS
# ============================================================

import re
import feedparser
import logging
from parsers.base import BaseParser, RawArticle

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://export.arxiv.org/rss/q-bio.NC",    # Neurons & Cognition
    "https://export.arxiv.org/rss/q-bio.PE",    # Populations & Evolution
    "https://export.arxiv.org/rss/cs.AI",       # AI (для нейросетей мозга)
]

# RSS-фид arXiv кладёт в summary служебный префикс листинга перед самим
# абстрактом ("arXiv:2607.11656v1 Announce Type: new  Abstract: ..."),
# который раньше уходил в текст статьи как есть — читатель видел буквально
# "ArXiv:2607.09773v1 Тип объявления: новое Аннотация:" после перевода
# (вычитка реальных публикаций 2026-07-15).
_ARXIV_LISTING_PREFIX_RE = re.compile(
    r"^arXiv:\S+\s+Announce Type:\s*\S+\s*Abstract:\s*", re.IGNORECASE
)


def _strip_arxiv_listing_prefix(summary: str) -> str:
    return _ARXIV_LISTING_PREFIX_RE.sub("", summary)


class ArxivParser(BaseParser):
    source_name = "arxiv"

    def fetch(self) -> list[RawArticle]:
        articles = []
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                # Берём только последние 30 статей из каждого фида
                for entry in feed.entries[:30]:
                    title    = entry.get("title", "").replace("\n", " ").strip()
                    url      = entry.get("link", "")
                    abstract = _strip_arxiv_listing_prefix(
                        entry.get("summary", "").replace("\n", " ").strip()
                    )
                    arxiv_id = url.split("/abs/")[-1] if "/abs/" in url else ""

                    if not title or not url:
                        continue

                    articles.append(RawArticle(
                        title=title,
                        url=url,
                        abstract=abstract,
                        source="arxiv",
                        external_id=arxiv_id,
                        is_peer_reviewed=False,   # препринты не рецензированы
                    ))
            except Exception as e:
                logger.error(f"arXiv RSS error ({feed_url}): {e}")
        return articles
