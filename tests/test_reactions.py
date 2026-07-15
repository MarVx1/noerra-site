import unittest
from unittest.mock import MagicMock, patch

import bot.reactions as reactions


def _reaction_count_event(chat_id: int, message_id: int, reactions_list):
    """reactions_list: list of (emoji_or_none, custom_emoji_id_or_none, total_count)."""
    event = MagicMock()
    event.chat.id = chat_id
    event.message_id = message_id
    items = []
    for emoji, custom_id, total_count in reactions_list:
        r = MagicMock()
        r.type.emoji = emoji
        r.type.custom_emoji_id = custom_id
        r.total_count = total_count
        items.append(r)
    event.reactions = items
    return event


class TestOnMessageReactionCount(unittest.IsolatedAsyncioTestCase):
    async def test_saves_emoji_reaction_counts(self):
        event = _reaction_count_event(-100, 42, [("👍", None, 3), ("❤", None, 1)])
        with patch.object(reactions, "save_post_reaction_counts") as save:
            await reactions.on_message_reaction_count(event)
        save.assert_called_once_with(-100, 42, {"👍": 3, "❤": 1})

    async def test_custom_emoji_reactions_are_labeled_distinctly(self):
        event = _reaction_count_event(-100, 42, [(None, "custom123", 2)])
        with patch.object(reactions, "save_post_reaction_counts") as save:
            await reactions.on_message_reaction_count(event)
        save.assert_called_once_with(-100, 42, {"custom:custom123": 2})


if __name__ == "__main__":
    unittest.main()
