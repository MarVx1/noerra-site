import unittest
from unittest.mock import patch, MagicMock

import requests

from parsers.youtube import YouTubeParser, format_youtube_block
from parsers.base import RawArticle


class _MockResponse:
    def __init__(self, *, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _rss_entry(video_id, title, description=""):
    return (
        "<entry>"
        f"<yt:videoId>{video_id}</yt:videoId>"
        f"<title>{title}</title>"
        f"<media:description>{description}</media:description>"
        "</entry>"
    )


class TestFetchChannelRss(unittest.TestCase):
    def setUp(self):
        self.parser = YouTubeParser()

    def test_parses_entries(self):
        xml = _rss_entry("abc123", "Neuroscience talk", "A description")
        resp = _MockResponse(text=xml)
        with patch("parsers.youtube.requests.get", return_value=resp):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["video_id"], "abc123")
        self.assertEqual(videos[0]["title"], "Neuroscience talk")
        self.assertEqual(videos[0]["description"], "A description")

    def test_limits_to_last_10_entries(self):
        xml = "".join(_rss_entry(f"id{i}", f"Title {i}") for i in range(15))
        resp = _MockResponse(text=xml)
        with patch("parsers.youtube.requests.get", return_value=resp):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")
        self.assertEqual(len(videos), 10)

    def test_non_200_status_returns_empty(self):
        resp = _MockResponse(status_code=404)
        with patch("parsers.youtube.requests.get", return_value=resp):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")
        self.assertEqual(videos, [])

    def test_skips_entries_missing_video_id_or_title(self):
        xml = "<entry><title>No id here</title></entry>" + _rss_entry("ok1", "Has both")
        resp = _MockResponse(text=xml)
        with patch("parsers.youtube.requests.get", return_value=resp):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")
        self.assertEqual([v["video_id"] for v in videos], ["ok1"])

    def test_retries_once_on_timeout_then_succeeds(self):
        xml = _rss_entry("id1", "Recovered")
        resp = _MockResponse(text=xml)
        with patch("parsers.youtube.requests.get", side_effect=[requests.exceptions.ReadTimeout(), resp]):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")
        self.assertEqual(len(videos), 1)

    def test_returns_empty_after_two_timeouts(self):
        with patch("parsers.youtube.requests.get", side_effect=requests.exceptions.ReadTimeout()):
            videos = self.parser._fetch_channel_rss("huberman", "UCxxx")
        self.assertEqual(videos, [])


class TestMatchTopic(unittest.TestCase):
    def setUp(self):
        self.parser = YouTubeParser()

    def test_matches_known_keyword(self):
        self.assertEqual(self.parser._match_topic("Understanding ADHD and focus"), "ADHD")

    def test_matches_case_insensitively(self):
        self.assertEqual(self.parser._match_topic("DOPAMINE and reward pathways"), "dopamine")

    def test_returns_none_for_unrelated_title(self):
        self.assertIsNone(self.parser._match_topic("Cooking pasta the Italian way"))

    def test_does_not_match_rem_as_substring_of_remember(self):
        """Регрессия: голое 'rem' ловилось внутри 'remember'/'remarkable' —
        тот же класс бага, что уже чинили в classifier.py (54 ложных
        срабатывания на 'remains'). Живой случай: '2026 Stanford
        Commencement Ceremony' попал в тему 'сон' (2026-07-15)."""
        self.assertIsNone(self.parser._match_topic(
            "Commencement speech: remember this remarkable day"
        ))

    def test_still_matches_rem_sleep_phrase(self):
        self.assertEqual(self.parser._match_topic("Understanding REM sleep cycles"), "sleep")


class TestFetch(unittest.TestCase):
    def setUp(self):
        self.parser = YouTubeParser()

    def test_deduplicates_videos_across_channels_and_filters_by_topic(self):
        shared_video = {"video_id": "dup1", "title": "sleep science talk", "description": "desc"}
        unrelated_video = {"video_id": "unrel", "title": "cooking pasta", "description": ""}

        with patch.object(self.parser, "_fetch_channel_rss", return_value=[shared_video, unrelated_video]), \
             patch.object(self.parser, "_find_timestamp", return_value=(None, "")):
            articles = self.parser.fetch()

        # shared_video встречается в каждом канале (мок одинаковый для всех),
        # но должен попасть в итог только один раз; unrelated_video должен
        # быть отфильтрован, т.к. тема не определяется.
        self.assertEqual(len(articles), 1)
        self.assertIn("sleep science talk", articles[0].title)

    def test_uses_description_excerpt_when_no_timestamp_found(self):
        video = {"video_id": "v1", "title": "sleep science talk", "description": "Full description text"}
        with patch.object(self.parser, "_fetch_channel_rss", return_value=[video]), \
             patch.object(self.parser, "_find_timestamp", return_value=(None, "")):
            articles = self.parser.fetch()

        a = articles[0]
        self.assertEqual(a.abstract, "Full description text")
        self.assertNotIn("?t=", a.url)

    def test_uses_timestamp_url_when_transcript_match_found(self):
        video = {"video_id": "v1", "title": "sleep science talk", "description": "desc"}
        with patch.object(self.parser, "_fetch_channel_rss", return_value=[video]), \
             patch.object(self.parser, "_find_timestamp", return_value=(120, "excerpt around match")):
            articles = self.parser.fetch()

        a = articles[0]
        self.assertEqual(a.abstract, "excerpt around match")
        self.assertIn("?t=120", a.url)
        self.assertEqual(a.external_id, "v1_120")


class TestFormatYoutubeBlock(unittest.TestCase):
    def test_returns_empty_for_missing_article_or_url(self):
        self.assertEqual(format_youtube_block(None), "")
        self.assertEqual(format_youtube_block(RawArticle(title="T", url="")), "")

    def test_uses_engine_block_when_available(self):
        article = RawArticle(title="T", url="https://youtu.be/abc?t=90", abstract="abs", source="youtube")
        with patch("parsers.youtube.EditorialEngine") as mock_engine_cls:
            mock_engine_cls.return_value.generate_youtube_block.return_value = "ENGINE BLOCK"
            result = format_youtube_block(article)
        self.assertEqual(result, "ENGINE BLOCK")

    def test_falls_back_to_legacy_formatting_when_engine_raises(self):
        article = RawArticle(
            title="T", url="https://youtu.be/abc?t=90", abstract="A" * 250, source="youtube",
        )
        with patch("parsers.youtube.EditorialEngine", side_effect=RuntimeError("boom")):
            result = format_youtube_block(article)
        self.assertIn("1:30", result)  # 90 seconds -> 1:30
        self.assertIn("...", result)  # truncated abstract > 200 chars


if __name__ == "__main__":
    unittest.main()
