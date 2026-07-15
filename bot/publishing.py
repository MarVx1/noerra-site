# ============================================================
#  bot/publishing.py — публикация статей и отправка на модерацию
#  (_publish_article, send_for_moderation, send_draft_for_editor,
#  get_digest_candidates_info/count)
#
#  Вынесено из bot/bot.py. Патчится тестами напрямую (tests/test_bot.py
#  импортирует этот модуль как `pub`) — если добавляешь новый вызов
#  внешней зависимости внутри этих функций, импортируй её сюда же, а не
#  через bot.bot: иначе patch.object(pub, "...") перестанет перехватывать.
# ============================================================

import asyncio
import logging

from config.settings import MIN_SCORE_TO_MODERATE, TOP_PER_TOPIC, MAX_TOPICS_IN_DIGEST
from database.db import (
    get_article_by_id, update_article_status, save_publication,
    get_top_articles_by_topic, get_draft_with_context,
)
from publisher.publisher import create_telegraph_page, send_to_channel
from adaptation.utils import _shorten as safe_shorten
from adaptation.utils import _shorten_by_paragraphs
from adaptation.utils import esc_preserve_own_tags

from bot.bot import get_bot, ADMIN_ID, html_escape
from bot.keyboards import moderation_keyboard, draft_moderation_keyboard

logger = logging.getLogger(__name__)


def get_digest_candidates_info() -> tuple[int, dict[str, dict[str, object]]]:
    """Возвращает количество статей для дайджеста и данные по темам."""
    raw_articles = get_top_articles_by_topic(
        top_per_topic=TOP_PER_TOPIC,
        max_topics=MAX_TOPICS_IN_DIGEST,
        min_score=MIN_SCORE_TO_MODERATE,
    )
    topic_data: dict[str, dict[str, object]] = {}
    for item in raw_articles:
        topic = item["topic"] or "unknown"
        if topic not in topic_data:
            topic_data[topic] = {"count": 0, "titles": []}
        topic_data[topic]["count"] += 1
        titles = topic_data[topic]["titles"]
        if len(titles) < 2:
            titles.append(item["title"])
    return len(raw_articles), topic_data


def get_digest_candidates_count() -> int:
    """Возвращает число статей, готовых для дайджеста."""
    return get_digest_candidates_info()[0]


# ── Публикация одной статьи ───────────────────────────────────

async def _publish_article(article_id: int) -> tuple[bool, str]:
    """
    Публикует статью: Telegraph → Telegram канал.
    Возвращает (успех, telegraph_url или сообщение об ошибке).
    """
    # DB запрос в потоке — не блокирует event loop
    article = await asyncio.to_thread(get_article_by_id, article_id)
    if not article:
        return False, "Статья не найдена"

    # Telegraph — асинхронный (в отдельном потоке)
    telegraph_url = await create_telegraph_page(
        title=article["title"],
        summary_ru=article["summary_ru"] or article["abstract"] or "",
        source_url=article["url"],
    )
    if not telegraph_url:
        return False, "Ошибка создания Telegraph-страницы"

    post_text = (article["post_text"] or "").replace("TELEGRAPH_URL", telegraph_url)
    if not post_text:
        post_text = (
            f"<b>{article['title']}</b>\n\n"
            f"📖 <a href='{telegraph_url}'>Читать</a>  "
            f"🔗 <a href='{article['url']}'>Источник</a>"
        )

    msg_id = await send_to_channel(post_text)

    # DB запись в потоке
    def _save_publish():
        update_article_status(article_id, "published")
        save_publication(article_id, telegraph_url, msg_id or 0)

    await asyncio.to_thread(_save_publish)
    return True, telegraph_url


# ── Отправка одной статьи на модерацию ───────────────────────

async def send_for_moderation(article_id: int):
    article = get_article_by_id(article_id)
    if not article:
        return

    preview = html_escape((article['summary_ru'] or article['abstract'] or '')[:600])
    source_link = f"\n🔗 <a href='{article['url']}'>Оригинал</a>" if article['url'] else ""

    text = (
        f"📋 <b>Статья на модерацию</b>\n\n"
        f"<b>Тема:</b> {html_escape(article['topic'] or '—')}\n"
        f"<b>Score:</b> {article['score']}\n"
        f"<b>Источник:</b> {html_escape(article['source'])}\n\n"
        f"<b>{html_escape(article['title'])}</b>\n\n"
        f"{preview}"
        f"{source_link}"
    )

    try:
        await get_bot().send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=moderation_keyboard(article_id),
            disable_web_page_preview=True,
        )
        update_article_status(article_id, "pending")
    except Exception as e:
        logger.error(f"Ошибка отправки на модерацию: {e}")


