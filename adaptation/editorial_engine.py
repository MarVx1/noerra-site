# ============================================================
#  adaptation/editorial_engine.py — независимый редакционный движок
# ============================================================

from typing import Literal
from dataclasses import asdict
from adaptation.publication import Publication
from parsers.base import RawArticle
from classifier.classifier import get_topic_ru, get_topic_case
from database import db
from adaptation.knowledge import build_knowledge_context
from intelligence.research_analysis.passport_builder import build_research_passport
from intelligence.trust_engine.trust_assessor import estimate_trust_level
from adaptation.text_patterns import _pick
from adaptation.reader_question import build_reader_question
from adaptation.analogy_bank import build_analogy
from adaptation.simplifier import simplify_text
from adaptation.transitions import build_transition
from adaptation.jargon_glossary import simplify_methodology_terms
from adaptation.utils import (
    _clean_text,
    _split_sentences,
    _translate,
    _extract_practical_sentence,
    _extract_key_sentence,
    _shorten,
    _decompose_abstract,
    _detect_numbers,
    _fix_translation,
    _strip_latin_abbreviations,
    _strip_section_labels,
    _strip_translated_section_labels,
    classify_abstract_form,
)

# Названия источников — имена собственные, поэтому остаются латиницей, но
# должны быть оформлены как бренд, а не как сырое поле из БД ("frontiers").
SOURCE_NAMES = {
    "pubmed": "PubMed",
    "arxiv": "arXiv",
    "cyberleninka": "КиберЛенинка",
    "rss": "RSS",
    "youtube": "YouTube",
    "frontiers": "Frontiers",
    "plos-one": "PLOS ONE",
    "psyarxiv": "PsyArXiv",
    "nplus1": "N+1",
    "postnauka": "ПостНаука",
    "naked-science": "Naked Science",
}

Scenario = Literal[
    "discovery",
    "confirmation",
    "debunk",
    "practical",
    "discussion",
    "review",
    "explanation",
]

# ── Паттерны с падежными формами ───────────────────────────────
# Шаблоны используют {topic_nom}, {topic_gen}, {topic_prep}, {topic_inst}
# и их _lower варианты для правильного согласования.

# Формула сильного начала (EDITORIAL_PLAYBOOK.md, Правило 1-2):
# начинать с человека, не с исследования — вопрос/парадокс/повседневная
# ситуация/неожиданный факт, а не "новое исследование показывает...".
LEAD_PATTERNS = {
    "discovery": [
        "Кажется, что про {topic_acc_lower} уже всё известно — но выясняется, что это не так.",
        "Многие воспринимают {topic_acc_lower} как что-то само собой разумеющееся, даже не задумываясь, как это устроено на самом деле.",
        # Не "как устроен {topic}": темы бывают женского рода, и получалось
        # "как устроен психология". Родительный падеж снимает согласование.
        "Есть неожиданная деталь в устройстве {topic_gen_lower}, о которой мало кто задумывается.",
    ],
    "confirmation": [
        "Кажется очевидным, как {topic_nom_lower} влияет на повседневную жизнь. Но подтвердить очевидное оказалось не так просто.",
        "То, что многие интуитивно чувствуют про {topic_acc_lower}, теперь подкреплено более надёжными данными.",
        "Догадки о {topic_prep_lower}, которые долго оставались лишь догадками, постепенно превращаются в нечто более надёжное.",
    ],
    "debunk": [
        "Кажется очевидным то, что принято думать про {topic_acc_lower}. Но всё оказывается сложнее.",
        "Почти каждый слышал расхожее мнение о {topic_prep_lower} — и почти никто не проверял, насколько оно верно.",
        "Привычное представление о {topic_prep_lower} не выдерживает более пристального взгляда.",
    ],
    "practical": [
        "Почему знания о {topic_prep_lower} так редко доходят до реальных действий?",
        "Почти каждый хотел бы применить то, что известно про {topic_acc_lower} — вопрос в том, как именно.",
        "Разобраться в {topic_prep_lower} мало — гораздо важнее понять, что с этим делать уже сегодня.",
    ],
    "discussion": [
        "Кажется, что про {topic_acc_lower} давно есть единое мнение. На деле споры продолжаются.",
        "Почти в любом разговоре про {topic_acc_lower} рано или поздно всплывают разногласия.",
        "Взгляд на {topic_acc_lower} не так однозначен, как может показаться на первый взгляд.",
    ],
    "review": [
        "Почти каждый хоть раз задавался вопросом, что вообще известно про {topic_acc_lower}.",
        "Разобраться в {topic_prep_lower} за один присест непросто — слишком много всего накопилось.",
        "Картина того, что известно про {topic_acc_lower}, продолжает меняться быстрее, чем кажется.",
    ],
    "explanation": [
        "Мало кто может с ходу объяснить, как именно работает {topic_nom_lower}.",
        "Кажется очевидным, что такое {topic_nom_lower} — но объяснить это простыми словами не так легко.",
        "Слово «{topic_nom_lower}» у всех на слуху, но не все точно знают, что за ним стоит.",
    ],
}

