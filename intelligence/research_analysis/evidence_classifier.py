"""
Evidence classifier.

Отвечает за определение:
- типа исследования;
- силы доказательств.
"""

import re

# Весь словарь PATTERNS ниже описывает ДИЗАЙН исследования (meta_analysis,
# systematic_review, RCT, cohort_study...) и ничего не знает про ОБЪЕКТ
# исследования — эти же слова одинаково употребимы и для работ на людях,
# и для работ на животных/in vitro ("meta-analysis of rodent models",
# "a randomized controlled trial ... in rats"). Раньше это давало
# "Высокий" уровень доказательности мета-анализу мышиных работ — то же
# самое, что и мета-анализу людей (найдено 2026-07-16, живой пример —
# article id=499, "8 cohorts" из c57bl/6jrj мышей классифицировался как
# study_type="cohort_study"/evidence="moderate"). is_animal_or_invitro_study()
# — независимый сигнал ОБ ОБЪЕКТЕ, используется в classify_evidence_strength()
# для понижения итоговой оценки на ступень, не заменяя сам study_type
# (методологическая информация — "это был мета-анализ" — не теряется).
_ANIMAL_OR_INVITRO_MARKERS = (
    "mice", "mouse", "rodent", "murine", "in vitro", "cell culture",
    "zebrafish", "monkey", "macaque",
)
# Отдельно, с границей слова: голое "rat"/"rats" подстрокой ловит
# "demonstrate", "moderate", "generate", "narrate" — калибровано на
# реальных абстрактах noerra.db, 2026-07-16.
_RAT_RE = re.compile(r"\brats?\b", re.IGNORECASE)


def is_animal_or_invitro_study(text: str) -> bool:
    """Список не претендует на полноту — растёт по факту встречаемости
    на реальных абстрактах (проверено на noerra.db, 91 статья: mice x6,
    rats x3, rodent x2, mouse x2, monkey x1)."""
    if not text:
        return False
    lower = text.lower()
    if _RAT_RE.search(lower):
        return True
    return any(m in lower for m in _ANIMAL_OR_INVITRO_MARKERS)


PATTERNS = [

    (
        "meta_analysis",
        (
            "meta-analysis",
            "meta analysis",
            "мета-анализ",
        )
    ),


    (
        "systematic_review",
        (
            "systematic review",
            "систематический обзор",
        )
    ),


    (
        "randomized_controlled_trial",
        (
            # Раньше здесь было голое "randomized", и работа попадала в RCT
            # из-за фразы в разделе про будущие исследования: "Future research
            # should ... use randomized controlled designs". Теперь ключи
            # описывают ДИЗАЙН САМОГО исследования, а не упоминание рандомизации.
            "randomized controlled trial",
            "randomised controlled trial",
            "randomized clinical trial",
            "randomised clinical trial",
            "randomized trial",
            "randomised trial",
            "randomly assigned",
            "controlled trial",
            "rct",
            "рандомизированн",
        )
    ),


    (
        "cohort_study",
        (
            "cohort",
            "когорт",
        )
    ),


    (
        "observational_study",
        (
            "observational",
            "наблюдатель",
        )
    ),


    (
        "case_report",
        (
            "case report",
            "clinical case",
            "описание случая",
        )
    ),


    (
        "review",
        (
            "review",
            "обзор",
        )
    ),

]


def _match_study_type(text: str) -> str | None:
    lower = text.lower()
    for study_type, keywords in PATTERNS:
        if any(keyword in lower for keyword in keywords):
            return study_type
    return None


def detect_study_type(
    text: str,
    title: str = ""
) -> str:
    """
    Определяет тип научного исследования
    по тексту статьи.

    Заголовок (если передан) имеет приоритет: именно он объявляет, ЧЕМ
    является работа, тогда как в теле абстракта другие типы исследований
    лишь упоминаются. Без этого нарративный обзор рандомизированных
    испытаний определялся как сам RCT — и в статью попадал завышенный
    уровень доказательности, что нарушает научную честность.
    """

    if title:
        by_title = _match_study_type(title)
        if by_title:
            return by_title

    return _match_study_type(text) or "unknown"



# Понижение на одну ступень для работ на животных/in vitro — тот же
# дизайн (мета-анализ, РКИ...) даёт более сильное свидетельство о людях,
# чем о мышах, см. is_animal_or_invitro_study() и комментарий выше неё.
_EVIDENCE_DOWNGRADE_ONE_STEP = {
    "high": "moderate",
    "moderate_high": "moderate",
    "moderate": "limited",
    "limited": "preliminary",
    "preliminary": "preliminary",
    "weak": "weak",
}


def classify_evidence_strength(
    study_type: str,
    peer_reviewed: bool,
    is_animal_or_invitro: bool = False,
) -> str:
    """
    Определяет силу доказательств
    на основе типа исследования
    и наличия peer-review.

    is_animal_or_invitro — см. is_animal_or_invitro_study(): та же
    методология (meta_analysis/RCT/cohort_study/...) описана одними и
    теми же ключевыми словами и для людей, и для животных/in vitro,
    поэтому study_type сам по себе не может это различить.
    """

    if study_type in {
        "meta_analysis",
        "systematic_review",
    }:
        result = "high"

    elif study_type == "randomized_controlled_trial":
        result = "moderate_high" if peer_reviewed else "moderate"

    elif study_type in {
        "cohort_study",
        "observational_study",
        "review",
    }:
        result = "moderate" if peer_reviewed else "limited"

    elif study_type == "case_report":
        result = "weak"

    else:
        result = "limited" if peer_reviewed else "preliminary"

    # Понижаем только когда study_type — распознанный дизайн (RCT/
    # meta_analysis/...): именно там методология "для людей" завышала
    # оценку для животных. Для study_type=="unknown" результат и так
    # "limited"/"preliminary" — понижать дальше уже некуда по смыслу,
    # это признанно достаточный итог (см. ТЗ 2026-07-16: "Обычное
    # исследование на мышах -> unknown/limited — разумно").
    if is_animal_or_invitro and study_type != "unknown":
        result = _EVIDENCE_DOWNGRADE_ONE_STEP.get(result, result)

    return result