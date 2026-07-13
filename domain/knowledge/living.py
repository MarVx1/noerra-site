from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class KnowledgeVersion:
    topic: str
    version: str
    summary: str
    changed_because: str


@dataclass
class KnowledgeDiff:
    topic: str
    from_version: str
    to_version: str
    before_text: str
    after_text: str
    reason: str


@dataclass
class OpenQuestion:
    topic: str
    question: str
    status: str = "open"


@dataclass
class Myth:
    topic: str
    myth_text: str
    correction: str = ""
    evidence_summary: str = ""


def create_knowledge_version(topic: str, version: str, summary: str, changed_because: str = "") -> KnowledgeVersion:
    return KnowledgeVersion(topic=topic, version=version, summary=summary, changed_because=changed_because)


def create_knowledge_diff(
    topic: str,
    from_version: str,
    to_version: str,
    before_text: str,
    after_text: str,
    reason: str,
) -> KnowledgeDiff:
    return KnowledgeDiff(
        topic=topic,
        from_version=from_version,
        to_version=to_version,
        before_text=before_text,
        after_text=after_text,
        reason=reason,
    )


def create_open_question(topic: str, question: str, status: str = "open") -> OpenQuestion:
    return OpenQuestion(topic=topic, question=question, status=status)


def create_myth(topic: str, myth_text: str, correction: str = "", evidence_summary: str = "") -> Myth:
    return Myth(topic=topic, myth_text=myth_text, correction=correction, evidence_summary=evidence_summary)


def build_knowledge_summary(claims: List[Dict[str, Any]], consensus_states: List[Dict[str, Any]]) -> str:
    if not claims:
        return "No established claims yet."
    total_support = sum(cs.get("support_count", 0) for cs in consensus_states)
    total_contradict = sum(cs.get("contradict_count", 0) for cs in consensus_states)
    high_confidence = sum(1 for cs in consensus_states if (cs.get("confidence") or 0) >= 0.6)
    return (
        f"Topic has {len(claims)} scientific claims. "
        f"Evidence shows {total_support} supporting and {total_contradict} contradicting findings. "
        f"{high_confidence} claims have high confidence (>=0.6)."
    )


def _is_valid_claim(text: str) -> bool:
    """Проверяет, что claim — это реальное утверждение, а не абзац методологии."""
    if not text or len(text) < 10:
        return False
    if len(text) > 300:
        return False
    lower = text.lower()
    skip_markers = (
        "we used", "we conducted", "we performed", "this study aimed",
        "the aim of", "objective:", "background:", "methods:",
        "мы использовали", "целью данного", "в данном исследовании",
    )
    if any(skip in lower for skip in skip_markers):
        return False
    return True


def detect_open_questions(claims: List[Dict[str, Any]], consensus_states: List[Dict[str, Any]]) -> List[OpenQuestion]:
    questions: List[OpenQuestion] = []
    for claim, cs in zip(claims, consensus_states):
        if cs.get("consensus_level") in ("contested", "mixed", "insufficient_data"):
            claim_text = claim.get("claim_text", "") or ""
            # Skip invalid claims (methodology descriptions, too long)
            if not _is_valid_claim(claim_text):
                continue
            # Ограничиваем длину
            if len(claim_text) > 150:
                claim_text = claim_text[:150].rsplit(" ", 1)[0] + "..."
            questions.append(create_open_question(
                topic=claim.get("topic", "unknown"),
                question=f"What is the true relationship regarding: {claim_text}?",
                status="open",
            ))
    return questions[:10]  # Limit to 10 questions per topic


def detect_myths_from_contradictions(claims: List[Dict[str, Any]], consensus_states: List[Dict[str, Any]]) -> List[Myth]:
    myths: List[Myth] = []
    for claim, cs in zip(claims, consensus_states):
        if cs.get("contradict_count", 0) > cs.get("support_count", 0):
            claim_text = claim.get("claim_text", "") or ""
            # Skip invalid claims
            if not _is_valid_claim(claim_text):
                continue
            # Ограничиваем длину
            if len(claim_text) > 200:
                claim_text = claim_text[:200].rsplit(" ", 1)[0] + "..."
            myths.append(create_myth(
                topic=claim.get("topic", "unknown"),
                myth_text=claim_text,
                correction="Current evidence suggests this claim may be incorrect or incomplete.",
                evidence_summary=f"Contradicted by {cs.get('contradict_count', 0)} studies.",
            ))
    return myths[:5]  # Limit to 5 myths per topic
