"""Reader Question (EDITORIAL_ENGINE.md, Stage 3).

До написания статьи должен быть сформулирован главный человеческий
вопрос — статья строится вокруг него, а не вокруг исследования.
Ключи словаря — те же сценарии, что и в editorial_engine.Scenario.
"""

import re

from adaptation.text_patterns import _pick

QUESTION_PATTERNS: dict[str, list[str]] = {
    "discovery": [
        "Что нового узнали учёные о {topic_prep_lower}?",
        "Почему это меняет взгляд на {topic_acc_lower}?",
        "Что именно обнаружили в новом исследовании {topic_gen_lower}?",
    ],
    "confirmation": [
        "Насколько можно доверять тому, что мы уже знали о {topic_prep_lower}?",
        "Почему это подтверждение о {topic_prep_lower} вообще важно?",
    ],
    "debunk": [
        "Правда ли то, что принято считать про {topic_acc_lower}?",
        "Почему привычное представление о {topic_prep_lower} может быть неточным?",
    ],
    "practical": [
        "Как это можно применить в жизни, если речь о {topic_prep_lower}?",
        "Что конкретно можно сделать уже сегодня, зная это о {topic_prep_lower}?",
    ],
    "discussion": [
        "Где в споре о {topic_prep_lower} правда?",
        "Почему учёные до сих пор расходятся во мнениях о {topic_prep_lower}?",
    ],
    "review": [
        "Что важно знать о {topic_prep_lower} прямо сейчас?",
        "Что изменилось в понимании {topic_gen_lower} за последнее время?",
    ],
    "explanation": [
        "Как именно работает {topic_nom_lower}?",
        # Не "устроен": темы бывают женского рода ("психология устроен").
        "Что на самом деле скрывается за словом «{topic_nom_lower}»?",
    ],
}

# Вопросы, ссылающиеся на конкретную находку статьи, а не только на тему —
# вопрос "что обнаружили о стрессе" подходит любой статье про стресс
# без разбора (найдено при вычитке реальной публикации, article id=483:
# "Что именно обнаружили в новом исследовании стресса?" для статьи про
# конкретный механизм MeA Tac2-Nk3R не отличалось бы от вопроса для любой
# другой статьи про стресс). {finding} — короткий фрагмент реальной
# находки, см. _extract_finding_subject; шаблоны рассчитаны на то, что
# {finding} может быть как именной группой, так и обрывком клаузы —
# двоеточие/тире переносят любую форму без риска сломать грамматику.
FINDING_QUESTION_PATTERNS: dict[str, list[str]] = {
    "discovery": [
        "Что именно показало новое исследование: {finding}?",
        "В чём конкретно суть находки о {topic_prep_lower} — {finding}?",
        "Что стоит за формулировкой «{finding}»?",
    ],
    "confirmation": [
        "Насколько надёжно подтверждается вот это: {finding}?",
    ],
    "debunk": [
        "Действительно ли верно, что {finding}?",
    ],
    "discussion": [
        "Что именно вызывает разногласия: {finding}?",
    ],
}

# Убираем частые вводные клише ("мы обнаружили, что...") перед тем как
# использовать находку как переменную часть вопроса — само по себе клише
# не несёт содержания, а вопрос с ним звучит как "что показало то, что
# показало исследование". Список калиброван по реальным находкам из
# noerra.db (analyze() на статьях 483, 391-398 и др., 2026-07-15) — не
# исчерпывающий, растёт по мере встречаемости новых формулировок.
_FINDING_PREFIX_RE = re.compile(
    r"^(мы\s+обнаружили,?\s*что\s+|"
    r"исследование\s+показало,?\s*что\s+|"
    r"результаты\s+показывают,?\s*что\s+|"
    r"было\s+установлено,?\s*что\s+|"
    r"установлено,?\s*что\s+)",
    re.IGNORECASE,
)

_MAX_FINDING_WORDS = 14
# Шире, чем _MAX_FINDING_WORDS: законченная клауза длиннее 14 слов всё
# равно читается лучше, чем обрубленная на середине по числу слов —
# граница по запятой того стоит (см. article id=393, где "—" и "(ПСИ)"
# как отдельные токены раздували счёт слов до обрезки).
_MAX_CLAUSE_WORDS = 20


def _extract_finding_subject(finding: str, max_words: int = _MAX_FINDING_WORDS) -> str:
    """Короткий фрагмент находки для подстановки в вопрос — не полный
    перифраз (это потребовало бы понимания смысла, чего нет в rule-based
    подходе), а очищенный и обрезанный кусок предложения, уже
    извлечённого декомпозицией абстракта (passport["main_idea"]).

    Предпочитает обрезать по первой запятой (граница клаузы — "X связано
    с Y, но Z" даёт полную мысль "X связано с Y"), а не вслепую по числу
    слов: на реальном примере (article id=391) обрезка по 14 словам
    попадала на середину второго придаточного и обрывала глагол без
    дополнения ("показывают»?"). Запятая — только если она не слишком
    близко к началу (не обрезает до одного слова) и не слишком далеко
    (не превращает "короткий фрагмент" в половину абзаца).
    """
    if not finding:
        return ""
    cleaned = _FINDING_PREFIX_RE.sub("", finding.strip())
    # Убираем скобочные пояснения (в т.ч. от jargon_glossary.py — там
    # своя запятая внутри скобок сбивала поиск границы клаузы, см.
    # article id=483). В коротком вопросе-фрагменте они не нужны — есть
    # в теле статьи.
    cleaned = re.sub(r"\s*\([^()]*\)", "", cleaned).strip()
    if not cleaned:
        return ""

    comma_idx = cleaned.find(",")
    if comma_idx != -1:
        words_before_comma = len(cleaned[:comma_idx].split())
        if 3 <= words_before_comma <= _MAX_CLAUSE_WORDS:
            return cleaned[:comma_idx].strip()

    words = cleaned.split()
    if not words:
        return ""
    excerpt = " ".join(words[:max_words])
    # Без "..." или "…" на конце — эта строка уходит в content_audit.py,
    # который считает литеральные "..." сигнатурой обрыва текста.
    return excerpt.rstrip(",;: ")


def build_reader_question(topic: str, scenario: str, finding: str = "") -> str:
    """Строит человеческий вопрос, вокруг которого строится статья.

    finding — passport["main_idea"] или decomposed["finding"]: конкретная
    находка статьи. Если после очистки от неё остаётся содержательный
    фрагмент, вопрос ссылается на него (FINDING_QUESTION_PATTERNS) —
    иначе используется прежний generic-вопрос по теме.
    """
    finding_subject = _extract_finding_subject(finding)
    finding_patterns = FINDING_QUESTION_PATTERNS.get(scenario)
    if finding_subject and finding_patterns:
        return _pick(finding_patterns, topic=topic, finding=finding_subject)
    patterns = QUESTION_PATTERNS.get(scenario, QUESTION_PATTERNS["discovery"])
    return _pick(patterns, topic=topic)
