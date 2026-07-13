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
        translated = _fix_translation(translated)
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


# ── Постобработка машинного перевода ───────────────────────────
# Google Translate часто выдаёт корявые формулировки.
# Этот словарь исправляет наиболее частые ошибки.

_TRANSLATION_FIXES: dict[str, str] = {
    "схемы вознаграждения": "системы награды",
    "схему вознаграждения": "систему награды",
    "схем вознаграждения": "систем награды",
    "схемам вознаграждения": "системам награды",
    "система вознаграждения": "система награды",
    "систему вознаграждения": "систему награды",
    "системы вознаграждения": "системы награды",
    "систем вознаграждения": "систем награды",
    # Полная парадигма склонения "вознаграждение" → "награда" — раньше
    # были только именительный/родительный/винительный, из-за чего
    # substring-замена "вознаграждение" → "награду" ложно обрезала более
    # длинные формы (например "вознаграждением" → "наградум", см. регресс
    # в manual QA генерации). Теперь _fix_translation матчит только целые
    # слова (\b), а отсутствовавшие падежи добавлены явно.
    "вознаграждением": "наградой",
    "вознаграждении": "награде",
    "вознаграждению": "награде",
    "вознаграждениям": "наградам",
    "вознаграждениями": "наградами",
    "вознаграждениях": "наградах",
    "вознаграждения": "награды",
    "вознаграждение": "награду",
    "вознаграждений": "наград",
    "прогнозирования вознаграждения": "предсказания награды",
    "прогнозирование вознаграждения": "предсказание награды",
    "ошибки прогнозирования": "ошибки предсказания",
    "ошибку прогнозирования": "ошибку предсказания",
    "ошибка прогнозирования": "ошибка предсказания",
    "мотивированное поведение": "мотивационное поведение",
    "мотивированного поведения": "мотивационного поведения",
    "убеждает": "показывает",
    "доказывает, что": "показывает, что",
    "экспериментальные результаты": "результаты эксперимента",
    "находки показывают": "результаты показывают",
    "мы демонстрируем": "исследователи демонстрируют",
    "мы показываем": "исследователи показывают",
    "мы обнаружили": "исследователи обнаружили",
    "мы нашли": "исследователи нашли",
    "в этом исследовании мы": "в этом исследовании",
    "наше исследование": "исследование",
    "наши результаты": "результаты",
    "наши выводы": "выводы",
    "согласно нашим": "согласно",
    "значительно ухудшают": "значительно ухудшает",
    "увеличивает, когда": "возрастает, когда",
}


# Предкомпилированные правила с границами слова (\b) — раньше замена шла
# через обычный text.replace(), и короткий ключ типа "вознаграждение"
# ложно матчился как ПРЕФИКС более длинной словоформы ("вознаграждением"),
# обрезая её до "наградум". \b гарантирует, что заменяется только слово
# целиком, а не подстрока внутри другой словоформы.
_TRANSLATION_FIX_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(bad) + r"\b"), good)
    for bad, good in _TRANSLATION_FIXES.items()
]


def _fix_translation(text: str) -> str:
    """Исправляет типичные ошибки машинного перевода."""
    if not text:
        return text
    for pattern, good in _TRANSLATION_FIX_RULES:
        text = pattern.sub(good, text)
    # Убираем артефакты: двойные пробелы, лишние точки
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return text.strip()


# ── Декомпозиция абстракта ─────────────────────────────────────
# Разлагает текст на компоненты без повторов: каждое предложение
# используется ровно один раз в одной роли.

