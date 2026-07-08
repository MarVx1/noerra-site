# ============================================================
#  parsers/rss.py — универсальный RSS-парсер
#  N+1, ПостНаука, Naked Science, Frontiers и др.
# ============================================================

import feedparser
import logging
from parsers.base import BaseParser, RawArticle

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    # ── Русскоязычные научные медиа (Tier 2) ─────────────────
    {
        "url":    "https://nplus1.ru/rss",
        "source": "nplus1",
        "trusted": True,
    },
    {
        "url":    "https://postnauka.ru/feed",
        "source": "postnauka",
        "trusted": True,
    },
    {
        "url":    "https://naked-science.ru/feed",
        "source": "naked-science",
        "trusted": True,
    },

    # ── Международные (Tier 1-2) ──────────────────────────────
    {
        "url":    "https://www.frontiersin.org/journals/human-neuroscience/rss",
        "source": "frontiers",
        "trusted": True,
    },
    {
        "url":    "https://www.frontiersin.org/journals/psychology/rss",
        "source": "frontiers",
        "trusted": True,
    },
    {
        "url":    "https://journals.plos.org/plosone/feed/atom",
        "source": "plos-one",
        "trusted": True,
    },
    {
        "url":    "https://psyarxiv.com/feed",
        "source": "psyarxiv",
        "trusted": False,   # препринты
    },
]


class RSSParser(BaseParser):
    source_name = "rss"

    def fetch(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for src in RSS_SOURCES:
            try:
                feed = feedparser.parse(src["url"])
                for entry in feed.entries:
                    url   = entry.get("link", "")
                    title = entry.get("title", "").strip()
                    if not url or not title or url in seen:
                        continue
                    seen.add(url)

                    abstract = (
                        entry.get("summary", "") or
                        entry.get("description", "")
                    ).strip()

                    articles.append(RawArticle(
                        title=title,
                        url=url,
                        abstract=abstract,
                        source=src["source"],
                        is_peer_reviewed=src["trusted"],
                    ))
            except Exception as e:
                logger.error(f"RSS error ({src['url']}): {e}")

        return articles
