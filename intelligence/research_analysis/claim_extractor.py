from parsers.base import RawArticle

from domain.knowledge.entities import ScientificClaim

from intelligence.research_analysis.text_extractors import (
    split_sentences,
)



def extract_scientific_claims(
    article: RawArticle,
    topic: str
) -> list[ScientificClaim]:
    """
    Извлекает научные утверждения
    из текста исследования.

    Результат используется
    для построения Knowledge Graph.
    """


    sentences = split_sentences(
        article.abstract or article.title
    )


    # Слова-маркеры научных результатов
    markers = (
        "found",
        "show",
        "shows",
        "showed",
        "demonstrate",
        "demonstrates",
        "suggest",
        "suggests",
        "indicate",
        "indicates",
        "associated",
        "linked",

        # русский язык
        "показ",
        "выяв",
        "свидетель",
        "связан",
        "обнаруж",
        "подтверж",
    )


    # Исключаем методологические предложения
    skip_markers = (
        "we used",
        "we conducted",
        "we performed",
        "this study aimed",
        "the aim of",
        "objective:",
        "background:",
        "methods:",

        "мы использовали",
        "целью данного",
    )


    claims: list[ScientificClaim] = []


    for sentence in sentences:

        lower = sentence.lower()


        # слишком длинное предложение
        if len(sentence) > 300:
            continue


        # пропускаем описание методов
        if any(
            skip in lower
            for skip in skip_markers
        ):
            continue


        # ищем результативные утверждения
        if any(
            marker in lower
            for marker in markers
        ):


            relation = "supports"


            # если есть отрицание
            if any(
                word in lower
                for word in (
                    "not",
                    "no ",
                    "не ",
                    "опроверг",
                )
            ):
                relation = "contradicts"



            claims.append(
                ScientificClaim(

                    claim_text=sentence.strip(),

                    topic=topic,

                    relation=relation,

                    confidence=(
                        0.65
                        if relation == "supports"
                        else 0.55
                    ),

                    reasoning=(
                        "Extracted from "
                        "result-oriented sentence "
                        "in abstract."
                    ),
                )
            )


    # Если не нашли утверждения
    # пытаемся использовать название статьи
    if not claims and article.title:


        title_lower = article.title.lower()


        skip_title_markers = (
            "a low-overhead",
            "a novel",
            "a system",
            "a framework",
            "a tool",
            "an approach",
            "a method",
            "a model",
            "introducing",
            "towards",
            "scaling",
            "efficient",
        )


        if not any(
            skip in title_lower
            for skip in skip_title_markers
        ):


            claims.append(

                ScientificClaim(

                    claim_text=
                    article.title.strip()[:200],

                    topic=topic,

                    relation="mentions",

                    confidence=0.35,

                    reasoning=(
                        "Fallback claim from title "
                        "because no result sentence "
                        "was detected."
                    ),
                )
            )


    return claims[:3]