"""Knowledge Routes: learning paths through topics."""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class RouteStep:
    order: int
    topic: str
    title: str
    description: str
    key_claims: List[str]
    estimated_time: str  # e.g., "15 min", "1 hour"


@dataclass
class KnowledgeRoute:
    route_id: str
    title: str
    description: str
    target_audience: str
    steps: List[RouteStep]
    total_time: str
    prerequisites: List[str] = field(default_factory=list)
    outcomes: List[str] = field(default_factory=list)


ROUTE_TEMPLATES = {
    "adhd_fundamentals": KnowledgeRoute(
        route_id="adhd_fundamentals",
        title="Понять СДВГ",
        description="От базовых механизмов внимания до современных исследований и практик.",
        target_audience="general",
        steps=[
            RouteStep(1, "attention", "Как работает внимание", "Базовые механизмы внимания и исполнительных функций.", [], "15 min"),
            RouteStep(2, "ADHD", "Что такое СДВГ", "Нейробиология СДВГ, диагностические критерии, распространённость.", [], "20 min"),
            RouteStep(3, "working_memory", "Рабочая память", "Связь рабочей памяти и СДВГ, современные исследования.", [], "15 min"),
            RouteStep(4, "ADHD", "Современные подходы", "Терапия, медикаменты, поведенческие интервенции.", [], "20 min"),
        ],
        total_time="70 min",
        prerequisites=[],
        outcomes=[
            "Понимать механизмы внимания и исполнительных функций",
            "Знать диагностические критерии СДВГ",
            "Разбираться в современных подходах к терапии",
        ],
    ),
    "sleep_science": KnowledgeRoute(
        route_id="sleep_science",
        title="Наука сна",
        description="От циркадных ритмов до влияния сна на память и продуктивность.",
        target_audience="general",
        steps=[
            RouteStep(1, "sleep", "Циркадные ритмы", "Как работают биологические часы, мелатонин, свет.", [], "15 min"),
            RouteStep(2, "sleep", "Фазы сна", "REM, медленный сон, их функции.", [], "15 min"),
            RouteStep(3, "memory", "Сон и память", "Консолидация памяти, влияние недосыпа.", [], "20 min"),
            RouteStep(4, "sleep", "Оптимизация сна", "Практические рекомендации на основе исследований.", [], "20 min"),
        ],
        total_time="70 min",
        prerequisites=[],
        outcomes=[
            "Понимать циркадные ритмы и фазы сна",
            "Знать влияние сна на когнитивные функции",
            "Уметь применять научно обоснованные практики",
        ],
    ),
    "dopamine_motivation": KnowledgeRoute(
        route_id="dopamine_motivation",
        title="Дофамин и мотивация",
        description="От системы вознаграждения до практического применения в повседневной жизни.",
        target_audience="informed",
        steps=[
            RouteStep(1, "dopamine", "Дофаминовая система", "Анатомия, пути, рецепторы.", [], "20 min"),
            RouteStep(2, "reward", "Система вознаграждения", "Nucleus accumbens, prediction error.", [], "20 min"),
            RouteStep(3, "motivation", "Мотивация и обучение", "Роль дофамина в обучении и принятии решений.", [], "20 min"),
            RouteStep(4, "dopamine", "Практическое применение", "Как использовать знания о дофамине в жизни.", [], "20 min"),
        ],
        total_time="80 min",
        prerequisites=["basic_neuroscience"],
        outcomes=[
            "Понимать дофаминовую систему мозга",
            "Знать роль дофамина в мотивации и обучении",
            "Уметь применять знания на практике",
        ],
    ),
}


def get_route(route_id: str) -> KnowledgeRoute | None:
    return ROUTE_TEMPLATES.get(route_id)


def list_routes() -> List[Dict[str, str]]:
    return [
        {"id": r.route_id, "title": r.title, "description": r.description, "time": r.total_time}
        for r in ROUTE_TEMPLATES.values()
    ]


def build_route_from_topics(topic_sequence: List[str], title: str = "") -> KnowledgeRoute:
    """Build a custom route from a sequence of topics."""
    steps = []
    for i, topic in enumerate(topic_sequence, 1):
        steps.append(RouteStep(
            order=i,
            topic=topic,
            title=f"Тема: {topic}",
            description=f"Изучение темы {topic}",
            key_claims=[],
            estimated_time="15 min",
        ))

    return KnowledgeRoute(
        route_id=f"custom_{'_'.join(topic_sequence)}",
        title=title or f"Маршрут: {', '.join(topic_sequence)}",
        description="Пользовательский маршрут изучения.",
        target_audience="general",
        steps=steps,
        total_time=f"{len(steps) * 15} min",
        prerequisites=[],
        outcomes=[],
    )


def route_to_text(route: KnowledgeRoute) -> str:
    """Convert route to human-readable text."""
    lines = [
        f"\U0001f4da <b>{route.title}</b>",
        f"<i>{route.description}</i>",
        f"\U0001f3af Аудитория: {route.target_audience}",
        f"\u23f1 Общее время: {route.total_time}",
        "",
    ]

    if route.prerequisites:
        lines.append("<b>Требования:</b>")
        for p in route.prerequisites:
            lines.append(f"  \u2022 {p}")
        lines.append("")

    lines.append("<b>Шаги:</b>")
    for step in route.steps:
        lines.append(f"  {step.order}. <b>{step.title}</b> ({step.estimated_time})")
        lines.append(f"     {step.description}")
        if step.key_claims:
            lines.append(f"     Ключевые утверждения: {', '.join(step.key_claims[:3])}")
        lines.append("")

    if route.outcomes:
        lines.append("<b>Результаты:</b>")
        for o in route.outcomes:
            lines.append(f"  \u2022 {o}")

    return "\n".join(lines)


def suggest_route_for_topic(topic: str) -> KnowledgeRoute | None:
    """Suggest a route that includes the given topic."""
    for route in ROUTE_TEMPLATES.values():
        for step in route.steps:
            if step.topic.lower() == topic.lower():
                return route
    return None


def get_topics_from_route(route: KnowledgeRoute) -> List[str]:
    """Extract unique topics from a route."""
    topics = []
    for step in route.steps:
        if step.topic not in topics:
            topics.append(step.topic)
    return topics
