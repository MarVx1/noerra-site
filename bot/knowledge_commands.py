# ============================================================
#  bot/knowledge_commands.py — команды Knowledge Core (/knowledge,
#  /claims, /myths, /questions, /audit, /route, /reasoning, /model,
#  /graph, /memory, /timeline)
#
#  Вынесено из bot/bot.py: эти 11 команд самодостаточны (сами делают
#  локальные импорты domain.knowledge.*/database.db) и не покрыты
#  тестами через bot.bot — перенос не затрагивает ни один из 47
#  тестов в tests/test_bot.py.
# ============================================================

import asyncio
import logging

from aiogram.filters import Command
from aiogram.types import Message

from bot.bot import dp, is_admin, html_escape
from classifier.classifier import get_topic_ru
from database.db import get_claims_for_topic, get_open_questions, get_myths

logger = logging.getLogger(__name__)


@dp.message(Command("knowledge"))
async def cmd_knowledge(message: Message):
    if not is_admin(message.from_user.id):
        return

    from intelligence.knowledge_audit import audit_all_topics

    audits = audit_all_topics(stale_days=30)
    if not audits:
        await message.answer("📭 В базе знаний пока нет тем.")
        return

    lines = ["🧠 <b>Knowledge Core</b>\n"]
    for a in audits[:10]:
        topic_ru = get_topic_ru(a.topic)
        stale_icon = "⚠️" if a.is_stale else "✅"
        contra_icon = "🔥" if a.has_contradictions else ""
        lines.append(
            f"{stale_icon} <b>{topic_ru}</b> ({a.topic})\n"
            f"   Claims: {a.claims_count} | Confidence: {a.confidence:.2f} | "
            f"Level: {a.consensus_level}\n"
            f"   Open Q: {a.open_questions_count} | Myths: {a.myths_count} {contra_icon}\n"
            f"   <i>{html_escape(a.recommendation)}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("claims"))
async def cmd_claims(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /claims &lt;тема&gt;\nНапример: /claims sleep", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    claims = get_claims_for_topic(topic, limit=20)
    if not claims:
        await message.answer(f"📭 Нет утверждений для темы «{html_escape(topic)}».")
        return

    lines = [f"🔬 <b>Утверждения: {get_topic_ru(topic)}</b>\n"]
    for c in claims[:15]:
        level = c["consensus_level"] or "unknown"
        conf = c["confidence"] or 0
        support = c["support_count"] or 0
        contradict = c["contradict_count"] or 0
        lines.append(
            f"• {html_escape(c['claim_text'][:200])}\n"
            f"  <i>Consensus: {level} | Conf: {conf:.2f} | +{support}/-{contradict}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("myths"))
async def cmd_myths(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /myths &lt;тема&gt;\nНапример: /myths dopamine", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    myths = get_myths(topic, limit=10)
    if not myths:
        await message.answer(f"📭 Нет мифов для темы «{html_escape(topic)}».")
        return

    lines = [f"🚫 <b>Мифы: {get_topic_ru(topic)}</b>\n"]
    for m in myths:
        lines.append(
            f"• <b>Миф:</b> {html_escape(m['myth_text'][:200])}\n"
            f"  <b>Коррекция:</b> {html_escape(m['correction'] or '—')[:200]}\n"
            f"  <i>{html_escape(m['evidence_summary'] or '')}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("questions"))
async def cmd_questions(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /questions &lt;тема&gt;\nНапример: /questions sleep", parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    questions = get_open_questions(topic, limit=10)
    if not questions:
        await message.answer(f"📭 Нет открытых вопросов для темы «{html_escape(topic)}».")
        return

    lines = [f"❓ <b>Открытые вопросы: {get_topic_ru(topic)}</b>\n"]
    for q in questions:
        lines.append(f"• {html_escape(q['question'][:300])}\n  <i>Status: {q['current_status']}</i>\n")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("audit"))
async def cmd_audit(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("🔍 Запуск аудита базы знаний... Это может занять до 30 секунд.")

    # Запускаем тяжёлый аудит в отдельном потоке
    async def run_audit():
        from intelligence.knowledge_audit import audit_all_topics, detect_knowledge_debt, track_confidence_drift

        audits = audit_all_topics(stale_days=30)
        if not audits:
            return "📭 Аудит пуст — в базе нет тем."

        stale = [a for a in audits if a.is_stale]
        contradictions = [a for a in audits if a.has_contradictions]
        debt = detect_knowledge_debt(stale_days=30)

        lines = [
            "🔍 <b>Аудит базы знаний</b>\n",
            f"Всего тем: {len(audits)}",
            f"Устаревших: {len(stale)}",
            f"С противоречиями: {len(contradictions)}",
            f"Knowledge Debt: {len(debt)}\n",
        ]

        if stale:
            lines.append("⚠️ <b>Устаревшие темы:</b>")
            for a in stale[:5]:
                lines.append(f"  • {get_topic_ru(a.topic)} ({a.topic}) — {a.last_updated}")
            lines.append("")

        if debt:
            lines.append("📋 <b>Knowledge Debt:</b>")
            for d in debt[:5]:
                lines.append(f"  • {get_topic_ru(d['topic'])} — {d['new_articles']} новых статей, last: {d['last_knowledge_update']}")
            lines.append("")

        # Confidence drift for first 3 active topics
        drifts_found = False
        for a in audits[:3]:
            if a.claims_count > 0:
                drifts = track_confidence_drift(a.topic)
                significant = [d for d in drifts if d.direction != "stable"]
                if significant:
                    if not drifts_found:
                        lines.append("📉 <b>Confidence Drift:</b>")
                        drifts_found = True
                    for d in significant[:3]:
                        emoji = "📈" if d.direction == "increased" else "📉"
                        lines.append(
                            f"  {emoji} {get_topic_ru(d.topic)}: "
                            f"{d.previous_confidence:.2f} → {d.current_confidence:.2f} "
                            f"({d.direction}, Δ={d.delta:+.2f})"
                        )

        if not drifts_found and not stale and not debt:
            lines.append("✅ База знаний в хорошем состоянии.")

        return "\n".join(lines)

    try:
        result = await asyncio.to_thread(run_audit)
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        await message.answer(f"❌ Ошибка аудита: {e}", parse_mode="HTML")


@dp.message(Command("route"))
async def cmd_route(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.routes import list_routes, get_route, route_to_text, suggest_route_for_topic

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        routes = list_routes()
        if not routes:
            await message.answer("📭 Маршруты изучения пока не настроены.")
            return
        lines = ["📚 <b>Маршруты изучения</b>\n"]
        for r in routes:
            lines.append(f"• <b>{r['title']}</b> ({r['time']})\n  {r['description']}\n  /route {r['id']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    route_id = parts[1].strip()
    route = get_route(route_id)
    if not route:
        route = suggest_route_for_topic(route_id)
    if not route:
        await message.answer(f"Маршрут «{html_escape(route_id)}» не найден.")
        return

    await message.answer(route_to_text(route), parse_mode="HTML")


@dp.message(Command("reasoning"))
async def cmd_reasoning(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /reasoning &lt;тема&gt;\n"
            "Показывает reasoning chain для топ-claim по теме.",
            parse_mode="HTML",
        )
        return

    topic = parts[1].strip().lower()
    claims = get_claims_for_topic(topic, limit=5)
    if not claims:
        await message.answer(f"📭 Нет утверждений для темы «{html_escape(topic)}».")
        return

    from domain.knowledge.reasoning import build_reasoning_chain, chain_to_text
    from database.db import get_consensus_for_topic

    top_claim = claims[0]
    consensus_rows = get_consensus_for_topic(topic, limit=10)

    consensus = {}
    for cs in consensus_rows:
        if cs["claim_id"] == top_claim["id"]:
            consensus = dict(cs)
            break

    evidence = [dict(c) for c in claims]
    chain = build_reasoning_chain(
        topic=topic,
        claim_text=top_claim["claim_text"],
        evidence=evidence,
        consensus=consensus,
    )

    await message.answer(chain_to_text(chain), parse_mode="HTML")


@dp.message(Command("model"))
async def cmd_model(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        from domain.knowledge.mental_models import list_mental_models
        models = list_mental_models()
        if not models:
            await message.answer("📭 Модели понимания пока не настроены.")
            return
        lines = ["🧩 <b>Модели понимания</b>\n"]
        for m in models:
            lines.append(f"• <b>{m['topic_ru']}</b> ({m['topic']})\n  {m['title']}\n  /model {m['topic']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    from domain.knowledge.mental_models import get_mental_model, model_to_text
    topic = parts[1].strip().lower()
    model = get_mental_model(topic)
    if not model:
        await message.answer(f"Модель для темы «{html_escape(topic)}» не найдена.")
        return

    await message.answer(model_to_text(model), parse_mode="HTML")


@dp.message(Command("graph"))
async def cmd_graph(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /graph &lt;тема&gt;\n"
            "Показывает граф понимания по теме.",
            parse_mode="HTML",
        )
        return

    topic = parts[1].strip().lower()
    await message.answer(f"🕸 Строю граф для темы «{html_escape(topic)}»...")

    async def build_graph():
        from domain.knowledge.graph import build_graph_from_claims, graph_to_text
        from database.db import get_consensus_for_topic

        claims = get_claims_for_topic(topic, limit=20)
        if not claims:
            return f"📭 Нет данных для графа по теме «{html_escape(topic)}»."

        consensus = get_consensus_for_topic(topic, limit=20)
        open_qs = get_open_questions(topic, limit=10)
        myths = get_myths(topic, limit=10)

        claims_list = [dict(c) for c in claims]
        consensus_list = [dict(c) for c in consensus]
        questions_list = [row["question"] for row in open_qs]
        myths_list = [row["myth_text"] for row in myths]

        graph = build_graph_from_claims(
            topic=topic,
            claims=claims_list,
            consensus=consensus_list,
            myths=myths_list,
            open_questions=questions_list,
        )

        return graph_to_text(graph, topic)

    try:
        result = await asyncio.to_thread(build_graph)
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Graph build failed: {e}")
        await message.answer(f"❌ Ошибка построения графа: {e}", parse_mode="HTML")


@dp.message(Command("memory"))
async def cmd_memory(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.editorial_memory import build_editorial_memory, memory_to_text
    from database.db import get_editorial_decisions

    decisions_rows = get_editorial_decisions(limit=100)
    if not decisions_rows:
        await message.answer("📭 Редакционная память пуста — пока нет решений.")
        return

    decisions = [dict(row) for row in decisions_rows]
    memory = build_editorial_memory(decisions)
    memory.analyze_patterns()

    await message.answer(memory_to_text(memory), parse_mode="HTML")


@dp.message(Command("timeline"))
async def cmd_timeline(message: Message):
    if not is_admin(message.from_user.id):
        return

    from domain.knowledge.timeline import get_timeline, list_timelines, timeline_to_text

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        timelines = list_timelines()
        if not timelines:
            await message.answer("📭 Временные шкалы пока не настроены.")
            return
        lines = ["📜 <b>История развития знаний</b>\n"]
        for t in timelines:
            lines.append(f"• <b>{t['topic_ru']}</b> ({t['topic']}): {t['events']} событий\n  /timeline {t['topic']}\n")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    topic = parts[1].strip().lower()
    timeline = get_timeline(topic)
    if not timeline:
        await message.answer(f"Временная шкала для темы «{html_escape(topic)}» не найдена.")
        return

    await message.answer(timeline_to_text(timeline), parse_mode="HTML")
