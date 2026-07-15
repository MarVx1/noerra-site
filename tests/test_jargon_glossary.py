import unittest

from adaptation.jargon_glossary import simplify_methodology_terms


class TestSimplifyMethodologyTerms(unittest.TestCase):
    def test_annotates_known_term(self):
        text = "Мыши демонстрировали изменения в тесте открытого поля."
        result = simplify_methodology_terms(text)
        self.assertIn("тесте открытого поля (", result)
        self.assertIn("измеряет тревожность", result)

    def test_leaves_clean_text_unchanged(self):
        text = "Дофамин кодирует ошибку предсказания вознаграждения."
        self.assertEqual(simplify_methodology_terms(text), text)

    def test_empty_text_returns_empty(self):
        self.assertEqual(simplify_methodology_terms(""), "")

    def test_caps_annotations_per_text(self):
        """Реальный пример (article id=483): 6 терминов подряд в одном
        предложении — аннотировать все делает текст нечитаемым, поэтому
        лимит на число аннотаций за текст."""
        text = (
            "поведение в тесте на предпочтение сахарозы, тесте принудительного "
            "плавания и тесте социального взаимодействия, а также тревожное "
            "поведение в приподнятом крестообразном лабиринте, тесте с "
            "подавлением новизны при кормлении и тесте открытого поля"
        )
        result = simplify_methodology_terms(text, max_annotations=3)
        self.assertEqual(result.count("("), 3)

    def test_zero_cap_leaves_text_unchanged(self):
        text = "поведение в тесте открытого поля."
        self.assertEqual(simplify_methodology_terms(text, max_annotations=0), text)

    def test_matches_across_grammatical_case(self):
        """Термины встречаются в разных падежах в реальных переводах
        (предложный после 'в', родительный и т.п.) — паттерн должен ловить
        оба, не только точную форму из article id=483."""
        self.assertIn("(", simplify_methodology_terms("животных тестировали в приподнятом крестообразном лабиринте."))
        self.assertIn("(", simplify_methodology_terms("использовался приподнятый крестообразный лабиринт."))


if __name__ == "__main__":
    unittest.main()
