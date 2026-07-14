# ============================================================
#  bot/commands.py — базовые команды (/start, /digest, /stats,
#  /invalidate_cache, /help, /drafts)
#
#  Вынесено из bot/bot.py. Патчится тестами напрямую (tests/test_bot.py
#  импортирует этот модуль как `cmd_mod`) — если добавляешь новый вызов
#  внешней зависимости внутри этих команд, импортируй её сюда же, а не
#  через bot.bot: иначе patch.object(cmd_mod, "...") перестанет
#  перехватывать.
# ============================================================

from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from bot.bot import dp, is_admin, html_escape
from bot.publishing import get_digest_candidates_count, get_digest_candidates_info
from bot.keyboards import draft_moderation_keyboard
from classifier.classifier import get_topic_ru
from database.db import (
    get_stats, get_pending_drafts,
    count_translations_matching, invalidate_translations_matching,
)


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
