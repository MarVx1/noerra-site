# ============================================================
#  bot/bot.py — Telegram бот с модерацией и дайджестом
# ============================================================

import logging
import asyncio
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.filters import Command

from adaptation.utils import _shorten as safe_shorten

from config.settings import (
    BOT_TOKEN, ADMIN_CHAT_ID,
    MIN_SCORE_TO_MODERATE, TOP_PER_TOPIC, MAX_TOPICS_IN_DIGEST,
)
from database.db import (
    get_article_by_id, update_article_status,
    save_publication, get_stats, get_top_articles_by_topic,
    get_pending_drafts, get_draft_by_id, get_draft_with_context, save_editor_feedback,
    get_claims_for_topic, get_open_questions, get_myths,
    get_latest_knowledge_version, get_knowledge_history,
    get_reasoning_chain,
    count_translations_matching, invalidate_translations_matching,
)
from classifier.classifier import get_topic_ru
from publisher.publisher import create_telegraph_page, send_to_channel

logger = logging.getLogger(__name__)

dp = Dispatcher()

# Ленивая инициализация Bot — тот же приём, что и в publisher.get_bot().
# Bot(token=...) валидирует токен сразу и падает с TokenValidationError на
# пустом BOT_TOKEN. Если создавать его на уровне модуля, то `import bot.bot`
# рушится без .env — и вместе с ним падают даже тесты, не касающиеся Telegram.
_bot_instance: Bot | None = None


def get_bot() -> Bot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(token=BOT_TOKEN)
    return _bot_instance

# Приводим ADMIN_CHAT_ID к числу один раз при старте —
# защищает от ошибки, если в settings.py он случайно указан как строка "123456789"
try:
    ADMIN_ID = int(ADMIN_CHAT_ID)
except (TypeError, ValueError):
    logger.error(
        f"ADMIN_CHAT_ID имеет неверный формат: {ADMIN_CHAT_ID!r}. "
        f"Должно быть число без кавычек, например: ADMIN_CHAT_ID = 123456789"
    )
    ADMIN_ID = None


def is_admin(user_id: int) -> bool:
    """Безопасное сравнение с ADMIN_ID (устойчиво к типам)."""
    return ADMIN_ID is not None and int(user_id) == ADMIN_ID


def html_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


class CallbackLoggingMiddleware(BaseMiddleware):
    """
    Логирует АБСОЛЮТНО ЛЮБОЕ нажатие кнопки, не мешая остальным обработчикам.
    В отличие от обычного @dp.callback_query() без фильтра, middleware
    не "съедает" событие — все обработчики ниже продолжают работать как обычно.
    """
    async def __call__(self, handler, event: CallbackQuery, data: dict):
        logger.info(
            f"🔘 Callback получен: data='{event.data}' "
            f"от user_id={event.from_user.id} "
            f"(ADMIN_ID={ADMIN_ID}, совпадает={is_admin(event.from_user.id)})"
        )
        # ВАЖНО: вызываем handler, иначе кнопка не сработает!
        return await handler(event, data)


dp.callback_query.middleware(CallbackLoggingMiddleware())


# ── Клавиатура одиночной модерации ───────────────────────────

def moderation_keyboard(article_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"approve:{article_id}"),
        InlineKeyboardButton(text="❌ Отклонить",    callback_data=f"reject:{article_id}"),
    ]])


def draft_moderation_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"draft_approve:{draft_id}"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"draft_edit:{draft_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить — слабое исследование", callback_data=f"draft_reject:{draft_id}:weak_study"),
            InlineKeyboardButton(text="❌ Отклонить — плохой текст", callback_data=f"draft_reject:{draft_id}:poor_text"),
        ],
        [
            InlineKeyboardButton(text="❌ Отклонить — мало пользы", callback_data=f"draft_reject:{draft_id}:low_value"),
        ],
    ])


