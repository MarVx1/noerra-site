# ============================================================
#  bot/bot.py — ядро Telegram-бота: диспетчер, ленивая
#  инициализация Bot, проверка админа, общие утилиты.
#
#  Обработчики команд/кнопок вынесены в отдельные модули (см. импорты
#  в конце файла) — каждый регистрируется на этом же `dp`.
# ============================================================

import logging
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import CallbackQuery

from config.settings import BOT_TOKEN, ADMIN_CHAT_ID

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


# ── Запуск ────────────────────────────────────────────────────

async def start_bot():
    logger.info("Бот запущен")
    await dp.start_polling(get_bot())


# Регистрация обработчиков, вынесенных в отдельные модули. Импорт должен
# идти здесь, в конце файла, — dp/is_admin/html_escape/get_bot уже
# определены выше, а сами модули при импорте регистрируют свои
# @dp.message/@dp.callback_query на этом же диспетчере.
from bot import keyboards  # noqa: F401,E402
from bot import publishing  # noqa: F401,E402
# Re-export: scheduler.py делает `from bot.bot import send_draft_for_editor`
# (см. scheduler/scheduler.py:_get_send_draft) — внешний потребитель за
# пределами пакета bot, поэтому имя должно быть видно и на bot.bot, а не
# только на bot.publishing.
from bot.publishing import send_draft_for_editor  # noqa: F401,E402
from bot import commands  # noqa: F401,E402
from bot import callbacks  # noqa: F401,E402
from bot import knowledge_commands  # noqa: F401,E402
from bot import cluster_callbacks  # noqa: F401,E402
