import unittest

from adaptation.content_audit import check_abrupt_cutoff, check_leaked_metadata, audit_text
from database.db import init_db, get_conn, save_article, save_summary, get_recent_summaries

_MARKER = "TEST_CONTENT_AUDIT_MARKER_XYZ"


class TestCheckAbruptCutoff(unittest.TestCase):
    def test_flags_mid_word_truncation(self):
        text = "Он участвует в обучении, а не просто в получении уд..."
        self.assertTrue(check_abrupt_cutoff(text))

    def test_flags_shorten_fallback_ellipsis(self):
        text = "Некое длинное предложение без точки внутри лимита символов..."
        self.assertTrue(check_abrupt_cutoff(text))

    def test_allows_clean_sentence_ending(self):
        text = "Дофамин кодирует ошибку предсказания вознаграждения."
        self.assertFalse(check_abrupt_cutoff(text))

    def test_allows_transition_into_link(self):
        """Обрыв на переходной фразе — ок, если дальше идёт ссылка (Stage 10
        transitions, см. историю обсуждения с редактором)."""
        text = "Чтобы это стало нагляднее, вот сравнение.\n\n📘 <a href='x'>Читать полностью</a>"
        self.assertFalse(check_abrupt_cutoff(text))


class TestCheckLeakedMetadata(unittest.TestCase):
    def test_flags_english_prefix_leak(self):
        text = "arXiv:2607.11656v1 Announce Type: new Abstract: Something."
        self.assertTrue(check_leaked_metadata(text))

    def test_flags_translated_prefix_leak(self):
        text = "ArXiv:2607.09773v1 Тип объявления: новое Аннотация: Что-то."
        self.assertTrue(check_leaked_metadata(text))

    def test_allows_clean_text(self):
        text = "Дофамин участвует в обучении и мотивации."
        self.assertFalse(check_leaked_metadata(text))


class TestAuditText(unittest.TestCase):
    def test_clean_text_has_no_problems(self):
        text = "Дофамин кодирует ошибку предсказания вознаграждения. Основано на PubMed."
        self.assertEqual(audit_text(text), [])

    def test_empty_text_has_no_problems(self):
        self.assertEqual(audit_text(""), [])

    def test_collects_multiple_problems(self):
        text = "ArXiv:2607.09773v1 Тип объявления: новое Аннотация: Something in English..."
        problems = audit_text(text)
        self.assertEqual(len(problems), 3)  # cutoff + leaked metadata + latin

    def test_acronyms_alone_are_not_flagged(self):
        text = "Мы обучили модель на ADNI и оценили на OASIS-3."
        self.assertEqual(audit_text(text), [])


class TestGetRecentSummaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM summaries WHERE article_id IN (SELECT id FROM articles WHERE title LIKE ?)",
                (f"%{_MARKER}%",),
            )
            conn.execute("DELETE FROM articles WHERE title LIKE ?", (f"%{_MARKER}%",))

    def test_returns_post_text_joined_with_title_and_topic(self):
        article_id = save_article(
            source="pubmed", title=f"{_MARKER} title", url=f"https://example.com/{_MARKER}",
            topic="sleep",
        )
        save_summary(article_id, "summary", f"{_MARKER} post text")

        rows = get_recent_summaries(limit=50)
        match = next(r for r in rows if r["id"] == article_id)
        self.assertEqual(match["title"], f"{_MARKER} title")
        self.assertEqual(match["topic"], "sleep")
        self.assertEqual(match["post_text"], f"{_MARKER} post text")

    def test_respects_limit(self):
        rows = get_recent_summaries(limit=1)
        self.assertLessEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