TITLE_PATTERNS = {
    "discovery": [
        # Расширено с 3 до 8 вариантов (2026-07-15, живой тест на 4
        # драфтах): при высокой доле сценария "discovery" среди
        # PubMed-статей 3 варианта регулярно давали одинаковый заголовок
        # у разных статей одной темы (id 515/516 — оба "Когниция:
        # неожиданный поворот в новом исследовании"). Не устраняет
        # коллизии полностью (учёта уже опубликованных заголовков по теме
        # всё ещё нет — предложено отдельным пунктом на будущее), но
        # снижает вероятность в ~2.5 раза.
        "Новое о {topic_prep_lower}: что обнаружили исследователи",
        "{topic_nom}: неожиданный поворот в новом исследовании",
        "Что нового узнали о {topic_prep_lower}",
        "{topic_nom}: чего мы раньше не знали",
        "Свежий взгляд на {topic_acc_lower}",
        "{topic_nom}: результат, который меняет ожидания",
        "Что выяснили о {topic_prep_lower} на этот раз",
        "{topic_nom}: свежие данные",
    ],
    "confirmation": [
        "{topic_nom}: очередное подтверждение",
        "Новые данные подтверждают прежние выводы о {topic_prep_lower}",
        "{topic_nom}: гипотеза набирает вес",
    ],
    "debunk": [
        "{topic_nom}: популярное заблуждение не подтверждается",
        "Что не так с привычным взглядом на {topic_acc_lower}",
        "{topic_nom}: новые данные против старых представлений",
    ],
    "practical": [
        "{topic_nom}: как применить в жизни",
        "Практический вывод из нового исследования о {topic_prep_lower}",
        "{topic_nom}: что делать с этими знаниями",
    ],
    "discussion": [
        "{topic_nom}: научный спор продолжается",
        "Разные взгляды на {topic_acc_lower} в новых исследованиях",
        "{topic_nom}: где согласие, а где разногласия",
    ],
    "review": [
        "{topic_nom}: обзор новых данных",
        "Что важно знать о {topic_prep_lower} прямо сейчас",
        "{topic_nom}: итоги последних исследований",
    ],
    "explanation": [
        "{topic_nom}: как это работает",
        "Понятное объяснение механизма {topic_gen_lower}",
        "{topic_nom}: что стоит за терминами",
    ],
}

WHY_PATTERNS = [
    # Прежний вариант "Это важно, потому что меняет то, как мы понимаем X"
    # убран: он ничего не сообщает сверх самого факта "это важно" и в
    # вычитке реальных публикаций 2026-07-14 читался как пустой штамп.
    "Речь не просто о теории — это влияет на реальные решения, связанные с {topic_inst_lower}.",
    "Главное здесь — практический взгляд на {topic_acc_lower}, а не абстрактные рассуждения.",
    "Это не праздный вопрос: ответ на него влияет на то, как мы вообще думаем о {topic_prep_lower}.",
    "Дело не в самом факте, а в том, что он меняет в наших ожиданиях от {topic_gen_lower}.",
]

CAVEAT_PATTERNS = [
    "Это не окончательный ответ — скорее очередной шаг в долгом исследовании.",
    "Новые данные расширяют картину, но для окончательных выводов нужны дальнейшие проверки.",
    "Стоит помнить: это одно исследование, и его выводы требуют подтверждения.",
]

PRACTICAL_OPENERS = [
    "На практике это означает: {value}",
    "Что это даёт в реальной жизни: {value}",
    "Практический вывод: {value}",
]

PRACTICAL_FOOTERS = [
    "Именно поэтому результат стоит взять на заметку.",
    "Такой подход помогает применять знания о {topic_prep_lower}, а не просто накапливать их.",
    "Это делает находку полезной — не только для науки, но и для повседневных решений.",
]

# Честные формулировки, когда практической пользы нет — вместо того чтобы
# выдумывать совет (ТЗ прямо запрещает "выдумывать советы", Stage 8).
HONEST_NO_PRACTICAL_PATTERNS = [
    "Пока это скорее фундаментальный результат: прямых практических рекомендаций исследование не даёт.",
    "Находка интересна с научной точки зрения, но говорить о практическом применении пока рано.",
    "Авторы не формулируют практических выводов — это в первую очередь вклад в фундаментальное понимание темы.",
]

# Рамка значимости — не практический вывод (тот отвечает "что делать"),
# а честный ответ на "зачем вообще такое исследование", когда прямого
# приложения к людям нет (типичный случай — фундаментальные animal
# studies). Раньше в этом случае _collect_body_blocks() просто ничего не
# добавляла (decomposed["practical"] пуст → блок молча пропускался) —
# статья заканчивалась без единого слова о том, зачем читателю вообще
# это знать (разбор реальной публикации, article id=483, "Стресс:
# неожиданный поворот" — животное исследование без явного human-value).
# Отдельный банк от HONEST_NO_PRACTICAL_PATTERNS: та фраза говорит "советов
# нет", эта — "вот зачем такое исследование в принципе нужно", разный смысл.
SIGNIFICANCE_FRAME_PATTERNS = [
    "Это лабораторное исследование — прямых выводов для людей пока нет, но оно закладывает основу для будущих работ о {topic_prep_lower}.",
    "Прямого применения к повседневной жизни здесь нет — это шаг к более полному пониманию {topic_gen_lower}.",
    "Такие фундаментальные результаты не дают готовых советов, но именно на них потом строятся более прикладные исследования {topic_gen_lower}.",
]

# То же самое по смыслу (нет прямой рекомендации), но БЕЗ утверждения
# "лабораторное исследование" — для study_type, которые по определению
# относятся к людям. evidence_classifier.PATTERNS вообще не содержит
# категории "animal_study"/"in_vitro" — весь его словарь (meta_analysis,
# systematic_review, randomized_controlled_trial, cohort_study,
# observational_study, case_report, review) описывает дизайн исследований
# НА людях. Найдено на живом драфте "Сон: итоги последних исследований"
# (систематический обзор, доказательность "Высокий") — рамка значимости
# заявляла "это лабораторное исследование", хотя это обзор человеческих
# работ, что прямо противоречило метаданным того же поста (2026-07-16).
SIGNIFICANCE_FRAME_PATTERNS_HUMAN = [
    "Прямого применения к повседневной жизни здесь нет — это шаг к более полному пониманию {topic_gen_lower}.",
    "Такие фундаментальные результаты не дают готовых советов, но именно на них потом строятся более прикладные исследования {topic_gen_lower}.",
    "Конкретных рекомендаций авторы не дают, но данные уточняют картину происходящего с {topic_inst_lower}.",
]

