"""Simplification (EDITORIAL_ENGINE.md, Stage 6).

Убирает канцеляризмы и длинные вводные конструкции — тот же идиом, что
и _TRANSLATION_FIXES в adaptation/utils.py (словарь замен), но для
стилистики, а не ошибок машинного перевода.

Ограничение rule-based подхода: это только фиксированные regex-замены,
они не умеют перестраивать синтаксически неудачное предложение — это
принятый компромисс без LLM (см. план доработки).
"""

import re

from adaptation.utils import _capitalize_sentences

# (паттерн, замена) — порядок важен, более специфичные идут раньше.
SIMPLIFICATION_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bв данной работе\b,?\s*", re.I), ""),
    (re.compile(r"\bнастоящее исследование\b", re.I), "это исследование"),
    (re.compile(r"\bв ходе исследования\b,?\s*", re.I), ""),
    (re.compile(r"\bавторы исследования\b", re.I), "исследователи"),
    (re.compile(r"\bбыло установлено,\s*что\b", re.I), ""),
    (re.compile(r"\bбыло установлено\b", re.I), "выяснилось"),
    (re.compile(r"\bтаким образом,?\s*", re.I), ""),
    (re.compile(r"\bследует отметить,\s*что\b", re.I), ""),
    (re.compile(r"\bследует отметить\b", re.I), "важно"),
    (re.compile(r"\bисследование демонстрирует,?\s*что\b", re.I), ""),
    (re.compile(r"\bисследование демонстрирует\b", re.I), "видно"),
    (re.compile(r"\bучёные обнаружили,?\s*что\b", re.I), ""),
    (re.compile(r"\bученые обнаружили,?\s*что\b", re.I), ""),
]


def simplify_text(text: str) -> str:
    """Убирает канцелярские обороты, не меняя смысл предложения."""
    if not text:
        return text
    for pattern, replacement in SIMPLIFICATION_RULES:
        text = pattern.sub(replacement, text)
    # Удаление оборота может срезать НАЧАЛО предложения: "Таким образом,
    # пищевое вознаграждение..." → "пищевое вознаграждение..." со строчной.
    text = _capitalize_sentences(text)
    # Уборка артефактов после удаления оборотов: двойные пробелы, пробел
    # перед знаком препинания, предложение, начинающееся со строчной буквы
    # после точки — не решаем, оставляем на усмотрение редактора/critic.
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"^[,\s]+", "", text, flags=re.M)
    return text.strip()
