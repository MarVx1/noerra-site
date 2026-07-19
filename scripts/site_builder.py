"""
Чистый рендер статического сайта-архива — только stdlib, никаких
импортов из остального проекта (adaptation/database/config).

Причина: этот модуль используется ДВУМЯ путями с разным окружением —
scripts/generate_site.py (локально, полный venv проекта, доступ к
noerra.db) и scripts/render_from_json.py (GitHub Actions, только
data/published.json, без БД и без тяжёлых зависимостей вроде aiogram/
deep-translator). Чтобы Action не тянул requirements.txt целиком ради
рендера HTML, вся логика форматирования (эскейпинг, обрезка описания)
выполняется ОДИН раз на стороне generate_site.py и попадает в JSON уже
готовой — этот файл только собирает готовые строки в HTML/XML.

Каждая статья — dict с полями:
    id            int
    title         str  — заголовок (уже готовый для <title>/<h1>)
    topic_ru      str  — русское название темы, для группировки на индексе
    body_html     str  — текст статьи, абзацы разделены "\\n\\n", инлайн
                          <b>/<i> уже безопасно проэкранированы вызывающей
                          стороной (см. adaptation/utils.py:esc_preserve_own_tags)
    description   str  — короткое plain-text описание для <meta description>
    source_url    str  — ссылка на оригинал источника (PubMed/arXiv/...)
    telegraph_url str | None — ссылка на исходный пост в Telegraph, опционально
    date          str  — ISO-дата публикации, "YYYY-MM-DD"
"""

import html
import os
import shutil

CHANNEL_URL = "https://t.me/noerra_publishes"
SITE_TITLE = "Noerra — научпоп-архив"
SITE_DESCRIPTION = "Разборы научных статей о мозге, сне, стрессе, СДВГ и когнитивной науке простым языком."


def slug_for(article: dict) -> str:
    """Имя файла статьи. Специально не транслитерируем русский заголовок в
    URL — заголовок/H1/текст важнее для SEO, чем сам слаг, а транслитерация
    кириллицы добавляет реальный риск неоднозначностей (омографы, разная
    транслитерация е/ё/й у разных библиотек) ради маргинальной пользы.
    id гарантирует уникальность и стабильность ссылки при регенерации."""
    return f"article-{article['id']}.html"


def _paragraphs_html(body_html: str) -> str:
    parts = [p.strip() for p in (body_html or "").split("\n\n") if p.strip()]
    return "\n".join(f"    <p>{p}</p>" for p in parts)


_PAGE_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,500;0,600;1,400&family=Inter:wght@400;500;600&display=swap');
    :root {
        --bg: #0d1e21; --bg-raised: #132a2e; --border: #22403f;
        --text: #e9ece9; --text-dim: #9fb3ae; --text-faint: #6b8380;
        --gold: #c9974a; --gold-bright: #e3bd7e;
    }
    * { box-sizing: border-box; }
    body { font: 16px/1.6 Inter, -apple-system, Segoe UI, Roboto, sans-serif;
           max-width: 700px; margin: 0 auto; padding: 48px 20px 64px;
           color: var(--text); background: var(--bg); }
    a { color: var(--gold-bright); text-decoration: none; border-bottom: 1px solid rgba(201,151,74,0.35); }
    a:hover { border-bottom-color: var(--gold-bright); }
    h1 { font-family: 'Newsreader', Georgia, serif; font-weight: 600;
         font-size: 2em; line-height: 1.25; letter-spacing: -0.01em; margin-bottom: 0.4em; }
    h1 a { border-bottom: none; color: var(--text); }
    .meta { color: var(--text-dim); font-size: 0.95em; margin-bottom: 2.5em; }
    .meta a { color: var(--gold); }
    .topic-tag { display: inline-block; background: rgba(201,151,74,0.12); color: var(--gold);
                 border-radius: 10px; padding: 2px 10px; font-size: 0.85em; }
    footer { margin-top: 3em; padding-top: 1.2em; border-top: 1px solid var(--border);
             font-size: 0.9em; color: var(--text-faint); }
    footer a { display: inline-block; margin-right: 1.2em; color: var(--gold); }
    ul.article-list { list-style: none; padding: 0; }
    ul.article-list li { padding: 14px 0; border-bottom: 1px solid var(--border); }
    ul.article-list a { font-family: 'Newsreader', Georgia, serif; font-weight: 500;
                         font-size: 1.08em; color: var(--text); border-bottom: none; }
    ul.article-list a:hover { color: var(--gold-bright); }
    ul.article-list .date { color: var(--text-faint); font-size: 0.85em; margin-left: 4px; }
    h2.topic-heading { font-family: 'Newsreader', Georgia, serif; font-weight: 600;
                        margin-top: 2.2em; font-size: 1.3em; color: var(--gold-bright); }
