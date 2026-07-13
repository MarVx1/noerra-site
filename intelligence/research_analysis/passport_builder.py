from parsers.base import RawArticle

from domain.knowledge.entities import ResearchPassport

from intelligence.research_analysis.evidence_classifier import (
    detect_study_type,
    classify_evidence_strength,
)

from intelligence.research_analysis.text_extractors import (
    extract_doi,
    extract_sample_size,
    extract_limitations,
    extract_practical_value,
    extract_key_findings,
)

from intelligence.trust_engine.trust_assessor import assess_trust



def build_research_passport(
    article: RawArticle,
    topic: str,
    article_id: int
) -> ResearchPassport:
    """
    Создание ResearchPassport
    из необработанной статьи.

    Это основной сервисный слой
    анализа исследования.
    """


    text = (
        f"{article.title} "
        f"{article.abstract or ''}"
    )


    # Определяем тип исследования. Заголовок передаётся отдельно: он имеет
    # приоритет, иначе обзор RCT определяется как сам RCT.
    study_type = detect_study_type(text, title=article.title or "")


    # Определяем уровень доказательности
    evidence_strength = classify_evidence_strength(
        study_type,
        article.is_peer_reviewed
    )


    # Извлекаем ключевые результаты
    findings = extract_key_findings(
        article.abstract or article.title
    )


    # Размер выборки
    sample_size = extract_sample_size(text)


    # Ограничения исследования
    limitations = extract_limitations(text)


    # Оценка доверия
    trust = assess_trust(
        evidence_strength=evidence_strength,
        peer_reviewed=article.is_peer_reviewed,
        has_limitations=bool(limitations),
        has_sample_size=bool(sample_size),
    )


    return ResearchPassport(

        article_id=article_id,

        title=article.title,

        url=article.url,

        source=article.source,

        topic=topic,


        doi=extract_doi(text),


        authors=article.authors,


        published_at=article.published,


        study_type=study_type,


        peer_reviewed=article.is_peer_reviewed,


        sample_size=sample_size,


        methodology=study_type,


        limitations=limitations,


        practical_value=extract_practical_value(text),


        evidence_strength=evidence_strength,


        key_findings=findings,


        trust_level=trust.score,
    )