"""
Research Analysis Layer — анализ научных исследований.

Единая точка импорта для компонентов Research Analysis:
- passport_builder: создание ResearchPassport
- claim_extractor: извлечение ScientificClaim
- evidence_classifier: тип исследования и сила доказательств
- text_extractors: утилиты извлечения из текста
"""

from intelligence.research_analysis.passport_builder import (
    build_research_passport,
)

from intelligence.research_analysis.claim_extractor import (
    extract_scientific_claims,
)

from intelligence.research_analysis.evidence_classifier import (
    detect_study_type,
    classify_evidence_strength,
    is_animal_or_invitro_study,
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
