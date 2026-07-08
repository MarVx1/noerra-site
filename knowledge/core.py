"""
Legacy compatibility module.

Новая логика находится:

domain/
intelligence/

"""

from domain.knowledge.entities import (
    ResearchPassport,
    ScientificClaim,
)


from intelligence.research_analysis.passport_builder import (
    build_research_passport,
)


from intelligence.research_analysis.claim_extractor import (
    extract_scientific_claims,
)


from intelligence.research_analysis.evidence_classifier import (
    detect_study_type,
    classify_evidence_strength,
)


from intelligence.research_analysis.text_extractors import (
    extract_key_findings,
    extract_doi,
    extract_sample_size,
    extract_limitations,
    extract_practical_value,
    normalize_claim,
    split_sentences,
)