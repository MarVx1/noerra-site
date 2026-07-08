"""
Text extraction utilities.

Набор функций для извлечения
структурированной информации из текста.
"""

import re



def extract_key_findings(
    text: str
) -> list[str]:
    """
    Извлекает основные результаты
    исследования.
    """

    sentences = split_sentences(text)


    result_markers = (
        "found",
        "show",
        "demonstrat",
        "suggest",
        "indicat",

        "показ",
        "выяв",
        "обнаруж",
    )


    findings = [
        sentence
        for sentence in sentences
        if any(
            marker in sentence.lower()
            for marker in result_markers
        )
    ]


    return findings[:3] or sentences[:1]



def extract_doi(
    text: str
) -> str:
    """
    Извлечение DOI статьи.
    """

    match = re.search(
        r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
        text,
        flags=re.IGNORECASE
    )


    return (
        match.group(0)
        if match
        else ""
    )



def extract_sample_size(
    text: str
) -> str:
    """
    Поиск размера выборки.
    """

    match = re.search(
        r"\b(?:n\s*=\s*|sample(?: size)?(?: of)?\s+)(\d{2,7})\b",
        text,
        flags=re.IGNORECASE
    )


    return (
        match.group(1)
        if match
        else ""
    )



def extract_limitations(
    text: str
) -> str:
    """
    Поиск ограничений исследования.
    """

    sentences = split_sentences(text)


    for sentence in sentences:

        lower = sentence.lower()


        if any(
            marker in lower
            for marker in (
                "limitation",
                "limited by",
                "огранич",
                "недостат",
            )
        ):

            return sentence


    return ""



def extract_practical_value(
    text: str
) -> str:
    """
    Поиск практического значения.
    """

    sentences = split_sentences(text)


    for sentence in sentences:

        lower = sentence.lower()


        if any(
            marker in lower
            for marker in (
                "clinical",
                "therapy",
                "intervention",
                "practice",
                "treatment",

                "лечение",
                "практик",
                "терап",
            )
        ):

            return sentence


    return ""



def normalize_claim(
    text: str
) -> str:
    """
    Нормализация текста утверждения.
    """

    return re.sub(
        r"\s+",
        " ",
        text.strip().lower()
    )



def split_sentences(
    text: str
) -> list[str]:
    """
    Разделение текста на предложения.
    """

    return [
        sentence.strip()

        for sentence in re.split(
            r"(?<=[.!?])\s+",
            text or ""
        )

        if sentence.strip()
    ]