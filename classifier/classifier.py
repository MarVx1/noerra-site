# ============================================================
#  classifier/classifier.py — определение темы статьи
# ============================================================

import logging
import re
from parsers.base import RawArticle
from config.topics import TOPIC_KEYWORDS

logger = logging.getLogger(__name__)


# Совпадение в ЗАГОЛОВКЕ весит больше, чем в теле абстракта: заголовок —
# это предмет статьи, а в теле тема может быть упомянута мимоходом.
# Именно из-за этого статья "The long road after breast cancer" получала
# тему "сон" (слово мелькнуло в абстракте) и публиковалась как
# "Сон: очередное подтверждение".
TITLE_WEIGHT_MULTIPLIER = 2

# Минимальный взвешенный вес темы-победителя. Ниже порога считаем, что
# статья не о нашей тематике, и возвращаем "unknown" — scheduler уже умеет
# складывать такие статьи в off_topic и не публиковать.
#
# Порог подобран на размеченной выборке из БД (8 статей по теме / 7 не по
# теме): все 8 корректных проходят, отсеиваются все грубые ложные темы.
# Относительная confidence для этого не годится — она измеряет лишь
# перевес над другими темами, а не то, о статье ли это вообще (хорошие
# статьи опускались до 0.33, ложные поднимались до 0.50 — разделения нет).
MIN_TOPIC_SCORE = 6

# Ключевое слово должно начинаться с границы слова, иначе оно ловится
# внутри посторонних слов: "axon" в "taxonomy", "rem" в "remains".
# Граница ставится ТОЛЬКО в начале — окончание намеренно свободно, чтобы
# сохранить морфологию: "behavior" → "behavioral", "attention" →
# "attentional", "stress" → "stressors", "cognition" → "cognitions".
_KEYWORD_PATTERNS: dict[str, list[tuple[re.Pattern, int]]] = {
    topic: [(re.compile(rf"\b{re.escape(kw.lower())}"), weight)
            for kw, weight in keywords.items()]
    for topic, keywords in TOPIC_KEYWORDS.items()
}


