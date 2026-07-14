import re
import unittest
from parsers.base import RawArticle
from adaptation.editorial_engine import (
    detect_scenario, build_editorial_text, EditorialEngine,
    Scenario,
    LEAD_PATTERNS, TITLE_PATTERNS, WHY_PATTERNS, CAVEAT_PATTERNS,
    PRACTICAL_OPENERS, PRACTICAL_FOOTERS, HONEST_NO_PRACTICAL_PATTERNS,
)
from adaptation.critic import EditorialCritic, HYPE_MARKERS, CANCELLERISM_MARKERS
from adaptation.publication import Publication
from adaptation.reader_question import QUESTION_PATTERNS, build_reader_question
from adaptation.analogy_bank import TOPIC_ANALOGIES, GENERIC_ANALOGIES, build_analogy
from adaptation.transitions import (
    TRANSITION_INTO_BODY, TRANSITION_INTO_ANALOGY, TRANSITION_INTO_SIGNIFICANCE,
    build_transition,
)
from classifier.classifier import _TOPIC_CASES


class TestDetectScenario(unittest.TestCase):
    """Tests for scenario detection logic."""

    def test_debunk(self):
        article = RawArticle(
            title="Myth about dopamine",
            url="https://example.com",
            abstract="This paper refutes a widespread misconception about dopamine.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "debunk")

    def test_practical(self):
        article = RawArticle(
            title="Practical application of sleep research",
            url="https://example.com",
            abstract="This study provides a practical method for improving sleep habits.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "practical")

    def test_confirmation(self):
        article = RawArticle(
            title="Replication study confirms previous findings",
            url="https://example.com",
            abstract="This study replicates and confirms earlier results on stress.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "confirmation")

    def test_discovery(self):
        article = RawArticle(
            title="Novel pathway for neural growth",
            url="https://example.com",
            abstract="A previously unknown discovery was made for neural growth.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "discovery")

    def test_review(self):
        article = RawArticle(
            title="Meta-analysis of sleep studies",
            url="https://example.com",
            abstract="This meta-analysis provides an overview of several studies on insomnia.",
            source="pubmed",
        )
        # "meta-analysis" matches review, "several studies" matches discussion,
        # but review comes after discussion in priority order,
        # so this should be "discussion" unless we make abstract review-specific
        # Use abstract with only review markers
        article2 = RawArticle(
            title="Systematic review of sleep research",
            url="https://example.com",
            abstract="This systematic review summarizes key findings from published literature.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article2), "review")

    def test_explanation(self):
        article = RawArticle(
            title="How the amygdala processes fear",
            url="https://example.com",
            abstract="This paper explains the mechanism of fear response in the brain.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "explanation")

    def test_discussion(self):
        article = RawArticle(
            title="Debate on dopamine's role in motivation",
            url="https://example.com",
            abstract="Multiple studies present competing views on dopamine function.",
            source="pubmed",
        )
        self.assertEqual(detect_scenario(article), "discussion")

    def test_empty_abstract_falls_back_to_discovery(self):
        article = RawArticle(
            title="Some random neuroscience paper",
            url="https://example.com",
            abstract="",
            source="arxiv",
        )
        scenario = detect_scenario(article)
        self.assertIn(scenario, ["discovery", "explanation"])


class TestEditorialEngineAnalyze(unittest.TestCase):
    """Tests for EditorialEngine.analyze() — passport generation."""

    def setUp(self):
        self.engine = EditorialEngine()
        self.article = RawArticle(
            title="Dopamine and motivation: new evidence",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior. "
                     "The results show significant correlation in the nucleus accumbens.",
            source="pubmed",
        )

    def test_passport_contains_required_fields(self):
        passport = self.engine.analyze(self.article, "dopamine")
        required = [
            "topic", "topic_ru", "scenario", "title", "lead", "abstract",
            "main_idea", "evidence", "practical_value", "publication_type",
            "novelty", "audience", "confidence_score", "novelty_score",
            "suggested_format", "tone", "source", "editor_notes",
        ]
        for field in required:
            self.assertIn(field, passport, f"Missing field: {field}")

    def test_passport_confidence_score_range(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertGreaterEqual(passport["confidence_score"], 0.0)
        self.assertLessEqual(passport["confidence_score"], 1.0)

    def test_passport_novelty_score_range(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertGreaterEqual(passport["novelty_score"], 0.0)
        self.assertLessEqual(passport["novelty_score"], 1.0)

    def test_passport_editor_notes_not_empty(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertIsInstance(passport["editor_notes"], list)
        self.assertGreater(len(passport["editor_notes"]), 0)

    def test_passport_knowledge_context(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertIn("knowledge_context", passport)

    def test_passport_topic_ru_mapping(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertEqual(passport["topic_ru"], "Дофамин")

    def test_passport_scenario_detected(self):
        passport = self.engine.analyze(self.article, "dopamine")
        self.assertIn(passport["scenario"], [
            "discovery", "confirmation", "debunk", "practical",
            "discussion", "review", "explanation",
        ])


class TestEditorialEngineBuildStructure(unittest.TestCase):
    """Tests for EditorialEngine.build_structure()."""

    def setUp(self):
        self.engine = EditorialEngine()
        self.article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )

    def test_structure_returns_list(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        self.assertIsInstance(structure, list)
        self.assertGreater(len(structure), 0)

    def test_structure_contains_title_and_lead(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        self.assertEqual(structure[0], passport["title"])
        self.assertEqual(structure[1], passport["lead"])

    def test_structure_contains_why_block(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        why_blocks = [s for s in structure if "Почему" in s]
        self.assertGreater(len(why_blocks), 0)

    def test_structure_contains_caveat(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        # Caveat patterns are randomly chosen, check for any of them
        caveat_markers = [
            "не окончательный", "не догма", "очередной шаг",
            "расширяют картину", "стоит помнить",
            "требуют дальнейшей", "требует подтверждения",
            "одно исследование",
        ]
        caveat_blocks = [s for s in structure if any(m in s.lower() for m in caveat_markers)]
        self.assertGreater(len(caveat_blocks), 0)

    def test_structure_contains_source_line(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        source_blocks = [s for s in structure if "Основано на материалах" in s]
        self.assertGreater(len(source_blocks), 0)


class TestEditorialEngineGenerateText(unittest.TestCase):
    """Tests for EditorialEngine.generate_text()."""

    def setUp(self):
        self.engine = EditorialEngine()
        self.article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )

    def test_generate_text_returns_string(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        text = self.engine.generate_text(passport, structure)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 50)

    def test_generate_text_contains_title(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        text = self.engine.generate_text(passport, structure)
        self.assertIn(passport["title"], text)

    def test_generate_text_has_paragraphs(self):
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        text = self.engine.generate_text(passport, structure)
        self.assertIn("\n\n", text)


class TestEditorialEngineCreatePublication(unittest.TestCase):
    """Tests for EditorialEngine.create_publication_for_article()."""

    def setUp(self):
        self.engine = EditorialEngine()
        self.article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )

    def test_publication_is_dataclass(self):
        pub = self.engine.create_publication_for_article(self.article, "dopamine")
        self.assertIsInstance(pub, Publication)

    def test_publication_has_required_fields(self):
        pub = self.engine.create_publication_for_article(self.article, "dopamine")
        self.assertTrue(pub.title)
        self.assertTrue(pub.lead)
        self.assertTrue(pub.short_version)
        self.assertTrue(pub.full_version)
        self.assertIsInstance(pub.sources, list)
        self.assertTrue(pub.topic)
        self.assertTrue(pub.format)
        self.assertIsInstance(pub.confidence_score, float)

    def test_publication_confidence_in_range(self):
        pub = self.engine.create_publication_for_article(self.article, "dopamine")
        self.assertGreaterEqual(pub.confidence_score, 0.0)
        self.assertLessEqual(pub.confidence_score, 1.0)

    def test_publication_short_version_is_subset_of_full(self):
        pub = self.engine.create_publication_for_article(self.article, "dopamine")
        self.assertIn(pub.short_version, pub.full_version)


class TestEditorialCritic(unittest.TestCase):
    """Tests for EditorialCritic."""

    def setUp(self):
        self.critic = EditorialCritic()

    def test_passes_good_publication(self):
        passport = {
            "confidence_score": 0.8,
            "main_idea": "Дофамин влияет на мотивацию",
            "evidence_strength": "high",
            "limitations": "Небольшая выборка.",
            "sources": "PubMed",
            "analogy": "Дофамин работает как система предсказаний, а не кнопка удовольствия.",
        }
        # Текст русский: критик блокирует латиницу в статье.
        text = (
            "Достаточно длинный текст публикации, который должен пройти проверки критика.\n\n"
            "Здесь ещё немного содержания, добавляющего общей длины этой публикации.\n\n"
            "А вот третий абзац, где слов ещё больше, чтобы текст точно оказался достаточно длинным. "
            "Практический вывод: это может помочь принять решение."
        )
        review = self.critic.review(passport, text)
        self.assertTrue(review["passed"])

    def test_fails_low_confidence(self):
        passport = {
            "confidence_score": 0.2,
            "evidence_strength": "weak",
            "publication_type": "article",
            "main_idea": "",
        }
        review = self.critic.review(passport, "Короткий текст.")
        self.assertFalse(review["passed"])
        self.assertTrue(any("Low confidence" in item for item in review["scientific"]))

    def test_fails_short_text(self):
        """Short text is a soft problem — reported but does not block."""
        passport = {
            "confidence_score": 0.8,
            "main_idea": "Некоторая идея",
            "evidence_strength": "high",
            "limitations": "Тестовое ограничение.",
            "sources": "Тестовый источник.",
            "analogy": "Это похоже на тестовую аналогию.",
        }
        review = self.critic.review(passport, "Короткий текст.")
        self.assertTrue(review["passed"])
        self.assertTrue(any("too short" in item.lower() for item in review["clarity"]))

    def test_fails_missing_main_idea(self):
        passport = {
            "confidence_score": 0.8,
            "publication_type": "article",
            "main_idea": "",
        }
        review = self.critic.review(passport, "Long enough text. " * 20)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Main idea not detected" in item for item in review["scientific"]))

    def test_review_returns_problems_list(self):
        passport = {
            "confidence_score": 0.2,
            "publication_type": "article",
            "main_idea": "",
        }
        review = self.critic.review(passport, "Short.")
        self.assertIsInstance(review["problems"], list)
        self.assertGreater(len(review["problems"]), 0)

    def test_review_returns_scientific_and_style_separately(self):
        passport = {
            "confidence_score": 0.2,
            "main_idea": "",
            "evidence_strength": "weak",
            "limitations": "",
            "sources": "",
        }
        review = self.critic.review(passport, "Short.")
        self.assertIsInstance(review["scientific"], list)
        self.assertIsInstance(review["clarity"], list)


class TestBuildEditorialText(unittest.TestCase):
    """Tests for the legacy build_editorial_text wrapper."""

    def test_returns_string(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        text = build_editorial_text(article, "dopamine")
        self.assertIsInstance(text, str)

    def test_contains_source_line(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        text = build_editorial_text(article, "dopamine")
        self.assertIn("Основано на материалах", text)

    def test_contains_title(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        text = build_editorial_text(article, "dopamine")
        self.assertTrue(text.split("\n")[0])


class TestTemplatesDoNotContainBannedPhrases(unittest.TestCase):
    """Regression guard: шаблоны генерации не должны содержать хайп/канцеляризмы
    из EDITORIAL_ENGINE.md / EDITORIAL_PLAYBOOK.md (см. critic.HYPE_MARKERS /
    CANCELLERISM_MARKERS). Защищает от повторения бага, когда собственные
    шаблоны движка нарушали же те правила, которые проверяет критик.
    """

    def _assert_clean(self, name: str, text: str, banned: tuple[str, ...]):
        low = text.lower()
        for marker in banned:
            self.assertNotIn(
                marker, low,
                f"{name!r} contains banned phrase {marker!r}: {text!r}",
            )

    def test_dict_pattern_banks_are_clean(self):
        banned = HYPE_MARKERS + CANCELLERISM_MARKERS
        for bank_name, bank in (
            ("LEAD_PATTERNS", LEAD_PATTERNS),
            ("TITLE_PATTERNS", TITLE_PATTERNS),
        ):
            for scenario, templates in bank.items():
                for template in templates:
                    self._assert_clean(f"{bank_name}[{scenario}]", template, banned)

    def test_list_pattern_banks_are_clean(self):
        banned = HYPE_MARKERS + CANCELLERISM_MARKERS
        for bank_name, templates in (
            ("WHY_PATTERNS", WHY_PATTERNS),
            ("CAVEAT_PATTERNS", CAVEAT_PATTERNS),
            ("PRACTICAL_OPENERS", PRACTICAL_OPENERS),
            ("PRACTICAL_FOOTERS", PRACTICAL_FOOTERS),
            ("HONEST_NO_PRACTICAL_PATTERNS", HONEST_NO_PRACTICAL_PATTERNS),
        ):
            for template in templates:
                self._assert_clean(bank_name, template, banned)

    def test_analogy_and_question_banks_are_clean(self):
        banned = HYPE_MARKERS + CANCELLERISM_MARKERS
        for topic, templates in TOPIC_ANALOGIES.items():
            for template in templates:
                self._assert_clean(f"TOPIC_ANALOGIES[{topic}]", template, banned)
        for scenario, templates in GENERIC_ANALOGIES.items():
            for template in templates:
                self._assert_clean(f"GENERIC_ANALOGIES[{scenario}]", template, banned)
        for scenario, templates in QUESTION_PATTERNS.items():
            for template in templates:
                self._assert_clean(f"QUESTION_PATTERNS[{scenario}]", template, banned)
        for bank_name, templates in (
            ("TRANSITION_INTO_BODY", TRANSITION_INTO_BODY),
            ("TRANSITION_INTO_ANALOGY", TRANSITION_INTO_ANALOGY),
            ("TRANSITION_INTO_SIGNIFICANCE", TRANSITION_INTO_SIGNIFICANCE),
        ):
            for template in templates:
                self._assert_clean(bank_name, template, banned)


class TestPracticalValueHonesty(unittest.TestCase):
    """Practical Value (Stage 8): запрещено выдумывать советы — если реальной
    практической пользы нет, текст должен честно об этом сообщать.
    """

    def test_no_fabricated_advice_when_no_practical_marker(self):
        # Сценарий "practical" (триггер — слово "method"/"метод" из
        # SCENARIO_MARKERS["practical"]), но без маркеров реальной
        # практической пользы (recommend/should/helps/практич.../...) —
        # decomposed["practical"] останется пустым, и должен сработать
        # честный fallback, а не выдуманный совет.
        article = RawArticle(
            title="New method for recording neural signals",
            url="https://example.com",
            abstract=(
                "This paper introduces a new method for recording electrical signals from neurons. "
                "Researchers observed distinct pulse patterns in isolated brain tissue."
            ),
            source="pubmed",
        )
        engine = EditorialEngine()
        passport = engine.analyze(article, "neuroscience")
        # detect_scenario() увидел триггер "method"/"метод" и предложил
        # "practical", но раз реального практического вывода не нашлось,
        # analyze() понижает сценарий — иначе заголовок и вопрос читателя
        # обещали бы применение, которого текст сам не подтверждает.
        self.assertNotEqual(passport["scenario"], "practical")
        self.assertFalse(passport["practical_value"])
        structure = engine.build_structure(passport)
        text = "\n\n".join(structure)
        # Старый баг: жёстко зашитая фраза-выдумка про "осознанные решения"
        self.assertNotIn(
            "Результат помогает принять более осознанные решения, связанные с этой темой.",
            text,
        )
        # Сценарий понижен до не-practical, поэтому текст просто не поднимает
        # тему практического применения — ни выдуманного совета, ни честной
        # оговорки о его отсутствии. Заголовок и вопрос читателя при этом
        # тоже не должны обещать применение, которого не будет в статье.
        self.assertNotIn("как применить", passport["title"].lower())
        self.assertNotIn("применить", passport["reader_question"].lower())


class TestReaderQuestion(unittest.TestCase):
    """Reader Question (Stage 3): настоящий вопрос, а не утверждение."""

    def test_all_scenarios_produce_a_question(self):
        for scenario in QUESTION_PATTERNS:
            question = build_reader_question("dopamine", scenario)
            self.assertTrue(question.strip().endswith("?"), f"{scenario}: {question!r}")

    def test_unknown_scenario_falls_back_to_discovery(self):
        question = build_reader_question("dopamine", "not-a-real-scenario")
        self.assertTrue(question.strip().endswith("?"))

    def test_passport_reader_question_is_a_question(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        engine = EditorialEngine()
        passport = engine.analyze(article, "dopamine")
        self.assertTrue(passport["reader_question"].strip().endswith("?"))
        self.assertEqual(passport["key_question"], passport["reader_question"])

    def test_reader_question_present_in_generated_text(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        text = build_editorial_text(article, "dopamine")
        engine = EditorialEngine()
        passport = engine.analyze(article, "dopamine")
        # Текст детерминирован по content, но вопрос выбирается случайно —
        # проверяем структуру блоков напрямую, а не сгенерированный текст.
        structure = engine.build_structure(passport)
        self.assertIn(passport["reader_question"], structure)
        # Инвариант, на который полагается scheduler.py: blocks[0] — заголовок.
        self.assertEqual(structure[0], passport["title"])


class TestAnalogyBank(unittest.TestCase):
    """Analogy (Stage 7): обязательная аналогия для каждой публикуемой темы."""

    def test_every_known_topic_has_an_analogy_bank(self):
        for topic in _TOPIC_CASES:
            self.assertIn(topic, TOPIC_ANALOGIES, f"Нет банка аналогий для темы {topic!r}")
            self.assertTrue(TOPIC_ANALOGIES[topic], f"Пустой банк аналогий для темы {topic!r}")

    def test_topic_analogy_banks_have_at_least_8_entries(self):
        """Расширенный банк (Фаза после Editorial Polish) — минимум 8 на
        тему, чтобы заметнее не повторяться при активной публикации."""
        for topic in _TOPIC_CASES:
            self.assertGreaterEqual(
                len(TOPIC_ANALOGIES[topic]), 8,
                f"Банк аналогий для {topic!r} меньше 8 записей",
            )

    def test_topic_analogy_banks_have_no_duplicates(self):
        for topic, bank in TOPIC_ANALOGIES.items():
            self.assertEqual(len(bank), len(set(bank)), f"Дубликаты в банке аналогий {topic!r}")

    def test_topic_analogy_banks_respect_max_sentence_length(self):
        """Аналогия — обычно одно длинное предложение (в отличие от прочих
        шаблонов), поэтому легко случайно превысить лимит в 25 слов
        (style_metrics.MAX_SENTENCE_WORDS) при добавлении новых записей."""
        from adaptation.style_metrics import compute_style_metrics
        for topic, bank in TOPIC_ANALOGIES.items():
            for analogy in bank:
                report = compute_style_metrics(analogy)
                self.assertEqual(
                    report.long_sentences, [],
                    f"Аналогия для {topic!r} превышает лимит длины предложения: {analogy!r}",
                )

    def test_build_analogy_known_topic(self):
        for topic in _TOPIC_CASES:
            analogy = build_analogy(topic, "discovery")
            self.assertTrue(analogy.strip())
            self.assertIn(analogy, TOPIC_ANALOGIES[topic])

    def test_build_analogy_unknown_topic_falls_back_to_generic(self):
        for scenario in GENERIC_ANALOGIES:
            analogy = build_analogy("not-a-real-topic", scenario)
            self.assertTrue(analogy.strip())
            self.assertIn(analogy, GENERIC_ANALOGIES[scenario])

    def test_build_analogy_unknown_topic_and_scenario_never_crashes(self):
        analogy = build_analogy("not-a-real-topic", "not-a-real-scenario")
        self.assertTrue(analogy.strip())

    def test_passport_contains_analogy(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract="This research finds a link between dopamine and motivated behavior.",
            source="pubmed",
        )
        engine = EditorialEngine()
        passport = engine.analyze(article, "dopamine")
        self.assertTrue(passport["analogy"].strip())
        structure = engine.build_structure(passport)
        self.assertTrue(any(passport["analogy"] in block for block in structure))


class TestBuildNamedStructure(unittest.TestCase):
    """Article Outline (Stage 4): именованные обязательные блоки."""

    def setUp(self):
        # Многопредложный абстракт: однопредложные абстракты — реалистичный
        # краевой случай, когда всё содержание уходит в lead и
        # what_science_found легитимно пуст (это soft, а не hard check).
        self.article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract=(
                "This research finds a link between dopamine and motivated behavior. "
                "The study used a sample of 40 participants performing a reward task. "
                "Results suggest that dopamine release predicts effort investment."
            ),
            source="pubmed",
        )
        self.engine = EditorialEngine()

    def test_all_required_blocks_present_and_non_empty(self):
        passport = self.engine.analyze(self.article, "dopamine")
        named = self.engine.build_named_structure(passport)
        for key in ("hook", "reader_question", "what_science_found", "analogy", "why", "caveat"):
            self.assertIn(key, named)
            self.assertTrue(named[key].strip(), f"Block {key!r} is empty")

    def test_build_structure_still_returns_plain_list(self):
        """Низкорисковый вариант: build_structure() не меняет сигнатуру."""
        passport = self.engine.analyze(self.article, "dopamine")
        structure = self.engine.build_structure(passport)
        self.assertIsInstance(structure, list)
        self.assertTrue(all(isinstance(s, str) for s in structure))
        self.assertEqual(structure[0], passport["title"])


class TestCheckOutlineComplete(unittest.TestCase):
    def setUp(self):
        self.critic = EditorialCritic()
        self.good_named_blocks = {
            "hook": "Hook text.",
            "reader_question": "Why does this matter?",
            "what_science_found": "Science found this.",
            "analogy": "This is like something familiar.",
            "why": "Why block text.",
            "caveat": "Caveat text.",
        }

    def test_complete_outline_has_no_issues(self):
        issues = self.critic.check_outline_complete(self.good_named_blocks)
        self.assertEqual(issues, [])

    def test_missing_block_is_reported(self):
        blocks = {**self.good_named_blocks, "analogy": ""}
        issues = self.critic.check_outline_complete(blocks)
        self.assertTrue(any("analogy" in issue for issue in issues))

    def test_review_uses_named_blocks_when_provided(self):
        passport = {
            "confidence_score": 0.8,
            "main_idea": "Некоторая идея",
            "evidence_strength": "high",
            "limitations": "Тестовое ограничение.",
            "sources": "Тестовый источник.",
            "analogy": "Test analogy.",
        }
        text = (
            "This is a long enough text for a publication that should pass the critic checks.\n\n"
            "Here is some more content that adds to the overall length of this particular publication.\n\n"
            "And here is a third paragraph with even more words to ensure the text is definitely long enough."
        )
        broken_blocks = {**self.good_named_blocks, "why": ""}
        review = self.critic.review(passport, text, named_blocks=broken_blocks)
        self.assertTrue(any("why" in issue for issue in review["outline"]))


class TestTransitions(unittest.TestCase):
    """Ритмические переходы (Editorial Polish, EDITORIAL_PLAYBOOK.md Правило 10)."""

    def test_build_transition_known_kinds(self):
        for kind, bank in (
            ("into_body", TRANSITION_INTO_BODY),
            ("into_analogy", TRANSITION_INTO_ANALOGY),
            ("into_significance", TRANSITION_INTO_SIGNIFICANCE),
        ):
            transition = build_transition(kind)
            self.assertIn(transition, bank)

    def test_build_transition_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            build_transition("not-a-real-kind")

    def test_structure_contains_transitions(self):
        article = RawArticle(
            title="Dopamine and motivation",
            url="https://example.com",
            abstract=(
                "This research finds a link between dopamine and motivated behavior. "
                "The study used a sample of 40 participants performing a reward task. "
                "Results suggest that dopamine release predicts effort investment."
            ),
            source="pubmed",
        )
        engine = EditorialEngine()
        passport = engine.analyze(article, "dopamine")
        structure = engine.build_structure(passport)
        self.assertTrue(any(b in TRANSITION_INTO_BODY for b in structure))
        self.assertTrue(any(b in TRANSITION_INTO_ANALOGY for b in structure))
        self.assertTrue(any(b in TRANSITION_INTO_SIGNIFICANCE for b in structure))
        # Инвариант scheduler.py: blocks[0] — заголовок, не должен сдвинуться.
        self.assertEqual(structure[0], passport["title"])



class TestGenderAgreementInTemplates(unittest.TestCase):
    """Темы бывают разного рода (дофамин — м.р., психология — ж.р.), поэтому
    шаблон не должен содержать краткое причастие/прилагательное м.р.,
    согласуемое с темой: получалось "как устроен психология".
    """

    RISKY = re.compile(
        r"\b(устроен|связан|важен|нужен|полезен|известен|изучен|сложен)\b(?![аоыи])"
    )

    def _all_banks(self):
        banks = {}
        for name, bank in (("LEAD", LEAD_PATTERNS), ("TITLE", TITLE_PATTERNS),
                           ("QUESTION", QUESTION_PATTERNS)):
            for scenario, templates in bank.items():
                banks[f"{name}[{scenario}]"] = templates
        for name, templates in (("WHY", WHY_PATTERNS), ("CAVEAT", CAVEAT_PATTERNS),
                                ("FOOTERS", PRACTICAL_FOOTERS)):
            banks[name] = templates
        return banks

    def test_no_gendered_participles_after_substitution(self):
        for bank_name, templates in self._all_banks().items():
            for template in templates:
                for topic, cases in _TOPIC_CASES.items():
                    kwargs = {f"topic_{k}": v for k, v in cases.items()}
                    try:
                        rendered = template.format(**kwargs)
                    except KeyError:
                        continue
                    with self.subTest(bank=bank_name, topic=topic):
                        self.assertIsNone(
                            self.RISKY.search(rendered),
                            f"Несогласование по роду: {rendered!r}",
                        )


if __name__ == '__main__':
    unittest.main()
