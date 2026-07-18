"""
Перегенерирует сохранённый текст (summaries.post_text/summary_ru,
drafts.title/lead/body/short_version/full_version) для ещё не
опубликованных статей — прогоняя их заново через ТЕКУЩИЙ пайплайн
генерации (EditorialEngine.analyze -> build_structure -> generate_text),
той же логикой построения post_text, что scheduler._run_pipeline_sync()
использует для новых статей.

Зачем: все редакционные фиксы (глоссарий жаргона, честный
significance frame человек/животное, фильтр критериев отбора обзоров,
anti-repeat заголовков и т.д.) применяются только к статьям, которые
проходят пайплайн ПОСЛЕ соответствующего коммита. Статьи, обработанные
раньше, несут старый текст с уже исправленными в коде дефектами.

Трогает только status IN ('new', 'pending', 'approved', 'edit_requested') —
эти статьи ещё не опубликованы, перезапись их текста ни на что в канале
не влияет. status='published' НЕ трогается вообще (см. фильтр запроса
в database.db.get_articles_by_statuses) — их Telegraph/канал уже
показывают старый текст, переписывать БД задним числом только создало
бы расхождение между тем, что в базе, и тем, что реально опубликовано.

Офлайн: только чтение статей + перезапись summaries/drafts. Без
публикации, без Telegram, без Telegraph.

Идемпотентно: повторный запуск не плодит дубли (database.db.replace_summary
удаляет старую строку перед вставкой; database.db.update_draft_content
обновляет существующий драфт по его id, не создаёт новый).

Устойчиво к сетевым обрывам: перевод (deep-translator) обращается к сети
на каждую статью; per-article try/except не даёт одной сетевой ошибке
уронить весь прогон — статья пропускается с логом, остальные продолжают
обрабатываться, повторный запуск скрипта до-обработает пропущенное.

Запуск (вручную, один раз):
    python scripts/regenerate_summaries.py
"""

import logging
import sys

