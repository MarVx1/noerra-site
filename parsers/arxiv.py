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

# cs.AI — общая категория arXiv: в ней наравне с работами про нейросети
# мозга (memristor-схемы, spiking neural networks и т.п.) идёт весь обычный
# ML — агенты, LLM, RL-алгоритмы, которые к нейронауке никакого отношения
# не имеют. Раньше такая статья ("Online Reinforcement Learning for
# Multi-turn Computer-Use Agents") доходила до классификатора и получала
# тему "dopamine" по словам reward/reinforcement, которые в ML и в
# нейронауке о дофамине означают разное — по одним ключевым словам их не
# различить (вычитка 2026-07-15). Фильтруем ИСТОЧНИК, а не классификатор:
# только для cs.AI требуем явный нейро/био-якорь, иначе статья вообще не
# попадает в кандидаты. q-bio.NC/q-bio.PE не трогаем — это уже
# специализированные нейро-категории самого arXiv.
_BRAIN_ANCHOR_RE = re.compile(
    r"\b(brain|neuron|neuronal|synap|cortex|cortical|neuroscien|neurobiolog|"
    r"biologically inspired|brain-inspired|neuromorphic|spiking neural|"
    r"hippocamp|cerebell|cerebra|dopamin)",
    re.IGNORECASE,
)


def _is_brain_relevant(text: str) -> bool:
    return bool(_BRAIN_ANCHOR_RE.search(text))

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

                    if feed_url.endswith("/cs.AI") and not _is_brain_relevant(f"{title} {abstract}"):
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
