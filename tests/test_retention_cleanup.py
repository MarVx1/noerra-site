import unittest

from database.db import (
    init_db, get_conn, save_article, save_draft, save_publication,
    save_summary, cleanup_unpublished_older_than,
)

_MARKER = "TEST_RETENTION_MARKER_XYZ"


def _backdate(conn, table, row_id, days_ago):
    conn.execute(
        f"UPDATE {table} SET created_at = datetime('now', ?) WHERE id = ?",
        (f"-{days_ago} days", row_id),
    )


class TestCleanupUnpublishedOlderThan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM publications WHERE article_id IN (SELECT id FROM articles WHERE title LIKE ?)",
                (f"%{_MARKER}%",),
            )
            conn.execute(
                "DELETE FROM drafts WHERE article_id IN (SELECT id FROM articles WHERE title LIKE ?)"
                " OR title LIKE ?",
                (f"%{_MARKER}%", f"%{_MARKER}%"),
            )
            conn.execute(
                "DELETE FROM summaries WHERE article_id IN (SELECT id FROM articles WHERE title LIKE ?)",
                (f"%{_MARKER}%",),
            )
            conn.execute("DELETE FROM articles WHERE title LIKE ?", (f"%{_MARKER}%",))

    def _make_article(self, days_old, status="new", source="pubmed"):
        article_id = save_article(
            source=source, title=f"{_MARKER} article {days_old}d",
            url=f"https://example.com/{_MARKER}/{days_old}/{status}/{source}",
            status=status,
        )
        with get_conn() as conn:
            _backdate(conn, "articles", article_id, days_old)
        return article_id

    def _make_draft(self, article_id, days_old, status="pending"):
        draft_id = save_draft(
            article_id, f"{_MARKER} title", "lead", "body", "short", "full",
            "PubMed", "sleep", "analysis", 0.5, "general",
        )
        with get_conn() as conn:
            conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, draft_id))
            _backdate(conn, "drafts", draft_id, days_old)
        return draft_id

    def test_deletes_old_unpublished_article(self):
        article_id = self._make_article(days_old=10)
        stats = cleanup_unpublished_older_than(days=7)
        self.assertEqual(stats["articles"], 1)
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
        self.assertIsNone(row)

    def test_keeps_recent_unpublished_article(self):
        article_id = self._make_article(days_old=2)
        cleanup_unpublished_older_than(days=7)
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
        self.assertIsNotNone(row)

    def test_keeps_old_published_article_regardless_of_age(self):
        """Публикация — единственная защита от удаления, независимо от
        возраста и articles.status (status теоретически может разъехаться)."""
        article_id = self._make_article(days_old=30, status="published")
        save_publication(article_id, "https://telegra.ph/test")
        cleanup_unpublished_older_than(days=7)
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
        self.assertIsNotNone(row)

    def test_deletes_old_youtube_article_same_as_any_source(self):
        article_id = self._make_article(days_old=10, source="youtube", status="low_score")
        stats = cleanup_unpublished_older_than(days=7)
        self.assertEqual(stats["articles"], 1)
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
        self.assertIsNone(row)

    def test_cascades_to_drafts_and_summaries(self):
        article_id = self._make_article(days_old=10)
        draft_id = self._make_draft(article_id, days_old=9)
        save_summary(article_id, "summary", "post text")
        stats = cleanup_unpublished_older_than(days=7)
        self.assertEqual(stats["drafts"], 1)
        self.assertEqual(stats["summaries"], 1)
        with get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone())

    def test_deletes_old_standalone_draft_without_article(self):
        """Драфт с article_id=0 (см. живые данные 2026-07-15, draft id=1
        и т.п.) — своя ветка удаления, не через каскад от статьи."""
        draft_id = self._make_draft(article_id=0, days_old=10)
        stats = cleanup_unpublished_older_than(days=7)
        self.assertGreaterEqual(stats["drafts"], 1)
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        self.assertIsNone(row)

    def test_keeps_recent_articles_and_drafts_together(self):
        article_id = self._make_article(days_old=1)
        draft_id = self._make_draft(article_id, days_old=1)
        cleanup_unpublished_older_than(days=7)
        with get_conn() as conn:
            self.assertIsNotNone(conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone())


if __name__ == "__main__":
    unittest.main()
