import unittest

from adaptation.content_audit import (
    audit_text,
    check_structured_abstract_leak,
    check_duplicate_long_sentence,
    check_dangling_transition,
    check_title_or_lead_repeats_recent,
)
from database.db import init_db, get_conn, save_draft

_MARKER = "TEST_AUDIT_V2_MARKER"


class TestCheckStructuredAbstractLeak(unittest.TestCase):
    def test_flags_ru_label(self):
        text = "ЦЕЛЬ: Этот обзор направлен на отображение существующих данных о фармацевтах."
        self.assertTrue(check_structured_abstract_leak(text))

    def test_flags_en_label(self):
        text = "AIM: This review aimed to map existing evidence."
        self.assertTrue(check_structured_abstract_leak(text))

    def test_clean_text_not_flagged(self):
        text = "Дофамин кодирует ошибку предсказания вознаграждения. Основано на PubMed."
        self.assertFalse(check_structured_abstract_leak(text))

    def test_does_not_flag_acronym_before_colon(self):
        text = "Изменённая связь у детей и подростков с СДВГ: метаанализ нейровизуализации."
        self.assertFalse(check_structured_abstract_leak(text))


class TestCheckDuplicateLongSentence(unittest.TestCase):
    def test_flags_verbatim_repeat_across_paragraphs(self):
        """Реальный случай (article id=634, 'СДВГ: свежие данные'):
        находка повторена дословно в лиде и в вопросе-цитате."""
        text = (
            "СДВГ: свежие данные\n\n"
            "Есть неожиданная деталь в устройстве СДВГ. Этот обзор направлен на "
            "отображение существующих эмпирических данных об участии фармацевтов "
            "в услугах по СДВГ.\n\n"
            "Что именно показало новое исследование: Этот обзор направлен на "
            "отображение существующих эмпирических данных об участии фармацевтов "
            "в услугах по СДВГ?"
        )
        self.assertTrue(check_duplicate_long_sentence(text))

    def test_short_repeated_phrase_below_threshold_not_flagged(self):
        text = "Это важно. Основано на PubMed. Это важно, но по-другому дальше."
        self.assertFalse(check_duplicate_long_sentence(text, min_words=8))

    def test_clean_text_not_flagged(self):
        text = (
            "Дофамин кодирует ошибку предсказания вознаграждения у мышей в новом эксперименте.\n\n"
            "Это отдельная содержательная мысль без повторов ни с чем предыдущим совсем."
        )
        self.assertFalse(check_duplicate_long_sentence(text))


class TestCheckDanglingTransition(unittest.TestCase):
    def test_flags_transition_as_last_paragraph(self):
        text = "Первый абзац с реальным фактом из исследования.\n\nВот как это можно себе представить."
        self.assertTrue(check_dangling_transition(text))

    def test_does_not_flag_transition_followed_by_content(self):
        text = (
            "Первый абзац с фактом.\n\n"
            "Вот как это можно себе представить.\n\n"
            "<i>Реальная аналогия идёт здесь, за переходом.</i>"
        )
        self.assertFalse(check_dangling_transition(text))

    def test_clean_text_not_flagged(self):
        self.assertFalse(check_dangling_transition("Обычный текст без переходов вообще."))

    def test_flags_transition_followed_only_by_read_more_link(self):
        """Реальный опубликованный пост (article id=635, 2026-07-16):
        переход — не последний абзац (после него всегда идёт ссылка
        «Читать полностью»), поэтому исходная проверка ("последний
        абзац") это пропускала, хотя пост реально обрывался на
        переходе-обещании."""
        text = (
            "Лид с фактом.\n\n"
            "Разберёмся по порядку.\n\n"
            "📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"
        )
        self.assertTrue(check_dangling_transition(text))

    def test_does_not_flag_read_more_link_after_real_content(self):
        text = (
            "Лид с фактом.\n\n"
            "Вопрос читателя?\n\n"
            "📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"
        )
        self.assertFalse(check_dangling_transition(text))

    def test_empty_text_not_flagged(self):
        self.assertFalse(check_dangling_transition(""))


class TestCheckTitleOrLeadRepeatsRecent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def tearDown(self):
        with get_conn() as conn:
            conn.execute("DELETE FROM drafts WHERE topic = ?", (f"{_MARKER}_topic",))

    def test_flags_repeated_title(self):
        save_draft(
            0, f"{_MARKER} Заголовок", "Лид один", "body", "short", "full",
            "PubMed", f"{_MARKER}_topic", "analysis", 0.5, "general",
        )
        problems = check_title_or_lead_repeats_recent(
            f"{_MARKER}_topic", f"{_MARKER} Заголовок", "Другой лид"
        )
        self.assertTrue(any("Заголовок повторяет" in p for p in problems))

    def test_flags_repeated_lead(self):
        save_draft(
            0, "Другой заголовок", f"{_MARKER} Лид совпадающий", "body", "short", "full",
            "PubMed", f"{_MARKER}_topic", "analysis", 0.5, "general",
        )
        problems = check_title_or_lead_repeats_recent(
            f"{_MARKER}_topic", "Совсем новый заголовок", f"{_MARKER} Лид совпадающий"
        )
        self.assertTrue(any("Лид дословно повторяет" in p for p in problems))

    def test_no_problems_for_novel_title_and_lead(self):
        problems = check_title_or_lead_repeats_recent(
            f"{_MARKER}_topic_unused", "Совершенно новый заголовок", "Совершенно новый лид"
        )
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