from parsers.base import RawArticle
from adaptation.editorial_engine import EditorialEngine
from adaptation.publication import Publication
from adaptation.utils import esc, esc_preserve_own_tags, _shorten_by_paragraphs
from classifier.classifier import get_topic_emoji
from database.db import (
    get_articles_by_statuses,
    replace_summary,
    get_latest_draft_for_article,
    update_draft_content,
    save_draft,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("regenerate_summaries")

ELIGIBLE_STATUSES = ("new", "pending", "approved", "edit_requested")

# is_peer_reviewed не хранится в таблице articles (см. схему в
# database/db.py) — реальные парсеры (parsers/*.py) проставляют его при
# первом сборе статьи по источнику, здесь та же карта, чтобы
# перегенерация видела peer_reviewed так же, как видел исходный прогон.
SOURCE_PEER_REVIEWED = {
    "pubmed": True,
    "cyberleninka": True,
    "arxiv": False,
    "youtube": False,
    "nplus1": True,
    "postnauka": True,
    "naked-science": True,
    "frontiers": True,
    "plos-one": True,
    "psyarxiv": False,
}


def _build_post_text(topic: str, pub: Publication) -> str:
    """Точная копия построения post_text из scheduler._run_pipeline_sync() —
    именно это поле читает bot/publishing.py:_publish_article() при
    реальной публикации в канал, так что расхождение с оригиналом здесь
    свело бы на нет весь смысл перегенерации."""
    visible_text = (pub.body or pub.lead or "").strip()
    if not visible_text:
        visible_text = pub.full_version.replace(pub.title, "", 1).strip()
    visible_text = _shorten_by_paragraphs(visible_text, 700) if visible_text else ""

    if visible_text:
        return (
            f"{get_topic_emoji(topic)} <b>{esc(pub.title)}</b>\n\n"
            f"{esc_preserve_own_tags(visible_text)} \U0001F447\n\n"
            f"\U0001F4D8 <a href='TELEGRAPH_URL'>Читать полностью</a>"
        )
    return (
        f"{get_topic_emoji(topic)} <b>{esc(pub.title)}</b> \U0001F447\n\n"
        f"\U0001F4D8 <a href='TELEGRAPH_URL'>Читать полностью</a>"
    )


def _regenerate_one(engine: EditorialEngine, row) -> tuple[str, str]:
    """Перегенерирует одну статью, перезаписывает summaries/drafts.
    Возвращает (старый post_text, новый post_text) для отчёта."""
    article = RawArticle(
        title=row["title"] or "",
        url=row["url"] or "",
        abstract=row["abstract"] or "",
        source=row["source"] or "",
        external_id=row["external_id"] or "",
        is_peer_reviewed=SOURCE_PEER_REVIEWED.get(row["source"] or "", False),
    )
    topic = row["topic"] or ""

    passport = engine.analyze(article, topic)
    structure = engine.build_structure(passport)
    full_text = engine.generate_text(passport, structure)

    # Та же сборка Publication, что adaptation/pipeline.py:Pipeline.run_for_article()
    parts = [p for p in full_text.split("\n\n") if p.strip()]
    short = parts[0] if parts else full_text
    pub = Publication(
        title=passport.get("title", ""),
        subtitle=None,
        lead=passport.get("lead", ""),
        body="\n\n".join(parts[1:]) if len(parts) > 1 else "",
        short_version=short,
        full_version=full_text,
        sources=passport.get("sources", [article.url, article.source] if article.url else [article.source]),
        topic=passport.get("topic", topic),
        format=passport.get("suggested_format", "analysis"),
        confidence_score=passport.get("confidence_score", 0.0) or 0.0,
        audience=passport.get("audience", "general"),
    )

    summary_ru = pub.full_version
    post_text = _build_post_text(topic, pub)
    old_post_text = row["old_post_text"] or ""

    replace_summary(row["id"], summary_ru, post_text)

    existing_draft = get_latest_draft_for_article(row["id"])
    if existing_draft:
        update_draft_content(
            existing_draft["id"], pub.title, pub.lead, pub.body, pub.short_version,
            pub.full_version, ", ".join(pub.sources), pub.topic, pub.format,
            pub.confidence_score or 0.0, pub.audience,
        )
    else:
        save_draft(
            row["id"], pub.title, pub.lead, pub.body, pub.short_version,
            pub.full_version, ", ".join(pub.sources), pub.topic, pub.format,
            pub.confidence_score or 0.0, pub.audience,
        )

    return old_post_text, post_text


def main() -> int:
    rows = get_articles_by_statuses(ELIGIBLE_STATUSES)
    total = len(rows)
    logger.info("Подпадает под критерий (status in %s): %s статей", ELIGIBLE_STATUSES, total)
    if not total:
        logger.info("Нечего перегенерировать.")
        return 0

    engine = EditorialEngine()
    regenerated = 0
    failed = 0
    examples: list[tuple[int, str, str, str]] = []

    for i, row in enumerate(rows, start=1):
        if i == 1 or i % 5 == 0 or i == total:
            logger.info("Обработка %s из %s (article_id=%s)", i, total, row["id"])
        try:
            old_text, new_text = _regenerate_one(engine, row)
            regenerated += 1
            if old_text != new_text and len(examples) < 5:
                examples.append((row["id"], row["title"] or "", old_text, new_text))
        except Exception:
            failed += 1
            logger.exception(
                "Пропущена статья article_id=%s (%s) — сеть/ошибка генерации, "
                "повторный запуск скрипта до-обработает",
                row["id"], (row["title"] or "")[:60],
            )

    logger.info("=" * 50)
    logger.info(
        "Готово | подпадало=%s | перегенерировано=%s | пропущено с ошибкой=%s",
        total, regenerated, failed,
    )

    print("\n" + "=" * 70)
    print(f"ИТОГО: подпадало под критерий={total}, перегенерировано={regenerated}, пропущено с ошибкой={failed}")
    print("=" * 70)
    for article_id, title, old_text, new_text in examples:
        print(f"\n--- article_id={article_id}: {title[:70]!r} ---")
        print("ДО:")
        print((old_text or "(пусто)")[:500])
        print("\nПОСЛЕ:")
        print((new_text or "(пусто)")[:500])

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
