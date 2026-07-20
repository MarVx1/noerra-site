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
    id             int
    title          str  — заголовок (уже готовый для <title>/<h1>)
    topic          str  — исходный ключ темы ("stress", "dopamine", ...)
    topic_ru       str  — русское название темы
    topic_emoji    str  — эмодзи темы (classifier.get_topic_emoji)
    lead_html      str  — лид-цитата (может быть пустой строкой — тогда
                           блок .lede не рендерится), уже проэкранирован
    body_html      str  — текст статьи БЕЗ лида (см. lead_html — вызывающая
                           сторона вырезает дублирующий первый абзац, см.
                           scripts/generate_site.py:_split_lead_from_body),
                           абзацы разделены "\\n\\n", инлайн <b>/<i> уже
                           безопасно проэкранированы (см.
                           adaptation/utils.py:esc_preserve_own_tags)
    description    str  — короткое plain-text описание для <meta description>
                           и подводки в списке статей на индексе
    evidence_badge str | None — готовый текст бейджа доказательности
                           ("🔬 Высокий (RCT)" и т.п.) или None, если для
                           статьи нет research_passports (бейдж просто не
                           рендерится, см. scripts/generate_site.py:_evidence_badge)
    source_url     str  — ссылка на оригинал источника (PubMed/arXiv/...)
    telegraph_url  str | None — ссылка на исходный пост в Telegraph, опционально
    date           str  — ISO-дата публикации, "YYYY-MM-DD"
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


