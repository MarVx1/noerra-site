import unittest
from database.db import init_db
from adaptation.utils import _clean_text, _split_sentences, _extract_key_sentence, _has_practical_marker, _fix_translation


class TestAdaptationUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
    def test_clean_text_removes_html_and_whitespace(self):
        text = "<p>Hello <b>world</b>!</p>   \n  New line."
        self.assertEqual(_clean_text(text), "Hello world! New line.")

    def test_split_sentences(self):
        text = "First sentence. Second sentence! Third?"
        self.assertEqual(_split_sentences(text), [
            "First sentence.",
            "Second sentence!",
            "Third?",
        ])

    def test_extract_key_sentence_prefers_results(self):
        abstract = "We found an effect. The results show improvement. Final statement."
        self.assertEqual(_extract_key_sentence(abstract), "The results show improvement.")

    def test_has_practical_marker_ignores_ispolzovala_false_positive(self):
        """Регрессия: маркер 'польз' ложно совпадал с 'использовала(сь)'/
        'пользоваться' — обычными словами методологии, не про пользу.
        Из-за этого лимитации/методология ошибочно помечались как
        практический вывод (см. EditorialEngine.analyze() manual QA)."""
        sentence = "В исследовании использовалась небольшая выборка, поэтому необходима осторожность."
        self.assertFalse(_has_practical_marker(sentence))

    def test_has_practical_marker_detects_real_benefit_wording(self):
        sentence = "Эта методика приносит реальную пользу пациентам с бессонницей."
        self.assertTrue(_has_practical_marker(sentence))

    def test_fix_translation_does_not_truncate_instrumental_case(self):
        """Регрессия: text.replace('вознаграждение', 'награду') раньше
        матчился как префикс более длинной словоформы 'вознаграждением',
        обрезая её до 'наградум' (см. manual QA генерации статьи).
        _fix_translation теперь матчит только целые слова (\\b)."""
        text = "во время выполнения задания с вознаграждением."
        result = _fix_translation(text)
        self.assertIn("с наградой", result)
        self.assertNotIn("наградум", result)

    def test_fix_translation_covers_other_reward_case_forms(self):
        cases = {
            "думает о вознаграждении.": "о награде",
            "стремится к вознаграждению.": "к награде",
            "интересуется вознаграждениями.": "наградами",
            "разбирается в вознаграждениях.": "в наградах",
        }
        for text, expected_fragment in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected_fragment, _fix_translation(text))

    def test_fix_translation_still_replaces_bare_forms(self):
        self.assertIn("награды", _fix_translation("системы вознаграждения работают иначе."))
        self.assertIn("награду", _fix_translation("получить вознаграждение сразу."))


if __name__ == '__main__':
    unittest.main()
