import unittest
from parsers.base import RawArticle
from adaptation.cluster import build_cluster_post, build_telegraph_cluster
from adaptation.editorial import generate_telegram_text, generate_telegraph_text


class TestAdaptationGeneration(unittest.TestCase):
    def make_article(self) -> RawArticle:
        return RawArticle(
            title="Dopamine and motivation",
            url="https://example.com/article",
            abstract=(
                "A new study found that dopamine affects motivated behavior. "
                "The results show that learning speed improves when reward circuits are engaged."
            ),
            source="pubmed",
        )

    def test_generate_telegram_text_contains_telegraph_link(self):
        article = self.make_article()
        text = generate_telegram_text(article, "dopamine", "https://telegra.ph/example")
        self.assertIn("💊", text)
        self.assertIn("https://telegra.ph/example", text)
        self.assertIn("Почему это важно", text)

    def test_pointer_emoji_precedes_telegraph_link(self):
        """👇 сигнализирует переход к ссылке — добавляется в конец
        последней содержательной строки прямо перед ней (2026-07-16,
        раньше пользователь добавлял вручную)."""
        article = self.make_article()
        text = generate_telegram_text(article, "dopamine", "https://telegra.ph/example")
        lines = [l for l in text.split("\n") if l.strip()]
        link_idx = next(i for i, l in enumerate(lines) if "📘" in l)
        self.assertTrue(lines[link_idx - 1].rstrip().endswith("👇"))

    def test_no_pointer_emoji_without_telegraph_url(self):
        article = self.make_article()
        text = generate_telegram_text(article, "dopamine", telegraph_url=None)
        self.assertNotIn("👇", text)

    def test_generate_telegraph_text_contains_original_link(self):
        article = self.make_article()
        text = generate_telegraph_text(article, "dopamine")
        self.assertIn("Полный разбор", text)
        self.assertIn("Оригинал:", text)
        self.assertIn(article.url, text)

    def test_build_cluster_post_single_article(self):
        article = self.make_article()
        text = build_cluster_post("dopamine", [article], youtube_article=None, telegraph_url="https://telegra.ph/example")
        self.assertIn("💊", text)
        self.assertIn("PubMed", text)
        self.assertIn("📘 https://telegra.ph/example", text)
        self.assertIn("Почему это важно", text)

    def test_cluster_post_pointer_emoji_precedes_telegraph_link(self):
        article = self.make_article()
        text = build_cluster_post("dopamine", [article], youtube_article=None, telegraph_url="https://telegra.ph/example")
        lines = [l for l in text.split("\n") if l.strip()]
        link_idx = next(i for i, l in enumerate(lines) if l.startswith("📘"))
        self.assertTrue(lines[link_idx - 1].rstrip().endswith("👇"))

    def test_cluster_post_no_pointer_emoji_without_real_telegraph_url(self):
        article = self.make_article()
        text = build_cluster_post("dopamine", [article], youtube_article=None)
        self.assertNotIn("👇", text)

    def test_build_telegraph_cluster_multiple_articles(self):
        article = self.make_article()
        article2 = RawArticle(
            title="Reward circuits in the brain",
            url="https://example.com/article2",
            abstract=(
                "Study shows that reward-related brain areas influence decision-making. "
                "The evidence supports stronger motivation under reinforcement."
            ),
            source="arxiv",
        )
        text = build_telegraph_cluster("dopamine", [article, article2], youtube_article=None)
        self.assertIn("Дофамин", text)
        self.assertIn("Оригинал:", text)
        self.assertIn("arXiv", text)


if __name__ == '__main__':
    unittest.main()