def _decompose_abstract(abstract: str) -> dict[str, str]:
    """Разлагает абстракт на компоненты для разных частей статьи.

    Возвращает dict с ключами:
      - hook: цепляющее предложение (обычно главный результат)
      - context: дополнительное предложение (детали, цифры)
      - finding: ключевая находка
      - practical: практический вывод
      - method: методология (если есть)

    Каждое предложение исходного текста используется максимум в одной роли.
    """
    sentences = _split_sentences(abstract)
    if not sentences:
        return {"hook": "", "context": "", "finding": "", "practical": "", "method": ""}

    used: set[int] = set()

    # 1. Ищем ключевую находку (предложение с результатом)
    finding_idx = None
    for i, s in enumerate(sentences):
        if _has_result_marker(s):
            finding_idx = i
            break

    # 2. Ищем практический вывод (обычно в конце)
    practical_idx = None
    for i in range(len(sentences) - 1, -1, -1):
        if i == finding_idx:
            continue
        if _has_practical_marker(sentences[i]):
            practical_idx = i
            break

    # 3. Ищем методологию
    method_idx = None
    for i, s in enumerate(sentences):
        if i in (finding_idx, practical_idx):
            continue
        if _has_method_marker(s):
            method_idx = i
            break

    result: dict[str, str] = {"hook": "", "context": "", "finding": "", "practical": "", "method": ""}

    if finding_idx is not None:
        result["finding"] = sentences[finding_idx]
        used.add(finding_idx)

    if practical_idx is not None and practical_idx not in used:
        result["practical"] = sentences[practical_idx]
        used.add(practical_idx)

    if method_idx is not None and method_idx not in used:
        result["method"] = sentences[method_idx]
        used.add(method_idx)

    # 4. Хук — первое неиспользованное предложение (не методология)
    for i, s in enumerate(sentences):
        if i not in used and i != method_idx:
            result["hook"] = s
            used.add(i)
            break

    # 5. Контекст — ещё одно неиспользованное предложение
    for i, s in enumerate(sentences):
        if i not in used and i != method_idx:
            result["context"] = s
            used.add(i)
            break

    # Если finding пуст, используем hook как finding
    if not result["finding"] and result["hook"]:
        result["finding"] = result["hook"]
        result["hook"] = result["context"]
        result["context"] = ""

    return result


def _has_result_marker(sentence: str) -> bool:
    lower = sentence.lower()
    markers = (
        "found", "show", "shows", "showed", "demonstrate", "demonstrates",
        "reveal", "suggest", "indicate", "associated", "linked",
        "показ", "выяв", "свидетель", "связан", "обнаруж", "подтверж",
        "результаты показывают", "обнаружили", "установили",
    )
    return any(m in lower for m in markers)


def _has_practical_marker(sentence: str) -> bool:
    lower = sentence.lower()
    markers = (
        "recommend", "suggest", "should", "may help", "helps", "important",
        "implication", "practice", "clinical",
        "рекоменд", "следует", "может", "помогает", "важно",
        # "польза"/"пользу"/"полезн" — не голое "польз": оно ложно совпадало
        # с "использовал(ась/и)"/"пользоваться" — обычными словами методологии
        # ("Исследование ИСПОЛЬЗовало выборку из..."), из-за чего лимитации/
        # методология ошибочно помечались как практический вывод.
        "польза", "пользу", "полезн", "практичес", "применен", "клиничес",
    )
    return any(m in lower for m in markers)


def _has_method_marker(sentence: str) -> bool:
    lower = sentence.lower()
    markers = (
        "we used", "we conducted", "we performed", "this study aimed",
        "the aim", "objective:", "background:", "methods:",
        "participant", "sample", "n=", "n =",
        "мы использовали", "целью", "в данном исследовании",
        "участник", "выборка", "метод",
    )
    return any(m in lower for m in markers)


def _detect_numbers(text: str) -> str | None:
    """Извлекает заметные числа из текста (проценты, размеры выборки)."""
    # Проценты
    match = re.search(r"(\d+(?:\.\d+)?%)", text)
    if match:
        return match.group(1)
    # n=XXX
    match = re.search(r"n\s*=\s*(\d{2,6})", text, re.I)
    if match:
        return f"n={match.group(1)}"
    # Просто большие числа
    match = re.search(r"\b(\d{2,4})\s+(?:participants|patients|subjects|участников|пациентов)", text, re.I)
    if match:
        return f"{match.group(1)} участников"
    return None


def _detect_duplicates(text: str) -> list[str]:
    """Находит предложения, которые повторяются в тексте более одного раза."""
    sentences = [s.strip() for s in re.split(r"[\n\r]+", text) if s.strip()]
    if len(sentences) < 2:
        return []
    seen: dict[str, int] = {}
    duplicates = []
    for s in sentences:
        # Нормализуем для сравнения
        key = re.sub(r"\s+", " ", s.lower().strip())[:100]
        if len(key) < 15:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            duplicates.append(s[:80])
    return duplicates
