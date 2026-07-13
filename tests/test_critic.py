import unittest
from adaptation.critic import EditorialCritic, HARD_PROBLEM_TEXTS


class TestEditorialCritic(unittest.TestCase):
    def setUp(self):
        self.critic = EditorialCritic()
        self.good_passport = {
            "confidence_score": 0.8,
            "main_idea": "Недосып ухудшает рабочую память.",
            "evidence_strength": "high",
            "limitations": "Небольшой размер выборки.",
            "sources": "PubMed, arXiv",
            "analogy": "Сон похож на ночную смену уборщиков в офисе.",
        }
        # Текст фикстур — русский: критик блокирует латиницу в статье
        # (check_language_is_russian), и англоязычная заглушка теперь
        # справедливо не проходит.
        self.good_text = (
            "Недосып ухудшает рабочую память.\n\n"
            "Это важно, потому что влияет на повседневные решения.\n\n"
            "Практический вывод: стоит обеспечить достаточный сон.\n\n"
            "Однако доказательства пока не окончательные."
        )

    def test_passes_good_content(self):
        text = (
            "Недосып ухудшает рабочую память.\n\n"
            "Это важно, потому что влияет на повседневные решения.\n\n"
            "Практический вывод: стоит обеспечить достаточный сон.\n\n"
            "Однако доказательства пока не окончательные. Это развенчивает распространённый миф, "
            "будто сон — это просто отдых."
        )
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertLessEqual(len(review["problems"]), 1)

    def test_fails_low_confidence_weak(self):
        """Low confidence + weak evidence blocks publication."""
        passport = {**self.good_passport, "confidence_score": 0.2, "evidence_strength": "weak"}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Low confidence" in p for p in review["scientific"]))

    def test_passes_low_confidence_preliminary(self):
        """Low confidence + preliminary/limited is soft — does not block."""
        passport = {**self.good_passport, "confidence_score": 0.2, "evidence_strength": "preliminary"}
        review = self.critic.review(passport, self.good_text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("Limited evidence" in p for p in review["scientific"]))

    def test_fails_no_limitations(self):
        """Limitations is a soft problem — reported but does not block."""
        passport = {**self.good_passport, "limitations": ""}
        review = self.critic.review(passport, self.good_text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("Limitations" in p for p in review["scientific"]))

    def test_fails_hype_language(self):
        """Hype language is a soft problem — reported but does not block."""
        text = "Это революционный прорыв! Он полностью меняет всё."
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("Sensational" in p or "hype" in p.lower() for p in review["uncertainty"]))

    def test_fails_short_text(self):
        """Short text is a soft problem — reported but does not block."""
        review = self.critic.review(self.good_passport, "Слишком короткий текст.")
        self.assertTrue(review["passed"])
        self.assertTrue(any("too short" in p.lower() for p in review["clarity"]))

    def test_fails_no_practical_value(self):
        """Missing practical value is a soft problem — reported but does not block."""
        text = (
            "Недосып ухудшает рабочую память.\n\n"
            "Результаты показывают заметный эффект на когнитивные показатели.\n\n"
            "Однако доказательства пока не окончательные."
        )
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("Practical" in p for p in review["practical"]))

    def test_fails_no_sources(self):
        passport = {**self.good_passport, "sources": ""}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Sources" in p for p in review["scientific"]))

    def test_hype_language_russian_markers_soft(self):
        """Расширенный список хайп-маркеров (EDITORIAL_PLAYBOOK.md, Правило №8)
        — тоже soft на данном этапе (promotion в hard — Фаза 7)."""
        text = self.good_text + "\n\nЭто просто сенсация в мире науки!"
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("Sensational" in p for p in review["uncertainty"]))

    def test_cancellerism_detected_soft(self):
        """Канцеляризмы из EDITORIAL_ENGINE.md ('Запрещённые конструкции')
        сейчас soft — фиксируются, но не блокируют публикацию."""
        text = self.good_text + "\n\nТаким образом, было установлено, что эффект значим."
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("cancellerism" in p.lower() for p in review["style_language"]))

    def test_no_cancellerism_in_clean_text(self):
        review = self.critic.review(self.good_passport, self.good_text)
        self.assertEqual(review["style_language"], [])

    def test_rhythm_flags_repeated_paragraph_openers(self):
        text = (
            "Это первый абзац про сон.\n\n"
            "Это второй абзац про сон.\n\n"
            "Однако доказательства пока предварительные."
        )
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("monotonous rhythm" in p for p in review["rhythm"]))

    def test_rhythm_passes_varied_openers(self):
        review = self.critic.review(self.good_passport, self.good_text)
        self.assertEqual(review["rhythm"], [])

    def test_long_sentence_flagged_as_soft(self):
        """Стилевые метрики (Фаза 6) — soft на старте (burn-in rollout)."""
        long_sentence = " ".join(["слово"] * 30) + "."
        text = self.good_text + "\n\n" + long_sentence
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertTrue(any("exceed" in p and "words" in p for p in review["clarity"]))

    def test_latin_text_blocks_publication(self):
        """Требование: статья только на русском. Латиница — hard-стоп.

        Такое остаётся, когда имя гена — само подлежащее ("Как ADGRL3
        влияет..."): переписать rule-based нельзя, поэтому лучше не
        публиковать вовсе, чем выпустить полуанглийский текст.
        """
        text = self.good_text + "\n\nОднако то, как ADGRL3 влияет на дофамин, изучено плохо."
        review = self.critic.review(self.good_passport, text)
        self.assertFalse(review["passed"])
        self.assertTrue(any(p.startswith("Latin text") for p in review["hard_problems"]))

    def test_source_brand_names_are_allowed(self):
        """Названия источников — имена собственные, они не блокируют."""
        text = self.good_text + "\n\nОсновано на материалах: PubMed, arXiv."
        review = self.critic.review(self.good_passport, text)
        self.assertEqual(review["language"], [])

    def test_clean_russian_text_passes_language_check(self):
        self.assertEqual(self.critic.check_language_is_russian(self.good_text), [])

    def test_fails_missing_analogy(self):
        """Analogy (Stage 7) отсутствует — это hard-блокер публикации."""
        passport = {**self.good_passport, "analogy": ""}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertIn("Analogy is missing.", review["hard_problems"])

    def test_check_myths_ignores_non_debunk_scenarios(self):
        """Регрессия на баг: раньше check_myths никогда не мог сообщить о
        проблеме ни при каких условиях (return [] был недостижим). Теперь
        метод реально работает, но только для сценария 'debunk'."""
        issues = self.critic.check_myths("Нейтральный текст про сон и память.", scenario="discovery")
        self.assertEqual(issues, [])

    def test_check_myths_flags_debunk_without_myth_phrase(self):
        issues = self.critic.check_myths("Нейтральный текст про сон и память.", scenario="debunk")
        self.assertTrue(issues)
        self.assertIn("Debunk scenario but no explicit myth/misconception phrase found.", issues)

    def test_check_myths_passes_debunk_with_myth_phrase(self):
        issues = self.critic.check_myths("Это развенчивает распространённое заблуждение.", scenario="debunk")
        self.assertEqual(issues, [])

    def test_practical_honesty_passes_when_practical_value_true(self):
        passport = {**self.good_passport, "scenario": "practical", "practical_value": True}
        issues = self.critic.check_practical_honesty(passport, self.good_text)
        self.assertEqual(issues, [])

    def test_practical_honesty_passes_for_non_practical_scenario_silence(self):
        """Для сценариев, отличных от 'practical', отсутствие блока про
        пользу — легитимное честное умолчание, а не фабрикация."""
        passport = {**self.good_passport, "scenario": "discovery", "practical_value": False}
        issues = self.critic.check_practical_honesty(passport, self.good_text)
        self.assertEqual(issues, [])

    def test_practical_honesty_fails_when_practical_scenario_lacks_honest_fallback(self):
        passport = {**self.good_passport, "scenario": "practical", "practical_value": False}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("honest fallback" in p for p in review["practical_honesty"]))

    def test_practical_honesty_passes_when_honest_fallback_present(self):
        from adaptation.editorial_engine import HONEST_NO_PRACTICAL_PATTERNS
        passport = {**self.good_passport, "scenario": "practical", "practical_value": False}
        text = self.good_text + "\n\n" + HONEST_NO_PRACTICAL_PATTERNS[0]
        review = self.critic.review(passport, text)
        self.assertEqual(review["practical_honesty"], [])


class TestHardProblemTextsConsistency(unittest.TestCase):
    """Regression guard для HARD_PROBLEM_TEXTS (см. план доработки, Фаза 7).

    Полный рефакторинг на severity-коды (code, message) не был сделан —
    риск сломать ~15+ существующих проверок на подстроку сообщения счёл
    непропорциональным пользе для уже статичных 7 hard-строк. Вместо этого
    этот тест фиксирует ожидаемый состав set явным списком: любое случайное
    добавление/удаление/переименование hard-сообщения без обновления этого
    теста будет замечено при code review диффа теста, а не тихо потеряно.
    """

    def test_hard_problem_texts_exact_set(self):
        expected = {
            "Main idea not detected.",
            "Sources are not provided.",
            "Low confidence in findings (recommend verification of evidence).",
            "Evidence strength is low: weak.",
            "Duplicate sentences detected in text.",
            "Analogy is missing.",
            "Practical value is false but no honest fallback phrase found in text.",
        }
        self.assertEqual(HARD_PROBLEM_TEXTS, expected)


if __name__ == "__main__":
    unittest.main()
