# ============================================================
#  bot/reactions.py — учёт реакций на посты канала (Business Model
#  MVP шаг 3: "проверить реакцию аудитории", см. project memory
#  project-noerra-business-model).
#
#  message_reaction_count — агрегированное Telegram-событие: сколько
#  раз каждый эмодзи стоит под постом *сейчас*, без деанона того, кто
#  поставил реакцию (для каналов это единственный источник реакций —
#  message_reaction с личностью юзера сюда не приходит, реакции в
#  каналах анонимны).
# ============================================================

import logging
from aiogram.types import MessageReactionCountUpdated

from bot.bot import dp
from database.db import save_post_reaction_counts

logger = logging.getLogger(__name__)


def _reaction_label(reaction) -> str:
    """ReactionTypeEmoji -> emoji-строка, ReactionTypeCustomEmoji -> id."""
    return getattr(reaction, "emoji", None) or f"custom:{getattr(reaction, 'custom_emoji_id', '?')}"


@dp.message_reaction_count()
async def on_message_reaction_count(event: MessageReactionCountUpdated):
    counts = {_reaction_label(r.type): r.total_count for r in event.reactions}
    save_post_reaction_counts(event.chat.id, event.message_id, counts)
    logger.info(
        f"Реакции обновлены | chat={event.chat.id} message_id={event.message_id} | {counts}"
    )