# study_type, которые сам классификатор (intelligence/research_analysis/
# evidence_classifier.py) определяет только для исследований на людях.
_HUMAN_STUDY_TYPES = frozenset({
    "meta_analysis", "systematic_review", "randomized_controlled_trial",
    "cohort_study", "observational_study", "case_report", "review",
})

# Единственный доступный сигнал "это животные/in vitro, не люди" —
# evidence_classifier такую категорию не определяет вообще. Список не
# претендует на полноту, растёт по факту встречаемости на реальных
# абстрактах (уже переведены на русский на этом этапе пайплайна).
_ANIMAL_STUDY_MARKERS = ("мыш", "крыс", "грызун")


def _is_likely_animal_or_lab_study(abstract: str) -> bool:
    lower = (abstract or "").lower()
    return any(marker in lower for marker in _ANIMAL_STUDY_MARKERS)


def _significance_frame_patterns(study_type: str, abstract: str) -> list[str]:
    if study_type in _HUMAN_STUDY_TYPES:
        return SIGNIFICANCE_FRAME_PATTERNS_HUMAN
    if _is_likely_animal_or_lab_study(abstract):
        return SIGNIFICANCE_FRAME_PATTERNS
    # study_type == "unknown" и нет явных маркеров животных/лаборатории —
    # честнее не утверждать ничего конкретного о характере исследования.
    return SIGNIFICANCE_FRAME_PATTERNS_HUMAN

SCENARIO_MARKERS = {
    "debunk": [
        "debunk", "myth", "false", "not true", "contrary", "refute", "opposed", "misconception",
        "миф", "неправда", "ошибка", "опроверга", "сомнение", "вопреки",
    ],
    "confirmation": [
        "confirm", "support", "replicate", "consistent", "agreement", "reinforce", "reproduce",
        "подтверд", "соглас", "повтор", "поддерж", "идентич", "аналогич",
    ],
    "practical": [
        "practical", "application", "intervention", "therapy", "habit", "recommend",
        "практик", "примен", "рекоменд", "упражн", "метод", "тренировк", "решение",
    ],
    "discussion": [
        "discussion", "debate", "controvers", "conflict", "competing", "multiple studies",
        "дискус", "спор", "разноглас", "несколько исследований", "разные данные",
        # "сравн" убран: слово встречается в любом количественном исследовании
        # ("по сравнению с традиционными факторами риска") — не обязательно
        # означает научный спор/разногласия. Заголовок и вопрос читателя
        # обещали "разные взгляды", а статья была одиночным когортным
        # исследованием без какого-либо спора (вычитка 2026-07-15).
    ],
    "review": [
        "review", "meta-analysis", "overview", "synthesis", "several studies", "summary",
        "обзор", "мета-анализ", "синтез", "несколько работ", "итог", "резюме",
    ],
    "explanation": [
        "mechanism", "process", "how", "why", "explain", "explanation", "theory",
        "механизм", "процесс", "как работает", "почему", "объясн", "теори",
    ],
    "discovery": [
        "novel", "first", "new", "previously unknown", "discover", "uncovered", "unexpected",
        "новый", "впервые", "ранее не", "обнаруж", "неожидан", "открыт",
    ],
}


def _normalize_text(text: str) -> str:
    return _clean_text(text).lower()


def detect_scenario(article: RawArticle) -> Scenario:
    title = _translate(article.title or "")
    abstract = _translate(article.abstract or "")
    text = f"{title} {abstract}".lower()

    if any(marker in text for marker in SCENARIO_MARKERS["debunk"]):
        return "debunk"
    if any(marker in text for marker in SCENARIO_MARKERS["practical"]):
        return "practical"
    if any(marker in text for marker in SCENARIO_MARKERS["confirmation"]):
        return "confirmation"
    if any(marker in text for marker in SCENARIO_MARKERS["discussion"]):
        return "discussion"
    if any(marker in text for marker in SCENARIO_MARKERS["review"]):
        return "review"
    if any(marker in text for marker in SCENARIO_MARKERS["explanation"]):
        return "explanation"
    if any(marker in text for marker in SCENARIO_MARKERS["discovery"]):
        return "discovery"
    return "discovery"


def _build_title(topic: str, scenario: Scenario, avoid_titles: set[str] | None = None) -> str:
    """avoid_titles — заголовки недавних драфтов той же темы (см.
    database.get_recent_titles_and_leads_by_topic). Банк шаблонов
    конечен, и при частой теме random.choice регулярно даёт дословное
    совпадение (draft id 185/186, 2026-07-15, тема "Когниция") — если
    среди вариантов есть хоть один, не совпадающий с недавними, выбираем
    из них; если все совпали бы (банк исчерпан) — используем полный
    список, это не хуже прежнего поведения.
    """
    patterns = TITLE_PATTERNS[scenario]
    if avoid_titles:
        candidates = [p for p in patterns if _pick([p], topic=topic) not in avoid_titles]
        if candidates:
            patterns = candidates
    return _pick(patterns, topic=topic)


