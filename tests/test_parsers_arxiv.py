import unittest
from types import SimpleNamespace
from unittest.mock import patch

from parsers.arxiv import ArxivParser, RSS_FEEDS


def _feed(entries):
    return SimpleNamespace(entries=entries)


class TestArxivParser(unittest.TestCase):
    def test_fetch_builds_articles_from_feed_entries(self):
        entry = {
            "title": "Neural\ncorrelates of memory",
            "link": "https://arxiv.org/abs/1234.5678",
            "summary": "This paper studies memory.",
        }
        with patch("parsers.arxiv.feedparser.parse", return_value=_feed([entry])):
            articles = ArxivParser().fetch()

        # Один и тот же мок возвращается для каждого из RSS_FEEDS, поэтому
        # статьи дублируются по числу фидов — важно, что каждая корректна.
        self.assertEqual(len(articles), len(RSS_FEEDS))
        a = articles[0]
        self.assertEqual(a.title, "Neural correlates of memory")
        self.assertEqual(a.url, "https://arxiv.org/abs/1234.5678")
        self.assertEqual(a.abstract, "This paper studies memory.")
        self.assertEqual(a.source, "arxiv")
        self.assertEqual(a.external_id, "1234.5678")
        self.assertFalse(a.is_peer_reviewed)

    def test_fetch_skips_entries_without_title_or_url(self):
        entries = [
            {"title": "", "link": "https://arxiv.org/abs/1", "summary": "x"},
            {"title": "No link", "link": "", "summary": "x"},
            {"title": "Valid", "link": "https://arxiv.org/abs/2", "summary": "x"},
        ]
        with patch("parsers.arxiv.feedparser.parse", return_value=_feed(entries)):
            articles = ArxivParser().fetch()

        titles = {a.title for a in articles}
        self.assertEqual(titles, {"Valid"})

    def test_fetch_continues_after_one_feed_raises(self):
        def fake_parse(url):
            if url == RSS_FEEDS[0]:
                raise RuntimeError("boom")
            return _feed([{"title": "OK", "link": "https://arxiv.org/abs/3", "summary": ""}])

        with patch("parsers.arxiv.feedparser.parse", side_effect=fake_parse):
            articles = ArxivParser().fetch()

        # Один упавший фид не должен обрушить остальные.
        self.assertEqual(len(articles), len(RSS_FEEDS) - 1)

    def test_external_id_empty_when_no_abs_marker(self):
        entry = {"title": "T", "link": "https://arxiv.org/pdf/9999.0000", "summary": ""}
        with patch("parsers.arxiv.feedparser.parse", return_value=_feed([entry])):
            articles = ArxivParser().fetch()
        self.assertEqual(articles[0].external_id, "")


if __name__ == "__main__":
    unittest.main()