# Слито из двух эталонных статичных макетов (demo_index.html/demo_article.html,
# ТЗ 2026-07-20 "довести генерируемый сайт до демо-дизайна") — оба файла
# несут собственный полный <style>, здесь он один на оба типа страниц, из-за
# чего два места пришлось СКОПИРОВАТЬ, а не взять как есть: голый `footer{}`
# в двух демо-файлах задаёт РАЗНЫЕ правила (index: простой текстовый подвал;
# article: подвал с CTA-кнопкой) — конфликт при общем стиле, решён через
# `.article-footer`. Аналогично `<article class="entry">` в demo_index.html
# столкнулся бы с голым `article{...}` из demo_article.html (тот же тег,
# другие правила) — здесь карточки списка не `<article>`, а `<div class="entry">`
# (см. render_index_html). Визуально это ничего не меняет — только теговый
# селектор, не класс.
_PAGE_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;500;600&display=swap');
    :root{
        --bg:#0d1e21; --bg-raised:#14343a; --border:#22403f;
        --text:#e9ece9; --text-dim:#9fb3ae; --text-faint:#6b8380;
        --primary:#2e9d8a; --gold:#d99a3c; --gold-bright:#ead9b0;
        --serif:'Newsreader',Georgia,serif; --sans:'Inter',-apple-system,sans-serif;
    }
    *{box-sizing:border-box; margin:0; padding:0;}
    body{background:var(--bg); color:var(--text); font-family:var(--sans);
         line-height:1.5; -webkit-font-smoothing:antialiased;}
    a{color:inherit; text-decoration:none;}

    /* header (индекс) */
    header{max-width:760px; margin:0 auto; padding:64px 24px 40px; border-bottom:1px solid var(--border);}
    .wordmark{display:flex; align-items:baseline; gap:14px; margin-bottom:22px;}
    .wordmark .mark{font-family:var(--serif); font-size:26px; font-weight:600; color:var(--gold-bright); letter-spacing:0.02em;}
    .wordmark .tagline{font-size:13px; color:var(--text-faint); letter-spacing:0.03em;}
    header p.lede{font-family:var(--serif); font-size:21px; font-weight:400; line-height:1.5; color:var(--text); max-width:600px;}
    header p.lede .accent{color:var(--gold-bright); font-style:italic;}
    .channel-link{display:inline-flex; align-items:center; gap:8px; margin-top:24px; font-size:14px; color:var(--gold); border:1px solid var(--border); padding:9px 16px; border-radius:20px; transition:border-color .15s;}
    .channel-link:hover{border-color:var(--gold);}
    .channel-link::before{content:"\\2192"; color:var(--gold-bright);}

    /* фильтр тем — чисто визуальный, без JS: сузить страницу до одной темы
       можно средствами CSS/JS не пришлось, кнопки не функциональны, как и
       в эталоне (demo_index.html) — там тоже просто <button>, без обработчиков. */
    nav.topics{max-width:760px; margin:0 auto; padding:28px 24px 0; display:flex; flex-wrap:wrap; gap:8px;}
    nav.topics button{font-family:var(--sans); font-size:13px; color:var(--text-dim); background:transparent; border:1px solid var(--border); border-radius:14px; padding:6px 13px; cursor:pointer; transition:all .15s;}
    nav.topics button:hover, nav.topics button.active{color:var(--bg); background:var(--gold-bright); border-color:var(--gold-bright);}

    /* список статей (индекс) */
    main{max-width:760px; margin:0 auto; padding:32px 24px 100px;}
    .entry{display:grid; grid-template-columns:44px 1fr auto; gap:18px; align-items:start; padding:26px 0; border-bottom:1px solid var(--border);}
    .entry:first-child{padding-top:8px;}
    .entry .emoji{font-size:22px; line-height:1.3;}
    .entry h2{font-family:var(--serif); font-weight:500; font-size:19px; line-height:1.35; margin-bottom:6px;}
    .entry h2 a{transition:color .15s;}
    .entry h2 a:hover{color:var(--gold-bright);}
    .entry p{font-size:14.5px; color:var(--text-dim); line-height:1.55; max-width:52ch;}
    .entry .meta{font-size:12px; color:var(--text-faint); white-space:nowrap; text-align:right; padding-top:4px;}
    .entry .evidence{display:inline-block; margin-top:8px; font-size:11.5px; color:var(--gold); border:1px solid rgba(201,151,74,0.35); border-radius:10px; padding:2px 9px;}

    footer{max-width:760px; margin:0 auto; padding:36px 24px 60px; border-top:1px solid var(--border); font-size:13px; color:var(--text-faint);}

    @media (max-width:560px){
        .entry{grid-template-columns:32px 1fr;}
        .entry .meta{display:none;}
        header{padding:44px 20px 32px;}
    }

    /* страница статьи */
    .topbar{max-width:680px; margin:0 auto; padding:28px 24px 0; display:flex; justify-content:space-between; align-items:center;}
    .topbar a{font-size:14px; color:var(--text-dim);}
    .topbar a:hover{color:var(--gold-bright);}
    .topbar .mark{font-family:var(--serif); font-weight:600; color:var(--gold-bright); font-size:17px;}

    article{max-width:680px; margin:0 auto; padding:40px 24px 30px;}

    .kicker{display:flex; align-items:center; gap:10px; margin-bottom:18px; font-size:13px; color:var(--text-faint);}
    .kicker .emoji{font-size:17px;}
    .kicker .evidence{color:var(--gold); border:1px solid rgba(201,151,74,0.35); border-radius:10px; padding:2px 9px; font-size:11.5px;}

    article h1{font-family:var(--serif); font-weight:600; font-size:34px; line-height:1.28; margin-bottom:22px; letter-spacing:-0.01em;}

    .lede{font-family:var(--serif); font-style:italic; font-size:19px; color:var(--text-dim); line-height:1.5; padding-left:16px; border-left:2px solid var(--gold); margin-bottom:34px;}

    .prose{font-size:16.5px; line-height:1.75; color:var(--text);}
    .prose p{margin-bottom:22px; max-width:62ch;}
    .prose strong{color:var(--gold-bright); font-weight:500;}

    .source-link{display:inline-flex; align-items:center; gap:6px; font-size:14px; color:var(--gold); margin-top:8px; border-bottom:1px solid rgba(201,151,74,0.3); padding-bottom:1px;}

    .article-footer{max-width:680px; margin:50px auto 0; padding:28px 24px 60px; border-top:1px solid var(--border);}
    .cta{display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;}
    .cta p{font-family:var(--serif); font-size:17px; color:var(--text-dim); max-width:32ch;}
    .cta a.btn{background:var(--gold-bright); color:var(--bg); font-weight:600; font-size:14px; padding:11px 22px; border-radius:22px; white-space:nowrap;}
    .fineprint{margin-top:26px; font-size:12.5px; color:var(--text-faint); line-height:1.6;}

    @media (max-width:560px){
        article h1{font-size:27px;}
        .lede{font-size:17px;}
    }
