# ============================================================
#  classifier/classifier.py — определение темы статьи
# ============================================================

import logging
from parsers.base import RawArticle
from config.topics import TOPIC_KEYWORDS

logger = logging.getLogger(__name__)


def classify(article: RawArticle) -> tuple[str, float]:
    """
    Определяет тему статьи и уверенность (0.0–1.0).
    Возвращает (topic, confidence).
    Если ни одна тема не подошла — возвращает ('unknown', 0.0).
    """
    text = f"{article.title} {article.abstract}".lower()
    topic_scores: dict[str, int] = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for kw, weight in keywords.items():
            if kw.lower() in text:
                score += weight
        topic_scores[topic] = score

    if not any(topic_scores.values()):
        return "unknown", 0.0

    best_topic = max(topic_scores, key=lambda t: topic_scores[t])
    best_score = topic_scores[best_topic]
    total_score = sum(topic_scores.values())

    confidence = round(best_score / total_score, 2) if total_score > 0 else 0.0

    logger.debug(
        f"Topic '{best_topic}' (conf={confidence}) for '{article.title[:60]}'"
    )
    return best_topic, confidence


def get_topic_emoji(topic: str) -> str:
    return {
        "ADHD":             "⚡️",
        "dopamine":         "💊",
        "sleep":            "😴",
        "stress":           "😤",
        "anxiety":          "😰",
        "cognition":        "🧩",
        "neuroplasticity":  "🔄",
        "neuroscience":     "🧠",
        "psychology":       "💭",
    }.get(topic, "📌")


def get_topic_ru(topic: str) -> str:
    return {
        "ADHD":             "СДВГ",
        "dopamine":         "Дофамин",
        "sleep":            "Сон",
        "stress":           "Стресс",
        "anxiety":          "Тревожность",
        "cognition":        "Когниция",
        "neuroplasticity":  "Нейропластичность",
        "neuroscience":     "Нейронаука",
        "psychology":       "Психология",
    }.get(topic, "Наука")
