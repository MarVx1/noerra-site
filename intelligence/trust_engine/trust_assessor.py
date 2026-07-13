from dataclasses import dataclass



@dataclass
class TrustAssessment:
    """
    Результат оценки доверия
    к научному утверждению
    или исследованию.
    """

    level: str

    score: float

    reasons: list[str]

    cautions: list[str]



def assess_trust(
    evidence_strength: str,
    peer_reviewed: bool,
    has_limitations: bool,
    has_sample_size: bool,
    relation: str = "supports",
) -> TrustAssessment:
    """
    Оценивает уровень доверия
    к исследованию.

    Используется Evidence Engine.
    """


    score = {
        "high": 0.9,
        "moderate_high": 0.8,
        "moderate": 0.65,
        "limited": 0.45,
        "preliminary": 0.35,
        "weak": 0.25,
    }.get(
        evidence_strength,
        0.4
    )


    reasons: list[str] = [
        f"Evidence strength: {evidence_strength}."
    ]


    cautions: list[str] = []



    if peer_reviewed:

        score += 0.05

        reasons.append(
            "Peer-reviewed source."
        )

    else:

        score -= 0.05

        cautions.append(
            "Not peer-reviewed or peer review is unknown."
        )



    if has_sample_size:

        score += 0.03

        reasons.append(
            "Sample size is stated."
        )

    else:

        cautions.append(
            "Sample size is not detected."
        )



    if has_limitations:

        reasons.append(
            "Limitations are explicitly stated."
        )

    else:

        score -= 0.03

        cautions.append(
            "Limitations are not explicit."
        )



    if relation == "contradicts":

        cautions.append(
            "This evidence contradicts an existing or expected claim."
        )


    elif relation == "mentions":

        score -= 0.1

        cautions.append(
            "Claim is mentioned but not clearly supported by the abstract."
        )



    score = max(
        0.0,
        min(score, 1.0)
    )



    if score >= 0.8:

        level = "high_trust"


    elif score >= 0.6:

        level = "moderate_trust"


    elif score >= 0.4:

        level = "limited_trust"


    else:

        level = "low_trust"



    return TrustAssessment(
        level=level,
        score=round(score, 2),
        reasons=reasons,
        cautions=cautions,
    )



def estimate_trust_level(
    evidence_strength: str,
    peer_reviewed: bool,
) -> float:
    """
    Упрощённая оценка уровня доверия.

    Возвращает числовое значение trust level
    на основе силы доказательств и peer-review.
    Используется в ResearchPassport для быстрой
    оценки без полного TrustAssessment.
    """

    score = {
        "high": 0.9,
        "moderate_high": 0.8,
        "moderate": 0.65,
        "limited": 0.45,
        "preliminary": 0.35,
        "weak": 0.25,
    }.get(
        evidence_strength,
        0.4,
    )

    if peer_reviewed:
        score += 0.05
    else:
        score -= 0.05

    return round(
        max(0.0, min(score, 1.0)),
        2,
    )