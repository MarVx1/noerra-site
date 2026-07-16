import unittest
from unittest.mock import patch, MagicMock

from parsers.cyberleninka import CyberLeninaParser


class _MockResponse:
    def __init__(self, *, status_code=200, json_data=None, text="", json_raises=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._json_raises = json_raises

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_raises:
            raise self._json_raises
        return self._json_data


class TestFetchViaApi(unittest.TestCase):
    """Ключ верхнего уровня — "articles", не "hits" (тот не встречался
    ни разу ни в одном живом ответе API — отсюда "CyberLeninka: 0 статей"
    на каждом запуске, 2026-07-16). Внутри элемента нет "id" — только
    "link" (относительный путь "/article/n/slug"), см. живой JSON-ответ
    в коммите, добавившем этот фикс."""

    def setUp(self):
        self.parser = CyberLeninaParser()

    def test_returns_articles_on_200_with_articles_key(self):
        resp = _MockResponse(json_data={"articles": [
            {"link": "/article/n/one", "name": "Article one", "annotation": "abs one"},
            {"link": "/article/n/two", "name": "Article two", "annotation": "abs two"},
        ]})
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "Article one")
        self.assertEqual(results[0].url, "https://cyberleninka.ru/article/n/one")
        self.assertEqual(results[0].external_id, "one")
        self.assertTrue(results[0].is_peer_reviewed)

    def test_strips_search_highlight_tags_from_name_and_annotation(self):
        """API оборачивает совпавший поисковый термин в <b>...</b> —
        живой пример: "Циркадианная биофизика и <b>нейропластичность</b>"."""
        resp = _MockResponse(json_data={"articles": [
            {"link": "/article/n/x", "name": "Про <b>нейропластичность</b> мозга",
             "annotation": "<b>Нейропластичность</b> характеризуется способностью."},
        ]})
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())

        self.assertEqual(results[0].title, "Про нейропластичность мозга")
        self.assertEqual(results[0].abstract, "Нейропластичность характеризуется способностью.")

    def test_skips_articles_without_link(self):
        resp = _MockResponse(json_data={"articles": [
            {"name": "No link at all", "annotation": ""},
        ]})
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual(results, [])

    def test_skips_hits_already_in_seen(self):
        seen = {"https://cyberleninka.ru/article/n/one"}
        resp = _MockResponse(json_data={"articles": [
            {"link": "/article/n/one", "name": "Already seen", "annotation": ""},
            {"link": "/article/n/two", "name": "New one", "annotation": ""},
        ]})
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", seen)
        self.assertEqual([r.title for r in results], ["New one"])

    def test_server_error_returns_empty(self):
        resp = _MockResponse(status_code=500)
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual(results, [])

    def test_unexpected_status_returns_empty(self):
        resp = _MockResponse(status_code=404)
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual(results, [])

    def test_rate_limited_twice_returns_empty(self):
        resp = _MockResponse(status_code=429)
        with patch("parsers.cyberleninka.requests.post", return_value=resp), \
             patch("parsers.cyberleninka.time.sleep"):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual(results, [])

    def test_json_decode_error_returns_empty(self):
        import requests
        resp = _MockResponse(json_raises=requests.exceptions.JSONDecodeError("msg", "doc", 0))
        with patch("parsers.cyberleninka.requests.post", return_value=resp):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual(results, [])

    def test_generic_exception_retries_then_succeeds(self):
        good = _MockResponse(json_data={"articles": [{"link": "/article/n/nine", "name": "Recovered", "annotation": ""}]})
        with patch("parsers.cyberleninka.requests.post", side_effect=[RuntimeError("boom"), good]), \
             patch("parsers.cyberleninka.time.sleep"):
            results = self.parser._fetch_via_api("query", set())
        self.assertEqual([r.title for r in results], ["Recovered"])


class TestFetchViaWeb(unittest.TestCase):
    def setUp(self):
        self.parser = CyberLeninaParser()

    def test_extracts_articles_via_regex(self):
        html = (
            '<h2>First Title</h2>'
            '<div class="abstract">First abstract</div>'
            'href="/article/n/aaa111"'
        )
        resp = _MockResponse(status_code=200, text=html)
        with patch("parsers.cyberleninka.requests.get", return_value=resp):
            results = self.parser._fetch_via_web("query", set())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "First Title")
        self.assertEqual(results[0].abstract, "First abstract")
        self.assertEqual(results[0].url, "https://cyberleninka.ru/article/n/aaa111")

    def test_non_200_status_returns_empty(self):
        resp = _MockResponse(status_code=503)
        with patch("parsers.cyberleninka.requests.get", return_value=resp):
            results = self.parser._fetch_via_web("query", set())
        self.assertEqual(results, [])

    def test_exception_returns_empty(self):
        with patch("parsers.cyberleninka.requests.get", side_effect=RuntimeError("boom")):
            results = self.parser._fetch_via_web("query", set())
        self.assertEqual(results, [])

    def test_skips_link_already_in_seen(self):
        html = 'href="/article/n/aaa111"<h2>Title</h2>'
        seen = {"https://cyberleninka.ru/article/n/aaa111"}
        resp = _MockResponse(status_code=200, text=html)
        with patch("parsers.cyberleninka.requests.get", return_value=resp):
            results = self.parser._fetch_via_web("query", seen)
        self.assertEqual(results, [])


class TestFetch(unittest.TestCase):
    def test_falls_back_to_web_when_api_empty(self):
        parser = CyberLeninaParser()
        with patch.object(parser, "_fetch_via_api", return_value=[]) as mock_api, \
             patch.object(parser, "_fetch_via_web", return_value=[MagicMock()]) as mock_web, \
             patch("parsers.cyberleninka.time.sleep"):
            articles = parser.fetch()

        self.assertTrue(mock_api.called)
        self.assertTrue(mock_web.called)
        self.assertEqual(len(articles), len(mock_web.return_value) * len(mock_web.call_args_list))

    def test_does_not_call_web_when_api_succeeds(self):
        parser = CyberLeninaParser()
        with patch.object(parser, "_fetch_via_api", return_value=[MagicMock()]) as mock_api, \
             patch.object(parser, "_fetch_via_web") as mock_web, \
             patch("parsers.cyberleninka.time.sleep"):
            parser.fetch()

        self.assertTrue(mock_api.called)
        mock_web.assert_not_called()


if __name__ == "__main__":
    unittest.main()
