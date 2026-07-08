"""Knowledge Audit & Confidence Drift tracking."""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any
from database import db

logger = logging.getLogger(__name__)


@dataclass
class TopicAudit:
    topic: str
    claims_count: int
    consensus_level: str
    confidence: float
    last_updated: str
    is_stale: bool
    has_contradictions: bool
    open_questions_count: int
    myths_count: int
    recommendation: str = ""


@dataclass
class ConfidenceDrift:
    topic: str
    claim_text: str
    previous_confidence: float
    current_confidence: float
    direction: str  # "increased", "decreased", "stable"
    delta: float
    recommendation: str = ""


def audit_topic(topic: str, stale_days: int = 30) -> TopicAudit:
    claims = db.get_claims_for_topic(topic, limit=50)
    consensus = db.get_consensus_for_topic(topic, limit=50)
    open_qs = db.get_open_questions(topic, limit=50)
    myths = db.get_myths(topic, limit=50)
    latest_version = db.get_latest_knowledge_version(topic)

    claims_count = len(claims)
    has_contradictions = any(
        (cs.get("contradict_count", 0) if isinstance(cs, dict) else cs["contradict_count"]) > 0
        for cs in consensus
    )
    avg_confidence = 0.0
    consensus_level = "insufficient_data"
    if consensus:
        confidences = [
            float(cs.get("confidence", 0) if isinstance(cs, dict) else cs["confidence"])
            for cs in consensus
        ]
        avg_confidence = sum(confidences) / len(confidences)
        latest = consensus[-1] if isinstance(consensus[-1], dict) else dict(consensus[-1])
        consensus_level = latest.get("consensus_level", "insufficient_data")

    last_updated = latest_version["created_at"] if latest_version else "never"
    is_stale = _check_stale(last_updated, stale_days)

    recommendation = _build_recommendation(
        is_stale, has_contradictions, claims_count, avg_confidence, len(open_qs)
    )

    return TopicAudit(
        topic=topic,
        claims_count=claims_count,
        consensus_level=consensus_level,
        confidence=round(avg_confidence, 2),
        last_updated=str(last_updated),
        is_stale=is_stale,
        has_contradictions=has_contradictions,
        open_questions_count=len(open_qs),
        myths_count=len(myths),
        recommendation=recommendation,
    )


def audit_all_topics(stale_days: int = 30) -> List[TopicAudit]:
    all_claims = db.execute_query(
        "SELECT DISTINCT topic FROM scientific_claims WHERE status = 'active'"
    )
    topics = [row["topic"] for row in all_claims if row["topic"]]
    audits = []
    for topic in topics:
        try:
            audits.append(audit_topic(topic, stale_days))
        except Exception as e:
            logger.error(f"Audit failed for topic {topic}: {e}")
    return audits


def detect_stale_topics(stale_days: int = 30) -> List[str]:
    audits = audit_all_topics(stale_days)
    return [a.topic for a in audits if a.is_stale]


def detect_contradicted_topics() -> List[str]:
    audits = audit_all_topics()
    return [a.topic for a in audits if a.has_contradictions]


def track_confidence_drift(topic: str) -> List[ConfidenceDrift]:
    consensus_rows = db.get_consensus_for_topic(topic, limit=100)
    if len(consensus_rows) < 2:
        return []

    drifts: List[ConfidenceDrift] = []
    claims = {row["id"]: row for row in db.get_claims_for_topic(topic, limit=100)}

    # Group consensus states by claim_id, ordered by version
    by_claim: Dict[int, list] = {}
    for cs in consensus_rows:
        claim_id = cs["claim_id"]
        by_claim.setdefault(claim_id, []).append(cs)

    for claim_id, states in by_claim.items():
        if len(states) < 2:
            continue
        states_sorted = sorted(states, key=lambda s: s["version"])
        prev = states_sorted[-2]
        curr = states_sorted[-1]

        prev_conf = float(prev["confidence"] or 0)
        curr_conf = float(curr["confidence"] or 0)
        delta = round(curr_conf - prev_conf, 2)

        if abs(delta) < 0.05:
            direction = "stable"
            rec = "Confidence is stable."
        elif delta > 0:
            direction = "increased"
            rec = "Confidence has increased; consider updating the understanding model."
        else:
            direction = "decreased"
            rec = "Confidence has decreased; review contradicting evidence."

        claim_text = claims.get(claim_id, {}).get("claim_text", f"claim #{claim_id}")

        drifts.append(ConfidenceDrift(
            topic=topic,
            claim_text=claim_text,
            previous_confidence=prev_conf,
            current_confidence=curr_conf,
            direction=direction,
            delta=delta,
            recommendation=rec,
        ))

    return drifts


def detect_knowledge_debt(stale_days: int = 30) -> List[Dict[str, Any]]:
    """Find topics with many new articles but no recent knowledge updates."""
    recent_articles = db.execute_query(
        """SELECT topic, COUNT(*) as cnt
           FROM articles
           WHERE created_at >= datetime('now', ?)
             AND status NOT IN ('off_topic', 'low_score')
           GROUP BY topic
           HAVING cnt > 3
           ORDER BY cnt DESC""",
        (f"-{stale_days} days",),
    )

    debt = []
    for row in recent_articles:
        topic = row["topic"]
        latest = db.get_latest_knowledge_version(topic)
        is_stale = _check_stale(latest["created_at"], stale_days) if latest else True
        if is_stale:
            debt.append({
                "topic": topic,
                "new_articles": row["cnt"],
                "last_knowledge_update": latest["created_at"] if latest else "never",
            })
    return debt


def _check_stale(last_updated: str, stale_days: int) -> bool:
    if not last_updated or last_updated == "never":
        return True
    try:
        from database.db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT julianday('now') - julianday(?) as diff",
                (last_updated,),
            ).fetchone()
            return row["diff"] > stale_days
    except Exception:
        return False


def _build_recommendation(
    is_stale: bool,
    has_contradictions: bool,
    claims_count: int,
    confidence: float,
    open_questions: int,
) -> str:
    parts = []
    if is_stale:
        parts.append("Topic is stale — consider updating the understanding model.")
    if has_contradictions:
        parts.append("Contradictions detected — review contradicting evidence.")
    if claims_count == 0:
        parts.append("No claims extracted — check parser/classifier.")
    if confidence < 0.4:
        parts.append("Low overall confidence — more research needed.")
    if open_questions > 5:
        parts.append("Many open questions — consider a focused review.")
    if not parts:
        parts.append("Topic is in good shape.")
    return " ".join(parts)
