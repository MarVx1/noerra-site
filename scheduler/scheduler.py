# ============================================================
#  scheduler/scheduler.py — пайплайн + кластерный дайджест
# ============================================================

import asyncio
import logging
from collections import defaultdict
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from parsers.pubmed import PubMedParser
from parsers.arxiv import ArxivParser
from parsers.cyberleninka import CyberLeninaParser
from parsers.rss import RSSParser
from parsers.youtube import YouTubeParser
from parsers.base import RawArticle

from scoring.scorer import score_article
from classifier.classifier import classify, get_topic_emoji
from adaptation.utils import esc, _shorten
from adaptation.pipeline import Pipeline
from adaptation.adapter import generate_summary, generate_post
from adaptation.cluster import build_cluster_post
from adaptation.editorial_engine import EditorialEngine
from intelligence.research_analysis.passport_builder import build_research_passport
from intelligence.research_analysis.claim_extractor import extract_scientific_claims
from intelligence.research_analysis.text_extractors import normalize_claim
from database.db import (
    article_exists, save_article, save_summary,
    save_research_passport, upsert_scientific_claim, save_claim_evidence,
    update_consensus_for_claim,
    get_top_articles_by_topic, update_article_status, update_draft_status,
)
from config.settings import (
    PARSE_INTERVAL_MINUTES, MIN_SCORE_TO_MODERATE,
    MAX_ARTICLES_PER_RUN, TOP_PER_TOPIC, MAX_TOPICS_IN_DIGEST,
    DIGEST_HOUR, ADMIN_CHAT_ID, CHANNEL_ID,
)

# Lazy import to avoid circular dependency (bot -> scheduler -> bot)
_send_draft_for_editor = None
def _get_send_draft():
    global _send_draft_for_editor
    if _send_draft_for_editor is None:
        from bot.bot import send_draft_for_editor
        _send_draft_for_editor = send_draft_for_editor
    return _send_draft_for_editor

logger = logging.getLogger(__name__)


def _get_existing_urls_batch(articles: list[RawArticle]) -> set[str]:
    """Загружает существующие URL из БД одним запросом вместо N запросов."""
    urls = [a.url for a in articles if a.url]
    if not urls:
        return set()
    from database.db import execute_query
    placeholders = ",".join("?" * len(urls))
    rows = execute_query(f"SELECT url FROM articles WHERE url IN ({placeholders})", tuple(urls))
    return {row["url"] for row in rows}


