"""Editorial Memory: remembers past editorial decisions and their outcomes."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class EditorialDecision:
    draft_id: int
    article_id: int
    topic: str
    decision: str  # approved, rejected, edit_requested
    reason: str
    editor_id: str
    timestamp: str
    outcome: Optional[str] = None  # published, not_published, revised
    notes: str = ""


@dataclass
class Pattern:
    pattern_type: str  # rejection_reason, approval_pattern, topic_trend
    description: str
    frequency: int
    examples: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class EditorialMemory:
    decisions: List[EditorialDecision] = field(default_factory=list)
    patterns: List[Pattern] = field(default_factory=list)

    def add_decision(self, decision: EditorialDecision) -> None:
        self.decisions.append(decision)

    def analyze_patterns(self) -> List[Pattern]:
        patterns = []

        # Rejection reasons
        rejection_reasons: Dict[str, List[str]] = {}
        for d in self.decisions:
            if d.decision == "rejected":
                key = d.reason.lower()[:50]
                rejection_reasons.setdefault(key, []).append(f"Draft #{d.draft_id}")

        for reason, examples in rejection_reasons.items():
            if len(examples) >= 2:
                patterns.append(Pattern(
                    pattern_type="rejection_reason",
                    description=f"Частая причина отклонения: {reason}",
                    frequency=len(examples),
                    examples=examples[:3],
                    recommendation="Рассмотреть обновление критериев качества.",
                ))

        # Topic trends
        topic_decisions: Dict[str, Dict[str, int]] = {}
        for d in self.decisions:
            topic_decisions.setdefault(d.topic, {})
            topic_decisions[d.topic][d.decision] = topic_decisions[d.topic].get(d.decision, 0) + 1

        for topic, decisions in topic_decisions.items():
            approved = decisions.get("approved", 0)
            rejected = decisions.get("rejected", 0)
            if approved + rejected >= 3:
                approval_rate = approved / (approved + rejected)
                if approval_rate < 0.3:
                    patterns.append(Pattern(
                        pattern_type="topic_trend",
                        description=f"Тема {topic}: низкий уровень одобрения ({approval_rate:.0%})",
                        frequency=rejected,
                        recommendation="Проверить критерии отбора для этой темы.",
                    ))
                elif approval_rate > 0.9:
                    patterns.append(Pattern(
                        pattern_type="topic_trend",
                        description=f"Тема {topic}: высокий уровень одобрения ({approval_rate:.0%})",
                        frequency=approved,
                        recommendation="Тема соответствует критериям качества.",
                    ))

        self.patterns = patterns
        return patterns

    def get_recommendation_for_topic(self, topic: str) -> str:
        relevant = [p for p in self.patterns if topic in p.description.lower()]
        if relevant:
            return relevant[0].recommendation
        return "Нет специфических рекомендаций."

    def get_statistics(self) -> Dict:
        total = len(self.decisions)
        if total == 0:
            return {"total": 0}

        approved = sum(1 for d in self.decisions if d.decision == "approved")
        rejected = sum(1 for d in self.decisions if d.decision == "rejected")
        edited = sum(1 for d in self.decisions if d.decision == "edit_requested")

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "edit_requested": edited,
            "approval_rate": approved / total if total > 0 else 0,
            "topics_count": len(set(d.topic for d in self.decisions)),
        }


def build_editorial_memory(decisions: List[Dict]) -> EditorialMemory:
    """Build EditorialMemory from database rows."""
    memory = EditorialMemory()
    for d in decisions:
        memory.add_decision(EditorialDecision(
            draft_id=d.get("draft_id", d.get("id", 0)),
            article_id=d.get("article_id", 0),
            topic=d.get("topic", "unknown"),
            decision=d.get("decision", "unknown"),
            reason=d.get("reason", ""),
            editor_id=d.get("editor", ""),
            timestamp=str(d.get("created_at", "")),
            outcome=d.get("outcome"),
            notes=d.get("notes", ""),
        ))
    return memory


def memory_to_text(memory: EditorialMemory) -> str:
    lines = ["\U0001f4cb <b>Editorial Memory</b>\n"]

    stats = memory.get_statistics()
    lines.append(f"<b>Всего решений:</b> {stats.get('total', 0)}")
    lines.append(f"<b>Одобрено:</b> {stats.get('approved', 0)}")
    lines.append(f"<b>Отклонено:</b> {stats.get('rejected', 0)}")
    lines.append(f"<b>На доработку:</b> {stats.get('edit_requested', 0)}")
    if stats.get("total", 0) > 0:
        lines.append(f"<b>Уровень одобрения:</b> {stats.get('approval_rate', 0):.0%}")
    lines.append("")

    if memory.patterns:
        lines.append("<b>Паттерны:</b>")
        for p in memory.patterns[:5]:
            lines.append(f"  \u2022 {p.description} (частота: {p.frequency})")
            if p.recommendation:
                lines.append(f"    <i>\u2192 {p.recommendation}</i>")
        lines.append("")

    return "\n".join(lines)
