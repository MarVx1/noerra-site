# ============================================================
#  adaptation/editorial_engine.py — независимый редакционный движок
# ============================================================

import random
from typing import Literal
from dataclasses import asdict
from adaptation.publication import Publication
from parsers.base import RawArticle
from classifier.classifier import get_topic_ru
from database import db
from adaptation.knowledge import build_knowledge_context
from knowledge.core import build_research_passport
from adaptation.utils import (
    _clean_text,
    _split_sentences,
    _translate,
    _extract_practical_sentence,
    _extract_key_sentence,
    _shorten,
)

SOURCE_NAMES = {
    "pubmed": "PubMed",
    "arxiv": "arXiv",
    "cyberleninka": "CyberLeninka",
    "rss": "RSS",
    "youtube": "YouTube",
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

LEAD_PATTERNS = {
    "discovery": [
        "В двух словах: в той области, где долго было тихо, появился неожиданный поворот.",
        "Новая идея обычно начинается с вопроса, который раньше никто не ставил всерьёз.",
        "Это не очередное заявление о принципе — это попытка посмотреть на {topic} иначе.",
    ],
    "confirmation": [
        "То, что звучало как гипотеза, получает теперь уверенное подтверждение.",
        "Если вы считали, что {topic} связано с данным эффектом, это исследование добавляет важное подтверждение.",
        "В последние годы вокруг {topic} появилось несколько версий. Новая работа делает выбор в пользу одной из них.",
    ],
    "debunk": [
        "Пора раз и навсегда уточнить: то, что считается обычным мнением, далеко не всегда правда.",
        "Сколько раз вы слышали, что {topic} действует именно так? Этот материал предлагает другой взгляд.",
        "Стандартное объяснение удобнее, чем точное. Новое исследование показывает, где оно подводит.",
    ],
    "practical": [
        "Если вы хотите, чтобы {topic} перестало быть абстракцией, эта история вам поможет.",
        "Вопрос не в том, правда ли это, а в том, как это можно применить здесь и сейчас.",
        "Менее академично, но важнее: что следует изменить в повседневности, узнав это?",
    ],
    "discussion": [
        "В науке редко появляется одна точка зрения. Эта тема живёт в споре, и полезно его понять.",
        "Когда несколько исследований смотрят в одну сторону, их разговор становится главным событием.",
        "Этот материал расскажет не о единственной работе, а о том, как разные данные друг друга дополняют.",
    ],
    "review": [
        "Гораздо чаще наука не делает резких заявлений, а аккуратно складывает картину из мелких деталей.",
        "Несколько новых работ уже меняют взгляд на {topic}. Собрать их смысл — наша задача.",
        "Это не история одного исследования, а обзор того, как тема развивается в нескольких публикациях.",
    ],
    "explanation": [
        "Сначала кажется, что {topic} слишком сложно. На самом деле есть понятный путь, чтобы это увидеть.",
        "Если вы слышали о {topic}, но не могли разобраться, как это работает — здесь объяснение без шума.",
        "Лучше понять процесс важно не меньше, чем знать результат. Этот материал делает именно это.",
    ],
}

TITLE_PATTERNS = {
    "discovery": [
        "Новое понимание {topic}",
        "Как изменилось представление о {topic}",
        "Смена парадигмы для {topic}",
    ],
    "confirmation": [
        "Почему {topic} становится более уверенной идеей",
        "Ещё один аргумент в пользу {topic}",
        "Подтверждение важного предположения о {topic}",
    ],
    "debunk": [
        "Миф о {topic}",
        "Что не так с обычным представлением о {topic}",
        "Почему популярное объяснение {topic} вводит в заблуждение",
    ],
    "practical": [
        "{topic} в повседневной жизни",
        "Как {topic} помогает действовать иначе",
        "Польза {topic} для привычек и решений",
    ],
    "discussion": [
        "Что говорят разные исследования о {topic}",
        "Наука обсуждает {topic}",
        "Несколько взглядов на {topic}",
    ],
    "review": [
        "Обзор новых данных по {topic}",
        "Что важно знать о {topic} сейчас",
        "Текущее состояние темы {topic}",
    ],
    "explanation": [
        "Почему {topic} работает именно так",
        "Как устроено {topic}",
        "Понятное объяснение {topic}",
    ],
}

WHY_PATTERNS = [
    "Это важно потому, что влияет на то, как мы понимаем {topic} в жизни и на работе.",
    "Речь не только об открытии — речь о том, что меняет наши привычные представления.",
    "Главное здесь — не формула, а то, что это помогает иначе посмотреть на {topic}.",
]

CAVEAT_PATTERNS = [
    "Это не финальный ответ, но очередной шаг в долгой дискуссии.",
    "Важный момент: новые данные расширяют картину, но требуют дальнейшей проверки.",
    "Стоит помнить, что это не догма — это ещё одно наблюдение среди многих.",
]

PRACTICAL_OPENERS = [
    "Важное практическое наблюдение: {value}",
    "Что это даёт вам сегодня: {value}",
    "В реальной жизни это может означать следующее: {value}",
]

PRACTICAL_FOOTERS = [
    "Именно поэтому этот результат стоит сохранить в голове.",
    "Такой подход помогает смотреть на {topic} не только через теорию, но и через практику.",
    "Эта сторона делает находку полезной, а не просто интересной.",
]

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
        "дискус", "спор", "разноглас", "несколько исследований", "сравн", "разные данные",
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


def _pick(patterns: list[str], **kwargs) -> str:
    template = random.choice(patterns)
    return template.format(**kwargs)


def _build_title(topic_ru: str, scenario: Scenario) -> str:
    return _pick(TITLE_PATTERNS[scenario], topic=topic_ru)


def _build_lead(topic_ru: str, scenario: Scenario, title: str, abstract: str) -> str:
    sample = abstract.split(".")
    detail = sample[0].strip() if sample else ""
    return _pick(LEAD_PATTERNS[scenario], topic=topic_ru)


def _format_excerpt(abstract: str, max_sentences: int = 2) -> str:
    sentences = _split_sentences(abstract)
    if not sentences:
        return abstract
    return " ".join(sentences[:max_sentences])


def _build_discovery(topic_ru: str, abstract: str) -> list[str]:
    excerpt = _format_excerpt(abstract, 2)
    return [
        f"В статье внимательно разбирают новое наблюдение в сфере {topic_ru.lower()}.",
        f"Суть в том, что найденный эффект меняет привычный взгляд на тему.",
        excerpt,
        _build_practical(topic_ru, "discovery", abstract),
    ]


def _build_confirmation(topic_ru: str, abstract: str) -> list[str]:
    evidence = _format_excerpt(abstract, 2)
    return [
        f"Эта работа помогает понять, почему {topic_ru.lower()} перестаёт восприниматься как случайность.",
        f"Здесь важен не сам результат, а то, что он укладывается в уже существующую картину.",
        evidence,
        _build_practical(topic_ru, "confirmation", abstract),
    ]


def _build_debunk(topic_ru: str, abstract: str) -> list[str]:
    myth_fragment = _extract_practical_sentence(abstract)
    return [
        f"Обычное объяснение {topic_ru.lower()} выглядит простым, но оно обходит ключевой момент.",
        f"Новая работа показывает, что важная часть истории была упущена.",
        myth_fragment,
        _build_practical(topic_ru, "debunk", abstract),
    ]


def _build_discussion(topic_ru: str, abstract: str) -> list[str]:
    excerpt = _format_excerpt(abstract, 2)
    return [
        f"В обсуждении {topic_ru.lower()} теперь есть несколько сильных аргументов.",
        f"Важно увидеть, какие данные поддерживают каждую точку зрения.",
        excerpt,
        _build_practical(topic_ru, "discussion", abstract),
    ]


def _build_review(topic_ru: str, abstract: str) -> list[str]:
    excerpt = _format_excerpt(abstract, 2)
    return [
        f"За последнее время по теме {topic_ru.lower()} вышло несколько заметных работ.",
        f"Эта статья помогает сложить их в одну картину и выделить главное.",
        excerpt,
        _build_practical(topic_ru, "review", abstract),
    ]


def _build_explanation(topic_ru: str, abstract: str) -> list[str]:
    excerpt = _format_excerpt(abstract, 2)
    return [
        f"Здесь объясняют ключевой механизм {topic_ru.lower()} простым языком.",
        f"Суть не в терминах, а в том, как работа устроена и что это значит для нас.",
        excerpt,
        _build_practical(topic_ru, "explanation", abstract),
    ]


def _build_body(topic_ru: str, scenario: Scenario, abstract: str) -> list[str]:
    if scenario == "discovery":
        return _build_discovery(topic_ru, abstract)
    if scenario == "confirmation":
        return _build_confirmation(topic_ru, abstract)
    if scenario == "debunk":
        return _build_debunk(topic_ru, abstract)
    if scenario == "practical":
        return _build_practical_block(topic_ru, abstract)
    if scenario == "discussion":
        return _build_discussion(topic_ru, abstract)
    if scenario == "review":
        return _build_review(topic_ru, abstract)
    if scenario == "explanation":
        return _build_explanation(topic_ru, abstract)
    return _build_discovery(topic_ru, abstract)


def _build_practical_block(topic_ru: str, abstract: str) -> list[str]:
    advice = _extract_practical_sentence(abstract)
    return [
        f"Главное здесь — как это можно применить на практике.",
        advice or "Результат помогает принять решение и действовать с большей уверенностью.",
        _build_practical(topic_ru, "practical", abstract),
    ]


def _build_practical(topic_ru: str, scenario: Scenario, abstract: str) -> str:
    practical = _extract_practical_sentence(abstract)
    if not practical:
        practical = "Это исследование предлагает ориентир для тех, кто хочет действовать увереннее."
    opener = _pick(PRACTICAL_OPENERS, value=practical)
    footer = _pick(PRACTICAL_FOOTERS, topic=topic_ru)
    return f"{opener} {footer}"


def _build_why(topic_ru: str) -> str:
    return f"Почему это важно: {_pick(WHY_PATTERNS, topic=topic_ru)}"


def _build_caveat() -> str:
    return _pick(CAVEAT_PATTERNS)


def _build_source_line(articles: list[RawArticle]) -> str:
    sources = [a.source for a in articles if a.source]
    unique = []
    for source in sources:
        if source not in unique:
            unique.append(source)
    return f"Основано на материалах: {', '.join(unique) or 'разных источниках'}."


def _build_context_summary(passport: dict) -> str:
    kc = passport.get("knowledge_context") or {}
    if not kc:
        return ""

    lines = []
    related = kc.get("related_works", [])
    consensus = kc.get("consensus", [])
    contradictions = kc.get("contradictions", [])
    open_questions = kc.get("open_questions", [])

    if related:
        lines.append(f"По теме найдено {len(related)} близких работ.")
    if consensus:
        lines.append("Часть предыдущих исследований подтверждает общую картину.")
    if contradictions:
        lines.append("Есть и работы с другим взглядом, что важно учесть.")
    if open_questions:
        lines.append("Остаются открытые вопросы, требующие дальнейших проверок.")

    if related:
        top_titles = [item["title"] for item in related[:2]]
        lines.append(f"Среди ближайших работ: {', '.join(top_titles)}.")

    return " ".join(lines)


def build_editorial_text(article: RawArticle, topic: str) -> str:
    topic_ru = get_topic_ru(topic)
    scenario = detect_scenario(article)
    title = _build_title(topic_ru, scenario)
    abstract = _translate(_clean_text(article.abstract or ""))
    abstract = _shorten(abstract, max_len=1200)
    lead = _build_lead(topic_ru, scenario, title, abstract)
    body = _build_body(topic_ru, scenario, abstract)
    why = _build_why(topic_ru)
    caveat = _build_caveat()
    source_line = _build_source_line([article])
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
        abstract = _translate(_clean_text(article.abstract or ""))
        abstract = _shorten(abstract, max_len=1200)

        title = _build_title(topic_ru, scenario)
        lead = _build_lead(topic_ru, scenario, title, abstract)

        main_idea = _extract_key_sentence(abstract) or _translate(article.title or "")
        method_summary = _extract_practical_sentence(abstract)
        takeaway = main_idea if not method_summary else method_summary

        passport = {
            "topic": topic,
            "topic_ru": topic_ru,
            "scenario": scenario,
            "title": title,
            "lead": lead,
            "abstract": abstract,
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
            passport["limitations"] = research_passport.limitations
            passport["study_type"] = research_passport.study_type
            passport["peer_reviewed"] = research_passport.peer_reviewed
            passport["sample_size"] = research_passport.sample_size
            confidence_map = {
                "high": 0.9,
                "moderate_high": 0.8,
                "moderate": 0.65,
                "limited": 0.45,
                "preliminary": 0.35,
                "weak": 0.25,
            }
            passport["confidence_score"] = research_passport.trust_level
            passport["evidence"] = research_passport.evidence_strength
        except Exception:
            evidence = "preliminary"
            if scenario in ("confirmation",):
                evidence = "moderate"
            if scenario == "review":
                evidence = "high"
            passport["evidence"] = evidence
            passport["evidence_strength"] = evidence
            passport["trust_level"] = 0.4
            passport["limitations"] = ""
            passport["study_type"] = "unknown"
            passport["peer_reviewed"] = article.is_peer_reviewed
            passport["sample_size"] = ""
            passport["confidence_score"] = 0.9 if evidence == "high" else 0.6 if evidence == "moderate" else 0.3

        practical_sentence = _extract_practical_sentence(abstract)
        practical_value = bool(practical_sentence and practical_sentence.strip())

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

        confidence = "low"
        if passport["evidence"] == "high":
            confidence = "high"
        elif passport["evidence"] == "moderate":
            confidence = "medium"

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
        passport["key_question"] = main_idea
        passport["main_conclusion"] = takeaway
        passport["method_summary"] = method_summary
        passport["takeaway"] = takeaway
        if "limitations" not in passport or not passport["limitations"]:
            passport["limitations"] = _pick(CAVEAT_PATTERNS)
        passport["related_works"] = []
        passport["knowledge_context"] = {}
        passport["novelty_score"] = 0.8 if novelty == "high" else 0.5 if novelty == "medium" else 0.2
        passport["confidence_score"] = 0.9 if confidence == "high" else 0.6 if confidence == "medium" else 0.3
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
        """Build logical structure (blocks) based on passport and scenario."""
        topic_ru = passport["topic_ru"]
        scenario = passport["scenario"]
        abstract = passport["abstract"]

        blocks: list[str] = [passport["title"], passport["lead"]]

        body_blocks = _build_body(topic_ru, scenario, abstract)
        blocks.extend(body_blocks)

        if scenario != "practical" and passport.get("practical_value"):
            blocks.extend(_build_practical_block(topic_ru, abstract))

        context_summary = _build_context_summary(passport)
        if context_summary:
            blocks.append(context_summary)

        evidence_strength = passport.get("evidence_strength", "")
        if evidence_strength:
            blocks.append(f"<b>Уровень доказательности:</b> {evidence_strength}.")

        limitations = passport.get("limitations", "")
        if limitations:
            blocks.append(f"<b>Ограничения:</b> {limitations}")
        elif passport.get("study_type") in ("unknown", "observational_study", "case_report"):
            blocks.append("<b>Ограничения:</b> Требуются дополнительные исследования для подтверждения выводов.")

        blocks.append(_build_why(topic_ru))
        blocks.append(_build_caveat())
        blocks.append(_build_source_line([passport["article"]]))

        return blocks

    def generate_text(self, passport: dict, structure: list[str]) -> str:
        """Render the final text from structure; this is the single point to unify style."""
        # Join with double newlines for readability (Telegraph-friendly)
        return "\n\n".join([s for s in structure if s])

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
            "title": f"Тема: {topic_ru}",
            "lead": f"Обзор ключевых исследований по теме {topic_ru.lower()} и то, что из этого стоит запомнить.",
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
        topic_ru = passport["topic_ru"]
        lines: list[str] = [
            f"Тема: {topic_ru}",
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
            passport.get("practical_sentence") or _pick(WHY_PATTERNS, topic=topic_ru),
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
        passport = self.analyze_cluster(topic, articles)
        topic_ru = passport["topic_ru"]
        title = f"Обзор новых данных по {topic_ru}"
        lead = f"Что важно знать о {topic_ru.lower()} сейчас"
        body = []
        # include key points from each article
        for a in articles:
            excerpt = _extract_practical_sentence(_translate(_clean_text(a.abstract or ""))) or _translate(a.title or "")
            body.append(f"• {excerpt} ({SOURCE_NAMES.get((a.source or '').lower(), a.source or 'источник')})")

        caveat = _pick(CAVEAT_PATTERNS)
        sources = ", ".join({SOURCE_NAMES.get((a.source or '').lower(), a.source or 'источник') for a in articles})
        lines = [title, "", lead, "", "\n".join(body), "", caveat, "", f"Основано на исследованиях: {sources}."]
        return "\n\n".join([l for l in lines if l])
