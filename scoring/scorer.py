# ============================================================
#  scoring/scorer.py — оценка качества статьи
# ============================================================
#
#  Факторы и очки для научных статей (из документа Noerra):
#  +10  Peer reviewed (рецензируемый журнал)
#  +8   Trusted source (доверенный источник)
#  +10  Practical value (практическая ценность)
#  +5   Recent publication (свежая публикация)
#  +6   Clear findings (чёткие выводы)
#  -5   Overhyped topic (хайп без содержания)
#  +4   Boost keyword (усилитель из конфига)
#  -5   Penalty keyword (фильтр мусора)
#
#  YouTube получает отдельную формулу (_score_youtube_article) — эта
#  формула калибрована под структуру научной аннотации (peer review,
#  академические обороты "results show", упоминание года публикации) и
#  структурно не может присвоить видео проходной балл: ни один из 11
#  реальных видео, собранных парсером за 2026-07-10..14, не набрал
#  MIN_SCORE_TO_MODERATE=20 (максимум был 6) — не потому что видео
#  плохие, а потому что подкаст физически не пишется в стиле абстракта
#  (найдено на живых данных, 2026-07-15).
# ============================================================

import re
import logging
from datetime import datetime
from parsers.base import RawArticle
from parsers.youtube import YOUTUBE_CHANNELS
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


# Каналы из YOUTUBE_CHANNELS (parsers/youtube.py) — уже вручную
# отобранный список авторитетных источников (Huberman Lab, Stanford, MIT,
# Lex Fridman). Название канала попадает в конец заголовка парсером как
# "... [Huberman]" — извлекаем регэкспом, а не импортируем RawArticle с
# новым полем: формат детерминирован и задаётся тем же самым парсером.
_YOUTUBE_CHANNEL_SUFFIX_RE = re.compile(r"\[(\w+)\]\s*$")
_YOUTUBE_CHANNEL_NAMES = set(YOUTUBE_CHANNELS.keys())


def _score_youtube_article(article: RawArticle) -> int:
    """Отдельная формула для видео — score_article() калиброван под
    структуру научной аннотации (peer review, "results show", год
    публикации в тексте), ни один из этих сигналов физически не
    применим к подкасту/лекции.

    +10  Куратируемый канал (YOUTUBE_CHANNELS — уже ручной whitelist)
    +12  Подтверждённая релевантность по субтитрам (URL содержит ?t= —
         _find_timestamp() в parsers/youtube.py нашёл реальное
         упоминание темы в самой транскрипции, не только в заголовке;
         матчинг теперь по границе слова, см. parsers/youtube.py)
    +10  Practical value — тот же маркер, что и для научных статей,
         подкасты про протоколы/лечение используют ту же лексику
     -5  За каждое penalty-слово (общий фильтр мусора, не специфичен
         для источника)

    Порог MIN_SCORE_TO_MODERATE=20 достижим только видео из
    куратируемого канала с подтверждённой по субтитрам релевантностью
    (10+12=22) — просто заголовок без подтверждения (10) не проходит,
    ровно то, что отсеивало ложное попадание "Stanford Commencement
    Ceremony" в тему "сон" (там срабатывал только заголовок/подстрочный
    баг "rem", реальной релевантности по субтитрам не было).
    """
    text = f"{article.title} {article.abstract}".lower()
    score = 0
    reasons = []

    channel_match = _YOUTUBE_CHANNEL_SUFFIX_RE.search(article.title or "")
    if channel_match and channel_match.group(1).lower() in _YOUTUBE_CHANNEL_NAMES:
        score += 10
        reasons.append(f"+10 curated channel ({channel_match.group(1)})")

    if "?t=" in (article.url or ""):
        score += 12
        reasons.append("+12 transcript-confirmed relevance")

    if any(kw in text for kw in PRACTICAL_KEYWORDS):
        score += 10
        reasons.append("+10 practical value")

    penalty = sum(5 for kw in PENALTY_KEYWORDS if kw.lower() in text)
    if penalty:
        score -= penalty
        reasons.append(f"-{penalty} penalty")

    logger.debug(f"YouTube score {score} for '{article.title[:60]}': {', '.join(reasons)}")
    return max(score, 0)


def score_article(article: RawArticle) -> int:
    """
    Возвращает числовой score статьи.
    Чем выше — тем качественнее материал.
    """
    if (article.source or "").lower() == "youtube":
        return _score_youtube_article(article)

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
