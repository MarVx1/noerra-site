"""Общие утилиты для адаптации контента."""

import logging
import re
from database.db import get_translation, save_translation

logger = logging.getLogger(__name__)


def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _translate(text: str, lang: str = "ru") -> str:
    if not text or not text.strip():
        return text

    cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04FF")
    if cyrillic / max(len(text), 1) > 0.3:
        return text

    text = text.strip()
    cached = get_translation(text, lang)
    if cached:
        return cached

    sentences = _split_sentences(text)
    translated_sentences: list[str] = []
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="auto", target=lang)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_cached = get_translation(sentence, lang)
            if sentence_cached:
                translated_sentences.append(sentence_cached)
                continue

            translated_sentence = translator.translate(sentence[:4500]) or sentence
            save_translation(sentence, translated_sentence, lang)
            translated_sentences.append(translated_sentence)

        translated = " ".join(translated_sentences).strip()
    except Exception as e:
        logger.warning(f"Перевод недоступен: {e}")
        translated = text

    if translated and translated != text:
        save_translation(text, translated, lang)
    return translated


def _translate_title(title: str) -> str:
    return _translate(title)


def _extract_key_sentence(abstract: str) -> str:
    sentences = _split_sentences(abstract)
    markers = {
        "result": 5,
        "results": 5,
        "show": 4,
        "demonstrat": 4,
        "reveal": 4,
        "suggest": 3,
        "indicat": 3,
        "conclude": 3,
        "evidence": 3,
        "found": 2,
        "показал": 5,
        "выявил": 5,
        "установил": 5,
        "доказал": 5,
        "свидетельствует": 4,
    }
    best_sentence = None
    best_score = 0
    for sentence in sentences:
        score = sum(
            weight for marker, weight in markers.items()
            if marker in sentence.lower()
        )
        if score > best_score:
            best_score = score
            best_sentence = sentence
    if best_sentence:
        return best_sentence
    return sentences[0] if sentences else abstract[:200].strip()


def _extract_practical_sentence(abstract: str) -> str:
    sentences = _split_sentences(abstract)
    practical_markers = [
        "recommend", "suggest", "should", "may", "helps", "help", "important",
        "может", "рекомендуется", "следует", "помогает", "важно", "пользу",
    ]
    for sentence in reversed(sentences):
        if any(marker in sentence.lower() for marker in practical_markers):
            return sentence
    return sentences[-1] if sentences else "Требует дальнейшего изучения."


def _shorten(text: str, max_len: int = 600) -> str:
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    last_dot = cut.rfind('.')
    return cut[:last_dot + 1] if last_dot > max_len // 2 else cut + '...'
