# ============================================================
#  adaptation/adapter.py — адаптация и генерация поста
# ============================================================

import logging
from parsers.base import RawArticle
from adaptation.editorial import generate_telegram_text, generate_telegraph_text

logger = logging.getLogger(__name__)


# ── Генераторы ────────────────────────────────────────────────

def generate_summary(article: RawArticle, topic: str) -> str:
    """Генерирует материал для Telegraph — полный аналитический разбор."""
    return generate_telegraph_text(article, topic)


def generate_post(article: RawArticle, topic: str, telegraph_url: str) -> str:
    """енерирует полноценный Telegram-пост в редакционном стиле."""
    return generate_telegram_text(article, topic, telegraph_url)
