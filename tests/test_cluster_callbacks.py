"""Тесты bot/cluster_callbacks.py — кнопки кластерного поста.

Регрессия 2026-07-15 (первый живой запуск бота): on_cluster_confirm вызывал
асинхронный create_telegraph_page() без await, из-за чего в save_publication
и в текст поста утекал сам объект coroutine вместо URL — Telegram отвечал
"can't parse entities: Unsupported start tag 'coroutine'", а SQLite падал с
"type 'coroutine' is not supported".
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bot.bot as b
import bot.cluster_callbacks as cc


ADMIN = 123


def _callback(data: str, user_id: int = ADMIN, text: str = "Original text"):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message.text = text
    cb.message.edit_text = AsyncMock()
    return cb


ARTICLE = {
    "id": 1, "title": "T", "url": "https://example.com", "abstract": "A",
    "source": "pubmed", "topic": "sleep",
}


class TestOnClusterConfirm(unittest.IsolatedAsyncioTestCase):
    async def test_awaits_telegraph_page_and_saves_string_url(self):
        """Регрессия: create_telegraph_page — coroutine, её обязательно
        нужно await'ить, иначе telegraph_url — это объект coroutine, а не
        строка, и он утекает и в save_publication(), и в текст поста."""
        cb = _callback("cluster_confirm:1")
        telegraph_url = "https://telegra.ph/x"

        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cc, "get_article_by_id", return_value=ARTICLE), \
             patch("database.db.get_youtube_by_topic", return_value=None), \
             patch("adaptation.cluster.build_telegraph_cluster", return_value="content"), \
             patch("adaptation.cluster.build_cluster_post", return_value="post"), \
             patch("classifier.classifier.get_topic_ru", return_value="Сон"), \
             patch.object(cc, "create_telegraph_page", AsyncMock(return_value=telegraph_url)), \
             patch.object(cc, "send_to_channel", AsyncMock(return_value=42)), \
             patch.object(cc, "update_article_status"), \
             patch.object(cc, "save_publication") as save_pub:
            await cc.on_cluster_confirm(cb)

        # save_publication должен получить настоящую строку URL, а не coroutine.
        saved_url = save_pub.call_args.args[1]
        self.assertIsInstance(saved_url, str)
        self.assertEqual(saved_url, telegraph_url)
        self.assertIn(telegraph_url, cb.message.edit_text.await_args.args[0])

    async def test_reports_telegraph_error_when_creation_fails(self):
        cb = _callback("cluster_confirm:1")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cc, "get_article_by_id", return_value=ARTICLE), \
             patch("database.db.get_youtube_by_topic", return_value=None), \
             patch("adaptation.cluster.build_telegraph_cluster", return_value="content"), \
             patch("classifier.classifier.get_topic_ru", return_value="Сон"), \
             patch.object(cc, "create_telegraph_page", AsyncMock(return_value=None)), \
             patch.object(cc, "save_publication") as save_pub:
            await cc.on_cluster_confirm(cb)

        save_pub.assert_not_called()
        self.assertIn("Ошибка Telegraph", cb.message.edit_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
