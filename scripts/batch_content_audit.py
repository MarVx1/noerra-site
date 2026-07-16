"""
Батч-прогон EditorialEngine по всем статьям в noerra.db локально —
без отправки в Telegram и без Telegraph (см. дополнение №2 к ТЗ
"редакционное качество", п.2.1-2.2).

Экономит на живых публикациях: раньше цикл поиска дефектов был
"одна публикация -> один баг -> ждать следующую", а тут сразу весь
корпус за один прогон.

Исключает статьи со status='off_topic' — они (topic='unknown') никогда
не доходили до реального пайплайна генерации, тестировать генератор на
них бессмысленно (см. вывод в конце про масштаб выборки).

Сохраняет сгенерированные заголовки/лиды в drafts ПО ХОДУ обработки —
так же, как это делает реальный Pipeline.run_for_article() — иначе
anti-repeat в _build_title()/_build_lead() не видит статьи, обработанные
раньше в этом же батче, и коллизии между ними ложно считались бы более
частыми, чем в реальном проде (topic НЕ меняется — иначе anti-repeat
не увидел бы ни реальную историю, ни другие статьи батча по той же
теме). Никакой публикации, Telegraph/Telegram не трогает. Все созданные
этим скриптом draft-строки помечены через format="__batch_audit__" и в
конце прогона удаляются (см. cleanup в конце main()) — в БД ничего не
остаётся.

Run:
    python scripts/batch_content_audit.py
"""
import json
import os
import sys
import io
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from database.db import get_conn, save_draft
from parsers.base import RawArticle
from adaptation.editorial_engine import EditorialEngine
from adaptation.content_audit import audit_text, check_title_or_lead_repeats_recent
from adaptation.utils import esc_preserve_own_tags, _shorten_by_paragraphs

_BATCH_MARKER = "__batch_audit__"


def main():
    engine = EditorialEngine()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE status != 'off_topic' ORDER BY id"
        ).fetchall()

    results = []
    failed = []
    batch_draft_ids = []

    for row in rows:
        article = RawArticle(
            title=row["title"], url=row["url"], abstract=row["abstract"] or "",
            source=row["source"],
        )
        try:
            passport = engine.analyze(article, row["topic"])
            structure = engine.build_structure(passport)
            text = engine.generate_text(passport, structure)
        except Exception as e:
            failed.append({"article_id": row["id"], "error": str(e)})
            continue

        # anti-repeat УЖЕ сработал внутри analyze() (сверился с drafts
        # на момент вызова) — этот check лишь фиксирует итог для отчёта,
        # не влияет на сам выбор заголовка/лида.
        problems = audit_text(text)
        problems.extend(check_title_or_lead_repeats_recent(
            row["topic"], passport.get("title", ""), passport.get("lead", "")
        ))

        # Реальный опубликованный post_text строится НЕ из generate_text()
        # напрямую, а через отдельную обрезку в scheduler.py (visible_text =
        # _shorten_by_paragraphs(pub.body, 700) + ссылка на Telegraph) —
        # audit_text(text) выше эту обрезку не видит вообще, а именно в ней
        # нашёлся реальный live-баг (article id=635, 2026-07-16: сгенерированный
        # текст был полным, а опубликованный пост обрывался на переходе).
        # Пересобираем post_text той же формулой, чтобы батч ловил и это.
        parts = [p for p in text.split("\n\n") if p.strip()]
        body = "\n\n".join(parts[1:]) if len(parts) > 1 else ""
        visible_text = _shorten_by_paragraphs(body, 700) if body else ""
        if visible_text:
            post_text = f"{esc_preserve_own_tags(visible_text)} 👇\n\n📘 <a href='TELEGRAPH_URL'>Читать полностью</a>"
            post_text_problems = audit_text(post_text)
            problems.extend(f"[post_text] {p}" for p in post_text_problems)

        results.append({
            "article_id": row["id"],
            "topic": row["topic"],
            "status": row["status"],
            "scenario": passport.get("scenario"),
            "title": passport.get("title", ""),
            "problems": problems,
            "text": text,
        })

        # Сохраняем В ТОМ ЖЕ ПОРЯДКЕ, что реальный Pipeline.run_for_article() —
        # иначе anti-repeat не увидит статьи, уже обработанные раньше в
        # этом же прогоне, и коллизии внутри батча были бы переоценены.
        draft_id = save_draft(
            row["id"], passport.get("title", ""), passport.get("lead", ""),
            "", "", text, row["source"] or "", row["topic"],
            _BATCH_MARKER, 0.0, "general",
        )
        batch_draft_ids.append(draft_id)

    out_path = "scripts/output/batch_audit_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_articles_in_db": len(rows),
            "processed": len(results),
            "failed": failed,
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    flagged = [r for r in results if r["problems"]]
    print(f"Всего статей в БД (status != off_topic): {len(rows)}")
    print(f"Обработано: {len(results)} (failed={len(failed)})")
    print(f"С проблемами (content_audit + anti-repeat): {len(flagged)}")
    print(f"Результат сохранён в {out_path}")
    print()

    by_problem = defaultdict(int)
    for r in flagged:
        for p in r["problems"]:
            by_problem[p] += 1
    print("Разбивка по типам проблем:")
    for problem, count in sorted(by_problem.items(), key=lambda x: -x[1]):
        print(f"  {count:3d}  {problem}")

    print()
    print("Примеры (до 20):")
    for r in flagged[:20]:
        print(f"[{r['article_id']}] {r['topic']} ({r['scenario']}): {r['problems']}")

    if failed:
        print()
        print("Ошибки генерации:")
        for f in failed[:10]:
            print(f"  [{f['article_id']}] {f['error']}")

    # Cleanup: батч не должен оставлять следов в drafts — иначе следующий
    # запуск anti-repeat увидит "фантомные" заголовки из dry-run'а.
    with get_conn() as conn:
        placeholders = ",".join("?" * len(batch_draft_ids))
        deleted = conn.execute(
            f"DELETE FROM drafts WHERE id IN ({placeholders})", batch_draft_ids
        ).rowcount if batch_draft_ids else 0
    print()
    print(f"Cleanup: удалено {deleted} временных draft-строк батча (из {len(batch_draft_ids)} созданных).")


if __name__ == "__main__":
    main()
