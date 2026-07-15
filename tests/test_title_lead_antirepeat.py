import unittest

from adaptation.editorial_engine import _build_title, _build_lead, TITLE_PATTERNS, LEAD_PATTERNS
from database.db import init_db, get_conn, save_draft, get_recent_titles_and_leads_by_topic

_MARKER = "TEST_ANTIREPEAT_MARKER"


class TestBuildTitleAvoidsRecent(unittest.TestCase):
    def test_avoids_single_recent_title_when_alternatives_exist(self):
        recent = {_build_title("stress", "discovery")}
        for _ in range(20):
            title = _build_title("stress", "discovery", avoid_titles=recent)
            self.assertNotIn(title, recent)

    def test_falls_back_to_full_bank_when_all_titles_would_collide(self):
        """Если банк исчерпан (все варианты уже встречались) — не
        зависает и не падает, просто ведёт себя как без anti-repeat."""
        all_possible = {
            _build_title("stress", "discovery", avoid_titles=set())
            for _ in range(200)
        }
        # Все реальные варианты банка "discovery" для темы — считаем
        # закрытым множеством и передаём его целиком как "недавние".
        title = _build_title("stress", "discovery", avoid_titles=all_possible)
        self.assertTrue(title)  # не упало, вернуло непустую строку

    def test_no_avoid_set_behaves_as_before(self):
        title = _build_title("stress", "discovery", avoid_titles=None)
        self.assertTrue(title)


class TestBuildLeadAvoidsRecent(unittest.TestCase):
    def test_avoids_hook_whose_prefix_matches_recent_lead(self):
        decomposed = {"finding": "Некая находка про стресс."}
        baseline_lead = _build_lead("stress", "discovery", "abstract", decomposed)
        for _ in range(20):
            lead = _build_lead(
                "stress", "discovery", "abstract", decomposed,
                avoid_lead_prefixes=[baseline_lead],
            )
            # Хук нового лида не должен быть тем же, что у baseline —
            # проверяем через принадлежность к банку хуков.
            matching_hooks = [
                h for h in LEAD_PATTERNS["discovery"]
                if baseline_lead.startswith(_build_hook_only("stress", h))
            ]
            for hook_template in matching_hooks:
                self.assertFalse(lead.startswith(_build_hook_only("stress", hook_template)))

    def test_no_avoid_prefixes_behaves_as_before(self):
        decomposed = {"finding": "Некая находка."}
        lead = _build_lead("stress", "discovery", "abstract", decomposed, avoid_lead_prefixes=None)
        self.assertTrue(lead)


def _build_hook_only(topic, template):
    from adaptation.text_patterns import _pick
    return _pick([template], topic=topic)


class TestGetRecentTitlesAndLeadsByTopic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute("DELETE FROM drafts WHERE title LIKE ?", (f"%{_MARKER}%",))

    def test_returns_titles_and_leads_for_topic(self):
        save_draft(
            0, f"{_MARKER} title", f"{_MARKER} lead", "body", "short", "full",
            "PubMed", f"{_MARKER}_topic", "analysis", 0.5, "general",
        )
        titles, leads = get_recent_titles_and_leads_by_topic(f"{_MARKER}_topic")
        self.assertIn(f"{_MARKER} title", titles)
        self.assertIn(f"{_MARKER} lead", leads)

    def test_returns_empty_for_unknown_topic(self):
        titles, leads = get_recent_titles_and_leads_by_topic(f"{_MARKER}_no_such_topic")
        self.assertEqual(titles, set())
        self.assertEqual(leads, [])


if __name__ == "__main__":
    unittest.main()
