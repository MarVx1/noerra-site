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

    def test_practical_marker_accepts_genuine_recommendations(self):
        for sentence in (
            "Там, где это возможно, следует избегать приёма лекарств во время беременности.",
            "Пение может улучшить это обучение.",
            "Стоит пересмотреть режим сна перед экзаменом.",
            "Эти данные могут быть использованы для ранней диагностики.",
        ):
            with self.subTest(sentence=sentence):
                self.assertTrue(_has_practical_marker(sentence))

    def test_practical_marker_rejects_methodology(self):
        """Регрессия: в блок 'Практический вывод' попадала методология —
        'Были применены модели продольных структурных уравнений'."""
        for sentence in (
            "Были применены анализ модерации и модели структурных уравнений.",
            "Используя измерения кортизола, мы оценивали реакцию на стресс.",
            "Клинические данные анализировались с использованием регрессии.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(_has_practical_marker(sentence))

    def test_practical_marker_rejects_intro_and_definitions(self):
        for sentence in (
            "Глифосат является одним из наиболее широко используемых гербицидов.",
            "Микроглия стала ключевым регулятором пластичности нейронов.",
            "Способность различать полезные и отталкивающие стимулы важна для выживания.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(_has_practical_marker(sentence))

    def test_practical_marker_rejects_calls_for_future_research(self):
        """Призыв к будущим исследованиям — это задача для науки,
        а не практическая польза для читателя."""
        for sentence in (
            "Требуются дополнительные исследования для подтверждения выводов.",
            "Необходимы дальнейшие работы на больших выборках.",
        ):
            with self.subTest(sentence=sentence):
                self.assertFalse(_has_practical_marker(sentence))

    def test_practical_marker_word_boundary_predstoit(self):
        """Регрессия: маркер 'стоит' ловился внутри 'предСТОИТ выяснить' —
        открытый вопрос принимался за рекомендацию."""
        self.assertFalse(
            _has_practical_marker("Однако ещё предстоит выяснить, как это работает.")
        )

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



class TestRussianOnlyHelpers(unittest.TestCase):
    """Требование: в статье не должно быть английского текста."""

    def test_strips_latin_abbreviation_in_parens(self):
        from adaptation.utils import _strip_latin_abbreviations
        text = "Прилежащее ядро (NAc) и ядро ложа терминальной полоски (BNST) активны."
        result = _strip_latin_abbreviations(text)
        self.assertNotIn("NAc", result)
        self.assertNotIn("BNST", result)
        self.assertIn("Прилежащее ядро", result)
        self.assertNotIn(" ,", result)

    def test_keeps_parens_with_russian_content(self):
        from adaptation.utils import _strip_latin_abbreviations
        text = "Эффект сохраняется (по крайней мере неделю)."
        self.assertIn("(по крайней мере неделю)", _strip_latin_abbreviations(text))

    def test_removes_invisible_spaces(self):
        from adaptation.utils import _strip_latin_abbreviations
        self.assertNotIn("​", _strip_latin_abbreviations("ядро​​ мозга"))

    def test_latin_ratio_and_cleanliness(self):
        from adaptation.utils import _latin_ratio, _is_clean_russian
        self.assertEqual(_latin_ratio("Полностью русское предложение."), 0.0)
        self.assertTrue(_is_clean_russian("Полностью русское предложение."))
        self.assertFalse(_is_clean_russian("Mostly latin sentence here."))

    def test_decompose_prefers_latin_free_sentences(self):
        from adaptation.utils import _decompose_abstract
        abstract = (
            "Результаты показывают, что ADGRL3 KO мыши demonstrate altered DA release. "
            "Результаты показывают, что недосып ухудшает память."
        )
        d = _decompose_abstract(abstract)
        # При наличии выбора finding должен быть взят из чистого предложения.
        self.assertIn("недосып", d["finding"].lower())


if __name__ == '__main__':
    unittest.main()
