import unittest

from adaptation.utils import _shorten_by_paragraphs
from adaptation.transitions import TRANSITION_INTO_ANALOGY


class TestShortenByParagraphs(unittest.TestCase):
    def test_returns_text_unchanged_if_under_limit(self):
        text = "Короткий текст."
        self.assertEqual(_shorten_by_paragraphs(text, 800), text)

    def test_never_splits_a_paragraph_in_half(self):
        paragraphs = ["Абзац один.", "Абзац два подлиннее, но тоже короткий.", "Абзац три."]
        text = "\n\n".join(paragraphs)
        result = _shorten_by_paragraphs(text, len(paragraphs[0]) + 5)
        for para in result.split("\n\n"):
            self.assertIn(para, paragraphs)

    def test_drops_dangling_transition_left_at_the_end(self):
        """Реальный случай (драфты модерации id 152/156, 2026-07-15):
        абзац с переходом-обещанием влезает в лимит, а абзац с его
        содержанием (аналогия) — уже нет. Раньше превью обрывалось прямо
        на обещании; теперь висящий переход должен быть убран."""
        transition = TRANSITION_INTO_ANALOGY[0]
        text = "\n\n".join([
            "Первый содержательный абзац с реальным фактом из исследования.",
            transition,
            "<i>Аналогия, которая была бы следующей, но не влезает в лимит совсем.</i>" * 3,
        ])
        cutoff = len("Первый содержательный абзац с реальным фактом из исследования.") + len(transition) + 4
        result = _shorten_by_paragraphs(text, cutoff)
        self.assertFalse(result.rstrip().endswith(transition))
        self.assertIn("Первый содержательный абзац", result)

    def test_keeps_transition_when_its_payload_paragraph_fits_too(self):
        transition = TRANSITION_INTO_ANALOGY[0]
        payload = "<i>Короткая аналогия.</i>"
        text = "\n\n".join(["Факт.", transition, payload])
        result = _shorten_by_paragraphs(text, len(text))
        self.assertTrue(result.endswith(payload))

    def test_falls_back_to_sentence_cut_when_first_paragraph_exceeds_limit(self):
        long_paragraph = "Слово. " * 200
        result = _shorten_by_paragraphs(long_paragraph, 50)
        self.assertLessEqual(len(result), 53)  # +'...' допустим

    def test_real_draft_152_no_longer_ends_on_bare_transition(self):
        """Регрессия ровно на том тексте, который вызвал жалобу пользователя."""
        body = (
            "Он характеризуется таламокортикальной медленноволновой (МВ) "
            "активностью (0,5–4 Гц) и веретенами (10–16 Гц), "
            "которые синхронизируют корковую активность и регулируют синаптическую силу.\n\n"
            "Это лабораторное исследование — прямых выводов для людей пока нет, "
            "но оно закладывает основу для будущих работ о сне.\n\n"
            "Вот как это можно себе представить.\n\n"
            "<i>Это похоже на архивариуса, который каждую ночь разбирает кипу "
            "бумаг за день и раскладывает их по нужным полкам.</i>"
        )
        result = _shorten_by_paragraphs(body, 250)
        self.assertFalse(result.rstrip().endswith("Вот как это можно себе представить."))


if __name__ == "__main__":
    unittest.main()
