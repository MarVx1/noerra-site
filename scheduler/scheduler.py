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
from classifier.classifier import classify
from adaptation.pipeline import Pipeline
from adaptation.adapter import generate_summary, generate_post
from adaptation.cluster import build_cluster_post
from adaptation.editorial_engine import EditorialEngine
from adaptation.editorial_planner import EditorialPlanner
from knowledge.core import build_research_passport, extract_scientific_claims, normalize_claim
from database.db import (
    article_exists, save_article, save_summary,
    save_research_passport, upsert_scientific_claim, save_claim_evidence,
    update_consensus_for_claim,
    get_top_articles_by_topic, update_article_status, update_draft_status,
)
from config.settings import (
    PARSE_INTERVAL_MINUTES, MIN_SCORE_TO_MODERATE,
    MAX_ARTICLES_PER_RUN, TOP_PER_TOPIC, MAX_TOPICS_IN_DIGEST,
    DIGEST_HOUR, ADMIN_CHAT_ID,
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

    # Парсеры запускаются параллельно через ThreadPoolExecutor
    parsers = [
        PubMedParser(),
        ArxivParser(),
        CyberLeninaParser(),
        RSSParser(),
        YouTubeParser(),
    ]

    all_articles: list[RawArticle] = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="parser") as executor:
        future_to_parser = {executor.submit(parser.run): parser.source_name for parser in parsers}
        for future in as_completed(future_to_parser):
            source_name = future_to_parser[future]
            try:
                result = future.result()
                all_articles += result
                logger.info(f"Parser {source_name} completed: {len(result)} articles")
            except Exception as e:
                logger.error(f"Parser {source_name} failed: {e}")

    logger.info("Collected articles: %s", len(all_articles))

    # Batch проверка дубликатов — один запрос вместо N
    pipeline = Pipeline()
    sent = skipped_dup = skipped_topic = skipped_score = quality_failed = failed = 0
    drafts_to_send: list[int] = []

    # Предзагрузка существующих URL для быстрой проверки дубликатов
    existing_urls = _get_existing_urls_batch(all_articles[:MAX_ARTICLES_PER_RUN])

    for article in all_articles[:MAX_ARTICLES_PER_RUN]:
        try:
            if not article.url or not article.title:
                continue

            if article.url in existing_urls:
                skipped_dup += 1
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

            summary_ru = generate_summary(article, topic)
            post_text = generate_post(article, topic, "TELEGRAPH_URL")

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

            save_summary(article_id, summary_ru, post_text)

            passport = build_research_passport(article, topic, article_id)
            save_research_passport(passport)
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
                    evidence_strength=passport.evidence_strength,
                    confidence=claim.confidence,
                    reasoning=claim.reasoning,
                )
                update_consensus_for_claim(claim_id)

            result = pipeline.run_for_article(article, topic, article_id)
            draft_id = result.get("draft_id")
            review = result.get("review") or {}

            if not review.get("passed", False):
                update_article_status(article_id, "quality_failed")
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

        # Plan story and build content via EditorialPlanner + EditorialEngine
        planner = EditorialPlanner()
        plan = planner.plan_cluster(topic, raw)

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

    return scheduler


async def run_knowledge_audit():
    """Run daily knowledge audit and log stale topics + drifts."""
    logger.info("🔍 Running daily knowledge audit...")
    from knowledge.audit import audit_all_topics, detect_knowledge_debt, track_confidence_drift

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