# ── Пайплайн сбора ────────────────────────────────────────────
def _run_pipeline_sync():
    """Синхронное ядро пайплайна — всё, что не требует event loop.

    Возвращает список draft_id, которые нужно отправить редактору.
    """
    logger.info("=" * 50)
    logger.info("Pipeline started")

    # Предупреждение о известных проблемных источниках
    logger.warning(
        "Known unstable sources: cyberleninka (API may be down), youtube (RSS timeouts possible). "
        "If these return 0 articles, check parser logs."
    )

    # Парсеры запускаются параллельно через ThreadPoolExecutor
    parsers = [
        PubMedParser(),
        ArxivParser(),
        CyberLeninaParser(),
        RSSParser(),
        YouTubeParser(),
    ]

    all_articles: list[RawArticle] = []
    articles_by_source: dict[str, list] = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="parser") as executor:
        future_to_parser = {executor.submit(parser.run): parser.source_name for parser in parsers}
        for future in as_completed(future_to_parser):
            source_name = future_to_parser[future]
            try:
                result = future.result()
                articles_by_source[source_name] = result
                logger.info(f"Parser {source_name} completed: {len(result)} articles")
            except Exception as e:
                logger.error(f"Parser {source_name} failed: {e}")
                articles_by_source[source_name] = []

    # Round-robin merge: берём по одной статье от каждого источника по очереди.
    # Иначе источник, который просто ответил быстрее (или дал больше статей),
    # монополизирует весь лимит MAX_ARTICLES_PER_RUN, а остальные источники
    # никогда не доходят до оценки — независимо от их реального качества.
    import itertools
    per_source_lists = list(articles_by_source.values())
    all_articles = [
        a for a in itertools.chain.from_iterable(itertools.zip_longest(*per_source_lists))
        if a is not None
    ]

    logger.info("Collected articles: %s", len(all_articles))

    # Batch проверка дубликатов — один запрос вместо N
    pipeline = Pipeline()
    sent = skipped_dup = skipped_topic = skipped_score = quality_failed = failed = 0
    drafts_to_send: list[int] = []

    # Дедупликация по ВСЕМУ собранному списку, а не только по первым N —
    # иначе лимит съедается дублями, а реально новые статьи (которые
    # могут лежать дальше в списке) вообще не доходят до обработки.
    existing_urls = _get_existing_urls_batch(all_articles)
    new_candidates = [a for a in all_articles if a.url not in existing_urls]
    skipped_dup += len(all_articles) - len(new_candidates)

    to_process = new_candidates[:MAX_ARTICLES_PER_RUN]
    logger.info(f"К обработке: {len(to_process)} новых статей (из {len(new_candidates)} уникальных)")

    for i, article in enumerate(to_process, start=1):
        if i == 1 or i % 5 == 0 or i == len(to_process):
            logger.info(f"Обработка статьи {i} из {len(to_process)}: {article.title[:60]!r}")
        try:
            if not article.url or not article.title:
                continue

            score = score_article(article)
            topic, _ = classify(article)

            if topic == "unknown":
                save_article(
                    source=article.source,
                    title=article.title,
                    url=article.url,
                    abstract=article.abstract,
                    external_id=article.external_id,
                    topic="unknown",
                    score=score,
                    status="off_topic",
                )
                skipped_topic += 1
                existing_urls.add(article.url)
                continue

            if score < MIN_SCORE_TO_MODERATE:
                save_article(
                    source=article.source,
                    title=article.title,
                    url=article.url,
                    abstract=article.abstract,
                    external_id=article.external_id,
                    topic=topic,
                    score=score,
                    status="low_score",
                )
                skipped_score += 1
                existing_urls.add(article.url)
                continue

            # Единственный источник текста: Pipeline.run_for_article() вызывает
            # analyze()/generate_text() РОВНО ОДИН раз. Раньше здесь ДО этого
            # отдельно вызывались generate_summary()/generate_post(), которые
            # заново запускали analyze() со своим случайным выбором заголовка —
            # в итоге редактор одобрял один текст, а публиковался другой.
            article_id = save_article(
                source=article.source,
                title=article.title,
                url=article.url,
                abstract=article.abstract,
                external_id=article.external_id,
                topic=topic,
                score=score,
            )
            if article_id is None:
                skipped_dup += 1
                continue

            passport_research = build_research_passport(article, topic, article_id)
            save_research_passport(passport_research)
            for claim in extract_scientific_claims(article, topic):
                claim_id = upsert_scientific_claim(
                    claim.claim_text,
                    normalize_claim(claim.claim_text),
                    claim.topic,
                )
                save_claim_evidence(
                    claim_id=claim_id,
                    article_id=article_id,
                    relation=claim.relation,
                    evidence_strength=passport_research.evidence_strength,
                    confidence=claim.confidence,
                    reasoning=claim.reasoning,
                )
                update_consensus_for_claim(claim_id)

            result = pipeline.run_for_article(article, topic, article_id)
            draft_id = result.get("draft_id")
            review = result.get("review") or {}
            pub = result.get("publication")

            # summary_ru/post_text строятся из ТОГО ЖЕ Publication, что видел
            # редактор в драфте — не пересчитываются заново.
            summary_ru = pub.full_version if pub else (article.abstract or "")

            # ВАЖНО: pub.short_version по конструкции EditorialEngine всегда
            # равен pub.title (blocks[0] в build_structure() — это и есть title),
            # поэтому использовать его как "тело" поста бессмысленно — получится
            # дублирование заголовка без единого слова реального содержания.
            # Реальный, извлечённый из абстракта текст лежит в pub.body.
            visible_text = (pub.body or pub.lead or "").strip() if pub else ""
            if not visible_text and pub:
                # На случай пустого body — берём full_version за вычетом заголовка
                visible_text = pub.full_version.replace(pub.title, "", 1).strip()
            visible_text = _shorten(visible_text, 700) if visible_text else ""

            post_text = (
                f"{get_topic_emoji(topic)} <b>{esc(pub.title)}</b>\n\n"
                f"{esc(visible_text)}\n\n"
                f"📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"
                if pub and visible_text else
                (
                    f"{get_topic_emoji(topic)} <b>{esc(pub.title)}</b>\n\n"
                    f"📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"
                    if pub else generate_post(article, topic, "TELEGRAPH_URL")
                )
            )
            save_summary(article_id, summary_ru, post_text)

            if not review.get("passed", False):
                reject_reason = "; ".join(review.get("hard_problems") or review.get("problems", []))
                update_article_status(article_id, "quality_failed", reject_reason=reject_reason)
                if draft_id:
                    update_draft_status(draft_id, "quality_failed")
                quality_failed += 1
                logger.info(
                    "Article failed quality gate | article_id=%s | problems=%s",
                    article_id,
                    review.get("problems", []),
                )
                continue

            update_article_status(article_id, "pending")
            if draft_id:
                drafts_to_send.append(draft_id)

            sent += 1

        except Exception:
            failed += 1
            logger.exception("Article processing failed: %s", article.url or article.title)

    logger.info(
        "Pipeline finished | sent=%s | duplicates=%s | low_score=%s | off_topic=%s | quality_failed=%s | failed=%s",
        sent,
        skipped_dup,
        skipped_score,
        skipped_topic,
        quality_failed,
        failed,
    )

    # Update Living Knowledge for all topics touched in this run
    try:
        from scheduler.knowledge_updater import update_all_topics_knowledge
        update_all_topics_knowledge()
        logger.info("Living Knowledge updated for all topics.")
    except Exception as e:
        logger.error(f"Failed to update Living Knowledge: {e}")

    return drafts_to_send


