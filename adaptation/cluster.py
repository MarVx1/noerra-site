"""Редакционный генератор кластерного поста по теме."""

import logging
import re
from parsers.base import RawArticle
from parsers.youtube import format_youtube_block
from classifier.classifier import get_topic_emoji, get_topic_ru
from adaptation.utils import _translate, _extract_key_sentence, _clean_text, esc
from adaptation.editorial_engine import EditorialEngine
from domain.knowledge.mental_models import get_model_brief
from intelligence.research_analysis.evidence_classifier import (
    detect_study_type, classify_evidence_strength, is_animal_or_invitro_study,
)
from classifier.classifier import get_topic_case

logger = logging.getLogger(__name__)

SOURCE_NAMES = {
    "pubmed": "PubMed",
    "arxiv": "arXiv",
    "cyberleninka": "CyberLeninka",
    "rss": "RSS",
    "youtube": "YouTube",
}

INTRO_TEXT = {
    "ADHD": "Почему сегодня стоит говорить о СДВГ не как о невнимательности, а как о работе мозга?",
    "dopamine": "Как дофамин влияет на мотивацию и память — новые исследования дают ответ.",
    "sleep": "Почему сон перестаёт быть только отдыхом и превращается в инструмент продуктивности?",
    "stress": "Хронический стресс меняет не только настроение, но и сам мозг. Что об этом говорят исследования.",
    "anxiety": "Тревожность давно перестала быть только эмоцией. На неё смотрят как на физиологическую реакцию мозга.",
    "cognition": "Память, внимание и мышление — всё это сегодня связали с одним общим процессом. Разбираемся, что нового.",
    "neuroplasticity": "Мозг учится постоянно. Новые данные объясняют, что именно происходит, когда мы тренируемся.",
    "neuroscience": "Нейронаука снова показывает, как устроен мозг: от нейронов до поведения.",
    "psychology": "Психология поведения — не про слова, а про то, как мы выбираем действия. Вот что важно знать сейчас.",
}

HASHTAGS = {
    "ADHD":            "#СДВГ #внимание #нейронаука",
    "dopamine":        "#дофамин #мотивация #мозг",
    "sleep":           "#сон #здоровье #мозг",
    "stress":          "#стресс #здоровье #нейронаука",
    "anxiety":         "#тревожность #психология #мозг",
    "cognition":       "#когниция #память #обучение",
    "neuroplasticity": "#нейропластичность #мозг #обучение",
    "neuroscience":    "#нейронаука #мозг #наука",
    "psychology":      "#психология #поведение #наука",
}


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _source_label(article: RawArticle) -> str:
    return SOURCE_NAMES.get((article.source or "").lower(), article.source or "Источник")


def _snippet(article: RawArticle) -> str:
    abstract = _clean_text(article.abstract)
    abstract_ru = _translate(abstract) if abstract else ""
    if not abstract_ru:
        return _translate(article.title)
    key = _extract_key_sentence(abstract_ru)
    if key:
        return key
    sentences = _split_sentences(abstract_ru)
    return sentences[0] if sentences else _translate(article.title)


def _headline(topic: str, count: int) -> str:
    if count <= 1:
        return f"Новый взгляд на {get_topic_case(topic, 'acc_lower')}"
    return f"Что важно знать о {get_topic_case(topic, 'prep_lower')} сегодня"


def _collect_sources(articles: list[RawArticle]) -> str:
    sources = [SOURCE_NAMES.get((a.source or "").lower(), a.source or "источник") for a in articles]
    unique = []
    for src in sources:
        if src not in unique:
            unique.append(src)
    return ", ".join(unique)


