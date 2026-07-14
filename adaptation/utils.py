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


# Метки разделов структурированного абстракта. В источнике они часто
# приклеены к следующему слову ("IntroductionAlthough positive effects...") —
# HTML-теги вырезаются вместе с пробелом ещё на стороне фида. После перевода
# это давало в статье "ВведениеХотя часто сообщается..." и отдельный абзац
# "Методы.". Для научпоп-статьи такие метки — мусор, поэтому удаляем их
# целиком, а не просто отделяем пробелом. Делать это надо ДО перевода, пока
# текст ещё английский.
_SECTION_LABELS = (
    "Introduction", "Background", "Objectives", "Objective", "Purpose",
    "Aims", "Aim", "Materials and Methods", "Methods", "Method",
    "Results", "Result", "Findings", "Conclusions", "Conclusion",
    "Discussion", "Significance", "Importance",
)

# Граница слова ставится только слева: справа её нет — метка приклеена
# вплотную к следующему слову ("IntroductionAlthough"). Роль правой границы
# играет lookahead на заглавную букву: он же защищает обычную прозу
# ("Results show that...") от вырезания метки.
_SECTION_LABEL_RE = re.compile(
    r"\b(" + "|".join(_SECTION_LABELS) + r")\s*[:.\-–—]?\s*(?=[A-Z])"
)


def _strip_section_labels(text: str) -> str:
    """Убирает метки разделов структурированного абстракта."""
    if not text:
        return text
    text = _SECTION_LABEL_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


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


# ── Латиница в переведённом тексте ─────────────────────────────
# Google Translate оставляет как есть узкоспециальные аббревиатуры и
# латинские термины (WMH, vmPFC, tDCS, fsQCA, stratum oriens). Словарём их
# не закрыть: половина придумана авторами конкретной статьи. Вместо этого
# при разборе абстракта предпочитаем предложения без латиницы — в абстракте
# обычно есть из чего выбрать.

# Порог подобран на выборке из БД: при 0.08 число статей с полностью чистым
# телом максимально (18/31), дальше ужесточение уже ничего не даёт — у
# оставшихся латиница есть во ВСЕХ предложениях (работы про нокаут генов,
# где имя гена и есть подлежащее). Такие статьи отсекает critic.
MAX_LATIN_RATIO = 0.08

# Аббревиатура в скобках: (NAc), (BNST), (SECPT), (ESCRT-III), (fMRI).
# Внутри — только латиница/цифры/дефисы, без кириллицы. Для научпоп-читателя
# это шум (ТЗ: каждый термин объясняется сразу, читатель не должен
# чувствовать себя глупым), а для требования "только русский" — прямое
# нарушение. Порог доли латиницы их не ловит: в длинном русском предложении
# "(NAc)" даёт всего ~3%.
_LATIN_PAREN = re.compile(r"\s*\((?=[^)]*[A-Za-z])[A-Za-z0-9\-–—/.,\s]{2,}\)")

# Google Translate вставляет неразрывные/нулевой ширины пробелы.
_INVISIBLE_SPACES = re.compile(r"[ ​‌‍﻿]+")


def _strip_latin_abbreviations(text: str) -> str:
    """Убирает латинские аббревиатуры в скобках и невидимые пробелы."""
    if not text:
        return text
    text = _INVISIBLE_SPACES.sub(" ", text)
    text = _LATIN_PAREN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _latin_ratio(sentence: str) -> float:
    """Доля латинских букв среди всех буквенных символов предложения."""
    letters = [c for c in sentence if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if "a" <= c.lower() <= "z")
    return latin / len(letters)


def _is_clean_russian(sentence: str) -> bool:
    """Предложение достаточно русское, чтобы не резать глаз читателю."""
    return _latin_ratio(sentence) <= MAX_LATIN_RATIO