def _build_lead(
    topic: str, scenario: Scenario, abstract: str, decomposed: dict,
    avoid_lead_prefixes: list[str] | None = None,
) -> str:
    """Лид = шаблонный хук + конкретное предложение из абстракта.

    avoid_lead_prefixes — лиды недавних драфтов той же темы; хук
    (шаблонная часть) — их неизменный префикс, реальная находка после
    него у каждой статьи своя. Как и в _build_title, не самая конкретная
    находка делает лиды похожими, а повторяющийся хук.
    """
    patterns = LEAD_PATTERNS[scenario]
    if avoid_lead_prefixes:
        candidates = [
            p for p in patterns
            if not any(prev.startswith(_pick([p], topic=topic)) for prev in avoid_lead_prefixes)
        ]
        if candidates:
            patterns = candidates
    hook = _pick(patterns, topic=topic)
    # Добавляем конкретику из абстракта, если есть
    finding = decomposed.get("finding", "")
    if finding:
        return f"{hook} {finding}"
    return hook


def _format_excerpt(abstract: str, max_sentences: int = 2) -> str:
    sentences = _split_sentences(abstract)
    if not sentences:
        return abstract
    return " ".join(sentences[:max_sentences])


def _collect_body_blocks(topic: str, decomposed: dict, abstract: str = "", study_type: str = "unknown") -> list[str]:
    """Собирает блоки body из декомпозиции, исключая finding (уже в лиде).

    Порядок: context → method → hook → practical.
    Каждое предложение используется ровно один раз.
    """
    blocks = []
    context = decomposed.get("context", "")
    if context:
        blocks.append(context)
    method = decomposed.get("method", "")
    if method:
        blocks.append(method)
    hook = decomposed.get("hook", "")
    if hook:
        blocks.append(hook)
    practical = decomposed.get("practical", "")
    if practical:
        blocks.append(_format_practical(topic, practical))
    else:
        # Рамка значимости вместо тишины — см. _significance_frame_patterns:
        # выбор зависит от study_type/abstract, не случаен (см. её докстринг).
        blocks.append(_pick(_significance_frame_patterns(study_type, abstract), topic=topic))
    return blocks


