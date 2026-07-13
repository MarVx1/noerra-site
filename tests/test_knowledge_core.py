import unittest
from parsers.base import RawArticle
from domain.knowledge.entities import ResearchPassport, ScientificClaim
from intelligence.research_analysis import (
    build_research_passport,
    extract_scientific_claims,
    detect_study_type,
    classify_evidence_strength,
    normalize_claim,
    split_sentences,
)
from intelligence.trust_engine import assess_trust, TrustAssessment
from intelligence.trust_engine.trust_assessor import estimate_trust_level


class TestResearchPassport(unittest.TestCase):
    def test_build_passport_pubmed(self):
        article = RawArticle(
            title="Sleep deprivation impairs working memory",
            url="https://pubmed.ncbi.nlm.nih.gov/123/",
            abstract="We found that sleep deprivation significantly reduces working memory performance in adults.",
            source="pubmed",
            authors=["Smith J", "Doe A"],
            published="2024 Jan",
            is_peer_reviewed=True,
        )
        passport = build_research_passport(article, "sleep", article_id=1)
        self.assertEqual(passport.article_id, 1)
        self.assertEqual(passport.topic, "sleep")
        self.assertEqual(passport.peer_reviewed, True)
        self.assertIn("working memory", passport.title.lower())
        self.assertIn("found", " ".join(passport.key_findings).lower())
        self.assertGreater(passport.trust_level, 0.4)

    def test_build_passport_arxiv(self):
        article = RawArticle(
            title="A neural model of attention",
            url="https://arxiv.org/abs/1234.5678",
            abstract="We propose a model explaining attention mechanisms.",
            source="arxiv",
            is_peer_reviewed=False,
        )
        passport = build_research_passport(article, "cognition", article_id=2)
        self.assertEqual(passport.peer_reviewed, False)
        self.assertIn(passport.evidence_strength, {"limited", "preliminary"})


class TestStudyTypeDetection(unittest.TestCase):
    def test_meta_analysis(self):
        self.assertEqual(detect_study_type("This meta-analysis combines 20 studies."), "meta_analysis")
        self.assertEqual(detect_study_type("Мета-анализ показывает эффект."), "meta_analysis")

    def test_rct(self):
        self.assertEqual(detect_study_type("Randomized controlled trial of therapy."), "randomized_controlled_trial")
        self.assertEqual(detect_study_type("A randomised trial."), "randomized_controlled_trial")

    def test_cohort(self):
        self.assertEqual(detect_study_type("Cohort study of 5000 participants."), "cohort_study")

    def test_unknown(self):
        self.assertEqual(detect_study_type("Some random text."), "unknown")


class TestEvidenceStrength(unittest.TestCase):
    def test_high_strength(self):
        self.assertEqual(classify_evidence_strength("meta_analysis", True), "high")
        self.assertEqual(classify_evidence_strength("systematic_review", True), "high")

    def test_moderate_strength(self):
        self.assertEqual(classify_evidence_strength("randomized_controlled_trial", True), "moderate_high")
        self.assertEqual(classify_evidence_strength("cohort_study", True), "moderate")

    def test_weak_strength(self):
        self.assertEqual(classify_evidence_strength("case_report", False), "weak")
        self.assertEqual(classify_evidence_strength("unknown", False), "preliminary")


class TestTrustLevel(unittest.TestCase):
    def test_high_trust(self):
        self.assertAlmostEqual(estimate_trust_level("high", True), 0.95, places=2)

    def test_low_trust(self):
        self.assertLess(estimate_trust_level("weak", False), 0.3)


class TestScientificClaims(unittest.TestCase):
    def test_extract_claims_with_results(self):
        article = RawArticle(
            title="Dopamine and reward",
            url="https://example.com",
            abstract="We found that dopamine levels predict reward learning. This suggests a key mechanism.",
            source="pubmed",
        )
        claims = extract_scientific_claims(article, "dopamine")
        self.assertGreater(len(claims), 0)
        self.assertTrue(any("dopamine" in c.claim_text.lower() for c in claims))

    def test_extract_claims_fallback(self):
        article = RawArticle(
            title="A study of something",
            url="https://example.com",
            abstract="This paper discusses various ideas without clear results.",
            source="rss",
        )
        claims = extract_scientific_claims(article, "neuroscience")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].relation, "mentions")


class TestNormalizeClaim(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_claim("  Sleep   improves memory  "), "sleep improves memory")


class TestSplitSentences(unittest.TestCase):
    def test_split(self):
        text = "First sentence. Second sentence! Third?"
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0], "First sentence.")

    def test_empty(self):
        self.assertEqual(split_sentences(""), [])


class TestTrustEngine(unittest.TestCase):
    def test_high_trust_assessment(self):
        result = assess_trust("high", True, has_limitations=True, has_sample_size=True, relation="supports")
        self.assertEqual(result.level, "high_trust")
        self.assertGreater(result.score, 0.85)
        self.assertEqual(len(result.cautions), 0)

    def test_limited_trust_assessment(self):
        result = assess_trust("limited", False, has_limitations=False, has_sample_size=False, relation="mentions")
        self.assertEqual(result.level, "low_trust")
        self.assertLess(result.score, 0.4)
        self.assertGreater(len(result.cautions), 0)

    def test_contradicts_warning(self):
        result = assess_trust("moderate", True, has_limitations=True, has_sample_size=True, relation="contradicts")
        self.assertTrue(any("contradicts" in c.lower() for c in result.cautions))


if __name__ == "__main__":
    unittest.main()
