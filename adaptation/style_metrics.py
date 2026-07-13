"""Style metrics (EDITORIAL_ENGINE.md, style requirements).

ТЗ: средняя длина предложения 12-20 слов (максимум 25), абзац не более
четырёх строк, ритмический переход каждые 2-3 абзаца.

Rule-based упрощение: "абзац не более 4 строк" трактуется как "не более
4 предложений" — типографская метрика "строк" не имеет смысла для
Telegram/переменной ширины экрана, где перенос строк зависит от
устройства читателя, а не от исходного текста.
"""

from dataclasses import dataclass, field

from adaptation.utils import _split_sentences

MAX_SENTENCE_WORDS = 25
TARGET_SENTENCE_WORDS_RANGE = (12, 20)
MAX_PARAGRAPH_SENTENCES = 4


@dataclass
class StyleReport:
    avg_sentence_len: float
    long_sentences: list[str] = field(default_factory=list)
    long_paragraphs: list[int] = field(default_factory=list)
    passes: bool = True


def compute_style_metrics(text: str) -> StyleReport:
    """Считает метрики стиля по абзацам (разделённым '\\n\\n') и предложениям."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    all_word_counts: list[int] = []
    long_sentences: list[str] = []
    long_paragraphs: list[int] = []

    for i, para in enumerate(paragraphs):
        sentences = _split_sentences(para)
        if len(sentences) > MAX_PARAGRAPH_SENTENCES:
            long_paragraphs.append(i)
        for sentence in sentences:
            word_count = len(sentence.split())
            all_word_counts.append(word_count)
            if word_count > MAX_SENTENCE_WORDS:
                long_sentences.append(sentence)

    avg = sum(all_word_counts) / len(all_word_counts) if all_word_counts else 0.0
    low, high = TARGET_SENTENCE_WORDS_RANGE
    avg_in_range = (low <= avg <= high) if all_word_counts else True
    passes = not long_sentences and not long_paragraphs and avg_in_range

    return StyleReport(
        avg_sentence_len=avg,
        long_sentences=long_sentences,
        long_paragraphs=long_paragraphs,
        passes=passes,
    )
