"""
Evidence classifier.

Отвечает за определение:
- типа исследования;
- силы доказательств.
"""


def detect_study_type(
    text: str
) -> str:
    """
    Определяет тип научного исследования
    по тексту статьи.
    """

    lower = text.lower()


    patterns = [

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
                "randomized",
                "randomised",
                "controlled trial",
                "rct",
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


    for study_type, keywords in patterns:

        if any(
            keyword in lower
            for keyword in keywords
        ):
            return study_type


    return "unknown"



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