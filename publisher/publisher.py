# ============================================================
#  publisher/publisher.py — публикация в Telegraph и Telegram
# ============================================================

import re
import asyncio
import logging
from html import unescape
from aiogram import Bot
from config.settings import (
    BOT_TOKEN, CHANNEL_ID,
    TELEGRAPH_TOKEN, TELEGRAPH_AUTHOR, TELEGRAPH_AUTHOR_URL,
)
import requests

logger = logging.getLogger(__name__)

# Lazy bot initialization — avoids crash on import when .env is missing
_bot_instance = None
def get_bot():
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(token=BOT_TOKEN)
    return _bot_instance


# ── Telegraph ─────────────────────────────────────────────────

def _create_telegraph_page_sync(title: str, summary_ru: str, source_url: str) -> str | None:
    """Синхронная реализация создания Telegraph (для запуска в to_thread)."""
    def clean_paragraph(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        return unescape(text).strip()

    paragraphs = [clean_paragraph(p) for p in summary_ru.split("\n") if clean_paragraph(p)]
    nodes = []
    for para in paragraphs:
        nodes.append({"tag": "p", "children": [para]})

    nodes.append({
        "tag": "p",
        "children": [
            {"tag": "a", "attrs": {"href": source_url}, "children": ["→ Оригинальная статья"]}
        ]
    })

    try:
        resp = requests.post(
            "https://api.telegra.ph/createPage",
            json={
                "access_token":  TELEGRAPH_TOKEN,
                "title":         title[:256],
                "author_name":   TELEGRAPH_AUTHOR,
                "author_url":    TELEGRAPH_AUTHOR_URL,
                "content":       nodes,
                "return_content": False,
            },
            timeout=30,  # Увеличенный таймаут
        )
        data = resp.json()
        if data.get("ok"):
            url = "https://telegra.ph/" + data["result"]["path"]
            logger.info(f"Telegraph создан: {url}")
            return url
        else:
            logger.error(f"Telegraph API error: {data}")
    except Exception as e:
        logger.error(f"Telegraph exception: {e}")
    return None


async def create_telegraph_page(title: str, summary_ru: str, source_url: str) -> str | None:
    """
    Асинхронная обёртка для создания Telegraph.
    Запускает синхронную версию в отдельном потоке, чтобы не блокировать event loop.
    """
    return await asyncio.to_thread(
        _create_telegraph_page_sync,
        title, summary_ru, source_url
    )


# ── Telegram ──────────────────────────────────────────────────

async def send_to_channel(post_text: str) -> int | None:
    """
    Публикует пост в канал.
    Возвращает telegram message_id или None.
    """
    try:
        msg = await get_bot().send_message(
            chat_id=CHANNEL_ID,
            text=post_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info(f"Опубликовано в канал, message_id={msg.message_id}")
        return msg.message_id
    except Exception as e:
        logger.error(f"Ошибка публикации в канал: {e}")
    return None


async def send_to_admin(admin_id: int, text: str, reply_markup=None) -> int | None:
    """Отправляет сообщение администратору."""
    try:
        msg = await get_bot().send_message(
            chat_id=admin_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return msg.message_id
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")
    return None