def _find_sentence(
    sentences: list[str],
    marker_fn,
    exclude: set[int],
    reverse: bool = False,
) -> int | None:
    """Ищет предложение по маркеру, отдавая приоритет чистому от латиницы.

    Два прохода: сначала только среди русских предложений, затем среди
    любых — чтобы не потерять блок целиком, если чистых вариантов нет.
    """
    order = range(len(sentences) - 1, -1, -1) if reverse else range(len(sentences))
    for require_clean in (True, False):
        for i in order:
            if i in exclude:
                continue
            if not marker_fn(sentences[i]):
                continue
            if require_clean and not _is_clean_russian(sentences[i]):
                continue
            return i
    return None


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

    # Каждый блок ищется через _find_sentence: сначала среди предложений без
    # латиницы, и только потом среди любых — иначе в статью попадали куски
    # вида "ингибирует последующую индукцию LTP в MML in vitro".

    # 1. Ключевая находка (предложение с результатом)
    finding_idx = _find_sentence(sentences, _has_result_marker, exclude=set())

    # 2. Практический вывод (обычно в конце)
    exclude = {finding_idx} if finding_idx is not None else set()
    practical_idx = _find_sentence(sentences, _has_practical_marker, exclude, reverse=True)

    # 3. Методология
    exclude = {i for i in (finding_idx, practical_idx) if i is not None}
    method_idx = _find_sentence(sentences, _has_method_marker, exclude)

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

    # 4. Хук — первое неиспользованное предложение (не методология).
    #    Латиницу так же обходим стороной, если есть выбор.
    hook_exclude = set(used) | ({method_idx} if method_idx is not None else set())
    hook_idx = _find_sentence(sentences, lambda s: True, hook_exclude)
    if hook_idx is not None:
        result["hook"] = sentences[hook_idx]
        used.add(hook_idx)

    # 5. Контекст — ещё одно неиспользованное предложение
    ctx_exclude = set(used) | ({method_idx} if method_idx is not None else set())
    ctx_idx = _find_sentence(sentences, lambda s: True, ctx_exclude)
    if ctx_idx is not None:
        result["context"] = sentences[ctx_idx]
        used.add(ctx_idx)

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


# Практический вывод — это РЕКОМЕНДАЦИЯ К ДЕЙСТВИЮ или указание, что даёт
# находка на практике. Раньше маркеры были слишком широкими ("может",
# "важно", "применен", "клиничес", "практичес") и ловили введение,
# методологию и гипотезы: в блок "Практический вывод" попадали фразы вроде
# "Были применены модели продольных структурных уравнений" и "Глифосат
# является одним из наиболее используемых гербицидов". Точность была ~9%.
_PRACTICAL_MARKERS = (
    "рекоменд",
    "следует",
    "стоит ",
    "может помочь", "могут помочь",
    "может улучшить", "может снизить", "может уменьшить",
    "может предотвратить", "может повысить", "может защитить",
    "может быть использован", "могут быть использованы",
    "может служить", "могут служить",
    "на практике", "в клинической практике", "в повседневной",
    "практическое значение", "практическое применение",
    "подчеркивает важность", "подчеркивает необходимость",
    # Не голое "полезн": оно ловит "полезные стимулы" (свойство стимула,
    # а не польза для читателя). Нужен именно оборот про пользу.
    "может быть полезн", "могут быть полезн", "будет полезн",
    "полезно для", "полезны для",
    # "пользу"/"польза" безопасны только с границей слова: голое "польз"
    # раньше совпадало с "исПОЛЬЗовалась".
    "пользу", "польза", "пользы",
    "recommend", "may help", "should be", "practical implication",
)

# Даже при наличии маркера предложение не является практическим выводом,
# если это методология, введение/определение или призыв к будущим
# исследованиям (последнее — не польза для читателя, а задача для науки).
_NOT_PRACTICAL_MARKERS = (
    # методология
    "использу", "используя", "с помощью", "измеря", "измерял",
    "анализирова", "оценивал", "были применены", "был применен",
    "были проведены", "был проведен", "мы использовали", "мы провели",
    "в качестве эталон", "шкал", "коэффициент", "модели ",
    "выборк", "участник",
    # введение / определение
    "является одним из", "представляет собой", "стал ключевым",
    "часто встречается", "определяется как",
    # будущие исследования — это не практическая польза для читателя
    "дальнейш", "будущих исследован", "будущие исследован",
    "дополнительные исследования", "future research",
)


# Маркеры сопоставляются по границе НАЧАЛА слова. Без этого "стоит " ловилось
# внутри "предСТОИТ выяснить" (открытый вопрос, а не рекомендация) — тот же
# класс бага, что "rem" в "remains" и "польз" в "использовалась".
_PRACTICAL_RE = [re.compile(rf"\b{re.escape(m.strip())}") for m in _PRACTICAL_MARKERS]
_NOT_PRACTICAL_RE = [re.compile(rf"\b{re.escape(m.strip())}") for m in _NOT_PRACTICAL_MARKERS]


def _has_practical_marker(sentence: str) -> bool:
    lower = sentence.lower()
    if any(p.search(lower) for p in _NOT_PRACTICAL_RE):
        return False
    return any(p.search(lower) for p in _PRACTICAL_RE)


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
