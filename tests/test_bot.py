"""Тесты Telegram-слоя (bot/bot.py + вынесенные модули bot/keyboards.py,
bot/publishing.py, bot/callbacks.py, bot/commands.py).

Telegram API и БД полностью замоканы — тесты офлайн и детерминированы.

ADMIN_ID патчится в каждом тесте явно, а не берётся из окружения: локально
он приходит из .env разработчика, а в CI из workflow (ADMIN_CHAT_ID=1), и
тест, завязанный на конкретное значение, ломался бы в одном из двух мест.

Важно: patch.object(<module>, "name", ...) перехватывает только вызовы,
чьи __globals__ указывают на именно этот <module> — то есть только вызовы
ИЗНУТРИ функций, физически определённых в этом модуле. Поэтому здесь
несколько module-алиасов (b/kb/pub/cb_mod/cmd_mod) вместо одного — каждый
патч целится в модуль, где соответствующий обработчик реально живёт.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import bot.bot as b
import bot.keyboards as kb
import bot.publishing as pub
import bot.callbacks as cb_mod
import bot.commands as cmd_mod


ADMIN = 123
STRANGER = 999


def _callback(data: str, user_id: int = ADMIN, text: str = "Original text"):
    """Собирает мок CallbackQuery с асинхронными answer()/message.edit_text()."""
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = user_id
    cb.answer = AsyncMock()
    cb.message.text = text
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _message(text: str = "/cmd", user_id: int = ADMIN):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    return msg


class TestIsAdmin(unittest.TestCase):
    def test_matches_admin_id(self):
        with patch.object(b, "ADMIN_ID", ADMIN):
            self.assertTrue(b.is_admin(ADMIN))

    def test_rejects_other_user(self):
        with patch.object(b, "ADMIN_ID", ADMIN):
            self.assertFalse(b.is_admin(STRANGER))

    def test_coerces_string_user_id(self):
        """is_admin устойчив к типам — user_id приводится к int."""
        with patch.object(b, "ADMIN_ID", ADMIN):
            self.assertTrue(b.is_admin("123"))

    def test_returns_false_when_admin_id_unset(self):
        """Если ADMIN_CHAT_ID некорректен, ADMIN_ID=None и доступа нет ни у кого."""
        with patch.object(b, "ADMIN_ID", None):
            self.assertFalse(b.is_admin(ADMIN))


class TestHtmlEscape(unittest.TestCase):
    def test_escapes_html_specials(self):
        self.assertEqual(b.html_escape("<b>a & b</b>"), "&lt;b&gt;a &amp; b&lt;/b&gt;")

    def test_ampersand_escaped_before_tags(self):
        """& должен экранироваться первым, иначе получится двойное экранирование."""
        self.assertEqual(b.html_escape("&lt;"), "&amp;lt;")

    def test_none_becomes_empty_string(self):
        self.assertEqual(b.html_escape(None), "")


class TestKeyboards(unittest.TestCase):
    def test_moderation_keyboard_callback_data(self):
        kb_markup = kb.moderation_keyboard(42)
        data = [btn.callback_data for row in kb_markup.inline_keyboard for btn in row]
        self.assertEqual(data, ["approve:42", "reject:42"])

    def test_draft_moderation_keyboard_has_three_reject_reasons(self):
        kb_markup = kb.draft_moderation_keyboard(7)
        data = [btn.callback_data for row in kb_markup.inline_keyboard for btn in row]
        self.assertIn("draft_approve:7", data)
        self.assertIn("draft_edit:7", data)
        rejects = [d for d in data if d.startswith("draft_reject:")]
        self.assertEqual(
            sorted(rejects),
            ["draft_reject:7:low_value", "draft_reject:7:poor_text", "draft_reject:7:weak_study"],
        )

    def test_draft_publish_keyboard(self):
        kb_markup = kb.draft_publish_keyboard(9)
        data = [btn.callback_data for row in kb_markup.inline_keyboard for btn in row]
        self.assertEqual(data, ["draft_publish:9"])


class TestGetDigestCandidatesInfo(unittest.TestCase):
    def test_groups_by_topic_and_counts(self):
        rows = [
            {"topic": "sleep", "title": "A"},
            {"topic": "sleep", "title": "B"},
            {"topic": "dopamine", "title": "C"},
        ]
        with patch.object(pub, "get_top_articles_by_topic", return_value=rows):
            total, topics = pub.get_digest_candidates_info()

        self.assertEqual(total, 3)
        self.assertEqual(topics["sleep"]["count"], 2)
        self.assertEqual(topics["dopamine"]["count"], 1)
        self.assertEqual(topics["sleep"]["titles"], ["A", "B"])

    def test_titles_capped_at_two_per_topic(self):
        rows = [{"topic": "sleep", "title": t} for t in ("A", "B", "C", "D")]
        with patch.object(pub, "get_top_articles_by_topic", return_value=rows):
            total, topics = pub.get_digest_candidates_info()

        self.assertEqual(topics["sleep"]["count"], 4)
        self.assertEqual(topics["sleep"]["titles"], ["A", "B"])

    def test_missing_topic_falls_back_to_unknown(self):
        with patch.object(pub, "get_top_articles_by_topic", return_value=[{"topic": None, "title": "X"}]):
            _, topics = pub.get_digest_candidates_info()
        self.assertIn("unknown", topics)

    def test_count_helper_returns_total(self):
        rows = [{"topic": "sleep", "title": "A"}, {"topic": "sleep", "title": "B"}]
        with patch.object(pub, "get_top_articles_by_topic", return_value=rows):
            self.assertEqual(pub.get_digest_candidates_count(), 2)


class TestPublishArticle(unittest.IsolatedAsyncioTestCase):
    ARTICLE = {
        "title": "T",
        "summary_ru": "S",
        "abstract": "A",
        "url": "https://example.com",
        "post_text": "Body TELEGRAPH_URL end",
    }

    async def test_returns_error_when_article_missing(self):
        with patch.object(pub, "get_article_by_id", return_value=None):
            ok, msg = await pub._publish_article(1)
        self.assertFalse(ok)
        self.assertEqual(msg, "Статья не найдена")

    async def test_returns_error_when_telegraph_fails(self):
        with patch.object(pub, "get_article_by_id", return_value=self.ARTICLE), \
             patch.object(pub, "create_telegraph_page", AsyncMock(return_value=None)):
            ok, msg = await pub._publish_article(1)
        self.assertFalse(ok)
        self.assertEqual(msg, "Ошибка создания Telegraph-страницы")

    async def test_success_substitutes_telegraph_url_and_saves(self):
        url = "https://telegra.ph/x"
        send = AsyncMock(return_value=555)
        with patch.object(pub, "get_article_by_id", return_value=self.ARTICLE), \
             patch.object(pub, "create_telegraph_page", AsyncMock(return_value=url)), \
             patch.object(pub, "send_to_channel", send), \
             patch.object(pub, "update_article_status") as upd, \
             patch.object(pub, "save_publication") as save:
            ok, result = await pub._publish_article(1)

        self.assertTrue(ok)
        self.assertEqual(result, url)
        # Плейсхолдер TELEGRAPH_URL должен быть заменён реальной ссылкой.
        send.assert_awaited_once_with(f"Body {url} end")
        upd.assert_called_once_with(1, "published")
        save.assert_called_once_with(1, url, 555)

    async def test_builds_fallback_post_text_when_empty(self):
        article = {**self.ARTICLE, "post_text": ""}
        send = AsyncMock(return_value=1)
        with patch.object(pub, "get_article_by_id", return_value=article), \
             patch.object(pub, "create_telegraph_page", AsyncMock(return_value="https://telegra.ph/y")), \
             patch.object(pub, "send_to_channel", send), \
             patch.object(pub, "update_article_status"), \
             patch.object(pub, "save_publication"):
            ok, _ = await pub._publish_article(1)

        self.assertTrue(ok)
        sent_text = send.await_args.args[0]
        self.assertIn("<b>T</b>", sent_text)
        self.assertIn("https://telegra.ph/y", sent_text)

    async def test_saves_zero_message_id_when_channel_send_returns_none(self):
        with patch.object(pub, "get_article_by_id", return_value=self.ARTICLE), \
             patch.object(pub, "create_telegraph_page", AsyncMock(return_value="https://telegra.ph/z")), \
             patch.object(pub, "send_to_channel", AsyncMock(return_value=None)), \
             patch.object(pub, "update_article_status"), \
             patch.object(pub, "save_publication") as save:
            await pub._publish_article(1)

        self.assertEqual(save.call_args.args[2], 0)


class TestSendForModeration(unittest.IsolatedAsyncioTestCase):
    ARTICLE = {
        "title": "T", "summary_ru": "S", "abstract": "A", "url": "https://example.com",
        "topic": "sleep", "score": 30, "source": "pubmed",
    }

    @staticmethod
    def _mock_bot(send_message):
        """Подменяет get_bot() — Bot создаётся лениво, глобального объекта нет."""
        fake = MagicMock()
        fake.send_message = send_message
        return patch.object(pub, "get_bot", return_value=fake)

    async def test_does_nothing_when_article_missing(self):
        send = AsyncMock()
        with patch.object(pub, "get_article_by_id", return_value=None), \
             self._mock_bot(send):
            await pub.send_for_moderation(1)
        send.assert_not_awaited()

    async def test_sends_message_and_marks_pending(self):
        send = AsyncMock()
        with patch.object(pub, "ADMIN_ID", ADMIN), \
             patch.object(pub, "get_article_by_id", return_value=self.ARTICLE), \
             self._mock_bot(send), \
             patch.object(pub, "update_article_status") as upd:
            await pub.send_for_moderation(1)

        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["chat_id"], ADMIN)
        upd.assert_called_once_with(1, "pending")

    async def test_does_not_mark_pending_when_send_fails(self):
        """Если Telegram недоступен, статья не должна помечаться отправленной."""
        send = AsyncMock(side_effect=RuntimeError("tg down"))
        with patch.object(pub, "get_article_by_id", return_value=self.ARTICLE), \
             self._mock_bot(send), \
             patch.object(pub, "update_article_status") as upd:
            await pub.send_for_moderation(1)

        upd.assert_not_called()


class TestApproveRejectCallbacks(unittest.IsolatedAsyncioTestCase):
    async def test_approve_denied_for_non_admin(self):
        cb = _callback("approve:1", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "_publish_article", AsyncMock()) as pub_call:
            await cb_mod.on_approve(cb)

        pub_call.assert_not_awaited()
        cb.answer.assert_awaited_once()
        self.assertIn("Нет прав", cb.answer.await_args.args[0])

    async def test_approve_publishes_and_appends_result(self):
        cb = _callback("approve:42")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "_publish_article", AsyncMock(return_value=(True, "https://telegra.ph/a"))) as pub_call:
            await cb_mod.on_approve(cb)

        pub_call.assert_awaited_once_with(42)
        self.assertIn("Опубликовано", cb.message.edit_text.await_args.args[0])

    async def test_approve_appends_error_on_failure(self):
        cb = _callback("approve:42")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "_publish_article", AsyncMock(return_value=(False, "boom"))):
            await cb_mod.on_approve(cb)

        self.assertIn("Ошибка", cb.message.edit_text.await_args.args[0])

    async def test_reject_denied_for_non_admin(self):
        cb = _callback("reject:1", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "update_article_status") as upd:
            await cb_mod.on_reject(cb)
        upd.assert_not_called()

    async def test_reject_updates_status(self):
        cb = _callback("reject:42")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "update_article_status") as upd:
            await cb_mod.on_reject(cb)

        upd.assert_called_once_with(42, "rejected")
        self.assertIn("Отклонено", cb.message.edit_text.await_args.args[0])


class TestDraftCallbacks(unittest.IsolatedAsyncioTestCase):
    DRAFT = {"article_id": 10}

    async def test_draft_approve_denied_for_non_admin(self):
        cb = _callback("draft_approve:5", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "save_editor_feedback") as fb:
            await cb_mod.on_draft_approve(cb)
        fb.assert_not_called()

    async def test_draft_approve_reports_missing_draft(self):
        cb = _callback("draft_approve:5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=None), \
             patch.object(cb_mod, "save_editor_feedback") as fb:
            await cb_mod.on_draft_approve(cb)

        fb.assert_not_called()
        self.assertIn("не найден", cb.answer.await_args.args[0])

    async def test_draft_approve_saves_feedback_and_shows_publish_button(self):
        """Кнопка публикации теперь идёт под ПРЕДПРОСМОТРОМ финального
        поста (новое сообщение с parse_mode="HTML"), а не под старой
        карточкой модерации (2026-07-16)."""
        cb = _callback("draft_approve:5")
        article = {"post_text": "😴 <b>Заголовок</b>\n\nТело поста 👇\n\n📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"}
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=self.DRAFT), \
             patch.object(cb_mod, "get_article_by_id", return_value=article), \
             patch.object(cb_mod, "save_editor_feedback") as fb, \
             patch.object(cb_mod, "update_article_status") as upd:
            await cb_mod.on_draft_approve(cb)

        fb.assert_called_once()
        self.assertEqual(fb.call_args.args[2], "approved")
        upd.assert_called_once_with(10, "approved")

        # Старая карточка: без reply_markup, без parse_mode="HTML".
        self.assertNotIn("reply_markup", cb.message.edit_text.await_args.kwargs)
        self.assertNotIn("parse_mode", cb.message.edit_text.await_args.kwargs)

        # Предпросмотр — новое сообщение, HTML, кнопка публикации здесь.
        preview_call = cb.message.answer.await_args
        self.assertEqual(preview_call.kwargs["parse_mode"], "HTML")
        kb_markup = preview_call.kwargs["reply_markup"]
        self.assertEqual(kb_markup.inline_keyboard[0][0].callback_data, "draft_publish:5")
        self.assertIn("Тело поста 👇", preview_call.args[0])
        self.assertIn("ссылка появится при публикации", preview_call.args[0])
        self.assertNotIn("TELEGRAPH_URL", preview_call.args[0])

    async def test_draft_approve_falls_back_when_no_post_text(self):
        cb = _callback("draft_approve:5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=self.DRAFT), \
             patch.object(cb_mod, "get_article_by_id", return_value={"post_text": None}), \
             patch.object(cb_mod, "save_editor_feedback"), \
             patch.object(cb_mod, "update_article_status"):
            await cb_mod.on_draft_approve(cb)

        fallback_call = cb.message.answer.await_args
        kb_markup = fallback_call.kwargs["reply_markup"]
        self.assertEqual(kb_markup.inline_keyboard[0][0].callback_data, "draft_publish:5")

    async def test_draft_reject_parses_reason_from_callback_data(self):
        cb = _callback("draft_reject:5:weak_study")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=self.DRAFT), \
             patch.object(cb_mod, "save_editor_feedback") as fb, \
             patch.object(cb_mod, "update_article_status") as upd:
            await cb_mod.on_draft_reject(cb)

        self.assertEqual(fb.call_args.kwargs["reason"], "weak_study")
        upd.assert_called_once_with(10, "rejected")
        self.assertIn("weak_study", cb.message.edit_text.await_args.args[0])

    async def test_draft_reject_uses_default_reason_when_absent(self):
        cb = _callback("draft_reject:5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=self.DRAFT), \
             patch.object(cb_mod, "save_editor_feedback") as fb, \
             patch.object(cb_mod, "update_article_status"):
            await cb_mod.on_draft_reject(cb)

        self.assertEqual(fb.call_args.kwargs["reason"], "rejected by editor")

    async def test_draft_publish_requires_article_id(self):
        cb = _callback("draft_publish:5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value={"article_id": None}), \
             patch.object(cb_mod, "_publish_article", AsyncMock()) as pub_call:
            await cb_mod.on_draft_publish(cb)

        pub_call.assert_not_awaited()
        self.assertIn("Нет статьи", cb.answer.await_args.args[0])

    async def test_draft_publish_publishes_linked_article(self):
        cb = _callback("draft_publish:5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "get_draft_by_id", return_value=self.DRAFT), \
             patch.object(cb_mod, "_publish_article", AsyncMock(return_value=(True, "https://telegra.ph/q"))) as pub_call:
            await cb_mod.on_draft_publish(cb)

        pub_call.assert_awaited_once_with(10)
        self.assertIn("Опубликовано в канал", cb.message.edit_text.await_args.args[0])


class TestDigestCallbacks(unittest.IsolatedAsyncioTestCase):
    async def test_digest_approve_publishes_all_ids_and_counts_successes(self):
        cb = _callback("digest_approve:1,2,3")
        # Вторая статья падает — счётчик должен показать 2 из 3.
        results = [(True, "u1"), (False, "err"), (True, "u3")]
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "_publish_article", AsyncMock(side_effect=results)) as pub_call:
            await cb_mod.on_digest_approve(cb)

        self.assertEqual([c.args[0] for c in pub_call.await_args_list], [1, 2, 3])
        self.assertIn("Опубликовано: 2 из 3", cb.message.edit_text.await_args.args[0])

    async def test_digest_approve_denied_for_non_admin(self):
        cb = _callback("digest_approve:1,2", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "_publish_article", AsyncMock()) as pub_call:
            await cb_mod.on_digest_approve(cb)
        pub_call.assert_not_awaited()

    async def test_digest_one_by_one_sends_each_for_moderation(self):
        cb = _callback("digest_one_by_one:4,5")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cb_mod, "send_for_moderation", AsyncMock()) as send:
            await cb_mod.on_digest_one_by_one(cb)

        self.assertEqual([c.args[0] for c in send.await_args_list], [4, 5])

    async def test_digest_reject_all_marks_skipped(self):
        cb = _callback("digest_reject_all")
        with patch.object(b, "ADMIN_ID", ADMIN):
            await cb_mod.on_digest_reject_all(cb)

        self.assertIn("пропущен", cb.message.edit_text.await_args.args[0])


class TestInvalidateCacheCommand(unittest.IsolatedAsyncioTestCase):
    """Команда обслуживания: удаляет из БД, поэтому требует явного confirm."""

    async def test_shows_usage_without_arguments(self):
        msg = _message("/invalidate_cache")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "invalidate_translations_matching") as inv:
            await cmd_mod.cmd_invalidate_cache(msg)

        inv.assert_not_called()
        self.assertIn("Использование", msg.answer.await_args.args[0])

    async def test_reports_when_nothing_matches(self):
        msg = _message("/invalidate_cache наградум")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "count_translations_matching", return_value=0), \
             patch.object(cmd_mod, "invalidate_translations_matching") as inv:
            await cmd_mod.cmd_invalidate_cache(msg)

        inv.assert_not_called()
        self.assertIn("не найдено", msg.answer.await_args.args[0])

    async def test_preview_does_not_delete_without_confirm(self):
        msg = _message("/invalidate_cache наградум")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "count_translations_matching", return_value=3), \
             patch.object(cmd_mod, "invalidate_translations_matching") as inv:
            await cmd_mod.cmd_invalidate_cache(msg)

        inv.assert_not_called()
        reply = msg.answer.await_args.args[0]
        self.assertIn("3", reply)
        self.assertIn("confirm", reply)

    async def test_confirm_deletes_matching_rows(self):
        msg = _message("/invalidate_cache наградум confirm")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "invalidate_translations_matching", return_value=2) as inv:
            await cmd_mod.cmd_invalidate_cache(msg)

        inv.assert_called_once_with("%наградум%")
        self.assertIn("Удалено 2", msg.answer.await_args.args[0])

    async def test_ignored_for_non_admin(self):
        msg = _message("/invalidate_cache наградум confirm", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "invalidate_translations_matching") as inv:
            await cmd_mod.cmd_invalidate_cache(msg)

        inv.assert_not_called()
        msg.answer.assert_not_awaited()


class TestAudienceStatsCommand(unittest.IsolatedAsyncioTestCase):
    async def test_shows_growth_and_top_posts(self):
        msg = _message("/audience_stats")
        history = [{"subscriber_count": 105}, {"subscriber_count": 100}]
        top_posts = [{"message_id": 42, "total": 7}]
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "get_channel_stats_history", return_value=history), \
             patch.object(cmd_mod, "get_top_reacted_posts", return_value=top_posts), \
             patch.object(cmd_mod, "get_publication_titles_for_message", return_value=["Дофамин: обзор"]):
            await cmd_mod.cmd_audience_stats(msg)

        reply = msg.answer.await_args.args[0]
        self.assertIn("105", reply)
        self.assertIn("+5", reply)
        self.assertIn("7", reply)
        self.assertIn("Дофамин: обзор", reply)

    async def test_handles_no_data_yet(self):
        msg = _message("/audience_stats")
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "get_channel_stats_history", return_value=[]), \
             patch.object(cmd_mod, "get_top_reacted_posts", return_value=[]):
            await cmd_mod.cmd_audience_stats(msg)

        reply = msg.answer.await_args.args[0]
        self.assertIn("снимков ещё нет", reply)
        self.assertIn("Реакций пока не зафиксировано", reply)

    async def test_ignored_for_non_admin(self):
        msg = _message("/audience_stats", user_id=STRANGER)
        with patch.object(b, "ADMIN_ID", ADMIN), \
             patch.object(cmd_mod, "get_channel_stats_history") as hist:
            await cmd_mod.cmd_audience_stats(msg)

        hist.assert_not_called()
        msg.answer.assert_not_awaited()


class TestLazyBotInitialization(unittest.TestCase):
    """Bot создаётся лениво: Bot(token=...) валидирует токен сразу и падает с
    TokenValidationError на пустом BOT_TOKEN. Если бы объект создавался на
    уровне модуля, `import bot.bot` рушился бы без .env — и вместе с ним
    падали бы даже тесты, не касающиеся Telegram (как было до фикса).
    """

    def test_module_has_no_eager_bot_object(self):
        self.assertFalse(
            hasattr(b, "bot"),
            "Глобальный Bot снова создаётся на уровне модуля — импорт без .env сломается",
        )

    def test_get_bot_caches_single_instance(self):
        with patch.object(b, "_bot_instance", None), \
             patch.object(b, "Bot") as bot_cls:
            first = b.get_bot()
            second = b.get_bot()

        self.assertIs(first, second)
        bot_cls.assert_called_once()  # токен валидируется ровно один раз

    def test_import_succeeds_with_empty_token(self):
        """Ключевая гарантия: модуль импортируется даже без BOT_TOKEN."""
        import importlib
        import config.settings as settings

        with patch.object(settings, "BOT_TOKEN", ""):
            module = importlib.reload(b)
            # Импорт прошёл, но Bot ещё не создан — упасть должно только при
            # явном обращении к get_bot(), а не при импорте.
            self.assertIsNone(module._bot_instance)

        importlib.reload(b)  # возвращаем модуль в исходное состояние


class TestCallbackLoggingMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_calls_handler_and_returns_its_result(self):
        """Middleware обязана вызвать handler — иначе кнопки перестают работать."""
        middleware = b.CallbackLoggingMiddleware()
        handler = AsyncMock(return_value="handled")
        event = _callback("approve:1")

        with patch.object(b, "ADMIN_ID", ADMIN):
            result = await middleware(handler, event, {})

        handler.assert_awaited_once_with(event, {})
        self.assertEqual(result, "handled")


if __name__ == "__main__":
    unittest.main()
