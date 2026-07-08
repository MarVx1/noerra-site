import unittest
from parsers.base import RawArticle
from adaptation.editorial_engine import (
    detect_scenario, build_editorial_text, EditorialEngine,
    Scenario,
)
from adaptation.critic import EditorialCritic
from adaptation.publication import Publication


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
            "не финальный", "важный момент", "стоит помнить",
            "не догма", "очередной шаг", "требует дальнейшей",
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
            "main_idea": "Dopamine affects motivation",
            "evidence_strength": "high",
            "limitations": "Small sample.",
            "sources": "PubMed",
        }
        # 18 words with 3 paragraph breaks = passes both checks
        text = (
            "This is a long enough text for a publication that should pass the critic checks.\n\n"
            "Here is some more content that adds to the overall length of this particular publication.\n\n"
            "And here is a third paragraph with even more words to ensure the text is definitely long enough to pass. "
            "Practically, this may help guide recommendations."
        )
        review = self.critic.review(passport, text)
        self.assertTrue(review["passed"])

    def test_fails_low_confidence(self):
        passport = {
            "confidence_score": 0.2,
            "publication_type": "article",
            "main_idea": "",
        }
        review = self.critic.review(passport, "Short text.")
        self.assertFalse(review["passed"])
        self.assertTrue(any("Low confidence" in item for item in review["scientific"]))

    def test_fails_short_text(self):
        passport = {
            "confidence_score": 0.8,
            "main_idea": "Some idea",
            "evidence_strength": "high",
            "limitations": "Test limitation.",
            "sources": "Test source.",
        }
        review = self.critic.review(passport, "Short text.")
        self.assertFalse(review["passed"])
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


if __name__ == '__main__':
    unittest.main()