async def run_pipeline():
    """Async-обёртка: запускает синхронное ядро в отдельном потоке,
    затем отправляет драфты редактору в event loop.

    Это НЕ блокирует polling — кнопки работают во время пайплайна.
    """
    # Синхронная часть — в отдельном потоке, не блокирует event loop
    drafts_to_send = await asyncio.to_thread(_run_pipeline_sync)

    # Async часть — отправка драфтов через bot API
    for draft_id in drafts_to_send:
        try:
            send_draft = _get_send_draft()
            await send_draft(draft_id)
        except Exception as e:
            logger.error("Failed to send draft to editor: %s", e)


async def send_daily_digest():
    """
    Формирует кластерный дайджест:
    по каждой теме — сборный пост из нескольких источников + подкаст.
    """
    from bot.bot import get_bot
    bot = get_bot()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from database.db import get_top_articles_by_topic, get_youtube_by_topic

    logger.info("📰 Формирую кластерный дайджест...")

    # Получаем статьи сгруппированные по темам
    raw_articles = get_top_articles_by_topic(
        top_per_topic=TOP_PER_TOPIC,
        max_topics=MAX_TOPICS_IN_DIGEST,
        min_score=MIN_SCORE_TO_MODERATE,
    )

    if not raw_articles:
        await bot.send_message(
            ADMIN_CHAT_ID,
            "📭 <b>Дайджест пуст</b>\n\nНет статей с достаточным score.",
            parse_mode="HTML",
        )
        return

    # Группируем по теме
    by_topic: dict[str, list] = defaultdict(list)
    for a in raw_articles:
        by_topic[a["topic"]].append(a)

    # Для каждой темы строим кластерный пост
    cluster_count = 0
    for topic, db_articles in by_topic.items():

        # Конвертируем из sqlite.Row в RawArticle для cluster builder
        raw = [
            RawArticle(
                title=a["title"],
                url=a["url"] or "",
                abstract=a["abstract"] or "",
                source=a["source"],
            )
            for a in db_articles
        ]

        # Берём YouTube для этой темы (если есть)
        yt_row = get_youtube_by_topic(topic)
        yt_article = None
        if yt_row:
            yt_article = RawArticle(
                title=yt_row["title"],
                url=yt_row["url"] or "",
                abstract=yt_row["abstract"] or "",
                source="youtube",
            )

        engine = EditorialEngine()

        # Telegram post (compact) — build via existing helper which uses engine
        post_text = build_cluster_post(
            topic=topic,
            articles=raw,
            youtube_article=yt_article,
            telegraph_url="TELEGRAPH_URL",
        )

        # Telegraph content generated by the engine for unified style
        telegraph_content = engine.generate_cluster_text(topic, raw)

        # ID статей для кнопок
        ids_str = ",".join(str(a["id"]) for a in db_articles)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Опубликовать",
                    callback_data=f"cluster_approve:{ids_str}",
                ),
                InlineKeyboardButton(
                    text="❌ Пропустить",
                    callback_data=f"cluster_reject:{ids_str}",
                ),
            ],
        ])

        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                post_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            for a in db_articles:
                update_article_status(a["id"], "pending")
            cluster_count += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка отправки кластера ({topic}): {e}")

    logger.info(f"Дайджест отправлен: {cluster_count} кластеров")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=PARSE_INTERVAL_MINUTES,
        id="noerra_pipeline",
        max_instances=1,
    )

    scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=DIGEST_HOUR,
        minute=0,
        id="noerra_digest",
    )

    scheduler.add_job(
        run_knowledge_audit,
        trigger="cron",
        hour=2,  # Run audit daily at 2 AM
        minute=0,
        id="noerra_audit",
    )

    scheduler.add_job(
        snapshot_channel_stats,
        trigger="cron",
        hour=3,  # После аудита, до дайджеста
        minute=0,
        id="noerra_channel_stats",
    )

    return scheduler


