# ============================================================
#  config/topics.py — темы, ключевые слова и веса
# ============================================================
#  Вес 3 = специфичный термин (сильный сигнал)
#  Вес 2 = тематическое слово (средний сигнал)
#  Вес 1 = общее слово (слабый сигнал)
# ============================================================

TOPIC_KEYWORDS: dict[str, dict[str, int]] = {

    "ADHD": {
        "adhd":                     3,
        "attention deficit":        3,
        "hyperactivity":            3,
        "inattention":              3,
        "executive function":       2,
        "working memory":           2,
        "methylphenidate":          3,
        "stimulant":                2,
        "attention":                1,
        "focus":                    1,
        "сдвг":                     3,
        "синдром дефицита":         3,
        "гиперактивность":          3,
    },

    "dopamine": {
        "dopamine":                 3,
        "dopaminergic":             3,
        "reward":                   2,
        "motivation":               2,
        "nucleus accumbens":        3,
        "mesolimbic":               3,
        "striatum":                 2,
        "reinforcement":            2,
        "pleasure":                 1,
        "дофамин":                  3,
        "вознаграждение":           2,
        "мотивация":                1,
    },

    "sleep": {
        "sleep":                    3,
        "circadian":                3,
        "insomnia":                 3,
        # Не голое "rem": как подстрока оно ловило remains/remote/remember
        # (54 ложных срабатывания по базе) и уводило статью в тему "сон".
        "rem sleep":                2,
        "slow-wave":                2,
        "melatonin":                3,
        "sleep deprivation":        3,
        "sleep quality":            2,
        "chronotype":               3,
        "сон":                      3,
        "бессонница":               3,
        "циркадный":                3,
        "мелатонин":                2,
    },

    "stress": {
        "stress":                   3,
        "cortisol":                 3,
        "hpa axis":                 3,
        "allostatic":               3,
        "burnout":                  2,
        "chronic stress":           3,
        "resilience":               2,
        "стресс":                   3,
        "кортизол":                 3,
        "выгорание":                2,
        "стрессоустойчивость":      2,
    },

    "anxiety": {
        "anxiety":                  3,
        "anxious":                  2,
        "panic disorder":           3,
        "generalized anxiety":      3,
        "amygdala":                 2,
        "fear":                     2,
        "phobia":                   2,
        "тревога":                  3,
        "тревожность":              3,
        "паническое расстройство":  3,
        "фобия":                    2,
    },

    "cognition": {
        "cognition":                3,
        "cognitive":                2,
        "memory":                   2,
        "learning":                 2,
        "intelligence":             2,
        "reasoning":                2,
        "attention":                2,
        "decision making":          2,
        "когниция":                 3,
        "когнитивный":              2,
        "память":                   2,
        "обучение":                 1,
        "мышление":                 2,
    },

    "neuroplasticity": {
        "neuroplasticity":          3,
        "plasticity":               2,
        "synaptic":                 2,
        "ltp":                      3,
        "long-term potentiation":   3,
        "neurogenesis":             3,
        "dendrite":                 2,
        "axon":                     2,
        "нейропластичность":        3,
        "пластичность":             2,
        "нейрогенез":               3,
        "синаптический":            2,
    },

    "neuroscience": {
        "neuroscience":             3,
        "neurobiology":             3,
        "neural":                   2,
        "brain":                    2,
        "cortex":                   2,
        "neuron":                   2,
        "fmri":                     3,
        "eeg":                      3,
        "нейронаука":               3,
        "нейробиология":            3,
        "мозг":                     2,
        "нейрон":                   2,
        "кора головного мозга":     2,
    },

    "psychology": {
        "psychology":               3,
        "psychotherapy":            3,
        "cognitive behavioral":     3,
        "mental health":            2,
        "psychopathology":          3,
        "emotion":                  2,
        "behavior":                 2,
        "психология":               3,
        "психотерапия":             3,
        "ментальное здоровье":      2,
        "эмоции":                   1,
        "поведение":                1,
    },
}

# Слова-усилители: +4 к итоговому score независимо от темы
BOOST_KEYWORDS: list[str] = [
    "breakthrough",
    "first evidence",
    "randomized controlled",
    "meta-analysis",
    "systematic review",
    "landmark",
    "новое исследование",
    "впервые доказано",
    "клиническое исследование",
    "мета-анализ",
]

# Слова-фильтры: -5 к score (отсеивает мусор)
PENALTY_KEYWORDS: list[str] = [
    "retracted",
    "pseudoscience",
    "horoscope",
    "astrology",
    "эзотерика",
    "астрология",
    "инфоцыган",
    "erratum",
    "correction notice",
]

# Доверенные источники (влияют на scoring)
TRUSTED_SOURCES: list[str] = [
    "pubmed",
    "arxiv",
    "nature",
    "science",
    "cell",
    "cyberleninka",
    "postnauka",
    "nplus1",
]
