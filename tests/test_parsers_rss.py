import unittest
from types import SimpleNamespace
from unittest.mock import patch

from parsers.rss import RSSParser, RSS_SOURCES


def _feed(entries):
    return SimpleNamespace(entries=entries)


class TestRSSParser(unittest.TestCase):
    def test_fetch_maps_trusted_flag_to_peer_reviewed(self):
        trusted_source = next(s for s in RSS_SOURCES if s["trusted"])
        untrusted_source = next(s for s in RSS_SOURCES if not s["trusted"])

        def fake_parse(url):
            if url == trusted_source["url"]:
                return _feed([{"title": "Trusted article", "link": "https://example.com/trusted", "summary": "abs"}])
            if url == untrusted_source["url"]:
                return _feed([{"title": "Preprint", "link": "https://example.com/preprint", "summary": "abs"}])
            return _feed([])

        with patch("parsers.rss.feedparser.parse", side_effect=fake_parse):
            articles = RSSParser().fetch()

        by_url = {a.url: a for a in articles}
        self.assertTrue(by_url["https://example.com/trusted"].is_peer_reviewed)
        self.assertFalse(by_url["https://example.com/preprint"].is_peer_reviewed)

    def test_fetch_deduplicates_by_url_across_sources(self):
        shared_entry = {"title": "Same article", "link": "https://example.com/same", "summary": "abs"}

        with patch("parsers.rss.feedparser.parse", return_value=_feed([shared_entry])):
            articles = RSSParser().fetch()

        matching = [a for a in articles if a.url == "https://example.com/same"]
        self.assertEqual(len(matching), 1)

    def test_abstract_falls_back_to_description(self):
        entry = {"title": "T", "link": "https://example.com/x", "description": "fallback text"}
        with patch("parsers.rss.feedparser.parse", return_value=_feed([entry])):
            articles = RSSParser().fetch()
        self.assertTrue(all(a.abstract == "fallback text" for a in articles if a.url == "https://example.com/x"))

    def test_skips_entries_without_title_or_link(self):
        entries = [
            {"title": "", "link": "https://example.com/a", "summary": "x"},
            {"title": "No link", "link": "", "summary": "x"},
        ]
        with patch("parsers.rss.feedparser.parse", return_value=_feed(entries)):
            articles = RSSParser().fetch()
        self.assertEqual(articles, [])

    def test_continues_after_one_source_raises(self):
        def fake_parse(url):
            if url == RSS_SOURCES[0]["url"]:
                raise RuntimeError("network down")
            return _feed([{"title": "OK", "link": f"https://example.com/{url}", "summary": ""}])

        with patch("parsers.rss.feedparser.parse", side_effect=fake_parse):
            articles = RSSParser().fetch()

        # Все источники, кроме первого (упавшего), должны дать по статье.
        self.assertEqual(len(articles), len(RSS_SOURCES) - 1)


if __name__ == "__main__":
    unittest.main()
