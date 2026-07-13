"""Ритмические переходы (EDITORIAL_ENGINE.md, Stage 10; EDITORIAL_PLAYBOOK.md,
Правило 10: "Каждые 2-3 абзаца должен происходить ритмический переход").

Rule-based ограничение: переходы — фиксированные связки, не адаптируются
под конкретное содержание соседних абзацев (в отличие от того, что мог бы
сделать редактор или LLM). Задача — избежать сухого перечисления фактов
подряд, а не подстроить переход под смысл конкретной пары абзацев.
"""

import random

# Переход от вопроса/лида к содержательной части статьи.
TRANSITION_INTO_BODY: list[str] = [
    "Вот что об этом известно.",
    "Разберёмся по порядку.",
    "Вот что удалось выяснить.",
]

# Переход от фактов к аналогии — сигнал смены регистра повествования.
TRANSITION_INTO_ANALOGY: list[str] = [
    "Чтобы это стало нагляднее, вот сравнение.",
    "Легче понять это на примере.",
    "Вот как это можно себе представить.",
]

# Переход от доказательной базы к практической/личной значимости.
TRANSITION_INTO_SIGNIFICANCE: list[str] = [
    "Но какое отношение это имеет к обычной жизни?",
    "Здесь начинается самое важное.",
    "И вот почему это касается не только учёных.",
]

_KIND_TO_BANK = {
    "into_body": TRANSITION_INTO_BODY,
    "into_analogy": TRANSITION_INTO_ANALOGY,
    "into_significance": TRANSITION_INTO_SIGNIFICANCE,
}


def build_transition(kind: str) -> str:
    """Возвращает связку по типу перехода: into_body/into_analogy/into_significance."""
    bank = _KIND_TO_BANK.get(kind)
    if not bank:
        raise ValueError(f"Unknown transition kind: {kind!r}")
    return random.choice(bank)
