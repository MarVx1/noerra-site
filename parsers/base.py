# ============================================================
#  parsers/base.py — базовый класс для всех парсеров
# ============================================================

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    """Сырая статья до оценки и адаптации."""
    title:       str
    url:         str
    abstract:    str    = ""
    source:      str    = ""
    external_id: str    = ""
    authors:     list   = field(default_factory=list)
    published:   str    = ""       # дата публикации (строка)
    is_peer_reviewed: bool = False  # рецензируемый журнал?


class BaseParser(ABC):
    """Базовый класс. Каждый парсер наследует его."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> list[RawArticle]:
        """Забирает статьи из источника. Возвращает список RawArticle."""
        ...

    def run(self) -> list[RawArticle]:
        """Запускает парсер с обработкой ошибок."""
        try:
            articles = self.fetch()
            logger.info(f"[{self.source_name}] Получено: {len(articles)} статей")
            return articles
        except Exception as e:
            logger.error(f"[{self.source_name}] Ошибка: {e}")
            return []
