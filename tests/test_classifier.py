"""Тесты классификатора тем.

Ключевой инвариант: лучше отдать "unknown" (статья уйдёт в off_topic и не
будет опубликована), чем присвоить ложную тему. Ложная тема — самый
разрушительный дефект: движок уверенно пишет грамотную статью
"Сон: очередное подтверждение" про рак молочной железы, вставляет туда
аналогию про сон, и критик такое пропускает.
"""

import unittest

from classifier.classifier import (
    classify, get_topic_ru, get_topic_case, get_topic_emoji,
    TITLE_WEIGHT_MULTIPLIER, MIN_TOPIC_SCORE, _TOPIC_CASES,
)
from parsers.base import RawArticle


def _article(title: str, abstract: str = "") -> RawArticle:
    return RawArticle(title=title, url="https://example.com", abstract=abstract)


class TestClassifyOnTopic(unittest.TestCase):
    def test_topic_in_title_is_classified(self):
        art = _article(
            "Intranasal dopamine: anatomical pathways and neuromodulatory potential",
            "Dopamine regulates motor control, motivation and reward processing in the brain.",
        )
        topic, conf = classify(art)
        self.assertEqual(topic, "dopamine")
        self.assertGreater(conf, 0)

    def test_stress_article_is_classified(self):
        art = _article(
            "Stress and resilience: cortisol hypo-response to acute stress",
            "Resilience is the outcome of adaptation to adversity. Cortisol stress response was measured.",
        )
        self.assertEqual(classify(art)[0], "stress")


class TestOffTopicRejection(unittest.TestCase):
    """Регрессия: реальные статьи из БД, которые раньше получали ложную тему."""

    def test_breast_cancer_article_is_not_labelled_sleep(self):
        # Реальный кейс: публиковалось как "Сон: очередное подтверждение".
        art = _article(
            "The long road after breast cancer: survivorship issues in young women",
            "Advances in early detection improved survival rates for young women with breast cancer. "
            "Survivors face treatment-related toxicity, family planning and career development issues. "
            "Some report fatigue and poor sleep quality.",
        )
        self.assertEqual(classify(art)[0], "unknown")

    def test_ophthalmology_article_is_not_labelled_sleep(self):
        art = _article(
            "Advances in behavioral vision training for childhood amblyopia",
            "Amblyopia is a neurodevelopmental disorder impairing visual function and binocular integration. "
            "Traditional treatments such as occlusion are limited by poor adherence.",
        )
        self.assertEqual(classify(art)[0], "unknown")

    def test_article_with_no_keywords_at_all_is_unknown(self):
        self.assertEqual(classify(_article("Cooking pasta the Italian way"))[0], "unknown")

    def test_incidental_keyword_mention_is_not_enough(self):
        """Одно случайное упоминание в теле не должно назначать тему."""
        art = _article(
            "Economic effects of remote work on urban housing markets",
            "Respondents reported that commuting time affected their sleep.",
        )
        self.assertEqual(classify(art)[0], "unknown")


class TestWordBoundaryMatching(unittest.TestCase):
    """Регрессия: ключевые слова ловились ВНУТРИ посторонних слов.

    'rem' (REM-сон) совпадал с remains/remote/remember — 54 ложных
    срабатывания по базе; 'axon' — с taxonomy. При этом морфологию терять
    нельзя, поэтому граница слова ставится только в начале.
    """

    def _score_of(self, topic: str, article: RawArticle) -> int:
        from classifier.classifier import _KEYWORD_PATTERNS
        title, abstract = article.title.lower(), article.abstract.lower()
        total = 0
        for pattern, weight in _KEYWORD_PATTERNS[topic]:
            if pattern.search(title) or pattern.search(abstract):
                total += weight
        return total

    def test_rem_does_not_match_inside_remains(self):
        art = _article("Study design", "The findings remain stable and the effect remains after control.")
        self.assertEqual(self._score_of("sleep", art), 0)

    def test_rem_does_not_match_inside_remote(self):
        art = _article("Remote work patterns", "Remote workers remember schedules differently.")
        self.assertEqual(self._score_of("sleep", art), 0)

    def test_rem_sleep_phrase_still_matches(self):
        art = _article("REM sleep and memory consolidation", "")
        self.assertGreater(self._score_of("sleep", art), 0)

    def test_axon_does_not_match_inside_taxonomy(self):
        art = _article("A taxonomy of research methods", "We propose a taxonomy for classification.")
        self.assertEqual(self._score_of("neuroplasticity", art), 0)

    def test_morphological_suffixes_still_match(self):
        """Окончание намеренно свободно: behavioral/attentional/stressors должны ловиться."""
        cases = [
            ("psychology", _article("Behavioral outcomes", "Behavioral therapy was applied.")),
            ("stress", _article("Chronic stressors", "Multiple stressors were measured.")),
            ("cognition", _article("Cognitive load", "Participants were tested cognitively.")),
        ]
        for topic, art in cases:
            with self.subTest(topic=topic):
                self.assertGreater(self._score_of(topic, art), 0)


class TestTitleWeighting(unittest.TestCase):
    def test_title_match_scores_higher_than_abstract_match(self):
        """Заголовок — предмет статьи, тело — лишь упоминание."""
        in_title = _article("Dopamine and reward prediction", "The study examined neural signalling.")
        in_body = _article("A study of neural signalling", "Dopamine and reward prediction were examined.")

        _, conf_title = classify(in_title)
        _, conf_body = classify(in_body)
        self.assertGreaterEqual(conf_title, conf_body)

    def test_multiplier_is_applied(self):
        self.assertGreater(TITLE_WEIGHT_MULTIPLIER, 1)

    def test_threshold_is_positive(self):
        self.assertGreater(MIN_TOPIC_SCORE, 0)


class TestTopicHelpers(unittest.TestCase):
    def test_every_topic_has_ru_name_emoji_and_cases(self):
        for topic in _TOPIC_CASES:
            self.assertTrue(get_topic_ru(topic))
            self.assertTrue(get_topic_emoji(topic))
            self.assertTrue(get_topic_case(topic, "prep_lower"))

    def test_unknown_topic_falls_back_gracefully(self):
        self.assertTrue(get_topic_ru("not-a-topic"))
        self.assertTrue(get_topic_case("not-a-topic", "gen"))


if __name__ == "__main__":
    unittest.main()
