import unittest

from parsers.base import RawArticle
from scoring.scorer import score_article
from config.settings import MIN_SCORE_TO_MODERATE


def _yt_article(title: str, url: str, abstract: str = "") -> RawArticle:
    return RawArticle(title=title, url=url, abstract=abstract, source="youtube", is_peer_reviewed=False)


class TestYoutubeScoring(unittest.TestCase):
    """До этого фикса YouTube оценивался по формуле, рассчитанной на
    структуру научной аннотации (peer review, "results show", год
    публикации в тексте) — ни один реальный видеоролик из 11, собранных
    парсером за 2026-07-10..14, не набирал MIN_SCORE_TO_MODERATE=20
    (максимум был 6), независимо от качества содержания."""

    def test_curated_channel_alone_is_not_enough(self):
        """Только заголовок/канал без подтверждения по субтитрам —
        ровно то, что раньше пропускало 'Stanford Commencement Ceremony'
        в тему 'сон' по ложному совпадению 'rem' внутри 'remember'."""
        article = _yt_article(
            "2026 Stanford Commencement Ceremony [Stanford]",
            "https://youtu.be/q0PR1sKZuFk",
        )
        score = score_article(article)
        self.assertLess(score, MIN_SCORE_TO_MODERATE)

    def test_curated_channel_with_transcript_confirmation_passes(self):
        article = _yt_article(
            "Essentials: Sleep Toolkit for Optimizing Sleep [Huberman]",
            "https://youtu.be/RTgJSQtvo88?t=18",
        )
        score = score_article(article)
        self.assertGreaterEqual(score, MIN_SCORE_TO_MODERATE)

    def test_uncurated_channel_does_not_get_channel_bonus(self):
        article = _yt_article(
            "Random unrelated video [SomeRandomChannel]",
            "https://youtu.be/xyz?t=10",
        )
        score_with_random_channel = score_article(article)
        curated = _yt_article(
            "Random unrelated video [Huberman]",
            "https://youtu.be/xyz?t=10",
        )
        score_with_curated_channel = score_article(curated)
        self.assertLess(score_with_random_channel, score_with_curated_channel)

    def test_transcript_confirmation_alone_without_curated_channel_is_not_enough(self):
        article = _yt_article(
            "Some video [UnknownChannel]",
            "https://youtu.be/xyz?t=10",
        )
        score = score_article(article)
        self.assertLess(score, MIN_SCORE_TO_MODERATE)

    def test_practical_keyword_adds_points(self):
        base = _yt_article("Talk about something [Huberman]", "https://youtu.be/xyz")
        with_practical = _yt_article(
            "Talk about treatment protocols [Huberman]", "https://youtu.be/xyz",
        )
        self.assertGreater(score_article(with_practical), score_article(base))

    def test_penalty_keywords_reduce_score(self):
        clean = _yt_article(
            "Sleep science deep dive [Huberman]", "https://youtu.be/xyz?t=5",
        )
        with_penalty = _yt_article(
            "Sleep science and astrology deep dive [Huberman]", "https://youtu.be/xyz?t=5",
        )
        self.assertLess(score_article(with_penalty), score_article(clean))

    def test_score_never_negative(self):
        article = _yt_article("astrology horoscope pseudoscience [Random]", "https://youtu.be/xyz")
        self.assertGreaterEqual(score_article(article), 0)


if __name__ == "__main__":
    unittest.main()