def classify(article: RawArticle) -> tuple[str, float]:
    """
    Определяет тему статьи и уверенность (0.0–1.0).
    Возвращает (topic, confidence).
    Если тема не определена или определена слишком слабо — ('unknown', 0.0).
    """
    title = (article.title or "").lower()
    abstract = (article.abstract or "").lower()
    topic_scores: dict[str, int] = {}
    # Вес 3 = "специфичный термин (сильный сигнал)" по определению в шапке
    # config/topics.py — без хотя бы одного такого слова тема держится
    # целиком на общей лексике (reward/reinforcement/learning/attention),
    # которая в arXiv-статьях про ML совпадает с нейронаучной один в один:
    # ML-статья "Online Reinforcement Learning for Computer-Use Agents"
    # набирала score по "reinforcement"+"reward" и уходила в тему "dopamine",
    # хотя ни разу не упоминала ни дофамин, ни мозг (вычитка 2026-07-15).
    topic_has_anchor: dict[str, bool] = {}

    for topic, patterns in _KEYWORD_PATTERNS.items():
        score = 0
        has_anchor = False
        for pattern, weight in patterns:
            matched = pattern.search(title) or pattern.search(abstract)
            if pattern.search(title):
                score += weight * TITLE_WEIGHT_MULTIPLIER
            elif pattern.search(abstract):
                score += weight
            if matched and weight >= 3:
                has_anchor = True
        topic_scores[topic] = score
        topic_has_anchor[topic] = has_anchor

    if not any(topic_scores.values()):
        return "unknown", 0.0

    best_topic = max(topic_scores, key=lambda t: topic_scores[t])
    best_score = topic_scores[best_topic]
    total_score = sum(topic_scores.values())

    confidence = round(best_score / total_score, 2) if total_score > 0 else 0.0

    if best_score < MIN_TOPIC_SCORE:
        logger.debug(
            f"Topic rejected: best '{best_topic}' scored {best_score} < {MIN_TOPIC_SCORE} "
            f"for '{article.title[:60]}'"
        )
        return "unknown", 0.0

    if not topic_has_anchor[best_topic]:
        logger.debug(
            f"Topic rejected: best '{best_topic}' had no specific anchor keyword "
            f"(score={best_score} came entirely from generic terms) for '{article.title[:60]}'"
        )
        return "unknown", 0.0

    logger.debug(
        f"Topic '{best_topic}' (score={best_score}, conf={confidence}) for '{article.title[:60]}'"
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


# ── Падежные формы для тем ─────────────────────────────────────
# Ключи: nom (именительный), gen (родительный), dat (дательный),
#        acc (винительный), inst (творительный), prep (предложный)
# _lower — вариант в нижнем регистре (для использования в середине предложения)

_TOPIC_CASES: dict[str, dict[str, str]] = {
    "ADHD": {
        "nom": "СДВГ", "gen": "СДВГ", "dat": "СДВГ",
        "acc": "СДВГ", "inst": "СДВГ", "prep": "СДВГ",
        "nom_lower": "СДВГ", "gen_lower": "СДВГ",
        "dat_lower": "СДВГ", "acc_lower": "СДВГ",
        "inst_lower": "СДВГ", "prep_lower": "СДВГ",
    },
    "dopamine": {
        "nom": "Дофамин", "gen": "Дофамина", "dat": "Дофамину",
        "acc": "Дофамин", "inst": "Дофамином", "prep": "Дофамине",
        "nom_lower": "дофамин", "gen_lower": "дофамина",
        "dat_lower": "дофамину", "acc_lower": "дофамин",
        "inst_lower": "дофамином", "prep_lower": "дофамине",
    },
    "sleep": {
        "nom": "Сон", "gen": "Сна", "dat": "Сну",
        "acc": "Сон", "inst": "Сном", "prep": "Сне",
        "nom_lower": "сон", "gen_lower": "сна",
        "dat_lower": "сну", "acc_lower": "сон",
        "inst_lower": "сном", "prep_lower": "сне",
    },
    "stress": {
        "nom": "Стресс", "gen": "Стресса", "dat": "Стрессу",
        "acc": "Стресс", "inst": "Стрессом", "prep": "Стрессе",
        "nom_lower": "стресс", "gen_lower": "стресса",
        "dat_lower": "стрессу", "acc_lower": "стресс",
        "inst_lower": "стрессом", "prep_lower": "стрессе",
    },
    "anxiety": {
        "nom": "Тревожность", "gen": "Тревожности", "dat": "Тревожности",
        "acc": "Тревожность", "inst": "Тревожностью", "prep": "Тревожности",
        "nom_lower": "тревожность", "gen_lower": "тревожности",
        "dat_lower": "тревожности", "acc_lower": "тревожность",
        "inst_lower": "тревожностью", "prep_lower": "тревожности",
    },
    "cognition": {
        "nom": "Когниция", "gen": "Когниции", "dat": "Когниции",
        "acc": "Когницию", "inst": "Когницией", "prep": "Когниции",
        "nom_lower": "когниция", "gen_lower": "когниции",
        "dat_lower": "когниции", "acc_lower": "когницию",
        "inst_lower": "когницией", "prep_lower": "когниции",
    },
    "neuroplasticity": {
        "nom": "Нейропластичность", "gen": "Нейропластичности", "dat": "Нейропластичности",
        "acc": "Нейропластичность", "inst": "Нейропластичностью", "prep": "Нейропластичности",
        "nom_lower": "нейропластичность", "gen_lower": "нейропластичности",
        "dat_lower": "нейропластичности", "acc_lower": "нейропластичность",
        "inst_lower": "нейропластичностью", "prep_lower": "нейропластичности",
    },
    "neuroscience": {
        "nom": "Нейронаука", "gen": "Нейронауки", "dat": "Нейронауке",
        "acc": "Нейронауку", "inst": "Нейронаукой", "prep": "Нейронауке",
        "nom_lower": "нейронаука", "gen_lower": "нейронауки",
        "dat_lower": "нейронауке", "acc_lower": "нейронауку",
        "inst_lower": "нейронаукой", "prep_lower": "нейронауке",
    },
    "psychology": {
        "nom": "Психология", "gen": "Психологии", "dat": "Психологии",
        "acc": "Психологию", "inst": "Психологией", "prep": "Психологии",
        "nom_lower": "психология", "gen_lower": "психологии",
        "dat_lower": "психологии", "acc_lower": "психологию",
        "inst_lower": "психологией", "prep_lower": "психологии",
    },
}


def get_topic_case(topic: str, case: str = "nom") -> str:
    """Возвращает тему в указанном падеже.

    Доступные падежи: nom, gen, dat, acc, inst, prep.
    Добавьте '_lower' для варианта в нижнем регистре (например, 'gen_lower').
    """
    cases = _TOPIC_CASES.get(topic)
    if cases:
        return cases.get(case, cases.get("nom", topic))
    # Fallback для неизвестных тем — возвращаем как есть
    return get_topic_ru(topic)
