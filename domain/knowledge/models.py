"""
Domain Models — бизнес-сущности Noerra Knowledge Platform.

Эти модели представляют агрегированное знание,
а не отдельные исследования.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class TrustProfile:
    """
    Профиль доверия для KnowledgeObject.
    
    Агрегирует оценки доверия от множества
    исследований по одной теме.
    """
    
    topic: str
    
    overall_trust_score: float = 0.0
    
    trust_level: str = "unknown"  # high_trust, moderate_trust, limited_trust, low_trust
    
    evidence_count: int = 0
    
    peer_reviewed_count: int = 0
    
    high_strength_count: int = 0
    
    moderate_strength_count: int = 0
    
    weak_strength_count: int = 0
    
    contradictions_count: int = 0
    
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    confidence_factors: List[str] = field(default_factory=list)
    
    caution_factors: List[str] = field(default_factory=list)
    
    def update_trust_level(self) -> None:
        """Вычисляет trust_level на основе overall_trust_score."""
        if self.overall_trust_score >= 0.8:
            self.trust_level = "high_trust"
        elif self.overall_trust_score >= 0.6:
            self.trust_level = "moderate_trust"
        elif self.overall_trust_score >= 0.4:
            self.trust_level = "limited_trust"
        else:
            self.trust_level = "low_trust"
    
    def add_confidence_factor(self, factor: str) -> None:
        if factor not in self.confidence_factors:
            self.confidence_factors.append(factor)
    
    def add_caution_factor(self, factor: str) -> None:
        if factor not in self.caution_factors:
            self.caution_factors.append(factor)


@dataclass
class KnowledgeObject:
    """
    Объект знания — агрегированное представление
    научного понимания по одной теме.
    
    Это центральная сущность Noerra,
    которая объединяет:
    - множество научных утверждений (ScientificClaim)
    - оценки доверия (TrustProfile)
    - понимание (UnderstandingModel)
    - историю изменений (KnowledgeVersion)
    """
    
    topic: str
    
    topic_ru: str = ""
    
    summary: str = ""
    
    trust_profile: Optional[TrustProfile] = None
    
    key_claims: List[str] = field(default_factory=list)
    
    consensus_points: List[str] = field(default_factory=list)
    
    open_questions: List[str] = field(default_factory=list)
    
    myths: List[str] = field(default_factory=list)
    
    practical_implications: List[str] = field(default_factory=list)
    
    related_topics: List[str] = field(default_factory=list)
    
    version: str = "1.0"
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    status: str = "active"  # active, archived, under_review
    
    def update_version(self) -> None:
        """Increments minor version on update."""
        parts = self.version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        self.version = f"{major}.{minor + 1}"
        self.updated_at = datetime.now().isoformat()
    
    def get_trust_summary(self) -> str:
        """Возвращает краткую сводку доверия."""
        if not self.trust_profile:
            return "Trust profile not available."
        tp = self.trust_profile
        return (
            f"Trust: {tp.trust_level} ({tp.overall_trust_score:.2f}) | "
            f"Evidence: {tp.evidence_count} studies | "
            f"Peer-reviewed: {tp.peer_reviewed_count} | "
            f"Contradictions: {tp.contradictions_count}"
        )
    
    def get_knowledge_summary(self) -> str:
        """Возвращает краткую сводку знания."""
        return (
            f"Topic: {self.topic_ru} ({self.topic}) | "
            f"Claims: {len(self.key_claims)} | "
            f"Consensus: {len(self.consensus_points)} | "
            f"Open questions: {len(self.open_questions)} | "
            f"Version: {self.version}"
        )


@dataclass
class KnowledgeVersion:
    """
    Версия KnowledgeObject.
    
    Сохраняет историю изменений
    для отслеживания эволюции знания.
    """
    
    knowledge_object_id: str  # topic
    
    version: str
    
    summary: str
    
    changed_because: str = ""
    
    changed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    changed_by: str = "system"  # system, editor, auto_update
    
    key_claims_snapshot: List[str] = field(default_factory=list)
    
    trust_score_snapshot: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "knowledge_object_id": self.knowledge_object_id,
            "version": self.version,
            "summary": self.summary,
            "changed_because": self.changed_because,
            "changed_at": self.changed_at,
            "changed_by": self.changed_by,
            "key_claims_snapshot": self.key_claims_snapshot,
            "trust_score_snapshot": self.trust_score_snapshot,
        }


@dataclass
class Publication:
    """
    Публикация — представление KnowledgeObject
    для конечного пользователя.
    
    Содержит адаптированный текст,
    форматированный для Telegram/Web.
    """
    
    topic: str
    
    title: str
    
    lead: str  # краткое введение (1-2 предложения)
    
    body: str  # основной текст
    
    short_version: str  # для Telegram (до 1000 символов)
    
    full_version: str  # для Web/Telegraph
    
    sources: List[str] = field(default_factory=list)
    
    key_takeaways: List[str] = field(default_factory=list)
    
    caveats: List[str] = field(default_factory=list)
    
    trust_level: str = "unknown"
    
    confidence_score: float = 0.0
    
    publication_date: str = field(default_factory=lambda: datetime.now().isoformat())
    
    platform: str = "telegram"  # telegram, web, api
    
    status: str = "draft"  # draft, published, archived
    
    def to_telegram_text(self) -> str:
        """Форматирует публикацию для Telegram."""
        return (
            f"📚 <b>{self.title}</b>\n\n"
            f"{self.lead}\n\n"
            f"{self.short_version}\n\n"
            f"🔍 <b>Доверие:</b> {self.trust_level} ({self.confidence_score:.2f})\n"
            f"📎 <b>Источники:</b> {len(self.sources)} исследований"
        )
    
    def to_web_html(self) -> str:
        """Форматирует публикацию для Web."""
        return f"""
<article>
    <h1>{self.title}</h1>
    <p class="lead">{self.lead}</p>
    <div class="body">{self.body}</div>
    <div class="trust">
        <strong>Trust Level:</strong> {self.trust_level} ({self.confidence_score:.2f})
    </div>
    <div class="sources">
        <h3>Sources</h3>
        <ul>{"".join(f"<li>{s}</li>" for s in self.sources)}</ul>
    </div>
    <div class="takeaways">
        <h3>Key Takeaways</h3>
        <ul>{"".join(f"<li>{t}</li>" for t in self.key_takeaways)}</ul>
    </div>
    {f'<div class="caveats"><h3>Caveats</h3><ul>{"".join(f"<li>{c}</li>" for c in self.caveats)}</ul></div>' if self.caveats else ''}
</article>
"""