async def snapshot_channel_stats():
    """Ежедневный снимок числа подписчиков канала (Business Model MVP шаг 3).

    get_chat_member_count — единственная метрика роста аудитории, которую
    Bot API отдаёт постфактум без MTProto-клиента; просмотры/репосты сюда
    не входят принципиально.
    """
    from bot.bot import get_bot
    from database.db import save_channel_stats_snapshot

    bot = get_bot()
    try:
        count = await bot.get_chat_member_count(CHANNEL_ID)
        save_channel_stats_snapshot(CHANNEL_ID, count)
        logger.info(f"📈 Снимок подписчиков: {count}")
    except Exception as e:
        logger.error(f"Не удалось снять статистику канала: {e}")


async def run_knowledge_audit():
    """Run daily knowledge audit and log stale topics + drifts."""
    logger.info("🔍 Running daily knowledge audit...")
    from intelligence.knowledge_audit import audit_all_topics, detect_knowledge_debt, track_confidence_drift

    try:
        audits = audit_all_topics(stale_days=30)
        stale = [a.topic for a in audits if a.is_stale]
        contradictions = [a.topic for a in audits if a.has_contradictions]

        if stale:
            logger.warning(f"Stale topics ({len(stale)}): {', '.join(stale)}")
        if contradictions:
            logger.warning(f"Topics with contradictions ({len(contradictions)}): {', '.join(contradictions)}")

        # Track drift for active topics
        for audit in audits[:10]:  # Limit to top 10 topics
            if audit.claims_count > 0:
                drifts = track_confidence_drift(audit.topic)
                for drift in drifts:
                    if drift.direction == "decreased":
                        logger.warning(
                            f"Confidence decreased for '{drift.claim_text[:50]}': "
                            f"{drift.previous_confidence} → {drift.current_confidence}"
                        )

        # Knowledge debt
        debt = detect_knowledge_debt(stale_days=30)
        if debt:
            logger.warning(f"Knowledge debt detected ({len(debt)} topics):")
            for d in debt:
                logger.warning(f"  - {d['topic']}: {d['new_articles']} new articles, "
                               f"last update: {d['last_knowledge_update']}")

        logger.info("Knowledge audit completed.")
    except Exception as e:
        logger.error(f"Knowledge audit failed: {e}")