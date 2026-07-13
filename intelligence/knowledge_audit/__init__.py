"""
Knowledge Audit — аналитический слой аудита знаний.

Единая точка импорта для компонентов Knowledge Audit.
"""

from intelligence.knowledge_audit.audit_engine import (
    TopicAudit,
    ConfidenceDrift,
    audit_topic,
    audit_all_topics,
    detect_stale_topics,
    detect_contradicted_topics,
    track_confidence_drift,
    detect_knowledge_debt,
    _build_recommendation,
)