def _build_discovery(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Discovery: новый результат, который меняет взгляд на тему."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_confirmation(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Confirmation: подтверждение ранее высказанной гипотезы."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_debunk(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Debunk: опровержение распространённого мнения."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_discussion(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Discussion: спорная тема с разными точками зрения."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_review(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Review: обзор нескольких работ по теме."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_explanation(topic: str, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Explanation: объяснение механизма простым языком."""
    return _collect_body_blocks(topic, decomposed, abstract, study_type)


def _build_body(topic: str, scenario: Scenario, abstract: str, decomposed: dict, study_type: str = "unknown") -> list[str]:
    """Строит основную часть статьи без повторов предложений."""
    if scenario == "discovery":
        return _build_discovery(topic, abstract, decomposed, study_type)
    if scenario == "confirmation":
        return _build_confirmation(topic, abstract, decomposed, study_type)
    if scenario == "debunk":
        return _build_debunk(topic, abstract, decomposed, study_type)
    if scenario == "practical":
        return _build_practical_block(topic, abstract, decomposed)
    if scenario == "discussion":
        return _build_discussion(topic, abstract, decomposed, study_type)
    if scenario == "review":
        return _build_review(topic, abstract, decomposed, study_type)
    if scenario == "explanation":
        return _build_explanation(topic, abstract, decomposed, study_type)
    return _build_discovery(topic, abstract, decomposed, study_type)


def _build_practical_block(topic: str, abstract: str, decomposed: dict) -> list[str]:
    """Practical scenario: фокус на применении. Finding уже в lead."""
    blocks = []
    # Добавляем дополнительные детали из абстракта
    method = decomposed.get("method", "")
    if method:
        blocks.append(method)
    hook = decomposed.get("hook", "")
    if hook:
        blocks.append(hook)
    # Решение "есть реальная практическая польза или нет" берётся из того же
    # маркера декомпозиции, что и passport["practical_value"] в analyze() —
    # иначе метаданные могут говорить "польза есть", а в тексте будет честная
    # заглушка про отсутствие пользы, или наоборот.
    practical = decomposed.get("practical", "")
    if practical and practical.strip():
        blocks.append(_format_practical(topic, practical))
    else:
        blocks.append(_pick(HONEST_NO_PRACTICAL_PATTERNS, topic=topic))
    return blocks


def _format_practical(topic: str, practical_sentence: str) -> str:
    """Форматирует практический вывод без повторов."""
    opener = _pick(PRACTICAL_OPENERS, topic=topic, value=practical_sentence)
    footer = _pick(PRACTICAL_FOOTERS, topic=topic)
    return f"{opener} {footer}"


def _build_why(topic: str) -> str:
    return f"Почему это важно: {_pick(WHY_PATTERNS, topic=topic)}"


def _build_caveat() -> str:
    return _pick(CAVEAT_PATTERNS)


def _build_source_line(articles: list[RawArticle]) -> str:
    sources = [SOURCE_NAMES.get((a.source or "").lower(), a.source or "источник")
               for a in articles if a.source]
    unique = []
    for source in sources:
        if source not in unique:
            unique.append(source)
    return f"Основано на материалах: {', '.join(unique) or 'разных источников'}."


def _evidence_ru(evidence: str) -> str:
    """Перевод уровня доказательности на русский."""
    return {
        "high": "высокий (метаанализ/систематический обзор)",
        "moderate_high": "высокий (RCT)",
        "moderate": "средний",
        "limited": "ограниченный",
        "preliminary": "предварительный",
        "weak": "низкий",
    }.get(evidence, evidence)


def _plural_related_works(n: int) -> str:
    """Согласует числительное: 1 близкая работа / 2 близкие работы / 5 близких работ."""
    if n % 10 == 1 and n % 100 != 11:
        return f"По теме найдена {n} близкая работа."
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"По теме найдено {n} близкие работы."
    return f"По теме найдено {n} близких работ."


def _build_context_summary(passport: dict) -> str:
    """Смысловой контекст знаний — работает на пункт ТЗ "Почему исследованию
    можно доверять".

    Перечисление заголовков близких работ ("Среди ближайших работ: ...")
    убрано намеренно:
    - такого блока нет в структуре статьи по ТЗ;
    - он читается как раздел "Литература", а ТЗ прямо запрещает писать как
      научная статья;
    - сырой заголовок вроде "Картирование эмоциональной функции при
      фибромиалгии: интеграция алекситимии и катастрофизации боли" нарушает
      правило "читатель никогда не должен чувствовать себя глупым";
    - он регулярно позорил: в статье про стрессоустойчивость человека
      всплывала работа "Стресс при отъеме ... у свиней". Ранжированием по
      схожести это не лечится — такие работы делят словарь с исходной
      (кортизол, ГГН-ось) и набирают высокий балл честно.
    Доверие к исследованию обслуживает блок "Уровень доказательности".
    """
    kc = passport.get("knowledge_context") or {}
    if not kc:
        return ""

    lines = []
    related = kc.get("related_works", [])
    consensus = kc.get("consensus", [])
    contradictions = kc.get("contradictions", [])

    if related:
        lines.append(_plural_related_works(len(related)))
    if consensus:
        lines.append("Часть предыдущих исследований подтверждает общую картину.")
    if contradictions:
        lines.append("Есть и работы с другим взглядом, что важно учесть.")
    # "Остаются открытые вопросы, требующие дальнейших проверок" сюда не
    # включаем: почти любой академический абстракт заканчивается призывом
    # к дальнейшим исследованиям, поэтому этот флаг истинен почти всегда и
    # не несёт информации — только раздувает блок одинаковым текстом в
    # каждой статье (вычитка реальных публикаций 2026-07-14).

    return " ".join(lines)


def build_editorial_text(article: RawArticle, topic: str) -> str:
    """Backwards-compatible wrapper that uses the EditorialEngine.

    The engine performs analysis (passport), builds structure and generates text.
    """
    engine = EditorialEngine()
    passport = engine.analyze(article, topic)
    structure = engine.build_structure(passport)
    text = engine.generate_text(passport, structure)
    return text


class EditorialEngine:
    """Editorial Engine: analyzes article and generates unified editorial text.

    Public flow:
    - analyze(article, topic) -> passport (dict)
    - build_structure(passport) -> list[str] (ordered blocks)
    - generate_text(passport, structure) -> str
    """

    def analyze(self, article: RawArticle, topic: str) -> dict:
        """Analyze article and produce a publication passport."""
        topic_ru = get_topic_ru(topic)
        scenario = detect_scenario(article)
        raw_abstract = _clean_text(article.abstract or "")
        # Диагностика формы абстракта (Дополнение №2 к ТЗ, п.2.3) — на
        # СЫРОМ тексте, до стрипинга меток: иначе "structured" никогда
        # не определится, метка к этому моменту уже будет вырезана.
        # Сейчас это информационное поле в passport, не меняет путь
        # генерации — см. docstring classify_abstract_form().
        abstract_form = classify_abstract_form(raw_abstract)
        # Метки разделов ("IntroductionAlthough...") убираем ДО перевода,
        # пока текст ещё английский.
        abstract = _translate(_strip_section_labels(raw_abstract))
        # Второй проход — уже на переведённом тексте (см. docstring
        # _strip_translated_section_labels): ловит метки, дожившие до
        # перевода, и метки в изначально русских источниках, для которых
        # английского прохода выше не было вовсе.
        abstract = _strip_translated_section_labels(abstract)
        abstract = _shorten(abstract, max_len=1200)
        # Simplification (Stage 6): убираем канцеляризмы на уровне
        # редакционного слоя, а не в _translate() — тот кэширует переводы
        # в БД, и подмешивать туда стилевые правки означало бы закэшировать
        # их как "перевод", не давая потом менять правила без инвалидации кэша.
        abstract = simplify_text(abstract)
        # Убираем латинские аббревиатуры в скобках — (NAc), (BNST), (SECPT).
        # Только на исходном тексте: наши собственные шаблоны трогать нельзя,
        # иначе из блока доказательности вырежется "(RCT)".
        abstract = _strip_latin_abbreviations(abstract)
        # Расшифровка методологического жаргона (тесты на грызунах и т.п.) —
        # до декомпозиции, чтобы расшифровка попала в любой блок, куда уйдёт
        # предложение (lead/body), а не только в один конкретный.
        abstract = simplify_methodology_terms(abstract)

        # Декомпозиция абстракта — каждое предложение в одной роли
        decomposed = _decompose_abstract(abstract)

        # detect_scenario() определяет "practical" по ключевым словам в
        # исходном тексте (intervention/therapy/рекоменд...), но реальный
        # практический вывод извлекается только здесь, из decomposed. Если
        # ключевые слова были, а вывода по факту нет — заголовок и вопрос
        # читателя не должны обещать применение, которого не будет в тексте
        # (см. HONEST_NO_PRACTICAL_PATTERNS в _build_practical_block).
        if scenario == "practical" and not (decomposed.get("practical") or "").strip():
            scenario = "discovery"

        # Anti-repeat (Stage 3 доп.): избегаем дословного совпадения
        # заголовка/лида с недавними драфтами той же темы — см.
        # _build_title/_build_lead. db-запрос обёрнут в try — сбой БД не
        # должен ронять генерацию текста, максимум теряется anti-repeat.
        try:
            avoid_titles, avoid_lead_prefixes = db.get_recent_titles_and_leads_by_topic(topic)
        except Exception:
            avoid_titles, avoid_lead_prefixes = set(), []

        title = _build_title(topic, scenario, avoid_titles=avoid_titles)
        lead = _build_lead(topic, scenario, abstract, decomposed, avoid_lead_prefixes=avoid_lead_prefixes)

        main_idea = decomposed.get("finding", "") or _extract_key_sentence(abstract) or _translate(article.title or "")
        method_summary = decomposed.get("method", "")
        takeaway = decomposed.get("practical", "") or main_idea

        passport = {
            "topic": topic,
            "topic_ru": topic_ru,
            "scenario": scenario,
            "abstract_form": abstract_form,
            "title": title,
            "lead": lead,
            "abstract": abstract,
            "decomposed": decomposed,
            "main_idea": main_idea,
            "publication_type": "article",
            "style": "neutral",
            "source": article.source,
            "sources": [article.url, article.source] if article.url else [article.source],
            "article": article,
        }

        research_passport = None
        try:
            research_passport = build_research_passport(article, topic, article_id=0)
            passport["evidence_strength"] = research_passport.evidence_strength
            passport["trust_level"] = research_passport.trust_level
            # Ограничения извлекаются из ОРИГИНАЛЬНОГО (английского) абстракта
            # в research_analysis и раньше попадали в статью непереведёнными —
            # блок "Ограничения:" был целиком на английском.
            passport["limitations"] = _strip_latin_abbreviations(
                _translate(research_passport.limitations)
            )
            passport["study_type"] = research_passport.study_type
            passport["peer_reviewed"] = research_passport.peer_reviewed
            passport["sample_size"] = research_passport.sample_size
            # Единственный источник истины для confidence_score — trust_engine
            passport["confidence_score"] = research_passport.trust_level
            passport["evidence"] = research_passport.evidence_strength
        except Exception:
            # Fallback: классифицируем по сценарию, но score — через trust_engine
            evidence = "preliminary"
            if scenario in ("confirmation",):
                evidence = "moderate"
            if scenario == "review":
                evidence = "high"
            passport["evidence"] = evidence
            passport["evidence_strength"] = evidence
            passport["trust_level"] = estimate_trust_level(evidence, article.is_peer_reviewed)
            passport["limitations"] = ""
            passport["study_type"] = "unknown"
            passport["peer_reviewed"] = article.is_peer_reviewed
            passport["sample_size"] = ""
            passport["confidence_score"] = estimate_trust_level(evidence, article.is_peer_reviewed)

        # practical_value отражает РЕАЛЬНО найденный маркер практической
        # пользы (декомпозиция абстракта), а не гарантированно непустой
        # fallback _extract_practical_sentence — иначе passport["practical_value"]
        # почти всегда был бы True, даже когда в тексте статьи честно
        # написано, что практической пользы нет (см. _build_practical_block).
        practical_marker_sentence = decomposed.get("practical", "")
        practical_value = bool(practical_marker_sentence and practical_marker_sentence.strip())
        practical_sentence = practical_marker_sentence or _extract_practical_sentence(abstract)

        tone_map = {
            "discovery": "curious",
            "confirmation": "measured",
            "debunk": "critical",
            "practical": "actionable",
            "discussion": "balanced",
            "review": "authoritative",
            "explanation": "calm",
        }
        tone = tone_map.get(scenario, "neutral")

        audience = "general"
        if "neuro" in abstract.lower() or "mechanism" in abstract.lower():
            audience = "informed"

        novelty = "low"
        if scenario == "discovery":
            novelty = "high"
        elif scenario in ("confirmation", "review"):
            novelty = "medium"

        suggested_format = "analysis"
        if scenario == "review":
            suggested_format = "overview"
        elif practical_value:
            suggested_format = "actionable"
        elif scenario == "explanation":
            suggested_format = "explanation"

        passport["novelty"] = novelty
        passport["audience"] = audience
        passport["story_angle"] = scenario
        passport["headline_hint"] = title
        passport["recommended_lead"] = lead
        # Reader Question (Stage 3): настоящий человеческий вопрос, а не
        # утверждение — статья строится вокруг него, а не вокруг исследования.
        passport["reader_question"] = build_reader_question(topic, scenario, finding=main_idea)
        passport["key_question"] = passport["reader_question"]  # алиас для обратной совместимости
        # Analogy (Stage 7): обязательный блок — critic.check_analogy_present
        # блокирует публикацию, если он пуст.
        passport["analogy"] = build_analogy(topic, scenario)
        passport["main_conclusion"] = takeaway
        passport["method_summary"] = method_summary
        passport["takeaway"] = takeaway
        if "limitations" not in passport or not passport["limitations"]:
            passport["limitations"] = ""
        passport["related_works"] = []
        passport["knowledge_context"] = {}
        passport["novelty_score"] = 0.8 if novelty == "high" else 0.5 if novelty == "medium" else 0.2
        # confidence_score уже установлен через trust_engine выше — не перетираем
        passport["suggested_format"] = suggested_format
        passport["tone"] = tone
        passport["practical_value"] = practical_value
        passport["practical_sentence"] = practical_sentence

        # Build knowledge context and attach to passport
        try:
            kc = build_knowledge_context(topic, article)
            passport["knowledge_context"] = asdict(kc)
            passport["related_works"] = kc.related_works
        except Exception:
            passport["knowledge_context"] = {}

        notes = []
        if passport["confidence_score"] < 0.5:
            notes.append("Низкая уверенность результатов — проверить методологию и выборку.")
        if passport["novelty"] == "high":
            notes.append("Подчеркнуть новизну и возможные альтернативные объяснения.")
        if passport["practical_value"]:
            notes.append("Выделить практическое применение и дать примеры.")
        if passport["audience"] == "informed":
            notes.append("Упомянуть ключевые механизмы и термины для подготовленного читателя.")
        passport["editor_notes"] = notes

        return passport

    def build_structure(self, passport: dict) -> list[str]:
        """Build logical structure (blocks) based on passport and scenario.

        Каждое предложение абстракта используется ровно один раз —
        декомпозиция гарантирует отсутствие повторов.
        """
        topic = passport["topic"]
        scenario = passport["scenario"]
        abstract = passport["abstract"]
        decomposed = passport.get("decomposed", {})

        blocks: list[str] = [passport["title"], passport["lead"]]
        reader_question = passport.get("reader_question", "")
        if reader_question:
            blocks.append(reader_question)

        body_blocks = _build_body(topic, scenario, abstract, decomposed, passport.get("study_type", "unknown"))
        # Ритмический переход перед содержательной частью (Rule 10) — только
        # если есть что вводить, иначе связка повисает перед аналогией.
        if body_blocks:
            blocks.append(build_transition("into_body"))
        blocks.extend(body_blocks)

        # Не добавляем practical_block повторно — body уже содержит practical
        # (раньше здесь вызывался _build_practical_block, что давало повторы)

        analogy = passport.get("analogy", "")
        if analogy:
            blocks.append(build_transition("into_analogy"))
            blocks.append(f"<i>{analogy}</i>")

        context_summary = _build_context_summary(passport)
        if context_summary:
            blocks.append(context_summary)

        evidence_strength = passport.get("evidence_strength", "")
        if evidence_strength:
            blocks.append(f"<b>Уровень доказательности:</b> {_evidence_ru(evidence_strength)}.")

        limitations = passport.get("limitations", "")
        if limitations:
            blocks.append(f"<b>Ограничения:</b> {limitations}")
        elif passport.get("study_type") in ("unknown", "observational_study", "case_report"):
            blocks.append("<b>Ограничения:</b> Требуются дополнительные исследования для подтверждения выводов.")

        blocks.append(build_transition("into_significance"))
        blocks.append(_build_why(topic))
        blocks.append(_build_caveat())
        blocks.append(_build_source_line([passport["article"]]))

        return blocks

    def build_named_structure(self, passport: dict) -> dict[str, str]:
        """Именованные блоки Article Outline (Stage 4) для структурных проверок критика.

        Параллельный build_structure() метод — не меняет сигнатуру и порядок
        существующего build_structure() (используется в 3 местах: pipeline.py,
        build_editorial_text(), create_publication_for_article()), чтобы не
        ломать их и существующие тесты. Возвращает block_name -> текст.
        """
        topic = passport["topic"]
        scenario = passport["scenario"]
        abstract = passport["abstract"]
        decomposed = passport.get("decomposed", {})

        body_blocks = _build_body(topic, scenario, abstract, decomposed, passport.get("study_type", "unknown"))
        limitations = passport.get("limitations", "")
        if not limitations and passport.get("study_type") in ("unknown", "observational_study", "case_report"):
            limitations = "Требуются дополнительные исследования для подтверждения выводов."

        return {
            "hook": passport.get("lead", ""),
            "reader_question": passport.get("reader_question", ""),
            "what_science_found": " ".join(body_blocks),
            "analogy": passport.get("analogy", ""),
            "limitations": limitations,
            "why": _build_why(topic),
            "caveat": _build_caveat(),
        }

    def generate_text(self, passport: dict, structure: list[str]) -> str:
        """Render the final text from structure; this is the single point to unify style."""
        # Финальный проход Simplifier — страховка от канцеляризмов, случайно
        # попавших в шаблоны при будущих правках (основная простановка уже
        # прошла в analyze() на уровне абстракта).
        cleaned = [simplify_text(s) for s in structure if s]
        # Join with double newlines for readability (Telegraph-friendly)
        return "\n\n".join([s for s in cleaned if s])

    def create_publication_for_article(self, article: RawArticle, topic: str) -> Publication:
        """Create a unified Publication object for a single article."""
        passport = self.analyze(article, topic)
        structure = self.build_structure(passport)
        full_text = self.generate_text(passport, structure)
        # short version: first paragraph
        parts = [p for p in full_text.split('\n\n') if p.strip()]
        short = parts[0] if parts else full_text

        pub = Publication(
            title=passport.get("title", ""),
            subtitle=None,
            lead=passport.get("lead", ""),
            body="\n\n".join(parts[1:]) if len(parts) > 1 else "",
            short_version=short,
            full_version=full_text,
            sources=[passport.get("source") or article.source or ""],
            topic=passport.get("topic", topic),
            format=passport.get("suggested_format", "analysis"),
            confidence_score=passport.get("confidence_score", passport.get("confidence_score", 0.0)) or passport.get("confidence_score", 0.0),
            audience=passport.get("audience", "general"),
            editor_notes=passport.get("editor_notes", []),
            knowledge_context=passport.get("knowledge_context", {}),
            story_angle=passport.get("story_angle"),
            suggested_format=passport.get("suggested_format"),
            tone=passport.get("tone"),
        )
        return pub

    def create_publication_for_cluster(self, topic: str, articles: list[RawArticle]) -> Publication:
        """Create a Publication object that represents a cluster/overview."""
        passport = self.analyze_cluster(topic, articles)
        structure = self.build_cluster_structure(passport)
        full_text = "\n".join(structure)
        parts = [p for p in full_text.split('\n\n') if p.strip()]
        short = parts[0] if parts else full_text
        sources = [a.source for a in articles if a.source]
        pub = Publication(
            title=passport.get("title", f"Тема: {passport.get('topic_ru', topic)}"),
            subtitle=None,
            lead=passport.get("lead", ""),
            body="\n\n".join(parts[1:]) if len(parts) > 1 else "",
            short_version=short,
            full_version=full_text,
            sources=sources,
            topic=topic,
            format="cluster",
            confidence_score=0.5,
            audience=passport.get("audience", "general"),
            editor_notes=passport.get("editor_notes", []),
            knowledge_context=passport.get("knowledge_context", {}),
            story_angle=passport.get("story_angle"),
            suggested_format=passport.get("suggested_format"),
            tone=passport.get("tone"),
        )
        return pub

    # ---- YouTube helper ----
    def generate_youtube_block(self, article: RawArticle) -> str:
        """Create an editorial-style YouTube block suitable for Telegram posts."""
        title = _translate(article.title or "")
        abstract = _translate(_clean_text(article.abstract or ""))
        lines = [f"🎙 <b>{title}</b>", "", abstract, "", f"Ссылка: {article.url}"]
        return "\n".join([l for l in lines if l])

    # ---- Cluster / multi-article support ----
    def analyze_cluster(self, topic: str, articles: list[RawArticle]) -> dict:
        """Create an aggregated passport for a cluster of articles."""
        topic_ru = get_topic_ru(topic)
        abstracts = [(_translate(_clean_text(a.abstract or "")) or _translate(a.title or "")) for a in articles]
        combined = "\n".join(abstracts)

        # Basic cluster heuristics
        main_idea = _format_excerpt(combined, 1)
        practical_sentences = [s for a in abstracts for s in (_extract_practical_sentence(a) or "").split(".") if s]
        practical_value = bool(practical_sentences)

        passport = {
            "topic": topic,
            "topic_ru": topic_ru,
            "publication_type": "cluster",
            "title": f"{topic_ru}: обзор ключевых исследований",
            "lead": f"Обзор ключевых исследований по теме «{topic_ru.lower()}» — что нового и что из этого стоит запомнить.",
            "abstract": combined,
            "main_idea": main_idea,
            "practical_value": practical_value,
            "practical_sentence": practical_sentences[0] if practical_sentences else "",
            "related_works": [{"title": a.title, "url": a.url, "source": a.source} for a in articles],
            "articles": articles,
        }
        return passport

    def build_cluster_structure(self, passport: dict) -> list[str]:
        """Build readable telegraph-style structure for a cluster."""
        topic = passport["topic"]
        topic_ru = passport["topic_ru"]
        lines: list[str] = [
            f"{topic_ru}: обзор ключевых исследований",
            "",
            passport.get("lead", ""),
            "",
            "Что нашли",
            "",
        ]

        for i, a in enumerate(passport.get("articles", []), 1):
            title_ru = _translate(a.title or "")
            snippet = a.abstract and _extract_practical_sentence(_translate(_clean_text(a.abstract))) or title_ru
            pretty_source = SOURCE_NAMES.get((a.source or "").lower(), a.source or "источник")
            lines += [f"{i}. {title_ru} ({pretty_source})", "", snippet, "", f"Оригинал: {a.url}", ""]

        # Collect pretty unique source names preserving order
        seen = []
        for a in passport.get("articles", []):
            pretty = SOURCE_NAMES.get((a.source or "").lower(), a.source or "источник")
            if pretty not in seen:
                seen.append(pretty)

        lines += [
            "Почему это важно",
            passport.get("practical_sentence") or _pick(WHY_PATTERNS, topic=topic),
            "",
            "Ограничения",
            _pick(CAVEAT_PATTERNS),
            "",
            f"Основано на исследованиях: {', '.join(seen)}.",
            "",
        ]
        return lines

    def generate_cluster_text(self, topic: str, articles: list[RawArticle]) -> str:
        passport = self.analyze_cluster(topic, articles)
        structure = self.build_cluster_structure(passport)
        return "\n".join(structure)

    # ---- Review generator ----
    def generate_review(self, topic: str, articles: list[RawArticle]) -> str:
        """Generate a review-style article that synthesizes multiple works."""
        topic_ru = get_topic_ru(topic)
        title = f"Обзор новых данных: {topic_ru}"
        lead = f"Что важно знать о {get_topic_case(topic, 'prep_lower')} прямо сейчас"
        body = []
        # include key points from each article
        for a in articles:
            excerpt = _extract_practical_sentence(_translate(_clean_text(a.abstract or ""))) or _translate(a.title or "")
            body.append(f"• {excerpt} ({SOURCE_NAMES.get((a.source or '').lower(), a.source or 'источник')})")

        caveat = _pick(CAVEAT_PATTERNS)
        sources = ", ".join({SOURCE_NAMES.get((a.source or '').lower(), a.source or 'источник') for a in articles})
        lines = [title, "", lead, "", "\n".join(body), "", caveat, "", f"Основано на исследованиях: {sources}."]
        return "\n\n".join([l for l in lines if l])
