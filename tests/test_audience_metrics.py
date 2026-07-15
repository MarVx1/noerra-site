import unittest

from database.db import (
    init_db,
    get_conn,
    save_post_reaction_counts,
    get_post_reaction_counts,
    save_channel_stats_snapshot,
    get_channel_stats_history,
)

# Уникальный маркер, чтобы не задеть реальные записи в общей noerra.db
# (см. tests/test_translation_cache.py — тот же приём).
_CHAT = "TEST_METRICS_MARKER_CHAT"


class TestPostReactionCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute("DELETE FROM post_reactions WHERE chat_id = ?", (_CHAT,))
            conn.execute("DELETE FROM channel_stats WHERE chat_id = ?", (_CHAT,))

    def test_save_and_get_roundtrip(self):
        save_post_reaction_counts(_CHAT, 1, {"thumbsup": 3, "heart": 1})
        self.assertEqual(get_post_reaction_counts(_CHAT, 1), {"thumbsup": 3, "heart": 1})

    def test_repeated_event_overwrites_not_accumulates(self):
        """message_reaction_count несёт актуальный снимок, а не дельту —
        повторное событие должно заменить старое значение, а не сложиться."""
        save_post_reaction_counts(_CHAT, 2, {"thumbsup": 3})
        save_post_reaction_counts(_CHAT, 2, {"thumbsup": 5, "fire": 2})
        self.assertEqual(get_post_reaction_counts(_CHAT, 2), {"thumbsup": 5, "fire": 2})

    def test_different_messages_are_isolated(self):
        save_post_reaction_counts(_CHAT, 3, {"thumbsup": 1})
        save_post_reaction_counts(_CHAT, 4, {"heart": 9})
        self.assertEqual(get_post_reaction_counts(_CHAT, 3), {"thumbsup": 1})
        self.assertEqual(get_post_reaction_counts(_CHAT, 4), {"heart": 9})

    def test_missing_message_returns_empty_dict(self):
        self.assertEqual(get_post_reaction_counts(_CHAT, 9999), {})


class TestChannelStatsHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute("DELETE FROM channel_stats WHERE chat_id = ?", (_CHAT,))

    def test_snapshots_accumulate_newest_first(self):
        save_channel_stats_snapshot(_CHAT, 100)
        save_channel_stats_snapshot(_CHAT, 105)
        history = get_channel_stats_history(_CHAT)
        self.assertEqual([r["subscriber_count"] for r in history], [105, 100])

    def test_history_respects_limit(self):
        for count in range(10):
            save_channel_stats_snapshot(_CHAT, count)
        history = get_channel_stats_history(_CHAT, limit=3)
        self.assertEqual(len(history), 3)


if __name__ == "__main__":
    unittest.main()
