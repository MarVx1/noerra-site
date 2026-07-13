import unittest

from adaptation.simplifier import simplify_text


class TestSimplifyText(unittest.TestCase):
    """Simplification (Stage 6): убирает канцеляризмы без потери смысла."""

    def test_empty_text_returns_empty(self):
        self.assertEqual(simplify_text(""), "")

    def test_removes_v_dannoy_rabote(self):
        text = "В данной работе рассматривается влияние сна на память."
        result = simplify_text(text)
        self.assertNotIn("в данной работе", result.lower())
        self.assertIn("рассматривается влияние сна на память", result)

    def test_replaces_nastoyashchee_issledovanie(self):
        text = "Настоящее исследование показывает связь между стрессом и сном."
        result = simplify_text(text)
        self.assertNotIn("настоящее исследование", result.lower())
        self.assertIn("это исследование", result.lower())

    def test_removes_v_khode_issledovaniya(self):
        text = "В ходе исследования участники проходили тестирование памяти."
        result = simplify_text(text)
        self.assertNotIn("в ходе исследования", result.lower())

    def test_replaces_avtory_issledovaniya(self):
        text = "Авторы исследования отмечают ограничения выборки."
        result = simplify_text(text)
        self.assertNotIn("авторы исследования", result.lower())
        self.assertIn("исследователи", result.lower())

    def test_removes_bylo_ustanovleno_chto(self):
        text = "Было установлено, что эффект сохраняется в течение недели."
        result = simplify_text(text)
        self.assertNotIn("было установлено", result.lower())

    def test_removes_takim_obrazom(self):
        text = "Таким образом, результаты подтверждают гипотезу."
        result = simplify_text(text)
        self.assertNotIn("таким образом", result.lower())

    def test_removes_sleduet_otmetit_chto(self):
        text = "Следует отметить, что размер выборки был небольшим."
        result = simplify_text(text)
        self.assertNotIn("следует отметить", result.lower())

    def test_removes_uchenye_obnaruzhili_chto(self):
        text = "Учёные обнаружили, что уровень кортизола растёт при недосыпе."
        result = simplify_text(text)
        self.assertNotIn("учёные обнаружили", result.lower())

    def test_no_double_spaces_after_removal(self):
        text = "В данной работе  рассматривается тема."
        result = simplify_text(text)
        self.assertNotIn("  ", result)

    def test_leaves_clean_text_unchanged_in_substance(self):
        text = "Дофамин связан с ожиданием награды, а не с самим удовольствием."
        result = simplify_text(text)
        self.assertIn("Дофамин связан с ожиданием награды", result)


if __name__ == "__main__":
    unittest.main()
