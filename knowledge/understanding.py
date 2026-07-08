from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class UnderstandingModel:
    topic: str
    topic_ru: str
    summary: str
    key_claims: List[str]
    consensus_points: List[str]
    open_questions: List[str]
    myths: List[str]
    practical_implications: List[str]
    confidence_level: str
    last_updated: str = ""
    version: str = "1.0"


def build_understanding_model(
    topic: str,
    topic_ru: str,
    claims: List[Dict[str, Any]],
    consensus_states: List[Dict[str, Any]],
    open_questions: List[str],
    myths: List[str],
) -> UnderstandingModel:
    key_claims = [c.get("claim_text", "") for c in claims[:5]]
    consensus_points = []
    practical_implications = []

    for cs in consensus_states[:5]:
        level = cs.get("consensus_level", "")
        if level in ("emerging_consensus", "supported"):
            consensus_points.append(f"Подтверждено: {cs.get('summary', '')}")
        elif level == "contested":
            consensus_points.append(f"Дискуссионно: {cs.get('summary', '')}")

    if consensus_states:
        avg_confidence = sum(cs.get("confidence", 0) for cs in consensus_states) / len(consensus_states)
        if avg_confidence >= 0.7:
            confidence_level = "high"
        elif avg_confidence >= 0.5:
            confidence_level = "moderate"
        elif avg_confidence >= 0.3:
            confidence_level = "limited"
        else:
            confidence_level = "low"
    else:
        confidence_level = "insufficient_data"

    summary = (
        f"Тема '{topic_ru}' включает {len(claims)} научных утверждений. "
        f"Уровень доверия: {confidence_level}. "
    )
    if open_questions:
        summary += f"Остаётся {len(open_questions)} открытых вопросов. "
    if myths:
        summary += f"Выявлено {len(myths)} распространённых заблуждений."

    return UnderstandingModel(
        topic=topic,
        topic_ru=topic_ru,
        summary=summary,
        key_claims=key_claims,
        consensus_points=consensus_points,
        open_questions=open_questions,
        myths=myths,
        practical_implications=practical_implications,
        confidence_level=confidence_level,
        version="1.0",
    )


def update_understanding_model(
    model: UnderstandingModel,
    new_claims: List[Dict[str, Any]],
    new_consensus: List[Dict[str, Any]],
) -> UnderstandingModel:
    existing_claims = set(model.key_claims)
    for claim in new_claims:
        claim_text = claim.get("claim_text", "")
        if claim_text not in existing_claims:
            model.key_claims.append(claim_text)
    model.key_claims = model.key_claims[:10]

    if new_consensus:
        avg_confidence = sum(cs.get("confidence", 0) for cs in new_consensus) / len(new_consensus)
        if avg_confidence >= 0.7:
            model.confidence_level = "high"
        elif avg_confidence >= 0.5:
            model.confidence_level = "moderate"
        else:
            model.confidence_level = "limited"

    version_parts = model.version.split(".")
    major = int(version_parts[0])
    minor = int(version_parts[1]) if len(version_parts) > 1 else 0
    model.version = f"{major}.{minor + 1}"

    model.summary = (
        f"Тема '{model.topic_ru}' включает {len(model.key_claims)} научных утверждений. "
        f"Уровень доверия: {model.confidence_level}. "
        f"Версия: {model.version}."
    )

    return model


def extract_practical_implications(claims: List[Dict[str, Any]], consensus: List[Dict[str, Any]]) -> List[str]:
    implications = []
    practical_markers = ("рекоменд", "следует", "может", "помогает", "важно", "практик", "примен")
    for claim in claims:
        text = claim.get("claim_text", "").lower()
        cs = next((c for c in consensus if c.get("claim_text") == claim.get("claim_text")), {})
        if cs.get("consensus_level") in ("supported", "emerging_consensus") and cs.get("confidence", 0) >= 0.6:
            if any(marker in text for marker in practical_markers):
                implications.append(claim.get("claim_text", ""))
    return implications[:5]
