"""
Domain Knowledge — доменные сущности Noerra.

Единая точка импорта для доменных сущностей knowledge domain.
"""

from domain.knowledge.entities import (
    ResearchPassport,
    ScientificClaim,
)

from domain.knowledge.models import (
    TrustProfile,
    KnowledgeObject,
    KnowledgeVersion as KnowledgeObjectVersion,
    Publication,
)