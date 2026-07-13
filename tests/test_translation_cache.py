import unittest

from database.db import (
    init_db,
    save_translation,
    get_translation,
    count_translations_matching,
    invalidate_translations_matching,
)

# Уникальный маркер, чтобы точно не задеть реальные записи кеша перевода
# в общей noerra.db и гарантированно найти/удалить только свои тестовые.
_MARKER = "TEST_CACHE_INVALIDATION_MARKER_XYZ"


class TestTranslationCacheInvalidation(unittest.TestCase):
    """Regression-защита: правки логики перевода не должны молча оставлять
    уже закэшированные некорректные переводы навсегда (см. manual QA,
    случай с 'наградум' из-за устаревшего кеша 'вознаграждением')."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        # Всегда чистим за собой, даже если тест упал.
        invalidate_translations_matching(f"%{_MARKER}%")

    def test_save_and_get_roundtrip(self):
        source = f"{_MARKER} source one"
        save_translation(source, f"{_MARKER} translated one", "ru")
        self.assertEqual(get_translation(source, "ru"), f"{_MARKER} translated one")

    def test_count_matching_reflects_saved_entries(self):
        save_translation(f"{_MARKER} a", f"{_MARKER} bad text A", "ru")
        save_translation(f"{_MARKER} b", f"{_MARKER} bad text B", "ru")
        save_translation(f"{_MARKER} c", "unrelated clean text", "ru")
        self.assertEqual(count_translations_matching(f"%{_MARKER}%"), 2)

    def test_invalidate_removes_only_matching_rows(self):
        save_translation(f"{_MARKER} x", f"{_MARKER} corrupted", "ru")
        save_translation(f"{_MARKER} y", "totally unrelated clean text", "ru")
        deleted = invalidate_translations_matching(f"%{_MARKER}%")
        self.assertEqual(deleted, 1)
        self.assertIsNone(get_translation(f"{_MARKER} x", "ru"))
        self.assertEqual(get_translation(f"{_MARKER} y", "ru"), "totally unrelated clean text")
        # Ручная зачистка второй строки, т.к. она не подходит под маркер-паттерн выше.
        invalidate_translations_matching("totally unrelated clean text")

    def test_invalidate_returns_zero_for_no_match(self):
        deleted = invalidate_translations_matching(f"%{_MARKER}_no_such_thing%")
        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
