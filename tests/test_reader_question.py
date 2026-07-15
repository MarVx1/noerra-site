import unittest

from adaptation.reader_question import (
    build_reader_question,
    _extract_finding_subject,
    QUESTION_PATTERNS,
    FINDING_QUESTION_PATTERNS,
)


class TestExtractFindingSubject(unittest.TestCase):
    def test_strips_boilerplate_prefix(self):
        finding = "Мы обнаружили, что социальная изоляция вызывала депрессивно-подобное поведение у мышей."
        subject = _extract_finding_subject(finding)
        self.assertNotIn("Мы обнаружили", subject)
        self.assertIn("социальная изоляция", subject)

    def test_cuts_at_clause_boundary_comma_not_mid_word(self):
        """Реальный случай (article id=391): без границы по запятой
        обрезка по числу слов попадала на середину глагола без
        дополнения ('показывают')."""
        finding = (
            "Обструктивное апноэ во сне связано со снижением когнитивных функций, "
            "но краткосрочные исследования показывают ограниченные преимущества."
        )
        subject = _extract_finding_subject(finding)
        self.assertEqual(subject, "Обструктивное апноэ во сне связано со снижением когнитивных функций")

    def test_strips_parenthetical_glossary_annotations(self):
        """Реальный случай (article id=483): jargon_glossary.py добавляет
        скобки со своей запятой внутри — граница клаузы не должна попадать
        внутрь скобки."""
        finding = (
            "Изоляция вызывала поведение в тесте на предпочтение сахарозы "
            "(проверяет, тянется ли животное к сладкому), тесте плавания."
        )
        subject = _extract_finding_subject(finding)
        self.assertNotIn("(", subject)
        self.assertNotIn(")", subject)

    def test_never_ends_with_literal_ellipsis(self):
        """content_audit.py считает литеральные '...' сигнатурой обрыва —
        извлечённый фрагмент не должен её создавать."""
        long_finding = " ".join(["слово"] * 30) + "."
        subject = _extract_finding_subject(long_finding)
        self.assertFalse(subject.endswith("..."))

    def test_empty_finding_returns_empty(self):
        self.assertEqual(_extract_finding_subject(""), "")

    def test_caps_word_count_fallback(self):
        long_finding = " ".join(f"слово{i}" for i in range(30)) + "."
        subject = _extract_finding_subject(long_finding, max_words=5)
        self.assertEqual(len(subject.split()), 5)


class TestBuildReaderQuestion(unittest.TestCase):
    def test_uses_finding_aware_template_when_finding_available(self):
        finding = "Мы обнаружили, что двухнедельная социальная изоляция вызывала депрессивно-подобное поведение у мышей."
        question = build_reader_question("stress", "discovery", finding=finding)
        self.assertTrue(question.strip().endswith("?"))
        self.assertIn("социальная изоляция", question)

    def test_falls_back_to_generic_when_finding_empty(self):
        question = build_reader_question("stress", "discovery", finding="")
        self.assertTrue(question.strip().endswith("?"))
        self.assertNotIn("социальная изоляция", question)

    def test_falls_back_to_generic_for_scenario_without_finding_templates(self):
        """explanation не расширялся finding-шаблонами (не входил в
        разобранный дефект) — должен остаться прежним generic-вопросом,
        не ссылаться на конкретику находки."""
        finding = "Мы обнаружили, что дофамин кодирует ошибку предсказания вознаграждения у мышей."
        question = build_reader_question("dopamine", "explanation", finding=finding)
        self.assertTrue(question.strip().endswith("?"))
        self.assertNotIn("ошибку предсказания", question)

    def test_all_scenarios_still_produce_a_question_without_finding(self):
        for scenario in QUESTION_PATTERNS:
            question = build_reader_question("dopamine", scenario)
            self.assertTrue(question.strip().endswith("?"), f"{scenario}: {question!r}")

    def test_finding_question_patterns_only_cover_intended_scenarios(self):
        """FINDING_QUESTION_PATTERNS — точечное расширение под найденный
        дефект (article id=483, сценарий discovery), не полная замена
        QUESTION_PATTERNS для всех сценариев."""
        self.assertIn("discovery", FINDING_QUESTION_PATTERNS)
        self.assertNotIn("practical", FINDING_QUESTION_PATTERNS)
        self.assertNotIn("explanation", FINDING_QUESTION_PATTERNS)
        self.assertNotIn("review", FINDING_QUESTION_PATTERNS)


if __name__ == "__main__":
    unittest.main()
