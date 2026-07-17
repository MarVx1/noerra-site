import unittest
from parsers.base import RawArticle
from domain.knowledge.entities import ResearchPassport, ScientificClaim
from intelligence.research_analysis import (
    build_research_passport,
    extract_scientific_claims,
    detect_study_type,
    classify_evidence_strength,
    is_animal_or_invitro_study,
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

    def test_review_of_rcts_is_a_review_not_an_rct(self):
        """Регрессия: нарративный обзор рандомизированных испытаний
        определялся как сам RCT, и статья получала завышенный уровень
        доказательности ("высокий (RCT)" вместо "средний")."""
        title = "Advances in behavioral vision training: a narrative review."
        abstract = "We reviewed randomized controlled trials of perceptual learning."
        self.assertEqual(detect_study_type(f"{title} {abstract}", title=title), "review")

    def test_future_work_mention_does_not_make_it_an_rct(self):
        """Регрессия: фраза про будущие исследования ("Future research should
        use randomized controlled designs") делала работу рандомизированным
        испытанием."""
        title = "Therapeutic Yoga: Outcomes from a Residential Program"
        abstract = (
            "Participants completed a yoga program. "
            "Future research should aim to use randomized controlled designs."
        )
        self.assertNotEqual(
            detect_study_type(f"{title} {abstract}", title=title),
            "randomized_controlled_trial",
        )

    def test_title_takes_priority_over_abstract(self):
        title = "A systematic review of sleep interventions"
        abstract = "We included cohort studies and randomized controlled trials."
        self.assertEqual(detect_study_type(f"{title} {abstract}", title=title), "systematic_review")

    def test_falls_back_to_full_text_when_title_has_no_type(self):
        title = "Sleep and memory"
        abstract = "This meta-analysis pooled 20 studies."
        self.assertEqual(detect_study_type(f"{title} {abstract}", title=title), "meta_analysis")


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


class TestIsAnimalOrInvitroStudy(unittest.TestCase):
    """PATTERNS в detect_study_type() описывает ТОЛЬКО дизайн исследования
    (meta_analysis/RCT/cohort_study/...) — одни и те же слова одинаково
    употребимы и для людей, и для животных/in vitro, поэтому study_type
    сам по себе не даёт сигнала "кого исследовали" (найдено 2026-07-16,
    живой пример — article id=499, мышиное исследование с "8 cohorts"
    классифицировалось как study_type="cohort_study")."""

    def test_detects_common_markers(self):
        for text in (
            "Mice were tested in an open field.",
            "We used a mouse model of depression.",
            "A rodent model of anxiety.",
            "Murine hippocampal neurons were recorded.",
            "Cells were grown in vitro.",
            "Primary cell culture experiments.",
            "Zebrafish larvae were imaged.",
            "Monkeys performed a reaching task.",
            "Macaque prefrontal cortex recordings.",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_animal_or_invitro_study(text))

    def test_rat_uses_word_boundary_not_substring(self):
        """Голое 'rat' подстрокой ловит 'demonstrate'/'moderate'/
        'generate'/'narrate' — калибровано на реальных абстрактах."""
        self.assertTrue(is_animal_or_invitro_study("Rats were tested daily."))
        self.assertTrue(is_animal_or_invitro_study("A study of rat behavior."))
        for text in (
            "The results demonstrate a clear effect.",
            "This is a moderate improvement.",
            "New cells generate over time.",
            "Authors narrate their findings.",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_animal_or_invitro_study(text))

    def test_ordinary_human_study_not_flagged(self):
        self.assertFalse(is_animal_or_invitro_study(
            "Participants completed a questionnaire about sleep quality."
        ))

    def test_empty_text_returns_false(self):
        self.assertFalse(is_animal_or_invitro_study(""))


class TestEvidenceStrengthAnimalDowngrade(unittest.TestCase):
    """Реальный дефект (ТЗ 2026-07-16): одна и та же методология давала
    одинаковый уровень доказательности и людям, и грызунам —
    "РКИ на крысах" -> moderate_high, "мета-анализ грызуновых моделей"
    -> high, наравне с человеческими исследованиями того же дизайна."""

    def test_meta_analysis_of_animals_downgraded_from_high(self):
        self.assertEqual(
            classify_evidence_strength("meta_analysis", True, is_animal_or_invitro=True),
            "moderate",
        )
        # Человеческий мета-анализ — не тронут.
        self.assertEqual(
            classify_evidence_strength("meta_analysis", True, is_animal_or_invitro=False),
            "high",
        )

    def test_rct_on_animals_downgraded_from_moderate_high(self):
        self.assertEqual(
            classify_evidence_strength("randomized_controlled_trial", True, is_animal_or_invitro=True),
            "moderate",
        )

    def test_unknown_study_type_not_downgraded_further(self):
        """ТЗ прямо отметило: 'Обычное исследование на мышах ->
        type=unknown evidence=limited — разумно' — уже достаточно низкая
        оценка, понижать её ещё дальше до 'preliminary' не нужно."""
        self.assertEqual(
            classify_evidence_strength("unknown", True, is_animal_or_invitro=True),
            "limited",
        )
        self.assertEqual(
            classify_evidence_strength("unknown", True, is_animal_or_invitro=False),
            "limited",
        )

    def test_default_flag_is_false_backward_compatible(self):
        self.assertEqual(classify_evidence_strength("meta_analysis", True), "high")


class TestBuildResearchPassportForAnimalStudies(unittest.TestCase):
    """Сквозная проверка через build_research_passport() — не только
    саму функцию classify_evidence_strength() в изоляции."""

    def test_rat_rct_gets_downgraded_evidence(self):
        article = RawArticle(
            title="A randomized controlled trial of ketamine in rats",
            url="https://example.com/rat-rct",
            abstract="Rats were randomly assigned to treatment or control.",
            source="pubmed",
            is_peer_reviewed=True,
        )
        passport = build_research_passport(article, "stress", article_id=1)
        self.assertEqual(passport.study_type, "randomized_controlled_trial")
        self.assertEqual(passport.evidence_strength, "moderate")

    def test_rodent_meta_analysis_gets_downgraded_evidence(self):
        article = RawArticle(
            title="Meta-analysis of rodent models of depression",
            url="https://example.com/rodent-meta",
            abstract="We pooled data from 40 rodent studies.",
            source="pubmed",
            is_peer_reviewed=True,
        )
        passport = build_research_passport(article, "stress", article_id=2)
        self.assertEqual(passport.study_type, "meta_analysis")
        self.assertEqual(passport.evidence_strength, "moderate")

    def test_human_systematic_review_unaffected(self):
        """Регрессия в обратную сторону так же плоха — человеческие
        обзоры не должны понизиться (article id=923, PubMed 42458137)."""
        article = RawArticle(
            title="Association between circadian rhythm disturbances and cognitive decline in the elderly: a systematic review.",
            url="https://example.com/923",
            abstract="This systematic review included studies evaluating circadian disturbances in elderly participants.",
            source="pubmed",
            is_peer_reviewed=True,
        )
        passport = build_research_passport(article, "sleep", article_id=3)
        self.assertEqual(passport.study_type, "systematic_review")
        self.assertEqual(passport.evidence_strength, "high")


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
