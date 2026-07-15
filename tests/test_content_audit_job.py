import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scheduler.scheduler import run_content_audit


def _summary_row(id_, title, post_text):
    return {"id": id_, "title": title, "topic": "sleep", "post_text": post_text}


class TestRunContentAudit(unittest.IsolatedAsyncioTestCase):
    async def test_sends_report_when_problems_found(self):
        rows = [
            _summary_row(1, "Clean post", "Дофамин кодирует ошибку предсказания."),
            _summary_row(2, "Broken post", "Обрезано на середине сло..."),
        ]
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with patch("database.db.get_recent_summaries", return_value=rows), \
             patch("bot.bot.get_bot", return_value=bot):
            await run_content_audit()

        bot.send_message.assert_awaited_once()
        report = bot.send_message.await_args.args[1]
        self.assertIn("Broken post", report)
        self.assertNotIn("Clean post", report)

    async def test_sends_nothing_when_all_clean(self):
        rows = [_summary_row(1, "Clean post", "Дофамин кодирует ошибку предсказания.")]
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with patch("database.db.get_recent_summaries", return_value=rows), \
             patch("bot.bot.get_bot", return_value=bot):
            await run_content_audit()

        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
