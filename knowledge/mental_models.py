"""Mental Models: correct understanding frameworks for each topic."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class MentalModel:
    topic: str
    topic_ru: str
    title: str
    correct_understanding: str
    common_misconception: str
    key_concepts: List[str]
    explanation: str
    practical_implication: str
    sources: List[str] = field(default_factory=list)


MENTAL_MODELS: Dict[str, MentalModel] = {
    "dopamine": MentalModel(
        topic="dopamine",
        topic_ru="Дофамин",
        title="Дофамин — система прогнозирования, а не удовольствия",
        correct_understanding=(
            "Дофамин — это нейромедиатор, который кодирует разницу между ожидаемым и "
            "полученным вознаграждением (prediction error). Он участвует в обучении, "
            "мотивации и принятии решений, а не просто в получении удовольствия."
        ),
        common_misconception="Дофамин — гормон удовольствия. Чем его больше, тем лучше.",
        key_concepts=["prediction error", "reward learning", "motivation", "nucleus accumbens", "reinforcement"],
        explanation=(
            "Современная нейронаука рассматривает дофамин как сигнал ошибки прогнозирования: "
            "он выделяется, когда результат лучше ожидаемого, и подавляется, когда хуже. "
            "Это делает его ключевым механизмом обучения, а не просто источником радости."
        ),
        practical_implication=(
            "Понимание дофамина помогает объяснить, почему непредсказуемые награды "
            "сильнее мотивируют, чем предсказуемые, и почему привычки формируются "
            "через повторение связанных с вознаграждением действий."
        ),
        sources=["Schultz 2016", "Wise 2004"],
    ),
    "sleep": MentalModel(
        topic="sleep",
        topic_ru="Сон",
        title="Сон — активный процесс консолидации, а не просто отдых",
        correct_understanding=(
            "Сон — это не пассивное состояние, а активный процесс, в котором мозг "
            "консолидирует память, очищает метаболические отходы и регулирует эмоции. "
            "Недостаток сна влияет на когнитивные функции, настроение и здоровье."
        ),
        common_misconception="Сон — это просто отдых. Можно спать меньше и работать больше.",
        key_concepts=["REM", "slow-wave sleep", "memory consolidation", "circadian rhythm", "glymphatic system"],
        explanation=(
            "Во время медленного сна происходит консолидация декларативной памяти, "
            "а во время REM — процедурной и эмоциональной. Глимфатическая система "
            "очищает мозг от метаболических отходов, включая бета-амилоид."
        ),
        practical_implication=(
            "Качественный сон 7-9 часов — это не роскошь, а необходимость для "
            "памяти, настроения и долгосрочного здоровья мозга."
        ),
        sources=["Walker 2017", "Diekelmann 2010"],
    ),
    "ADHD": MentalModel(
        topic="ADHD",
        topic_ru="СДВГ",
        title="СДВГ — нейробиологическое различие, а не лень",
        correct_understanding=(
            "СДВГ — это нейробиологическое расстройство с изменениями в префронтальной "
            "коре, стриатуме и дофаминовой системе. Оно влияет на исполнительные функции: "
            "рабочую память, торможение импульсов и планирование."
        ),
        common_misconception="СДВГ — это просто лень или невоспитанность. Нужно просто стараться.",
        key_concepts=["executive function", "working memory", "prefrontal cortex", "dopamine", "inhibition"],
        explanation=(
            "Мозг при СДВГ имеет структурные и функциональные отличия: сниженная "
            "активность префронтальной коры и изменения в дофаминовых путях. "
            "Это влияет на способность удерживать внимание и подавлять импульсы."
        ),
        practical_implication=(
            "Понимание СДВГ как нейробиологического различия снижает стигму и "
            "позволяет применять научно обоснованные стратегии: структуру среды, "
            "медикаментозную поддержку и поведенческие методы."
        ),
        sources=["Barkley 2015", "Faraone 2015"],
    ),
    "stress": MentalModel(
        topic="stress",
        topic_ru="Стресс",
        title="Стресс — не всегда враг, но хронический стресс меняет мозг",
        correct_understanding=(
            "Острый стресс — нормальная адаптивная реакция через HPA-ось и кортизол. "
            "Хронический стресс приводит к структурным изменениям мозга: уменьшению "
            "гиппокампа, увеличению амигдалы и нарушению префронтальной коры."
        ),
        common_misconception="Стресс — это только психологическая проблема. Нужно просто расслабиться.",
        key_concepts=["HPA axis", "cortisol", "hippocampus", "amygdala", "allostatic load"],
        explanation=(
            "Хронический стресс поддерживает высокий уровень кортизола, что повреждает "
            "гиппокамп (память) и усиливает реактивность амигдалы (страх). "
            "Префронтальная кора теряет способность тормозить стресс-реакцию."
        ),
        practical_implication=(
            "Управление стрессом — это не роскошь, а защита мозга. "
            "Регулярная физическая активность, сон и социальная поддержка "
            "доказанно снижают аллостатическую нагрузку."
        ),
        sources=["McEwen 2017", "Lupien 2009"],
    ),
    "neuroplasticity": MentalModel(
        topic="neuroplasticity",
        topic_ru="Нейропластичность",
        title="Мозг меняется всю жизнь, но не мгновенно",
        correct_understanding=(
            "Нейропластичность — способность мозга менять структуру и связи в ответ "
            "на опыт. Она работает через LTP, нейрогенез и синаптическую перестройку. "
            "Изменения требуют повторения и времени, а не одного усилия."
        ),
        common_misconception="Мозг пластичен — значит, можно быстро изменить любую привычку.",
        key_concepts=["LTP", "neurogenesis", "synaptic plasticity", "hippocampus", "repetition"],
        explanation=(
            "Долговременная потенциация (LTP) усиливает связи между нейронами при "
            "повторной активации. Нейрогенез в гиппокампе поддерживается обучением "
            "и физической активностью, но замедляется с возрастом."
        ),
        practical_implication=(
            "Изменение привычек требует повторения в течение недель, а не дней. "
            "Физическая активность и обучение новым навыкам поддерживают "
            "нейропластичность в любом возрасте."
        ),
        sources=["Doidge 2007", "Erickson 2014"],
    ),
    "anxiety": MentalModel(
        topic="anxiety",
        topic_ru="Тревожность",
        title="Тревожность — это физиологическая реакция, а не слабость",
        correct_understanding=(
            "Тревожность — это реакция амигдалы на угрозу, модулируемая префронтальной корой. "
            "Хроническая тревожность усиливает реактивность амигдалы и ослабляет "
            "тормозный контроль префронтальной коры."
        ),
        common_misconception="Тревожность — это просто нервозность. Нужно просто успокоиться.",
        key_concepts=["amygdala", "prefrontal cortex", "fear conditioning", "GABA", "HPA axis"],
        explanation=(
            "Амигдала активируется при угрозе, запуская физиологическую реакцию. "
            "При хронической тревожности префронтальная кора теряет способность "
            "тормозить амигдалу, создавая порочный круг."
        ),
        practical_implication=(
            "Когнитивно-поведенческая терапия, экспозиция и медикаменты "
            "доказанно восстанавливают тормозный контроль префронтальной коры "
            "над амигдалой."
        ),
        sources=["LeDoux 2015", "Shin 2016"],
    ),
}


def get_mental_model(topic: str) -> Optional[MentalModel]:
    return MENTAL_MODELS.get(topic)


def list_mental_models() -> List[Dict[str, str]]:
    return [
        {"topic": m.topic, "topic_ru": m.topic_ru, "title": m.title}
        for m in MENTAL_MODELS.values()
    ]


def model_to_text(model: MentalModel) -> str:
    lines = [
        f"🧩 <b>Модель понимания: {model.topic_ru}</b>",
        f"<b>{model.title}</b>\n",
        f"<b>Правильное понимание:</b>\n{model.correct_understanding}\n",
        f"<b>Распространённое заблуждение:</b>\n{model.common_misconception}\n",
        f"<b>Ключевые концепции:</b> {', '.join(model.key_concepts)}\n",
        f"<b>Объяснение:</b>\n{model.explanation}\n",
        f"<b>Практический вывод:</b>\n{model.practical_implication}\n",
    ]
    if model.sources:
        lines.append(f"<b>Источники:</b> {', '.join(model.sources)}")
    return "\n".join(lines)


def get_model_brief(topic: str) -> str:
    """Short version for inclusion in cluster posts."""
    model = get_mental_model(topic)
    if not model:
        return ""
    return (
        f"🧩 <b>Как это понимать:</b> {model.correct_understanding[:200]}..."
        if len(model.correct_understanding) > 200
        else f"🧩 <b>Как это понимать:</b> {model.correct_understanding}"
    )
