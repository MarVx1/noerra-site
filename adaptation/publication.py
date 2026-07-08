from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Publication:
    title: str
    subtitle: Optional[str]
    lead: str
    body: str
    short_version: str
    full_version: str
    sources: List[str]
    topic: str
    format: str
    confidence_score: float
    audience: str
    editor_notes: Optional[List[str]] = None
    knowledge_context: Optional[dict] = None
    story_angle: Optional[str] = None
    suggested_format: Optional[str] = None
    tone: Optional[str] = None