async def send_draft_for_editor(draft_id: int):
    draft_data = get_draft_with_context(draft_id)
    if not draft_data:
        return

    draft = draft_data
    article = draft_data.get("article", {})
    passport = draft_data.get("passport", {})

    # Расширенный preview: short_version (основной текст) + начало full_version
    short_text = draft.get('short_version') or ""
    full_text = draft.get('full_version') or ""
    lead_text = draft.get('lead') or ""
    body_text = draft.get('body') or ""

    # Формируем полноценный preview. lead — одно предложение, обрезка по
    # границе предложения ей не вредит. body/full_version — многоабзацный
    # текст с парами "переход-обещание + то, что обещано" (аналогия,
    # значимость) в соседних абзацах — для них обрезка по предложению
    # может обрубить между обещанием и содержанием (см. _shorten_by_paragraphs).
    preview_parts = []
    if lead_text:
        preview_parts.append(f"<b>Лид:</b> {html_escape(safe_shorten(lead_text, 400))}")
    if short_text:
        preview_parts.append(f"\n<b>Краткая версия:</b>\n{html_escape(safe_shorten(short_text, 800))}")
    # esc_preserve_own_tags, не html_escape: body/full_version — не голый
    # текст, там уже есть наши <i>/<b> (аналогия, уровень доказательности) —
    # html_escape ломал бы их в буквальные "&lt;i&gt;" (см. docstring
    # esc_preserve_own_tags, тот же баг нашёлся живьём в scheduler.py).
    if body_text:
        preview_parts.append(f"\n<b>Основной текст (уйдёт в Telegram):</b>\n{esc_preserve_own_tags(_shorten_by_paragraphs(body_text, 800))}")
    if full_text and len(full_text) > len(short_text):
        preview_parts.append(f"\n<b>Полная версия (уйдёт в Telegraph, фрагмент):</b>\n{esc_preserve_own_tags(_shorten_by_paragraphs(full_text, 600))}")

    # Если всё ещё мало текста, берём ещё
    combined_preview = "\n\n".join(preview_parts) if preview_parts else esc_preserve_own_tags(_shorten_by_paragraphs(full_text, 1500))
    if len(combined_preview) < 1000 and full_text:
        combined_preview = esc_preserve_own_tags(_shorten_by_paragraphs(full_text, 2000))

    # Обрезаем до разумного предела (Telegram limit ~4096) — тоже по границе абзаца
    if len(combined_preview) > 3800:
        combined_preview = _shorten_by_paragraphs(combined_preview, 3800) + "\n\n... (продолжение в Telegraph)"

    # Источники
    source_line = f"\n<b>Источники:</b> {html_escape(draft.get('sources', ''))}" if draft.get('sources') else ""
    if article.get('url'):
        source_line += f"\n🔗 <a href='{html_escape(article['url'])}'>Оригинал статьи</a>"

    # Editorial metadata
    editorial_meta = []
    if draft.get('format'):
        editorial_meta.append(f"📋 <b>Формат:</b> {html_escape(draft['format'])}")
    if draft.get('audience'):
        editorial_meta.append(f"👥 <b>Аудитория:</b> {html_escape(draft['audience'])}")
    if body_text:
        section_count = len([l for l in body_text.split('\n') if l.strip()])
        editorial_meta.append(f"📊 <b>Структура:</b> {section_count} блоков")

    editorial_info = "\n".join(editorial_meta) if editorial_meta else ""

    # Research passport data (научная информация)
    passport_info = []
    if passport.get('study_type') and passport['study_type'] != 'unknown':
        type_ru = {
            "meta_analysis": "Мета-анализ",
            "systematic_review": "Систематический обзор",
            "randomized_controlled_trial": "Рандомизированное контролируемое исследование",
            "cohort_study": "Когортное исследование",
            "observational_study": "Наблюдательное исследование",
            "case_report": "Описание случая",
            "review": "Обзор",
        }.get(passport['study_type'], passport['study_type'])
        passport_info.append(f"🔬 <b>Тип исследования:</b> {type_ru}")

    if passport.get('evidence_strength'):
        strength_ru = {
            "high": "Высокий",
            "moderate_high": "Выше среднего",
            "moderate": "Средний",
            "limited": "Ограниченный",
            "weak": "Низкий",
            "preliminary": "Предварительный",
        }.get(passport['evidence_strength'], passport['evidence_strength'])
        passport_info.append(f"💎 <b>Уровень доказательности:</b> {strength_ru}")

    if passport.get('sample_size'):
        passport_info.append(f"📈 <b>Размер выборки:</b> {html_escape(passport['sample_size'])}")

    if passport.get('limitations'):
        limitations = passport['limitations'][:200]
        passport_info.append(f"⚠️ <b>Ограничения:</b> {html_escape(limitations)}")

    if passport.get('key_findings'):
        findings = passport['key_findings']
        if isinstance(findings, str):
            findings = findings[:200]
        elif isinstance(findings, list):
            findings = "; ".join(findings[:3])[:200]
        passport_info.append(f"🎯 <b>Ключевые находки:</b> {html_escape(findings)}")

    passport_text = "\n".join(passport_info) if passport_info else ""

    text = (
        f"📝 <b>Драфт к публикации</b>\n\n"
        f"<b>🏷 {html_escape(draft.get('title', ''))}</b>\n\n"
        f"<b>Тема:</b> {html_escape(draft.get('topic') or '—')}\n"
        f"<b>Доверие:</b> {draft.get('confidence', 0):.2f}\n"
        f"{editorial_info}\n"
        f"{passport_text}\n"
        f"{source_line}\n\n"
        f"{'═' * 45}\n\n"
        f"{combined_preview}"
    )

    try:
        await get_bot().send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=draft_moderation_keyboard(draft_id),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки драфта редактору: {e}")
