"""Reader Question (EDITORIAL_ENGINE.md, Stage 3).

До написания статьи должен быть сформулирован главный человеческий
вопрос — статья строится вокруг него, а не вокруг исследования.
Ключи словаря — те же сценарии, что и в editorial_engine.Scenario.
"""

from adaptation.text_patterns import _pick

QUESTION_PATTERNS: dict[str, list[str]] = {
    "discovery": [
        "Что нового узнали учёные о {topic_prep_lower}?",
        "Почему это меняет взгляд на {topic_acc_lower}?",
        "Что именно обнаружили в новом исследовании {topic_gen_lower}?",
    ],
    "confirmation": [
        "Насколько можно доверять тому, что мы уже знали о {topic_prep_lower}?",
        "Почему это подтверждение о {topic_prep_lower} вообще важно?",
    ],
    "debunk": [
        "Правда ли то, что принято считать про {topic_acc_lower}?",
        "Почему привычное представление о {topic_prep_lower} может быть неточным?",
    ],
    "practical": [
        "Как это можно применить в жизни, если речь о {topic_prep_lower}?",
        "Что конкретно можно сделать уже сегодня, зная это о {topic_prep_lower}?",
    ],
    "discussion": [
        "Где в споре о {topic_prep_lower} правда?",
        "Почему учёные до сих пор расходятся во мнениях о {topic_prep_lower}?",
    ],
    "review": [
        "Что важно знать о {topic_prep_lower} прямо сейчас?",
        "Что изменилось в понимании {topic_gen_lower} за последнее время?",
    ],
    "explanation": [
        "Как именно работает {topic_nom_lower}?",
        "Почему {topic_nom_lower} устроен именно так?",
    ],
}


def build_reader_question(topic: str, scenario: str) -> str:
    """Строит человеческий вопрос, вокруг которого строится статья."""
    patterns = QUESTION_PATTERNS.get(scenario, QUESTION_PATTERNS["discovery"])
    return _pick(patterns, topic=topic)
