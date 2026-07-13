"""Общие примитивы подстановки шаблонов с падежами темы.

Вынесено из editorial_engine.py, чтобы им могли пользоваться и другие
модули (reader_question.py, analogy_bank.py) без обратного импорта из
editorial_engine.py.
"""

import random
import re

from classifier.classifier import get_topic_case


def _pick(patterns: list[str], topic: str = "", **kwargs) -> str:
    """Выбирает случайный шаблон и подставляет падежные формы темы.

    topic — английский ключ темы (например, 'dopamine'), по нему
    определяются падежные формы через get_topic_case().
    """
    template = random.choice(patterns)
    if not topic:
        return template.format(**kwargs)
    # Подставляем все падежные формы
    fmt_kwargs = {
        "topic_nom": get_topic_case(topic, "nom"),
        "topic_gen": get_topic_case(topic, "gen"),
        "topic_dat": get_topic_case(topic, "dat"),
        "topic_acc": get_topic_case(topic, "acc"),
        "topic_inst": get_topic_case(topic, "inst"),
        "topic_prep": get_topic_case(topic, "prep"),
        "topic_nom_lower": get_topic_case(topic, "nom_lower"),
        "topic_gen_lower": get_topic_case(topic, "gen_lower"),
        "topic_dat_lower": get_topic_case(topic, "dat_lower"),
        "topic_acc_lower": get_topic_case(topic, "acc_lower"),
        "topic_inst_lower": get_topic_case(topic, "inst_lower"),
        "topic_prep_lower": get_topic_case(topic, "prep_lower"),
    }
    fmt_kwargs.update(kwargs)
    result = template.format(**fmt_kwargs)
    # Авто-fix предлогов: "с " → "со " перед стечением согласных (со стрессом, со сном)
    result = re.sub(r'\bс (стр|спл|ств|скл|смн|сн)', r'со \1', result, flags=re.IGNORECASE)
    return result
