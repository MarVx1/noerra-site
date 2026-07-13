import logging
from datetime import datetime
from database import db
from domain.knowledge.living import (
    build_knowledge_summary,
    detect_open_questions,
    detect_myths_from_contradictions,
)
from domain.knowledge.understanding import build_understanding_model
from classifier.classifier import get_topic_ru

logger = logging.getLogger(__name__)


def update_topic_knowledge(topic: str) -> None:
    claims_rows = db.get_claims_for_topic(topic, limit=50)
    consensus_rows = db.get_consensus_for_topic(topic, limit=50)

    if not claims_rows:
        logger.debug(f"No claims for topic {topic}, skipping knowledge update.")
        return

    claims = [dict(row) for row in claims_rows]
    consensus = [dict(row) for row in consensus_rows]

    open_questions = detect_open_questions(claims, consensus)
    myths = detect_myths_from_contradictions(claims, consensus)

    for q in open_questions:
        existing = db.get_open_questions(topic, limit=100)
        if not any(q.question == e["question"] for e in existing):
            db.save_open_question(topic, q.question, q.status)
            logger.info(f"Saved open question for {topic}: {q.question}")

    for m in myths:
        existing = db.get_myths(topic, limit=100)
        if not any(m.myth_text == e["myth_text"] for e in existing):
            db.save_myth(topic, m.myth_text, m.correction, m.evidence_summary)
            logger.info(f"Saved myth for {topic}: {m.myth_text}")

    latest_version = db.get_latest_knowledge_version(topic)
    summary = build_knowledge_summary(claims, consensus)
    if latest_version:
        old_summary = latest_version["summary"] or ""
        if summary != old_summary:
            version_parts = latest_version["version"].split(".")
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            new_version = f"{major}.{minor + 1}"
            db.save_knowledge_version(topic, new_version, summary, "New evidence or consensus changes.")
            db.save_knowledge_diff(
                topic=topic,
                from_version=latest_version["version"],
                to_version=new_version,
                before_text=old_summary,
                after_text=summary,
                reason="New evidence or consensus changes.",
            )
            logger.info(f"Updated knowledge version for {topic}: {latest_version['version']} → {new_version}")
    else:
        db.save_knowledge_version(topic, "1.0", summary, "Initial version.")
        logger.info(f"Created initial knowledge version for {topic}: 1.0")


def update_all_topics_knowledge() -> None:
    all_claims = db.execute_query("SELECT DISTINCT topic FROM scientific_claims WHERE status = 'active'")
    topics = set(row["topic"] for row in all_claims if row["topic"])
    for topic in topics:
        try:
            update_topic_knowledge(topic)
        except Exception as e:
            logger.error(f"Failed to update knowledge for topic {topic}: {e}")


def get_understanding_for_topic(topic: str) -> dict:
    claims_rows = db.get_claims_for_topic(topic, limit=20)
    consensus_rows = db.get_consensus_for_topic(topic, limit=20)
    open_questions_rows = db.get_open_questions(topic, limit=10)
    myths_rows = db.get_myths(topic, limit=10)

    if not claims_rows:
        return {
            "topic": topic,
            "topic_ru": get_topic_ru(topic),
            "summary": "No data yet.",
            "key_claims": [],
            "consensus_points": [],
            "open_questions": [],
            "myths": [],
            "practical_implications": [],
            "confidence_level": "insufficient_data",
            "version": "0.0",
        }

    claims = [dict(row) for row in claims_rows]
    consensus = [dict(row) for row in consensus_rows]
    open_questions = [row["question"] for row in open_questions_rows]
    myths = [row["myth_text"] for row in myths_rows]

    model = build_understanding_model(
        topic=topic,
        topic_ru=get_topic_ru(topic),
        claims=claims,
        consensus_states=consensus,
        open_questions=open_questions,
        myths=myths,
    )

    return {
        "topic": model.topic,
        "topic_ru": model.topic_ru,
        "summary": model.summary,
        "key_claims": model.key_claims,
        "consensus_points": model.consensus_points,
        "open_questions": model.open_questions,
        "myths": model.myths,
        "practical_implications": model.practical_implications,
        "confidence_level": model.confidence_level,
        "version": model.version,
    }