def draft_publish_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    """Клавиатура после одобрения — публикация в канал."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Опубликовать в канал", callback_data=f"draft_publish:{draft_id}"),
        ],
    ])


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
    
    # Формируем полноценный preview — обрезка по границе предложения,
    # чтобы текст не рвался на полуслове
    preview_parts = []
    if lead_text:
        preview_parts.append(f"<b>Лид:</b> {html_escape(safe_shorten(lead_text, 400))}")
    if short_text:
        preview_parts.append(f"\n<b>Краткая версия:</b>\n{html_escape(safe_shorten(short_text, 800))}")
    if body_text:
        preview_parts.append(f"\n<b>Основной текст:</b>\n{html_escape(safe_shorten(body_text, 800))}")
    if full_text and len(full_text) > len(short_text):
        preview_parts.append(f"\n<b>Полная версия (фрагмент):</b>\n{html_escape(safe_shorten(full_text, 600))}")
    
    # Если всё ещё мало текста, берём ещё
    combined_preview = "\n\n".join(preview_parts) if preview_parts else html_escape(safe_shorten(full_text, 1500))
    if len(combined_preview) < 1000 and full_text:
        combined_preview = html_escape(safe_shorten(full_text, 2000))
    
    # Обрезаем до разумного предела (Telegram limit ~4096) — тоже по границе предложения
    if len(combined_preview) > 3800:
        combined_preview = safe_shorten(combined_preview, 3800) + "\n\n... (продолжение в Telegraph)"
    
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


# ── Команды ───────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    digest_count = get_digest_candidates_count()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="/digest"),
        ]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await message.answer(
        "👋 <b>Noerra Bot</b>\n\n"
        f"📬 В дайджесте сейчас: <b>{digest_count}</b> статьи\n\n"
        "Команды:\n"
        "/stats   — статистика\n"
        "/digest  — запросить дайджест прямо сейчас\n"
        "/help    — справка",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@dp.message(Command("digest"))
async def cmd_digest(message: Message):
    if not is_admin(message.from_user.id):
        return

    digest_count, topic_data = get_digest_candidates_info()
    if digest_count == 0:
        await message.answer(
            "📭 Сейчас нет статей для дайджеста. "
            "Подожди, пока парсер соберёт новые материалы."
        )
        return

    topic_lines = []
    for topic, data in sorted(topic_data.items(), key=lambda x: (-x[1]["count"], x[0])):
        titles = data["titles"]
        title_preview = " | ".join(html_escape(t) for t in titles)
        topic_lines.append(
            f"• <b>{get_topic_ru(topic)}</b>: {data['count']} статей\n"
            f"  — {title_preview}"
        )

    await message.answer(
        "⏳ Формирую дайджест...\n"
        f"Сейчас в нём <b>{digest_count}</b> статей.\n\n"
        "Темы:\n"
        + "\n".join(topic_lines),
        parse_mode="HTML",
    )
    from scheduler.scheduler import send_daily_digest
    await send_daily_digest()


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = get_stats()
    reject_lines = ""
    top_reasons = s.get("top_reject_reasons", [])
    if top_reasons:
        reject_lines = "\n\n<b>Топ-3 причины отказа (за неделю):</b>\n"
        for i, (reason, cnt) in enumerate(top_reasons, 1):
            reject_lines += f"  {i}. {reason} ({cnt})\n"
    await message.answer(
        f"📊 <b>Статистика Noerra</b>\n\n"
        f"Всего в базе:   {s['total']}\n"
        f"На модерации:   {s['pending']}\n"
        f"Одобрено:       {s['approved']}\n"
        f"Отклонено:      {s['rejected']}\n"
        f"Опубликовано:   {s['published']}"
        f"{reject_lines}",
        parse_mode="HTML",
    )


@dp.message(Command("invalidate_cache"))
async def cmd_invalidate_cache(message: Message):
    """Точечная очистка кеша переводов (database.translations) по подстроке.

    Нужна на случай, если правка логики перевода (_fix_translation и
    похожее) не должна молча оставлять уже закэшированные до правки
    некорректные переводы навсегда. Двухшаговое подтверждение — команда
    удаляет из БД без возможности отмены.
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Использование: /invalidate_cache &lt;подстрока&gt; [confirm]\n"
            "Например: /invalidate_cache наградум\n\n"
            "Сначала покажет, сколько записей кеша перевода содержат эту подстроку. "
            "Чтобы реально удалить — повторить команду с confirm в конце.",
            parse_mode="HTML",
        )
        return

    substring = parts[1].strip()
    confirmed = len(parts) > 2 and parts[2].strip().lower() == "confirm"
    pattern = f"%{substring}%"

    if not confirmed:
        count = count_translations_matching(pattern)
        if count == 0:
            await message.answer(f"📭 Записей кеша с «{html_escape(substring)}» не найдено.")
            return
        await message.answer(
            f"⚠️ Найдено {count} запис(ей) кеша перевода с «{html_escape(substring)}».\n"
            f"Чтобы удалить: /invalidate_cache {html_escape(substring)} confirm"
        )
        return

    deleted = invalidate_translations_matching(pattern)
    await message.answer(f"🗑 Удалено {deleted} запис(ей) кеша перевода с «{html_escape(substring)}».")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "ℹ️ <b>Как работает Noerra</b>\n\n"
        "1. Каждые 6 часов парсер собирает статьи\n"
        "2. В 10:00 приходит дайджест лучших статей\n"
        "3. Жмёшь ✅ Опубликовать все или 📋 Выбирать по одной\n"
        "4. Статьи уходят в канал через Telegraph\n\n"
        "<b>Контент:</b>\n"
        "/digest — получить дайджест прямо сейчас\n"
        "/drafts — показать драфты для редакции\n\n"
        "<b>Knowledge Core:</b>\n"
        "/knowledge — ядро знаний по темам\n"
        "/claims &lt;тема&gt; — научные утверждения\n"
        "/myths &lt;тема&gt; — мифы и заблуждения\n"
        "/questions &lt;тема&gt; — открытые вопросы\n"
        "/model [тема] — модели понимания\n"
        "/graph &lt;тема&gt; — граф понимания\n"
        "/reasoning &lt;тема&gt; — цепочка выводов\n"
        "/route [id|тема] — маршруты изучения\n"
        "/timeline [тема] — история развития знаний\n\n"
        "<b>Аудит:</b>\n"
        "/audit — аудит базы знаний\n"
        "/memory — редакционная память\n\n"
        "<b>Обслуживание:</b>\n"
        "/invalidate_cache &lt;подстрока&gt; [confirm] — очистить кеш перевода по подстроке",
        parse_mode="HTML",
    )