"""


_MONTHS_RU_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _format_date_ru(iso_date: str) -> str:
    """"2026-07-19" -> "19 июля 2026" (эталон — demo_index.html/
    demo_article.html показывают дату в человеческом виде, не ISO).
    sitemap.xml/robots.txt по-прежнему используют сырой ISO — это
    отдельная функция, не подмена date в самом article dict."""
    try:
        year, month, day = iso_date.split("-")
        return f"{int(day)} {_MONTHS_RU_GEN[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return iso_date


def render_article_html(article: dict, base_url: str) -> str:
    canonical = f"{base_url}articles/{slug_for(article)}"
    title = html.escape(article["title"])
    description = html.escape(article["description"])
    topic_ru = html.escape(article.get("topic_ru") or "")
    topic_emoji = html.escape(article.get("topic_emoji") or "")
    date_ru = _format_date_ru(article["date"])
    source_url = html.escape(article["source_url"] or "", quote=True)
    telegraph_url = article.get("telegraph_url")
    evidence_badge = article.get("evidence_badge")
    lead_html = article.get("lead_html") or ""

    source_line = (
        f'    <a class="source-link" href="{source_url}">&rarr; Оригинал исследования</a>\n'
        if source_url else ""
    )
    telegraph_line = (
        f'    <a class="source-link" href="{html.escape(telegraph_url, quote=True)}" style="margin-left:1.5em;">&rarr; Открыть в Telegraph</a>\n'
        if telegraph_url else ""
    )
    evidence_span = f'\n    <span class="evidence">{html.escape(evidence_badge)}</span>' if evidence_badge else ""
    # Лид — курсивная цитата на золотой плашке сразу под заголовком (класс
    # .lede в эталоне). Если лида нет (легаси-строка без drafts.lead),
    # блок просто не рендерится — тела статьи это не касается: см.
    # scripts/generate_site.py:_split_lead_from_body — body_html уже без
    # него, только когда лид действительно совпал с первым абзацем.
    lede_block = f'  <p class="lede">{lead_html}</p>\n\n' if lead_html else ""

    # "Главная находка" (карточка .card из эталона) сознательно не
    # рендерится — см. scripts/generate_site.py и отчёт по ТЗ 2026-07-20,
    # п.6: надёжного источника текста для неё в персистентных данных нет
    # (research_passports.key_findings — английский, сырой JSON-массив
    # строк, с артефактами вроде HTML-тегов/слипшихся секционных меток
    # у части статей; generate заново через EditorialEngine.analyze()
    # ради одной карточки — лишний перевод/связывание с движком для
    # read-only генератора статического сайта).

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Noerra</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="topbar">
  <a href="../index.html">&larr; Все разборы</a>
  <span class="mark">Noerra</span>
</div>

<article>
  <div class="kicker">
    <span class="emoji">{topic_emoji}</span>
    <span>{topic_ru} &middot; {date_ru}</span>{evidence_span}
  </div>
  <h1>{title}</h1>
{lede_block}  <div class="prose">
{_paragraphs_html(article['body_html'])}
{source_line}{telegraph_line}  </div>
</article>

<div class="article-footer">
  <div class="cta">
    <p>Такие разборы выходят регулярно в Telegram</p>
    <a class="btn" href="{html.escape(CHANNEL_URL, quote=True)}">Подписаться &rarr;</a>
  </div>
  <p class="fineprint">Noerra — независимый разбор научных публикаций. Мы не публикуем ради количества, не используем кликбейт и не выдаём гипотезы за факты.</p>
</div>
</body>
</html>
"""


def render_index_html(articles: list[dict], base_url: str) -> str:
    # Плоский список без группировки по темам (ТЗ 2026-07-20, п.1) —
    # порядок задаёт вызывающая сторона (database.db.get_published_articles_for_site
    # сортирует по дате публикации по убыванию), здесь только рендер.
    rows = []
    for a in articles:
        emoji = html.escape(a.get("topic_emoji") or "")
        title = html.escape(a["title"])
        description = html.escape(a.get("description") or "")
        evidence_badge = a.get("evidence_badge")
        evidence_span = f'\n      <span class="evidence">{html.escape(evidence_badge)}</span>' if evidence_badge else ""
        rows.append(
            f'  <div class="entry">\n'
            f'    <div class="emoji">{emoji}</div>\n'
            f'    <div>\n'
            f'      <h2><a href="articles/{slug_for(a)}">{title}</a></h2>\n'
            f'      <p>{description}</p>{evidence_span}\n'
            f'    </div>\n'
            f'    <div class="meta">{_format_date_ru(a["date"])}</div>\n'
            f'  </div>'
        )
    body = "\n\n".join(rows) if rows else "  <p>Пока нет опубликованных статей.</p>"

    # Таблички тем сверху — чисто визуальные (см. комментарий у nav.topics
    # в _PAGE_CSS), только темы, реально присутствующие среди статей —
    # не полный список из 9 канонических тем, как в demo_index.html
    # (тот список иллюстративный/статичный макет, а не спецификация).
    seen_topics: dict[str, str] = {}
    for a in articles:
        topic_ru = a.get("topic_ru") or "Наука"
        seen_topics.setdefault(topic_ru, a.get("topic_emoji") or "")
    topic_pills = "\n".join(
        f'  <button>{html.escape(emoji)} {html.escape(topic_ru)}</button>'
        for topic_ru, emoji in sorted(seen_topics.items())
    )

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
<header>
  <div class="wordmark">
    <span class="mark">Noerra</span>
    <span class="tagline">научные разборы без кликбейта</span>
  </div>
  <p class="lede">Мы не публикуем ради количества. Каждая статья — реальное исследование, переведённое и объяснённое так, чтобы было <span class="accent">приятно дочитать до конца</span>.</p>
  <a class="channel-link" href="{html.escape(CHANNEL_URL, quote=True)}">Читать в Telegram</a>
</header>

<nav class="topics" aria-label="Темы">
  <button class="active">Все темы</button>
{topic_pills}
</nav>

<main>
{body}
</main>

<footer>
  Noerra — независимый разбор научных публикаций. Источники: PubMed, arXiv, Frontiers, CyberLeninka.<br>
  Мы не публикуем ради количества, не используем кликбейт и не выдаём гипотезы за факты.
</footer>
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