import unittest
from unittest.mock import patch, MagicMock

import requests

from parsers.pubmed import PubMedParser


class _MockResponse:
    def __init__(self, *, json_data=None, text="", status_code=200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>Dopamine and Memory</ArticleTitle>
        <Abstract>
          <AbstractText>First part.</AbstractText>
          <AbstractText>Second part.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
        </AuthorList>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2023</Year><Month>Jun</Month></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID></PMID>
      <Article>
        <ArticleTitle>Missing PMID article</ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>99999</PMID>
      <Article>
        <ArticleTitle></ArticleTitle>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


class TestPubMedSearch(unittest.TestCase):
    def test_search_returns_id_list(self):
        resp = _MockResponse(json_data={"esearchresult": {"idlist": ["1", "2", "3"]}})
        with patch("parsers.pubmed.requests.get", return_value=resp):
            ids = PubMedParser()._search("dopamine")
        self.assertEqual(ids, ["1", "2", "3"])

    def test_search_retries_once_on_timeout_then_succeeds(self):
        resp = _MockResponse(json_data={"esearchresult": {"idlist": ["7"]}})
        with patch("parsers.pubmed.requests.get", side_effect=[requests.Timeout(), resp]), \
             patch("time.sleep"):
            ids = PubMedParser()._search("sleep")
        self.assertEqual(ids, ["7"])

    def test_search_returns_empty_after_two_timeouts(self):
        with patch("parsers.pubmed.requests.get", side_effect=requests.Timeout()), \
             patch("time.sleep"):
            ids = PubMedParser()._search("stress")
        self.assertEqual(ids, [])

    def test_search_returns_empty_on_generic_error(self):
        with patch("parsers.pubmed.requests.get", side_effect=RuntimeError("boom")):
            ids = PubMedParser()._search("anxiety")
        self.assertEqual(ids, [])


class TestPubMedFetchDetails(unittest.TestCase):
    def test_fetch_details_parses_valid_article_and_skips_invalid(self):
        resp = _MockResponse(text=SAMPLE_XML)
        with patch("parsers.pubmed.requests.get", return_value=resp):
            articles = PubMedParser()._fetch_details(["12345", "0", "99999"])

        self.assertEqual(len(articles), 1)
        a = articles[0]
        self.assertEqual(a.title, "Dopamine and Memory")
        self.assertEqual(a.abstract, "First part. Second part.")
        self.assertEqual(a.url, "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertEqual(a.external_id, "12345")
        self.assertEqual(a.authors, ["Smith John", "Doe Jane"])
        self.assertEqual(a.published, "2023 Jun")
        self.assertTrue(a.is_peer_reviewed)
        self.assertEqual(a.source, "pubmed")

    def test_fetch_details_returns_empty_on_malformed_xml(self):
        resp = _MockResponse(text="not xml at all <<<")
        with patch("parsers.pubmed.requests.get", return_value=resp):
            articles = PubMedParser()._fetch_details(["1"])
        self.assertEqual(articles, [])

    def test_fetch_details_returns_empty_after_two_timeouts(self):
        with patch("parsers.pubmed.requests.get", side_effect=requests.Timeout()), \
             patch("time.sleep"):
            articles = PubMedParser()._fetch_details(["1"])
        self.assertEqual(articles, [])


class TestPubMedFetch(unittest.TestCase):
    def test_fetch_dedupes_ids_across_queries(self):
        parser = PubMedParser()
        with patch.object(parser, "_search", return_value=["1", "2"]) as mock_search, \
             patch.object(parser, "_fetch_details") as mock_details:
            mock_details.side_effect = lambda ids: [MagicMock(external_id=i) for i in ids]
            articles = parser.fetch()

        # 8 запросов в QUERIES, каждый возвращает id ["1","2"] — но
        # seen_ids должен исключить повторные id из последующих запросов,
        # так что _fetch_details должен вызываться только один раз с новыми id.
        self.assertEqual(mock_details.call_count, 1)
        self.assertEqual(len(articles), 2)


if __name__ == "__main__":
    unittest.main()
