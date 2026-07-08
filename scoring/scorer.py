# ============================================================
#  scoring/scorer.py — оценка качества статьи
# ============================================================
#
#  Факторы и очки (из документа Noerra):
#  +10  Peer reviewed (рецензируемый журнал)
#  +8   Trusted source (доверенный источник)
#  +10  Practical value (практическая ценность)
#  +5   Recent publication (свежая публикация)
#  +6   Clear findings (чёткие выводы)
#  -5   Overhyped topic (хайп без содержания)
#  +4   Boost keyword (усилитель из конфига)
#  -5   Penalty keyword (фильтр мусора)
# ============================================================

import re
import logging
from datetime import datetime
from parsers.base import RawArticle
from config.topics import BOOST_KEYWORDS, PENALTY_KEYWORDS, TRUSTED_SOURCES

logger = logging.getLogger(__name__)

# Слова, сигнализирующие о практической ценности
PRACTICAL_KEYWORDS = [
    "treatment", "therapy", "intervention", "clinical",
    "practical", "application", "лечение", "терапия",
    "практический", "применение", "клинический",
]

# Слова, говорящие о чётких выводах
CLEAR_FINDINGS_KEYWORDS = [
    "found that", "results show", "we demonstrate",
    "evidence", "significantly", "demonstrated",
    "показано", "выявлено", "доказано", "результаты показывают",
]

# Признаки хайпа
HYPE_KEYWORDS = [
    "revolutionary", "miracle", "cure-all", "breakthrough cure",
    "100%", "guaranteed", "революционное открытие",
    "чудодейственный", "панацея",
]

# Признаки свежей публикации в тексте — динамически от текущего года
_current_year = datetime.now().year
RECENT_PATTERNS = [
    rf"\b{_current_year}\b",
    rf"\b{_current_year - 1}\b",
    rf"\b{_current_year - 2}\b",
]


def score_article(article: RawArticle) -> int:
    """
    Возвращает числовой score статьи.
    Чем выше — тем качественнее материал.
    """
    text = f"{article.title} {article.abstract}".lower()
    score = 0
    reasons = []

    # +10 Peer reviewed
    if article.is_peer_reviewed:
        score += 10
        reasons.append("+10 peer reviewed")

    # +8 Trusted source
    if any(src in article.source.lower() for src in TRUSTED_SOURCES):
        score += 8
        reasons.append(f"+8 trusted source ({article.source})")

    # +10 Practical value
    if any(kw in text for kw in PRACTICAL_KEYWORDS):
        score += 10
        reasons.append("+10 practical value")

    # +5 Recent publication
    if any(re.search(p, text) for p in RECENT_PATTERNS):
        score += 5
        reasons.append("+5 recent")

    # +6 Clear findings
    if any(kw in text for kw in CLEAR_FINDINGS_KEYWORDS):
        score += 6
        reasons.append("+6 clear findings")

    # -5 Hype / overhyped
    hype_count = sum(1 for kw in HYPE_KEYWORDS if kw in text)
    if hype_count > 0:
        score -= 5 * hype_count
        reasons.append(f"-{5 * hype_count} hype")

    # +4 Boost keywords
    boost = sum(4 for kw in BOOST_KEYWORDS if kw.lower() in text)
    if boost:
        score += boost
        reasons.append(f"+{boost} boost")

    # -5 Penalty keywords
    penalty = sum(5 for kw in PENALTY_KEYWORDS if kw.lower() in text)
    if penalty:
        score -= penalty
        reasons.append(f"-{penalty} penalty")

    logger.debug(f"Score {score} for '{article.title[:60]}': {', '.join(reasons)}")
    return max(score, 0)