@dp.message(Command("drafts"))
async def cmd_drafts(message: Message):
    if not is_admin(message.from_user.id):
        return

    drafts = get_pending_drafts(limit=20)
    if not drafts:
        await message.answer("📭 Сейчас нет драфтов для редакции.")
        return

    for draft in drafts:
        preview = html_escape((draft["short_version"] or draft["full_version"] or "")[:600])
        source_line = f"\n<b>Источники:</b> {html_escape(draft['sources'])}" if draft["sources"] else ""
        text = (
            f"📝 <b>Драфт #{draft['id']}</b>\n"
            f"<b>{html_escape(draft['title'])}</b>\n"
            f"<b>Тема:</b> {html_escape(draft['topic'] or '—')}\n"
            f"<b>Формат:</b> {html_escape(draft['format'] or '—')}\n"
            f"<b>Доверие:</b> {draft['confidence']:.2f}\n"
            f"<b>Аудитория:</b> {html_escape(draft['audience'] or '—')}\n"
            f"{source_line}\n\n"
            f"{preview}"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=draft_moderation_keyboard(draft['id']),
            disable_web_page_preview=True,
        )


# ── Knowledge Core команды ────────────────────────────────────

@dp.message(Command("knowledge"))
async def cmd_knowledge(message: Message):
    if not is_admin(message.from_user.id):
        return

    from intelligence.knowledge_audit import audit_all_topics

    audits = audit_all_topics(stale_days=30)
    if not audits:
        await message.answer("📭 В базе знаний пока нет тем.")
        return

    lines = ["🧠 <b>Knowledge Core</b>\n"]
    for a in audits[:10]:
        topic_ru = get_topic_ru(a.topic)
        stale_icon = "⚠️" if a.is_stale else "✅"
        contra_icon = "🔥" if a.has_contradictions else ""
        lines.append(
            f"{stale_icon} <b>{topic_ru}</b> ({a.topic})\n"
            f"   Claims: {a.claims_count} | Confidence: {a.confidence:.2f} | "
            f"Level: {a.consensus_level}\n"
            f"   Open Q: {a.open_questions_count} | Myths: {a.myths_count} {contra_icon}\n"
            f"   <i>{html_escape(a.recommendation)}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("claims"))
async def cmd_claims(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /claims &lt;тема&gt;\nНапример: /claims sleep", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    claims = get_claims_for_topic(topic, limit=20)
    if not claims:
        await message.answer(f"📭 Нет утверждений для темы «{html_escape(topic)}».")
        return

    lines = [f"🔬 <b>Утверждения: {get_topic_ru(topic)}</b>\n"]
    for c in claims[:15]:
        level = c["consensus_level"] or "unknown"
        conf = c["confidence"] or 0
        support = c["support_count"] or 0
        contradict = c["contradict_count"] or 0
        lines.append(
            f"• {html_escape(c['claim_text'][:200])}\n"
            f"  <i>Consensus: {level} | Conf: {conf:.2f} | +{support}/-{contradict}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("myths"))
async def cmd_myths(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /myths &lt;тема&gt;\nНапример: /myths dopamine", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    myths = get_myths(topic, limit=10)
    if not myths:
        await message.answer(f"📭 Нет мифов для темы «{html_escape(topic)}».")
        return

    lines = [f"🚫 <b>Мифы: {get_topic_ru(topic)}</b>\n"]
    for m in myths:
        lines.append(
            f"• <b>Миф:</b> {html_escape(m['myth_text'][:200])}\n"
            f"  <b>Коррекция:</b> {html_escape(m['correction'] or '—')[:200]}\n"
            f"  <i>{html_escape(m['evidence_summary'] or '')}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("questions"))
async def cmd_questions(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /questions &lt;тема&gt;\nНапример: /questions sleep", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    questions = get_open_questions(topic, limit=10)
    if not questions:
        await message.answer(f"📭 Нет открытых вопросов для темы «{html_escape(topic)}».")
        return

    lines = [f"❓ <b>Открытые вопросы: {get_topic_ru(topic)}</b>\n"]
    for q in questions:
        lines.append(f"• {html_escape(q['question'][:300])}\n  <i>Status: {q['current_status']}</i>\n")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("audit"))
async def cmd_audit(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("🔍 Запуск аудита базы знаний... Это может занять до 30 секунд.")

    # Запускаем тяжёлый аудит в отдельном потоке
    async def run_audit():
        from intelligence.knowledge_audit import audit_all_topics, detect_knowledge_debt, track_confidence_drift

        audits = audit_all_topics(stale_days=30)
        if not audits:
            return "📭 Аудит пуст — в базе нет тем."

        stale = [a for a in audits if a.is_stale]
        contradictions = [a for a in audits if a.has_contradictions]
        debt = detect_knowledge_debt(stale_days=30)

        lines = [
            "🔍 <b>Аудит базы знаний</b>\n",
            f"Всего тем: {len(audits)}",
            f"Устаревших: {len(stale)}",
            f"С противоречиями: {len(contradictions)}",
            f"Knowledge Debt: {len(debt)}\n",
        ]

        if stale:
            lines.append("⚠️ <b>Устаревшие темы:</b>")
            for a in stale[:5]:
                lines.append(f"  • {get_topic_ru(a.topic)} ({a.topic}) — {a.last_updated}")
            lines.append("")

        if debt:
            lines.append("📋 <b>Knowledge Debt:</b>")
            for d in debt[:5]:
                lines.append(f"  • {get_topic_ru(d['topic'])} — {d['new_articles']} новых статей, last: {d['last_knowledge_update']}")
            lines.append("")

        # Confidence drift for first 3 active topics
        drifts_found = False
        for a in audits[:3]:
            if a.claims_count > 0:
                drifts = track_confidence_drift(a.topic)
                significant = [d for d in drifts if d.direction != "stable"]
                if significant:
                    if not drifts_found:
                        lines.append("📉 <b>Confidence Drift:</b>")
                        drifts_found = True
                    for d in significant[:3]:
                        emoji = "📈" if d.direction == "increased" else "📉"
                        lines.append(
                            f"  {emoji} {get_topic_ru(d.topic)}: "
                            f"{d.previous_confidence:.2f} → {d.current_confidence:.2f} "
                            f"({d.direction}, Δ={d.delta:+.2f})"
                        )

        if not drifts_found and not stale and not debt:
            lines.append("✅ База знаний в хорошем состоянии.")

        return "\n".join(lines)

    try:
        result = await asyncio.to_thread(run_audit)
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        await message.answer(f"❌ Ошибка аудита: {e}", parse_mode="HTML")


@dp.message(Command("route"))
async def cmd_route(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.routes import list_routes, get_route, route_to_text, suggest_route_for_topic

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        routes = list_routes()
        if not routes:
            await message.answer("📭 Маршруты изучения пока не настроены.")
            return
        lines = ["📚 <b>Маршруты изучения</b>\n"]
        for r in routes:
            lines.append(f"• <b>{r['title']}</b> ({r['time']})\n  {r['description']}\n  /route {r['id']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    route_id = parts[1].strip()
    route = get_route(route_id)
    if not route:
        route = suggest_route_for_topic(route_id)
    if not route:
        await message.answer(f"Маршрут «{html_escape(route_id)}» не найден.")
        return

    await message.answer(route_to_text(route), parse_mode="HTML")


@dp.message(Command("reasoning"))
async def cmd_reasoning(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /reasoning &lt;тема&gt;\n"
            "Показывает reasoning chain для топ-claim по теме.",
            parse_mode="HTML",
        )
        return

    topic = parts[1].strip().lower()
    claims = get_claims_for_topic(topic, limit=5)
    if not claims:
        await message.answer(f"📭 Нет утверждений для темы «{html_escape(topic)}».")
        return

    from domain.knowledge.reasoning import build_reasoning_chain, chain_to_text
    from database.db import get_consensus_for_topic

    top_claim = claims[0]
    consensus_rows = get_consensus_for_topic(topic, limit=10)

    consensus = {}
    for cs in consensus_rows:
        if cs["claim_id"] == top_claim["id"]:
            consensus = dict(cs)
            break

    evidence = [dict(c) for c in claims]
    chain = build_reasoning_chain(
        topic=topic,
        claim_text=top_claim["claim_text"],
        evidence=evidence,
        consensus=consensus,
    )

    await message.answer(chain_to_text(chain), parse_mode="HTML")


@dp.message(Command("model"))
async def cmd_model(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        from domain.knowledge.mental_models import list_mental_models
        models = list_mental_models()
        if not models:
            await message.answer("📭 Модели понимания пока не настроены.")
            return
        lines = ["🧩 <b>Модели понимания</b>\n"]
        for m in models:
            lines.append(f"• <b>{m['topic_ru']}</b> ({m['topic']})\n  {m['title']}\n  /model {m['topic']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    from domain.knowledge.mental_models import get_mental_model, model_to_text
    topic = parts[1].strip().lower()
    model = get_mental_model(topic)
    if not model:
        await message.answer(f"Модель для темы «{html_escape(topic)}» не найдена.")
        return

    await message.answer(model_to_text(model), parse_mode="HTML")


@dp.message(Command("graph"))
async def cmd_graph(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /graph &lt;тема&gt;\n"
            "Показывает граф понимания по теме.",
            parse_mode="HTML",
        )
        return

    topic = parts[1].strip().lower()
    await message.answer(f"🕸 Строю граф для темы «{html_escape(topic)}»...")

    async def build_graph():
        from domain.knowledge.graph import build_graph_from_claims, graph_to_text
        from database.db import get_consensus_for_topic

        claims = get_claims_for_topic(topic, limit=20)
        if not claims:
            return f"📭 Нет данных для графа по теме «{html_escape(topic)}»."

        consensus = get_consensus_for_topic(topic, limit=20)
        open_qs = get_open_questions(topic, limit=10)
        myths = get_myths(topic, limit=10)

        claims_list = [dict(c) for c in claims]
        consensus_list = [dict(c) for c in consensus]
        questions_list = [row["question"] for row in open_qs]
        myths_list = [row["myth_text"] for row in myths]

        graph = build_graph_from_claims(
            topic=topic,
            claims=claims_list,
            consensus=consensus_list,
            myths=myths_list,
            open_questions=questions_list,
        )

        return graph_to_text(graph, topic)

    try:
        result = await asyncio.to_thread(build_graph)
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Graph build failed: {e}")
        await message.answer(f"❌ Ошибка построения графа: {e}", parse_mode="HTML")


@dp.message(Command("memory"))
async def cmd_memory(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.editorial_memory import build_editorial_memory, memory_to_text
    from database.db import get_editorial_decisions

    decisions_rows = get_editorial_decisions(limit=100)
    if not decisions_rows:
        await message.answer("📭 Редакционная память пуста — пока нет решений.")
        return

    decisions = [dict(row) for row in decisions_rows]
    memory = build_editorial_memory(decisions)
    memory.analyze_patterns()

    await message.answer(memory_to_text(memory), parse_mode="HTML")


@dp.message(Command("timeline"))
async def cmd_timeline(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.timeline import get_timeline, list_timelines, timeline_to_text

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        timelines = list_timelines()
        if not timelines:
            await message.answer("📭 Временные шкалы пока не настроены.")
            return
        lines = ["📜 <b>История развития знаний</b>\n"]
        for t in timelines:
            lines.append(f"• <b>{t['topic_ru']}</b> ({t['topic']}): {t['events']} событий\n  /timeline {t['topic']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    timeline = get_timeline(topic)
    if not timeline:
        await message.answer(f"Временная шкала для темы «{html_escape(topic)}» не найдена.")
        return

    await message.answer(timeline_to_text(timeline), parse_mode="HTML")


# ── Кнопки одиночной модерации ────────────────────────────────

@dp.callback_query(F.data.startswith("approve:"))
async def on_approve(callback: CallbackQuery):
    logger.info(f"✅ on_approve callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to approve")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    article_id = int(callback.data.split(":")[1])
    logger.info(f"Approving article_id={article_id}")
    await callback.answer("Публикую...", show_alert=False)
    ok, result = await _publish_article(article_id)
    suffix = f"\n\n✅ Опубликовано → {result}" if ok else f"\n\n❌ Ошибка: {result}"
    try:
        await callback.message.edit_text(
            callback.message.text + suffix,
        )
        logger.info(f"Article {article_id} published successfully: {result}")
    except Exception as e:
        logger.error(f"Failed to edit message after approve: {e}")
        pass


@dp.callback_query(F.data.startswith("reject:"))
async def on_reject(callback: CallbackQuery):
    logger.info(f"❌ on_reject callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to reject")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    article_id = int(callback.data.split(":")[1])
    logger.info(f"Rejecting article_id={article_id}")
    update_article_status(article_id, "rejected")
    await callback.answer("Отклонено", show_alert=False)
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отклонено",
        )
        logger.info(f"Article {article_id} rejected")
    except Exception as e:
        logger.error(f"Failed to edit message after reject: {e}")
        pass


@dp.callback_query(F.data.startswith("draft_approve:"))
async def on_draft_approve(callback: CallbackQuery):
    logger.info(f"📝 on_draft_approve callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_approve")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    draft_id = int(callback.data.split(":")[1])
    logger.info(f"Approving draft_id={draft_id}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "approved", reason="approved by editor")
    if draft["article_id"]:
        update_article_status(draft["article_id"], "approved")

    # Показываем кнопку "Опубликовать" после одобрения
    keyboard = draft_publish_keyboard(draft_id)
    await callback.answer("Одобрено! Теперь можно опубликовать.", show_alert=False)
    try:
        # ВАЖНО: не используем parse_mode="HTML" — callback.message.text это
        # уже plain text (с literal <b>, </b>, <a href='...'> из &lt;b&gt; и т.д.),
        # а parse_mode="HTML" заставит Telegram попытаться распартировать эти
        # символы как HTML-теги, что вызовет "Unexpected end tag".
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ Одобрено\n\nНажмите «Опубликовать в канал», чтобы отправить статью.",
            reply_markup=keyboard,
        )
        logger.info(f"Draft {draft_id} approved, publish button shown")
    except Exception as e:
        logger.error(f"Failed to edit message after draft_approve: {e}")
        pass


@dp.callback_query(F.data.startswith("draft_reject:"))
async def on_draft_reject(callback: CallbackQuery):
    logger.info(f"📝 on_draft_reject callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_reject")
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    parts = callback.data.split(":")
    draft_id = int(parts[1])
    reason = parts[2] if len(parts) > 2 else "rejected by editor"
    logger.info(f"Rejecting draft_id={draft_id}, reason={reason}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "rejected", reason=reason)
    if draft["article_id"]:
        update_article_status(draft["article_id"], "rejected")

    await callback.answer("Отклонено", show_alert=False)
    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ Отклонено ({reason})",
        )
        logger.info(f"Draft {draft_id} rejected: {reason}")
    except Exception as e:
        logger.error(f"Failed to edit message after draft_reject: {e}")
        pass


@dp.callback_query(F.data.startswith("draft_edit:"))
async def on_draft_edit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    draft_id = int(callback.data.split(":")[1])
    draft = get_draft_by_id(draft_id)
    if not draft:
        await callback.answer("Драфт не найден")
        return

    save_editor_feedback(draft_id, str(callback.from_user.id), "edit_requested", reason="editor requested edits")
    if draft["article_id"]:
        update_article_status(draft["article_id"], "edit_requested")

    await callback.answer("Редактирование запрошено")
    keyboard = draft_publish_keyboard(draft_id)
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✏️ Редактирование запрошено\n\nПосле редакции нажмите «Опубликовать в канал».",
            reply_markup=keyboard,
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("draft_publish:"))
async def on_draft_publish(callback: CallbackQuery):
    """Публикует одобренный драфт в канал: Telegraph → Telegram."""
    logger.info(f"📤 on_draft_publish callback: data={callback.data}, user={callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        logger.warning(f"Unauthorized user {callback.from_user.id} tried to draft_publish")
        await callback.answer("❌ Нет прав", show_alert=True)
        return

    draft_id = int(callback.data.split(":")[1])
    logger.info(f"Publishing draft_id={draft_id}")
    draft = get_draft_by_id(draft_id)
    if not draft:
        logger.error(f"Draft {draft_id} not found")
        await callback.answer("Драфт не найден", show_alert=True)
        return

    article_id = draft["article_id"]
    if not article_id:
        await callback.answer("❌ Нет статьи для публикации", show_alert=True)
        return

    await callback.answer("Публикую в канал...", show_alert=False)

    # Публикуем через _publish_article (Telegraph + канал)
    ok, result = await _publish_article(article_id)

    if ok:
        try:
            await callback.message.edit_text(
                callback.message.text + f"\n\n📤 Опубликовано в канал\n🔗 {result}",
            )
            logger.info(f"Draft {draft_id} published to channel: {result}")
        except Exception as e:
            logger.error(f"Failed to edit message after publish: {e}")
    else:
        try:
            await callback.message.edit_text(
                callback.message.text + f"\n\n❌ Ошибка публикации: {result}",
            )
        except Exception:
            pass
        logger.error(f"Draft {draft_id} publish failed: {result}")


# ── Кнопки дайджеста ─────────────────────────────────────────

@dp.callback_query(F.data.startswith("digest_approve:"))
async def on_digest_approve(callback: CallbackQuery):
    """Публикует все статьи из дайджеста."""
    if not is_admin(callback.from_user.id):
        return
    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer(f"Публикую {len(ids)} статей...")
    await callback.message.edit_text(
        callback.message.text + f"\n\n⏳ Публикую {len(ids)} статей...",
    )

    ok_count = 0
    for article_id in ids:
        ok, _ = await _publish_article(article_id)
        if ok:
            ok_count += 1

    try:
        await callback.message.edit_text(
            callback.message.text.replace(f"⏳ Публикую {len(ids)} статей...", "") +
            f"\n\n✅ Опубликовано: {ok_count} из {len(ids)}",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("digest_one_by_one:"))
async def on_digest_one_by_one(callback: CallbackQuery):
    """Отправляет статьи по одной для индивидуальной модерации."""
    if not is_admin(callback.from_user.id):
        return
    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer("Отправляю по одной...")
    await callback.message.edit_text(
        callback.message.text + f"\n\n📋 Отправляю {len(ids)} статей по одной...",
    )
    for article_id in ids:
        await send_for_moderation(article_id)


@dp.callback_query(F.data == "digest_reject_all")
async def on_digest_reject_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Пропущено")
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Дайджест пропущен",
        )
    except Exception:
        pass


# ── Запуск ────────────────────────────────────────────────────

async def start_bot():
    logger.info("Бот запущен")
    await dp.start_polling(get_bot())


# ── Кнопки кластерного поста ──────────────────────────────────

@dp.callback_query(F.data.startswith("cluster_approve:"))
async def on_cluster_approve(callback: CallbackQuery):
    """Первый шаг: запрос подтверждения перед публикацией кластера."""
    if not is_admin(callback.from_user.id):
        return

    ids = callback.data.split(":")[1]
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, опубликовать",
                callback_data=f"cluster_confirm:{ids}",
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"cluster_reject:{ids}",
            ),
        ],
    ])

    await callback.answer()
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n⚠️ Подтвердите публикацию кластера?",
            reply_markup=confirm_keyboard,
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("cluster_confirm:"))
async def on_cluster_confirm(callback: CallbackQuery):
    """Второй шаг: реальная публикация кластера после подтверждения."""
    if not is_admin(callback.from_user.id):
        return

    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    await callback.answer("Публикую...")

    from database.db import get_article_by_id
    from adaptation.cluster import build_cluster_post, build_telegraph_cluster
    from parsers.base import RawArticle
    from classifier.classifier import get_topic_ru

    # Собираем статьи
    articles_data = [get_article_by_id(aid) for aid in ids if get_article_by_id(aid)]
    if not articles_data:
        await callback.answer("Статьи не найдены")
        return

    topic = articles_data[0]["topic"]

    raw = [
        RawArticle(
            title=a["title"],
            url=a["url"] or "",
            abstract=a["abstract"] or "",
            source=a["source"],
        )
        for a in articles_data
    ]

    # Telegraph
    from database.db import get_youtube_by_topic
    yt_row = get_youtube_by_topic(topic)
    yt_article = None
    if yt_row:
        yt_article = RawArticle(
            title=yt_row["title"],
            url=yt_row["url"] or "",
            abstract=yt_row["abstract"] or "",
            source="youtube",
        )

    telegraph_content = build_telegraph_cluster(topic, raw, yt_article)
    topic_ru = get_topic_ru(topic)

    telegraph_url = create_telegraph_page(
        title=f"Noerra: {topic_ru}",
        summary_ru=telegraph_content,
        source_url=articles_data[0]["url"] or "",
    )

    if not telegraph_url:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Ошибка Telegraph",
        )
        return

    # Финальный пост с реальным Telegraph URL
    final_post = build_cluster_post(
        topic=topic,
        articles=raw,
        youtube_article=yt_article,
        telegraph_url=telegraph_url,
    )

    msg_id = await send_to_channel(final_post)

    for aid in ids:
        update_article_status(aid, "published")
        save_publication(aid, telegraph_url, msg_id or 0)

    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Опубликовано → {telegraph_url}",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("cluster_reject:"))
async def on_cluster_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ids = [int(i) for i in callback.data.split(":")[1].split(",")]
    for aid in ids:
        update_article_status(aid, "rejected")

    await callback.answer("Пропущено")
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Пропущено",
        )
    except Exception:
        pass