"""


def render_article_html(article: dict, base_url: str) -> str:
    canonical = f"{base_url}articles/{slug_for(article)}"
    title = html.escape(article["title"])
    description = html.escape(article["description"])
    topic_ru = html.escape(article.get("topic_ru") or "")
    source_url = html.escape(article["source_url"] or "", quote=True)
    telegraph_url = article.get("telegraph_url")

    telegraph_line = (
        f'      <a href="{html.escape(telegraph_url, quote=True)}">Открыть в Telegraph</a>\n'
        if telegraph_url else ""
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<style>{_PAGE_CSS}</style>
</head>
<body>
  <p><a href="../index.html">&larr; Все статьи</a></p>
  <article>
    <p class="meta"><span class="topic-tag">{topic_ru}</span> &middot; {article['date']}</p>
    <h1>{title}</h1>
{_paragraphs_html(article['body_html'])}
  </article>
  <footer>
      <a href="{source_url}">Источник</a>
{telegraph_line}      <a href="{html.escape(CHANNEL_URL, quote=True)}">Канал Noerra в Telegram</a>
  </footer>
</body>
</html>
"""


def render_index_html(articles: list[dict], base_url: str) -> str:
    by_topic: dict[str, list[dict]] = {}
    for a in articles:
        by_topic.setdefault(a.get("topic_ru") or "Наука", []).append(a)

    sections = []
    for topic_ru in sorted(by_topic):
        items = by_topic[topic_ru]
        rows = "\n".join(
            f'    <li><a href="articles/{slug_for(a)}">{html.escape(a["title"])}</a> '
            f'<span class="date">{a["date"]}</span></li>'
            for a in items
        )
        sections.append(
            f'  <h2 class="topic-heading">{html.escape(topic_ru)} ({len(items)})</h2>\n'
            f'  <ul class="article-list">\n{rows}\n  </ul>'
        )
    body = "\n".join(sections) if sections else "  <p>Пока нет опубликованных статей.</p>"

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(SITE_TITLE)}</title>
<meta name="description" content="{html.escape(SITE_DESCRIPTION)}">
<link rel="canonical" href="{base_url}index.html">
<style>{_PAGE_CSS}</style>
</head>
<body>
  <h1>{html.escape(SITE_TITLE)}</h1>
  <p class="meta">{html.escape(SITE_DESCRIPTION)} &mdash; <a href="{html.escape(CHANNEL_URL, quote=True)}">канал в Telegram</a></p>
{body}
</body>
</html>
"""


def render_sitemap_xml(articles: list[dict], base_url: str) -> str:
    urls = [f"  <url><loc>{base_url}index.html</loc></url>"]
    for a in articles:
        urls.append(
            f"  <url><loc>{base_url}articles/{slug_for(a)}</loc>"
            f"<lastmod>{a['date']}</lastmod></url>"
        )
    body = "\n".join(urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def render_robots_txt(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n"


# Единственная подпапка и единственные файлы верхнего уровня output_dir,
# которыми владеет сайт. build_site() трогает СТРОГО их и ничего больше —
# output_dir это docs/ в корне репозитория, а там уже жила docs/architecture/
# (ADR 0001 и другая документация проекта, см. adr-0001-rule-based-no-llm) —
# первая версия этого файла чистила output_dir целиком и снесла её при
# первом же прогоне (2026-07-19, поймано до коммита). Раз в docs/ может
# лежать что угодно не имеющее отношения к сайту, clear-логика обязана
# быть списком "что удалить", а не "что оставить".
_OWNED_SUBDIR = "articles"
_OWNED_TOP_LEVEL_FILES = ("index.html", "sitemap.xml", "robots.txt", ".nojekyll")


def clear_output_dir(output_dir: str) -> None:
    """Удаляет только то, чем владеет сайт (см. _OWNED_*) — идемпотентность
    для статей, выпавших из выборки, без риска задеть посторонние файлы,
    оказавшиеся в output_dir не по вине этого скрипта."""
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        return
    owned_dir = os.path.join(output_dir, _OWNED_SUBDIR)
    if os.path.isdir(owned_dir):
        shutil.rmtree(owned_dir)
    for name in _OWNED_TOP_LEVEL_FILES:
        path = os.path.join(output_dir, name)
        if os.path.isfile(path):
            os.remove(path)


def build_site(articles: list[dict], output_dir: str, base_url: str) -> dict:
    """Перезаписывает файлы сайта в output_dir (см. _OWNED_* в
    clear_output_dir) — остальное содержимое output_dir не трогается.
    Возвращает статистику для отчёта."""
    clear_output_dir(output_dir)
    articles_dir = os.path.join(output_dir, _OWNED_SUBDIR)
    os.makedirs(articles_dir, exist_ok=True)

    for article in articles:
        path = os.path.join(articles_dir, slug_for(article))
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_article_html(article, base_url))

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index_html(articles, base_url))

    with open(os.path.join(output_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(render_sitemap_xml(articles, base_url))

    with open(os.path.join(output_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(render_robots_txt(base_url))

    # .nojekyll — без него GitHub Pages пропускает через Jekyll и молча
    # игнорирует файлы/папки, начинающиеся с "_" (у нас таких нет, но
    # это стандартная защитная мера для /docs-деплоя без явного намерения
    # использовать Jekyll).
    open(os.path.join(output_dir, ".nojekyll"), "w").close()

    return {"pages": len(articles), "output_dir": output_dir}