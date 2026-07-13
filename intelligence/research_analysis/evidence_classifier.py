"""
Evidence classifier.

Отвечает за определение:
- типа исследования;
- силы доказательств.
"""


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



def classify_evidence_strength(
    study_type: str,
    peer_reviewed: bool
) -> str:
    """
    Определяет силу доказательств
    на основе типа исследования
    и наличия peer-review.
    """


    if study_type in {
        "meta_analysis",
        "systematic_review",
    }:
        return "high"



    if study_type == "randomized_controlled_trial":

        return (
            "moderate_high"
            if peer_reviewed
            else "moderate"
        )



    if study_type in {
        "cohort_study",
        "observational_study",
        "review",
    }:

        return (
            "moderate"
            if peer_reviewed
            else "limited"
        )



    if study_type == "case_report":

        return "weak"



    return (
        "limited"
        if peer_reviewed
        else "preliminary"
    )