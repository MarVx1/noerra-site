from dataclasses import dataclass, field


@dataclass
class ResearchPassport:
    """
    Паспорт научного исследования.

    Основная доменная сущность Noerra.
    Содержит информацию об исследовании,
    его качестве и уровне доверия.
    """

    article_id: int

    title: str
    url: str
    source: str
    topic: str

    doi: str = ""

    authors: list[str] = field(
        default_factory=list
    )

    journal: str = ""

    published_at: str = ""

    study_type: str = "unknown"

    peer_reviewed: bool = False

    sample_size: str = ""

    methodology: str = ""

    limitations: str = ""

    practical_value: str = ""

    evidence_strength: str = "limited"

    key_findings: list[str] = field(
        default_factory=list
    )

    trust_level: float = 0.0



@dataclass
class ScientificClaim:
    """
    Научное утверждение,
    извлечённое из исследования.

    В будущем будет использоваться
    для Knowledge Graph.
    """

    claim_text: str

    topic: str

    relation: str = "supports"

    confidence: float = 0.5

    reasoning: str = ""