def _evidence_badge(articles: list[RawArticle]) -> str:
    """Эмодзи-бейдж уровня доказательности на основе evidence_strength."""
    if not articles:
        return ""
    a = articles[0]
    text = f"{a.title} {a.abstract or ''}"
    study_type = detect_study_type(text, title=a.title or "")
    evidence = classify_evidence_strength(study_type, a.is_peer_reviewed, is_animal_or_invitro_study(text))
    badges = {
        "high": "🔬 Сильная доказательность (метаанализ/RCT)",
        "moderate_high": "🔬 Сильная доказательность (RCT)",
        "moderate": "📝 Предварительные данные",
        "limited": "📝 Предварительные данные",
        "preliminary": "💭 Гипотеза/мнение",
        "weak": "💭 Гипотеза/мнение",
    }
    return badges.get(evidence, "")


def build_cluster_post(
    topic: str,
    articles: list[RawArticle],
    youtube_article: RawArticle | None = None,
    telegraph_url: str = "TELEGRAPH_URL",
) -> str:
    emoji = get_topic_emoji(topic)
    topic_ru = get_topic_ru(topic)
    headline = _headline(topic, len(articles))
    intro = INTRO_TEXT.get(topic, f"Что нового в теме «{get_topic_case(topic, 'nom_lower')}»?")
    hashtags = HASHTAGS.get(topic, "#наука #мозг")

    lines = [
        f"{emoji} <b>{headline}</b>",
        "",
        esc(intro),
        "",
    ]

    engine = EditorialEngine()
    # Use engine to produce a compact Telegram cluster post via Publication
    if articles:
        pub = engine.create_publication_for_cluster(topic, articles)
        tg_title = pub.title
        tg_lead = pub.short_version
        lines = [f"{emoji} <b>{tg_title}</b>", "", esc(tg_lead), ""]
        if len(articles) == 1:
            a = articles[0]
            lines += [esc(_snippet(a)), "", f"{_source_label(a)}"]
        else:
            lines.append("В подборке:")
            for a in articles[:3]:
                lines.append(f"• <b>{_source_label(a)}:</b> {esc(_snippet(a))}")
            lines.append("")

    # Индикатор уровня доказательности
    badge = _evidence_badge(articles)
    if badge:
        lines.append(badge)
        lines.append("")

    if youtube_article:
        # Prefer engine's youtube block if available
        try:
            yt_block = engine.generate_youtube_block(youtube_article)
        except Exception:
            yt_block = format_youtube_block(youtube_article)
        if yt_block:
            lines.append(yt_block)
            lines.append("")

    lines += [
        "<b>Почему это важно</b>",
        esc("Эти работы помогают понять, какие выводы уже можно считать полезными, а какие — пока стоит обсуждать дальше."),
        "",
    ]

    # Mental model brief — correct understanding framework
    model_brief = get_model_brief(topic)
    if model_brief:
        lines += [model_brief, ""]

    # Confidence drift indicator
    try:
        from intelligence.knowledge_audit import track_confidence_drift
        drifts = track_confidence_drift(topic)
        significant = [d for d in drifts if d.direction != "stable" and abs(d.delta) >= 0.15]
        if significant:
            lines.append("<b>Динамика доверия:</b>")
            for d in significant[:2]:
                emoji = "📈" if d.direction == "increased" else "📉"
                lines.append(
                    f"{emoji} {d.claim_text[:80]}: "
                    f"{d.previous_confidence:.2f} → {d.current_confidence:.2f}"
                )
            lines.append("")
    except Exception:
        pass

    if telegraph_url and telegraph_url != "TELEGRAPH_URL":
        # 👇 в конец строки перед ссылкой — визуальный указатель "дальше
        # переход по ссылке" (2026-07-16, см. тот же фикс в editorial.py/
        # scheduler.py).
        lines += [
            esc("Полный материал доступен в расширенной версии.") + " 👇",
            f"📘 {telegraph_url}",
            "",
        ]

    lines += [
        esc(f"Основано на исследованиях: {_collect_sources(articles)}."),
        "",
        hashtags,
    ]

    return "\n".join(lines)


def build_telegraph_cluster(
    topic: str,
    articles: list[RawArticle],
    youtube_article: RawArticle | None = None,
) -> str:
    """Generate telegraph-style cluster content via the EditorialEngine."""
    engine = EditorialEngine()
    return engine.generate_cluster_text(topic, articles)
