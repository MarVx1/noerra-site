"""Reasoning Chain: stores the full reasoning trail for conclusions."""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ReasoningStep:
    step_type: str  # "evidence", "inference", "assumption", "limitation"
    description: str
    source: str  # article URL or claim ID
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningChain:
    topic: str
    claim_text: str
    steps: List[ReasoningStep]
    final_confidence: float
    conclusion: str
    assumptions: List[str]
    limitations: List[str]


def build_reasoning_chain(
    topic: str,
    claim_text: str,
    evidence: List[Dict[str, Any]],
    consensus: Dict[str, Any],
) -> ReasoningChain:
    steps: List[ReasoningStep] = []
    assumptions: List[str] = []
    limitations: List[str] = []

    # Step 1: Add evidence from articles
    for ev in evidence[:5]:
        steps.append(ReasoningStep(
            step_type="evidence",
            description=ev.get("claim_text", ev.get("title", ""))[:200],
            source=ev.get("url", f"claim_{ev.get('id', '')}"),
            confidence=float(ev.get("confidence", 0.5)),
            metadata={
                "study_type": ev.get("study_type", "unknown"),
                "peer_reviewed": ev.get("peer_reviewed", False),
            },
        ))

    # Step 2: Add consensus inference
    if consensus:
        steps.append(ReasoningStep(
            step_type="inference",
            description=f"Consensus: {consensus.get('consensus_level', 'unknown')} "
                        f"(support={consensus.get('support_count', 0)}, "
                        f"contradict={consensus.get('contradict_count', 0)})",
            source="consensus_engine",
            confidence=float(consensus.get("confidence", 0.5)),
            metadata={
                "support_count": consensus.get("support_count", 0),
                "contradict_count": consensus.get("contradict_count", 0),
            },
        ))

    # Step 3: Extract assumptions
    if consensus.get("consensus_level") in ("hypothesis", "insufficient_data"):
        assumptions.append("Evidence is preliminary and requires further validation.")
    if consensus.get("contradict_count", 0) > consensus.get("support_count", 0):
        assumptions.append("Contradictory evidence exists; conclusion may be revised.")

    # Step 4: Extract limitations
    for ev in evidence:
        if ev.get("limitations"):
            limitations.append(f"Study limitation: {ev['limitations'][:150]}")
        if ev.get("evidence_strength") in ("weak", "preliminary", "limited"):
            limitations.append(f"Limited evidence strength from {ev.get('source', 'unknown')}")

    # Calculate final confidence
    if steps:
        final_confidence = sum(s.confidence for s in steps) / len(steps)
    else:
        final_confidence = 0.0

    conclusion = f"Based on {len(evidence)} sources, the claim '{claim_text[:100]}' "
    if consensus.get("consensus_level") == "supported":
        conclusion += "is supported by current evidence."
    elif consensus.get("consensus_level") == "contested":
        conclusion += "remains contested in the scientific community."
    elif consensus.get("consensus_level") == "emerging_consensus":
        conclusion += "has emerging consensus."
    else:
        conclusion += "requires further research."

    return ReasoningChain(
        topic=topic,
        claim_text=claim_text,
        steps=steps,
        final_confidence=round(final_confidence, 2),
        conclusion=conclusion,
        assumptions=assumptions,
        limitations=limitations,
    )


def chain_to_text(chain: ReasoningChain) -> str:
    """Convert reasoning chain to human-readable text."""
    lines = [
        f"<b>Reasoning Chain: {chain.claim_text[:150]}</b>\n",
        f"<b>Conclusion:</b> {chain.conclusion}\n",
        f"<b>Confidence:</b> {chain.final_confidence:.2f}\n",
    ]

    if chain.assumptions:
        lines.append("<b>Assumptions:</b>")
        for a in chain.assumptions:
            lines.append(f"  • {a}")
        lines.append("")

    if chain.limitations:
        lines.append("<b>Limitations:</b>")
        for l in chain.limitations:
            lines.append(f"  • {l}")
        lines.append("")

    lines.append("<b>Evidence Trail:</b>")
    for i, step in enumerate(chain.steps, 1):
        emoji = {"evidence": "📚", "inference": "🔬", "assumption": "⚠️", "limitation": "⚠️"}.get(step.step_type, "•")
        lines.append(f"  {emoji} Step {i} [{step.step_type}]: {step.description[:150]}")
        lines.append(f"      Confidence: {step.confidence:.2f} | Source: {step.source[:50]}")

    return "\n".join(lines)


def validate_chain(chain: ReasoningChain) -> Dict[str, Any]:
    """Validate reasoning chain for completeness and coherence."""
    issues = []

    if len(chain.steps) < 2:
        issues.append("Chain has too few steps (minimum 2 recommended).")

    if not any(s.step_type == "evidence" for s in chain.steps):
        issues.append("No evidence steps in chain.")

    if chain.final_confidence < 0.3 and not chain.assumptions:
        issues.append("Low confidence but no assumptions stated.")

    if chain.final_confidence > 0.8 and chain.limitations:
        issues.append("High confidence despite stated limitations.")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "step_count": len(chain.steps),
        "evidence_count": sum(1 for s in chain.steps if s.step_type == "evidence"),
    }
