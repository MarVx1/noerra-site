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


def build_knowledge_context(topic: str, article=None, limit: int = 5) -> KnowledgeContext:
    """Build a lightweight knowledge context for a topic/article using DB heuristics."""
    related = []
    previous = []
    contradictions = []
    consensus = []
    open_q = []

    try:
        candidates = db.get_articles_by_topic(topic, limit=limit, min_score=10, status="new")
    except Exception:
        candidates = []

    for row in candidates:
        if article and getattr(article, "url", None) and row["url"] == article.url:
            continue

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
