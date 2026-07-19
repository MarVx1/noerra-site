"""
Читает опубликованные статьи из noerra.db и строит статический
сайт-архив в docs/ (для GitHub Pages) — той же логикой рендера
(scripts/site_builder.py), которую отдельно использует
scripts/render_from_json.py на стороне GitHub Actions.

Дополнительно экспортирует те же статьи в data/published.json и
пытается закоммитить+запушить ЭТОТ файл (не docs/ — docs/ на GitHub
пересобирает сам Action из published.json, см. .github/workflows/build-site.yml).
noerra.db — личные данные и не в git; published.json содержит только то,
что и так уже публично в канале, коммитить его безопасно.

Ничего из этого не часть автопайплайна scheduler.py — отдельный ручной
запуск (вручную или по расписанию через Планировщик заданий Windows,
т.к. у GitHub Actions физически нет доступа к локальному noerra.db).

Запуск:
    PYTHONPATH=. python scripts/generate_site.py            # docs/ + published.json + git push
    PYTHONPATH=. python scripts/generate_site.py --no-git   # без git-шага (локальный предпросмотр)
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_builder  # noqa: E402

from adaptation.utils import _shorten, _clean_text, esc_preserve_own_tags  # noqa: E402
from classifier.classifier import get_topic_ru  # noqa: E402
from config.settings import SITE_BASE_URL  # noqa: E402
from database.db import get_published_articles_for_site  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_site")

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA_FILE = REPO_ROOT / "data" / "published.json"

# Символов в <meta name="description"> — стандартная безопасная длина,
# с запасом от лимита ~155-160, за которым Google обрезает сниппет.
DESCRIPTION_MAX_LEN = 155


def _row_to_article(row) -> dict:
    body_text = row["body"] or row["full_version"] or ""
    plain = _clean_text(body_text)
    date = (row["published_at"] or row["created_at"] or "")[:10]
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "topic": row["topic"] or "",
        "topic_ru": get_topic_ru(row["topic"] or ""),
        # esc_preserve_own_tags: body_text содержит наши собственные <i>/<b>
        # (аналогия, доказательность) вперемешку с сырым текстом, где могут
        # встретиться случайные "<"/">" ("p < .001") — та же обработка, что
        # применяется к post_text в scheduler.py при сборке поста в канал.
        "body_html": esc_preserve_own_tags(body_text),
        "description": _shorten(plain, DESCRIPTION_MAX_LEN),
        "source_url": row["source_url"] or "",
        "telegraph_url": row["telegraph_url"],
        "date": date or "1970-01-01",
    }


def load_articles() -> list[dict]:
    rows = get_published_articles_for_site()
    return [_row_to_article(r) for r in rows]


def _git(*args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        ok = result.returncode == 0
        return ok, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def export_and_push(articles: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    logger.info("Записан %s (%s статей)", DATA_FILE, len(articles))

    # Сеть/отсутствие remote/незакоммиченные конфликты не должны ронять
    # скрипт — это звено А, оно может молча не сработать (например,
    # компьютер офлайн), следующий плановый запуск попробует снова.
    ok, out = _git("add", str(DATA_FILE.relative_to(REPO_ROOT)))
    if not ok:
        logger.warning("git add не удался: %s", out)
        return

    ok, out = _git("diff", "--cached", "--quiet")
    if ok:
        logger.info("published.json не изменился — коммитить нечего")
        return

    ok, out = _git(
        "commit", "-m",
        f"Update published.json ({len(articles)} articles)\n\nAutomated export from scripts/generate_site.py",
    )
    if not ok:
        logger.warning("git commit не удался: %s", out)
        return
    logger.info("Закоммичено: %s", out.splitlines()[0] if out else "OK")

    ok, out = _git("push")
    if not ok:
        logger.warning("git push не удался (нет remote/сети/прав?) — %s", out)
        return
    logger.info("Запушено успешно")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-git", action="store_true", help="Не делать git add/commit/push")
    args = parser.parse_args()

    articles = load_articles()
    logger.info("Опубликованных статей: %s", len(articles))

    stats = site_builder.build_site(articles, str(DOCS_DIR), SITE_BASE_URL)
    logger.info("Сайт собран: %s страниц статей в %s", stats["pages"], stats["output_dir"])

    if args.no_git:
        export_path_only(articles)
    else:
        export_and_push(articles)

    print(f"\nГотово: {len(articles)} статей -> {DOCS_DIR}")
    print(f"base_url = {SITE_BASE_URL}")
    if SITE_BASE_URL.startswith("https://example.github.io"):
        print(
            "\nВНИМАНИЕ: SITE_BASE_URL не настроен (используется заглушка) — "
            "canonical-ссылки и sitemap.xml указывают на example.github.io. "
            "Задайте SITE_BASE_URL в .env на реальный адрес GitHub Pages и "
            "перезапустите скрипт перед реальным деплоем."
        )
    return 0


def export_path_only(articles: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    logger.info("Записан %s (%s статей), git-шаг пропущен (--no-git)", DATA_FILE, len(articles))


if __name__ == "__main__":
    sys.exit(main())
