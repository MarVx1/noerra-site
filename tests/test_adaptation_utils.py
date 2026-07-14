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

    def test_practical_marker_rejects_meta_commentary_about_research(self):
        """Регрессия: 'подчёркивает необходимость' ловило meta-комментарий
        о самой науке ('нужна методологическая последовательность'), а не
        практическую пользу для читателя (найдено вычиткой реальной
        статьи про когницию, 2026-07-14)."""
        sentence = (
            "Этот дискурс подчеркивает необходимость концептуальной ясности, "
            "методологической последовательности и критического различия "
            "между нейронным взаимодействием и поведенческим выражением."
        )
        self.assertFalse(_has_practical_marker(sentence))

    def test_practical_marker_word_boundary_predstoit(self):
        """Регрессия: маркер 'стоит' ловился внутри 'предСТОИТ выяснить' —
        открытый вопрос принимался за рекомендацию."""
        self.assertFalse(
            _has_practical_marker("Однако ещё предстоит выяснить, как это работает.")
        )

    def test_fix_translation_does_not_truncate_instrumental_case(self):
        """Регрессия: text.replace('вознаграждение', 'награду') обрезал
        более длинную словоформу до 'наградум'. Сейчас одиночное слово
        вообще не заменяется (см. тест ниже), поэтому проверяем главное —
        текст не искажается."""
        result = _fix_translation("во время выполнения задания с вознаграждением.")
        self.assertNotIn("наградум", result)
        self.assertIn("с вознаграждением", result)

    def test_fix_translation_does_not_break_gender_agreement(self):
        """Регрессия: замена одиночного 'вознаграждение' (ср.р.) на
        'награда' (ж.р.) ломала согласование с прилагательным —
        'пищевое вознаграждение' превращалось в 'пищевое награду'.
        Одиночное слово теперь не заменяется: оно и так нормальное русское.
        """
        cases = (
            "Пищевое вознаграждение является полезной основой.",
            "Денежное вознаграждение увеличивает мотивацию.",
            "Пищевого вознаграждения ждали все.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(_fix_translation(text), text)

    def test_fix_translation_still_replaces_whole_noun_phrases(self):
        """Замены целой именной группы безопасны: заменяется и вершина,
        и зависимое слово, поэтому род не рассыпается."""
        self.assertIn("системы награды", _fix_translation("системы вознаграждения работают иначе."))
        self.assertIn(
            "ошибка предсказания награды",
            _fix_translation("ошибка прогнозирования вознаграждения растёт."),
        )

    def test_fix_translation_medicare_claims_not_complaints(self):
        """Регрессия: 'Medicare claims' (записи о страховых случаях)
        Google Translate перевёл дословно как 'претензии' (жалобы) —
        нашлось в реальной сгенерированной статье про CPAP и апноэ сна,
        2026-07-15."""
        result = _fix_translation(
            "участников, имеющих связанные претензии по программе Medicare, с одним или "
            "несколькими утверждениями CPAP."
        )
        self.assertNotIn("претензии", result)
        self.assertNotIn("утверждениями CPAP", result)
        self.assertIn("данные о страховых случаях Medicare", result)
        self.assertIn("случаями применения CPAP", result)

    def test_fix_translation_mage_is_not_a_wizard(self):
        """Регрессия: статистическое сокращение 'Mage' (mean age) Google
        Translate транслитерировал как 'Маг' (волшебник). Фикс ограничен
        позицией перед '=', чтобы не трогать настоящее слово 'маг'."""
        result = _fix_translation("54 женщины, Маг = 22,46, SD = 4,50.")
        self.assertNotIn("Маг", result)
        self.assertIn("Средний возраст = 22,46", result)

    def test_fix_translation_does_not_touch_genuine_word_mag(self):
        """Слово 'маг' само по себе (не рядом с '=') — обычное русское
        слово, трогать его нельзя."""
        text = "Маг из старой сказки был персонажем этой истории."
        self.assertEqual(_fix_translation(text), text)



class TestSectionLabels(unittest.TestCase):
    """Метки разделов структурированного абстракта приходят из источника
    приклеенными к следующему слову ("IntroductionAlthough...") — HTML-теги
    схлопываются ещё на стороне фида. В статье это давало "ВведениеХотя".
    """

    def test_strips_glued_label(self):
        from adaptation.utils import _strip_section_labels
        result = _strip_section_labels("IntroductionAlthough positive effects are reported.")
        self.assertEqual(result, "Although positive effects are reported.")

    def test_strips_glued_results_label(self):
        from adaptation.utils import _strip_section_labels
        result = _strip_section_labels("ResultsCorrelation analysis revealed links.")
        self.assertEqual(result, "Correlation analysis revealed links.")

    def test_strips_label_with_colon_or_space(self):
        from adaptation.utils import _strip_section_labels
        self.assertEqual(
            _strip_section_labels("Methods: We used a randomized design."),
            "We used a randomized design.",
        )
        self.assertEqual(
            _strip_section_labels("Background Adult ADHD is common."),
            "Adult ADHD is common.",
        )

    def test_leaves_ordinary_prose_untouched(self):
        """Lookahead на заглавную защищает обычную прозу от вырезания."""
        from adaptation.utils import _strip_section_labels
        for text in (
            "Results show that sleep improves memory.",
            "The method was validated in a cohort.",
        ):
            with self.subTest(text=text):
                self.assertEqual(_strip_section_labels(text), text)


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
