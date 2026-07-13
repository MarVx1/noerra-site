# ============================================================
#  adaptation/editorial.py — Telegram и Telegraph wrappers for Editorial Engine
# ============================================================

from typing import Iterable
from parsers.base import RawArticle
from classifier.classifier import get_topic_ru, get_topic_emoji
from adaptation.editorial_engine import EditorialEngine
from adaptation.publication import Publication
from adaptation.utils import esc

SOURCE_NAMES = {
    "pubmed": "PubMed",
    "arxiv": "arXiv",
    "cyberleninka": "CyberLeninka",
    "rss": "RSS",
    "youtube": "YouTube",
}


def _source_list(articles: Iterable[RawArticle]) -> str:
    names = []
    for article in articles:
        name = SOURCE_NAMES.get(article.source.lower(), article.source or "источник")
        if name not in names:
            names.append(name)
    return ", ".join(names) or "научные источники"


def generate_telegram_text(article: RawArticle, topic: str, telegraph_url: str | None = None) -> str:
    engine = EditorialEngine()

    # ВАЖНО: analyze()/build_structure() вызываются РОВНО ОДИН раз и переиспользуются
    # для заголовка, короткой версии и блока "почему важно". Раньше здесь было два
    # независимых вызова analyze() — а так как заголовок и текст выбираются случайно
    # (random.choice в _pick), каждый вызов давал РАЗНЫЙ результат, из-за чего
    # заголовок и содержание поста были рассинхронизированы между собой и с драфтом.
    passport = engine.analyze(article, topic)
    structure = engine.build_structure(passport)
    full_text = engine.generate_text(passport, structure)

    parts = [p for p in full_text.split('\n\n') if p.strip()]
    # parts[0] = title (уже показан в заголовке), parts[1] = lead — используем как краткую версию
    short_version = parts[1] if len(parts) > 1 else (parts[0] if parts else full_text)
    # startswith("Почему это важно") — не просто "Почему": Reader Question
    # (Stage 3) тоже нередко начинается с "Почему...?" (см.
    # adaptation/reader_question.py), и более широкий префикс случайно
    # перехватывал бы его вместо настоящего why-блока из _build_why().
    why_block = next(
        (s for s in structure if isinstance(s, str) and s.strip().startswith("Почему это важно")),
        None,
    )

    telegram_lines = [
        f"{get_topic_emoji(topic)} <b>{esc(passport.get('title', ''))}</b>",
        "",
        esc(short_version),
    ]
    if why_block:
        telegram_lines.extend(["", esc(why_block)])
    if telegraph_url:
        telegram_lines.extend(["", f"📘 <a href='{telegraph_url}'>Читать полностью</a>"])
    if article.source:
        telegram_lines.extend(["", esc(_source_list([article]))])
    return "\n".join([line for line in telegram_lines if line.strip()])


def generate_telegraph_text(article: RawArticle, topic: str) -> str:
    engine = EditorialEngine()
    pub: Publication = engine.create_publication_for_article(article, topic)
    original_line = f"Оригинал: {article.url}" if article.url else ""
    expanded_lines = [pub.full_version]
    if original_line:
        expanded_lines.extend(["", "Полный разбор", original_line])
    return "\n\n".join([line for line in expanded_lines if line])