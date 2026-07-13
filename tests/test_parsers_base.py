import unittest

from parsers.base import BaseParser, RawArticle


class TestRawArticle(unittest.TestCase):
    def test_defaults(self):
        a = RawArticle(title="T", url="https://example.com")
        self.assertEqual(a.abstract, "")
        self.assertEqual(a.source, "")
        self.assertEqual(a.external_id, "")
        self.assertEqual(a.authors, [])
        self.assertEqual(a.published, "")
        self.assertFalse(a.is_peer_reviewed)

    def test_authors_default_is_not_shared_between_instances(self):
        """dataclass field(default_factory=list) — регрессия на классическую
        ловушку изменяемого дефолтного аргумента."""
        a = RawArticle(title="A", url="https://example.com/a")
        b = RawArticle(title="B", url="https://example.com/b")
        a.authors.append("Someone")
        self.assertEqual(b.authors, [])


class _FailingParser(BaseParser):
    source_name = "failing"

    def fetch(self):
        raise RuntimeError("network is down")


class _OkParser(BaseParser):
    source_name = "ok"

    def fetch(self):
        return [RawArticle(title="A", url="https://example.com/a")]


class TestBaseParserRun(unittest.TestCase):
    def test_run_swallows_exceptions_and_returns_empty_list(self):
        parser = _FailingParser()
        self.assertEqual(parser.run(), [])

    def test_run_returns_fetch_result_on_success(self):
        parser = _OkParser()
        result = parser.run()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "A")


if __name__ == "__main__":
    unittest.main()
