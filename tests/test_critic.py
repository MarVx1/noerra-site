import unittest
from adaptation.critic import EditorialCritic


class TestEditorialCritic(unittest.TestCase):
    def setUp(self):
        self.critic = EditorialCritic()
        self.good_passport = {
            "confidence_score": 0.8,
            "main_idea": "Sleep deprivation impairs working memory.",
            "evidence_strength": "high",
            "limitations": "Small sample size.",
            "sources": "PubMed, arXiv",
        }
        self.good_text = (
            "This study found that sleep deprivation impairs working memory.\n\n"
            "This is important because it may affect daily decisions.\n\n"
            "Practically, this recommends ensuring adequate sleep.\n\n"
            "However, the evidence is not yet definitive."
        )

    def test_passes_good_content(self):
        text = (
            "This study found that sleep deprivation impairs working memory.\n\n"
            "This is important because it may affect daily decisions.\n\n"
            "Practically, this recommends ensuring adequate sleep.\n\n"
            "However, the evidence is not yet definitive. This addresses the common misconception that sleep is only rest."
        )
        review = self.critic.review(self.good_passport, text)
        self.assertTrue(review["passed"])
        self.assertLessEqual(len(review["problems"]), 1)

    def test_fails_low_confidence(self):
        passport = {**self.good_passport, "confidence_score": 0.2}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Low confidence" in p for p in review["scientific"]))

    def test_fails_no_limitations(self):
        passport = {**self.good_passport, "limitations": ""}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Limitations" in p for p in review["scientific"]))

    def test_fails_hype_language(self):
        text = "This is a revolutionary breakthrough! It changes everything."
        review = self.critic.review(self.good_passport, text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Sensational" in p or "hype" in p.lower() for p in review["uncertainty"]))

    def test_fails_short_text(self):
        review = self.critic.review(self.good_passport, "Too short text.")
        self.assertFalse(review["passed"])
        self.assertTrue(any("too short" in p.lower() for p in review["clarity"]))

    def test_fails_no_practical_value(self):
        text = "This study found that sleep deprivation impairs working memory.\n\n" * 3
        review = self.critic.review(self.good_passport, text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Practical" in p for p in review["practical"]))

    def test_fails_no_sources(self):
        passport = {**self.good_passport, "sources": ""}
        review = self.critic.review(passport, self.good_text)
        self.assertFalse(review["passed"])
        self.assertTrue(any("Sources" in p for p in review["scientific"]))


if __name__ == "__main__":
    unittest.main()
