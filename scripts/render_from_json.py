"""
Рендерит docs/ из data/published.json — без noerra.db, без сети, без
единой зависимости из requirements.txt (aiogram/deep-translator/...).
Это то, что запускает .github/workflows/build-site.yml на серверах
GitHub: там нет и не может быть доступа к локальному noerra.db (см.
докстринг scripts/generate_site.py), поэтому вся логика похода в БД
живёт отдельно, а этот скрипт только рендерит уже готовые данные —
той же функцией site_builder.build_site(), которой пользуется и
generate_site.py локально.

Запуск:
    python scripts/render_from_json.py
    python scripts/render_from_json.py --data path/to/published.json --base-url https://foo.github.io/bar/
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_builder  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_FILE = REPO_ROOT / "data" / "published.json"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs"

# Тот же плейсхолдер, что в config/settings.py:SITE_BASE_URL — дублируется
# здесь намеренно, а не импортируется, чтобы этот скрипт оставался
# полностью независимым от остального проекта (см. докстринг выше).
# Реальное значение приходит через --base-url/SITE_BASE_URL в CI.
DEFAULT_BASE_URL = "https://example.github.io/noerra-bot/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DEFAULT_DATA_FILE))
    parser.add_argument("--out", default=str(DEFAULT_DOCS_DIR))
    parser.add_argument("--base-url", default=os.environ.get("SITE_BASE_URL") or DEFAULT_BASE_URL)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/") + "/"

    with open(args.data, encoding="utf-8") as f:
        articles = json.load(f)

    stats = site_builder.build_site(articles, args.out, base_url)
    print(f"Rendered {stats['pages']} article pages into {stats['output_dir']} (base_url={base_url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
