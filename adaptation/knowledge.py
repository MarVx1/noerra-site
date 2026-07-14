from dataclasses import dataclass, asdict
from typing import List, Dict
import re
from database import db


@dataclass
class KnowledgeContext:
    related_works: List[Dict]
    previous_findings: List[str]
    contradictions: List[str]
    consensus: List[str]
    open_questions: List[str]


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 3]


def _similarity(text_a: str, text_b: str) -> float:
    """Доля общих слов (Jaccard) — насколько статьи говорят об одном и том же."""
    a, b = set(_tokenize(text_a)), set(_tokenize(text_b))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Ниже этого порога работа не считается близкой. Раньше порога не было
# вовсе: в "ближайшие работы" попадали первые статьи из той же темы, без
# какой-либо проверки на схожесть. В статье про стрессоустойчивость
# человека это давало "Стресс при отъеме ... у свиней" (обе статьи в
# корзине "stress"), а одни и те же работы кочевали из статьи в статью.
MIN_RELATEDNESS = 0.06


def build_knowledge_context(topic: str, article=None, limit: int = 5) -> KnowledgeContext:
    """Build a lightweight knowledge context for a topic/article using DB heuristics."""
    related = []
    previous = []
    contradictions = []
    consensus = []
    open_q = []

    try:
        # Берём с запасом — дальше отранжируем по схожести и отсечём далёкие.
        candidates = db.get_articles_by_topic(topic, limit=limit * 5, min_score=10, status="new")
    except Exception:
        candidates = []

    article_text = ""
    if article is not None:
        article_text = f"{getattr(article, 'title', '')} {getattr(article, 'abstract', '') or ''}"

    scored = []
    for row in candidates:
        if article and getattr(article, "url", None) and row["url"] == article.url:
            continue
        if not article_text:
            scored.append((0.0, row))
            continue
        candidate_text = f"{row['title']} {row['abstract'] or ''}"
        score = _similarity(article_text, candidate_text)
        if score >= MIN_RELATEDNESS:
            scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    for _score, row in scored[:limit]:
        title = row["title"]
        url = row["url"]
        source = row["source"] or ""
        abstract = row["abstract"] or ""

        related.append({"title": title, "url": url, "source": source})
        if re.search(r"not|contradict|oppose|вопреки|опроверг|не поддерж", abstract, re.I):
            contradictions.append(title)
        if re.search(r"confirm|support|подтверд|replicate|consistent|agreement|reproduce", abstract, re.I):
            previous.append(title)
        if re.search(r"further|unknown|require|требует|неизвестно|дальше|будущее|future", abstract, re.I):
            open_q.append(title)

    if len(previous) >= 2:
        consensus = previous[:3]
    elif len(previous) == 1 and len(contradictions) == 0:
        consensus = previous[:1]

    return KnowledgeContext(
        related_works=related,
        previous_findings=previous,
        contradictions=contradictions,
        consensus=consensus,
        open_questions=open_q,
    )
