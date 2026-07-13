import unittest

from adaptation.style_metrics import compute_style_metrics, MAX_SENTENCE_WORDS, MAX_PARAGRAPH_SENTENCES


class TestComputeStyleMetrics(unittest.TestCase):
    """Style metrics (ТЗ: 12-20 слов/предложение, макс 25, абзац ≤4 предложений)."""

    def test_empty_text(self):
        report = compute_style_metrics("")
        self.assertEqual(report.long_sentences, [])
        self.assertEqual(report.long_paragraphs, [])
        self.assertTrue(report.passes)

    def test_short_clean_sentence_passes(self):
        text = "Дофамин связан с ожиданием награды, а не с самим удовольствием от неё."
        report = compute_style_metrics(text)
        self.assertEqual(report.long_sentences, [])
        self.assertEqual(report.long_paragraphs, [])
        self.assertTrue(report.passes)

    def test_long_sentence_over_25_words_is_flagged(self):
        long_sentence = " ".join(["слово"] * 30) + "."
        report = compute_style_metrics(long_sentence)
        self.assertEqual(len(report.long_sentences), 1)
        self.assertFalse(report.passes)

    def test_sentence_at_exactly_max_words_is_not_flagged(self):
        sentence = " ".join(["слово"] * MAX_SENTENCE_WORDS) + "."
        report = compute_style_metrics(sentence)
        self.assertEqual(report.long_sentences, [])

    def test_paragraph_with_too_many_sentences_is_flagged(self):
        sentence = "Это короткое предложение."
        paragraph = " ".join([sentence] * (MAX_PARAGRAPH_SENTENCES + 1))
        report = compute_style_metrics(paragraph)
        self.assertEqual(report.long_paragraphs, [0])
        self.assertFalse(report.passes)

    def test_paragraph_at_max_sentences_is_not_flagged(self):
        sentence = "Это короткое предложение."
        paragraph = " ".join([sentence] * MAX_PARAGRAPH_SENTENCES)
        report = compute_style_metrics(paragraph)
        self.assertEqual(report.long_paragraphs, [])

    def test_multi_paragraph_only_flags_offending_paragraph(self):
        good_paragraph = "Это короткое предложение с разумной длиной."
        sentence = "Это короткое предложение."
        bad_paragraph = " ".join([sentence] * (MAX_PARAGRAPH_SENTENCES + 2))
        text = f"{good_paragraph}\n\n{bad_paragraph}"
        report = compute_style_metrics(text)
        self.assertEqual(report.long_paragraphs, [1])

    def test_average_sentence_length_computed(self):
        text = "Раз два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать."
        report = compute_style_metrics(text)
        self.assertGreater(report.avg_sentence_len, 0)


if __name__ == "__main__":
    unittest.main()
