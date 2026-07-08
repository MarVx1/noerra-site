"""Knowledge Timeline: история развития научных взглядов по теме."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class TimelineEvent:
    event_id: str
    event_type: str  # hypothesis, discovery, confirmation, contradiction, consensus, revision
    timestamp: str  # ISO date or approximate ("2010s", "early 2000s")
    title: str
    description: str
    topic: str
    key_claim: str = ""
    evidence_count: int = 0
    confidence_at_time: float = 0.0


@dataclass
class KnowledgeTimeline:
    topic: str
    topic_ru: str
    events: List[TimelineEvent] = field(default_factory=list)
    current_consensus: str = ""
    major_shifts: List[str] = field(default_factory=list)

    def add_event(self, event: TimelineEvent) -> None:
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)

    def get_events_by_type(self, event_type: str) -> List[TimelineEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def get_shifts(self) -> List[str]:
        shifts = []
        prev_confidence = 0.0
        for event in self.events:
            if abs(event.confidence_at_time - prev_confidence) > 0.3:
                direction = "↑" if event.confidence_at_time > prev_confidence else "↓"
                shifts.append(
                    f"{direction} {event.timestamp}: {event.title} "
                    f"(confidence {prev_confidence:.2f} → {event.confidence_at_time:.2f})"
                )
                prev_confidence = event.confidence_at_time
        return shifts


TIMELINE_TEMPLATES = {
    "dopamine": KnowledgeTimeline(
        topic="dopamine",
        topic_ru="Дофамин",
        events=[
            TimelineEvent(
                event_id="dopamine_1957",
                event_type="discovery",
                timestamp="1957",
                title="Открытие дофамина",
                description="Арвид Карлссон открывает дофамин как нейромедиатор.",
                topic="dopamine",
                key_claim="Dopamine exists as neurotransmitter",
                confidence_at_time=0.5,
            ),
            TimelineEvent(
                event_id="dopamine_1980s",
                event_type="hypothesis",
                timestamp="1980s",
                title="Дофамин как система вознаграждения",
                description="Формируется гипотеза о роли дофамина в удовольствии.",
                topic="dopamine",
                key_claim="Dopamine = pleasure chemical",
                confidence_at_time=0.6,
            ),
            TimelineEvent(
                event_id="dopamine_1990s",
                event_type="revision",
                timestamp="1990s",
                title="Prediction error hypothesis",
                description="Шульц показывает: дофамин кодирует ошибку прогнозирования, а не удовольствие.",
                topic="dopamine",
                key_claim="Dopamine encodes prediction error",
                confidence_at_time=0.75,
            ),
            TimelineEvent(
                event_id="dopamine_2000s",
                event_type="confirmation",
                timestamp="2000s",
                title="Подтверждение роли в обучении",
                description="Множество исследований подтверждают роль в обучении и мотивации.",
                topic="dopamine",
                key_claim="Dopamine critical for reinforcement learning",
                confidence_at_time=0.85,
            ),
            TimelineEvent(
                event_id="dopamine_2010s",
                event_type="consensus",
                timestamp="2010s",
                title="Современный консенсус",
                description="Консенсус: дофамин — это мотивация, обучение и прогнозирование, не просто удовольствие.",
                topic="dopamine",
                key_claim="Dopamine = motivation + learning + prediction",
                confidence_at_time=0.9,
            ),
        ],
        current_consensus="Дофамин кодирует ошибку прогнозирования вознаграждения и участвует в обучении и мотивации.",
        major_shifts=[
            "1980s → 1990s: от 'удовольствия' к 'предсказанию'",
            "2000s: подтверждение роли в обучении с подкреплением",
        ],
    ),
    "sleep": KnowledgeTimeline(
        topic="sleep",
        topic_ru="Сон",
        events=[
            TimelineEvent(
                event_id="sleep_1950s",
                event_type="discovery",
                timestamp="1950s",
                title="Открытие REM-сна",
                description="Обнаружена фаза быстрого движения глаз (REM).",
                topic="sleep",
                key_claim="REM sleep exists",
                confidence_at_time=0.6,
            ),
            TimelineEvent(
                event_id="sleep_1990s",
                event_type="discovery",
                timestamp="1990s",
                title="Консолидация памяти во сне",
                description="Исследования показывают роль сна в памяти.",
                topic="sleep",
                key_claim="Sleep consolidates memory",
                confidence_at_time=0.7,
            ),
            TimelineEvent(
                event_id="sleep_2010s",
                event_type="discovery",
                timestamp="2013",
                title="Глимфатическая система",
                description="Обнаружена система очистки мозга во время сна.",
                topic="sleep",
                key_claim="Glymphatic system clears brain during sleep",
                confidence_at_time=0.8,
            ),
            TimelineEvent(
                event_id="sleep_2020s",
                event_type="consensus",
                timestamp="2020s",
                title="Современный консенсус",
                description="Сон критичен для памяти, эмоций и очистки мозга от токсинов.",
                topic="sleep",
                key_claim="Sleep essential for memory, emotions, detoxification",
                confidence_at_time=0.9,
            ),
        ],
        current_consensus="Сон — активный процесс консолидации памяти, регуляции эмоций и очистки мозга.",
        major_shifts=[
            "1950s: открытие фаз сна",
            "1990s: связь с памятью",
            "2010s: открытие глимфатической системы",
        ],
    ),
    "ADHD": KnowledgeTimeline(
        topic="ADHD",
        topic_ru="СДВГ",
        events=[
            TimelineEvent(
                event_id="adhd_1900s",
                event_type="hypothesis",
                timestamp="early 1900s",
                title="Первые описания",
                description="Описаны симптомы невнимательности и гиперактивности.",
                topic="ADHD",
                key_claim="Attention deficit symptoms observed",
                confidence_at_time=0.3,
            ),
            TimelineEvent(
                event_id="adhd_1980s",
                event_type="discovery",
                timestamp="1980s",
                title="Нейробиологическая основа",
                description="Обнаружены различия в структуре мозга.",
                topic="ADHD",
                key_claim="ADHD has neurobiological basis",
                confidence_at_time=0.6,
            ),
            TimelineEvent(
                event_id="adhd_2000s",
                event_type="confirmation",
                timestamp="2000s",
                title="Генетические факторы",
                description="Подтверждена высокая наследуемость.",
                topic="ADHD",
                key_claim="ADHD highly heritable",
                confidence_at_time=0.8,
            ),
            TimelineEvent(
                event_id="adhd_2010s",
                event_type="consensus",
                timestamp="2010s",
                title="Современный консенсус",
                description="СДВГ — нейробиологическое расстройство с изменениями в префронтальной коре и дофаминовой системе.",
                topic="ADHD",
                key_claim="ADHD = prefrontal cortex + dopamine differences",
                confidence_at_time=0.85,
            ),
        ],
        current_consensus="СДВГ — нейробиологическое расстройство с генетической основой и структурными изменениями мозга.",
        major_shifts=[
            "1900s → 1980s: от 'поведения' к 'нейробиологии'",
            "2000s: генетические доказательства",
        ],
    ),
}


def get_timeline(topic: str) -> Optional[KnowledgeTimeline]:
    return TIMELINE_TEMPLATES.get(topic)


def list_timelines() -> List[Dict[str, str]]:
    return [
        {"topic": t.topic, "topic_ru": t.topic_ru, "events": len(t.events)}
        for t in TIMELINE_TEMPLATES.values()
    ]


def timeline_to_text(timeline: KnowledgeTimeline) -> str:
    lines = [
        f"📜 <b>История развития знаний: {timeline.topic_ru}</b>\n",
        f"<b>Текущий консенсус:</b> {timeline.current_consensus}\n",
    ]

    if timeline.major_shifts:
        lines.append("<b>Ключевые сдвиги:</b>")
        for shift in timeline.major_shifts:
            lines.append(f"  • {shift}")
        lines.append("")

    lines.append("<b>Хронология:</b>")
    for event in timeline.events:
        emoji = {
            "hypothesis": "💭",
            "discovery": "🔬",
            "confirmation": "✅",
            "contradiction": "⚡",
            "consensus": "🎯",
            "revision": "🔄",
        }.get(event.event_type, "•")
        lines.append(
            f"  {emoji} <b>{event.timestamp}</b>: {event.title}\n"
            f"      {event.description[:150]}"
        )

    return "\n".join(lines)


def build_timeline_from_consensus(
    topic: str,
    topic_ru: str,
    consensus_history: List[Dict],
) -> KnowledgeTimeline:
    """Build timeline from consensus version history."""
    timeline = KnowledgeTimeline(topic=topic, topic_ru=topic_ru)

    for i, cs in enumerate(consensus_history):
        event_type = "discovery" if i == 0 else "revision"
        if cs.get("consensus_level") == "supported":
            event_type = "confirmation"
        elif cs.get("consensus_level") == "emerging_consensus":
            event_type = "consensus"
        elif cs.get("consensus_level") == "contested":
            event_type = "contradiction"

        timeline.add_event(TimelineEvent(
            event_id=f"{topic}_v{cs.get('version', i)}",
            event_type=event_type,
            timestamp=str(cs.get("created_at", "unknown"))[:10],
            title=f"Версия {cs.get('version', i)}: {cs.get('consensus_level', 'unknown')}",
            description=cs.get("summary", "")[:200],
            topic=topic,
            confidence_at_time=float(cs.get("confidence", 0.5)),
        ))

    return timeline


def get_key_turning_points(timeline: KnowledgeTimeline) -> List[TimelineEvent]:
    """Find events that caused major confidence shifts."""
    if not timeline.events:
        return []

    turning_points = []
    prev_conf = timeline.events[0].confidence_at_time

    for event in timeline.events[1:]:
        delta = abs(event.confidence_at_time - prev_conf)
        if delta >= 0.15:
            turning_points.append(event)
            prev_conf = event.confidence_at_time

    return turning_points
