import unittest
from database.db import init_db
from adaptation.utils import _clean_text, _split_sentences, _extract_key_sentence


class TestAdaptationUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
    def test_clean_text_removes_html_and_whitespace(self):
        text = "<p>Hello <b>world</b>!</p>   \n  New line."
        self.assertEqual(_clean_text(text), "Hello world! New line.")

    def test_split_sentences(self):
        text = "First sentence. Second sentence! Third?"
        self.assertEqual(_split_sentences(text), [
            "First sentence.",
            "Second sentence!",
            "Third?",
        ])

    def test_extract_key_sentence_prefers_results(self):
        abstract = "We found an effect. The results show improvement. Final statement."
        self.assertEqual(_extract_key_sentence(abstract), "The results show improvement.")


if __name__ == '__main__':
    unittest.main()
