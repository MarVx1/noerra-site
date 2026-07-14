# ============================================================
#  bot/keyboards.py — inline-клавиатуры модерации
# ============================================================

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
