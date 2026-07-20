import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from scripts.site_builder import (
    build_site, clear_output_dir, render_article_html, render_index_html,
    render_robots_txt, render_sitemap_xml, slug_for, _format_date_ru,
)

BASE_URL = "https://example.github.io/noerra-bot/"


def _sample_articles():
    return [
        {
            "id": 483, "title": "Стресс: неожиданный поворот", "topic": "stress",
            "topic_ru": "Стресс", "topic_emoji": "😓",
            "lead_html": "Есть неожиданная деталь в устройстве стресса.",
            "body_html": "Первый абзац.\n\n<I>Аналогия.</i>",
            "description": "Короткое описание статьи про стресс.",
            "evidence_badge": "🔬 Высокий (RCT)",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "telegraph_url": "https://telegra.ph/stress-1", "date": "2026-07-15",
        },
        {
            "id": 877, "title": "Дофамин: как это работает", "topic": "dopamine",
            "topic_ru": "Дофамин", "topic_emoji": "💊",
            "lead_html": "",
            "body_html": "Текст про дофамин.",
            "description": "Короткое описание статьи про дофамин.",
            "evidence_badge": None,
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/2/",
            "telegraph_url": None, "date": "2026-07-16",
        },
    ]


class TestSlugFor(unittest.TestCase):
    def test_uses_numeric_id_not_title(self):
        # Русский заголовок в слаге не транслитерируется (см. докстринг
        # slug_for) — id гарантирует уникальность и стабильность ссылки.
        self.assertEqual(slug_for({"id": 483, "title": "Стресс"}), "article-483.html")

    def test_unique_per_id(self):
        a = slug_for({"id": 1, "title": "Одинаковый заголовок"})
        b = slug_for({"id": 2, "title": "Одинаковый заголовок"})
        self.assertNotEqual(a, b)


class TestFormatDateRu(unittest.TestCase):
    def test_converts_iso_to_human_russian(self):
        self.assertEqual(_format_date_ru("2026-07-19"), "19 июля 2026")
        self.assertEqual(_format_date_ru("2026-01-01"), "1 января 2026")

    def test_invalid_input_returned_unchanged(self):
        self.assertEqual(_format_date_ru("not-a-date"), "not-a-date")


class TestRenderArticleHtml(unittest.TestCase):
    def test_canonical_points_into_articles_subdir(self):
        """Регрессия: canonical/og:url раньше указывали на
        {base_url}article-483.html вместо {base_url}articles/article-483.html
        — файл реально лежит в articles/, см. build_site()."""
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn(
            '<link rel="canonical" href="https://example.github.io/noerra-bot/articles/article-483.html">',
            html,
        )
        self.assertIn(
            '<meta property="og:url" content="https://example.github.io/noerra-bot/articles/article-483.html">',
            html,
        )

    def test_title_and_h1_present(self):
        """Эталон (demo_article.html) — <title> с суффиксом " — Noerra",
        <h1> без него (голый заголовок статьи)."""
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn("<title>Стресс: неожиданный поворот — Noerra</title>", html)
        self.assertIn("<h1>Стресс: неожиданный поворот</h1>", html)

    def test_meta_description_present(self):
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn('<meta name="description" content="Короткое описание статьи про стресс.">', html)

    def test_source_and_channel_links_present(self):
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn('href="https://pubmed.ncbi.nlm.nih.gov/1/"', html)
        self.assertIn('href="https://t.me/noerra_publishes"', html)

    def test_telegraph_link_omitted_when_absent(self):
        html = render_article_html(_sample_articles()[1], BASE_URL)
        self.assertNotIn("Открыть в Telegraph", html)

    def test_body_paragraphs_split_on_blank_line(self):
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn("<p>Первый абзац.</p>", html)
        self.assertIn("<p><I>Аналогия.</i></p>", html)

    def test_title_html_escaped(self):
        article = dict(_sample_articles()[0], title='Тест <script>alert(1)</script> & "кавычки"')
        html = render_article_html(article, BASE_URL)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_lede_rendered_when_lead_present(self):
        """ТЗ 2026-07-20, п.5 — лид-цитата отдельным блоком .lede."""
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn('<p class="lede">Есть неожиданная деталь в устройстве стресса.</p>', html)

    def test_lede_omitted_when_lead_empty(self):
        html = render_article_html(_sample_articles()[1], BASE_URL)
        self.assertNotIn('class="lede"', html)

    def test_evidence_badge_in_kicker_when_present(self):
        """ТЗ 2026-07-20, п.4 — бейдж доказательности рядом с темой/датой."""
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn('<span class="evidence">🔬 Высокий (RCT)</span>', html)

    def test_evidence_badge_omitted_when_absent(self):
        """Статья без research_passports не должна ронять рендер — бейдж
        просто не выводится (см. scripts/generate_site.py:_evidence_badge)."""
        html = render_article_html(_sample_articles()[1], BASE_URL)
        self.assertNotIn('class="evidence"', html)

    def test_topic_emoji_and_date_in_kicker(self):
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn('<span class="emoji">😓</span>', html)
        self.assertIn("Стресс &middot; 15 июля 2026", html)

    def test_no_key_finding_card(self):
        """ТЗ 2026-07-20, п.6 — сознательно решено НЕ генерировать карточку
        "главная находка": надёжного источника текста для неё нет в
        персистентных данных (см. комментарий в site_builder.py)."""
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertNotIn('class="card"', html)
        self.assertNotIn("ГЛАВНАЯ НАХОДКА", html)


class TestRenderIndexHtml(unittest.TestCase):
    def test_flat_list_no_topic_grouping(self):
        """ТЗ 2026-07-20, п.1 — единый список статей, без секций по темам."""
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertNotIn('class="topic-heading"', html)
        self.assertNotIn("<ul", html)

    def test_links_to_both_articles(self):
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertIn('href="articles/article-483.html"', html)
        self.assertIn('href="articles/article-877.html"', html)

    def test_entry_shows_emoji_description_and_date(self):
        """ТЗ 2026-07-20, п.2/3 — эмодзи темы и подводка-описание в списке."""
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertIn('<div class="emoji">😓</div>', html)
        self.assertIn("<p>Короткое описание статьи про стресс.</p>", html)
        self.assertIn('<div class="meta">15 июля 2026</div>', html)

    def test_entry_evidence_badge_present_and_absent(self):
        """ТЗ 2026-07-20, п.4 — бейдж доказательности в списке, если есть."""
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertIn('<span class="evidence">🔬 Высокий (RCT)</span>', html)
        # У второй статьи evidence_badge=None — бейджа для неё в выводе нет,
        # но сам класс "evidence" встречается один раз (от первой статьи).
        self.assertEqual(html.count('class="evidence"'), 1)

    def test_topic_pills_only_for_present_topics(self):
        """Таблички тем — только реально встречающиеся, не все 9 канонических
        (demo_index.html показывает полный список как статичный макет)."""
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertIn(">😓 Стресс</button>", html)
        self.assertIn(">💊 Дофамин</button>", html)
        self.assertNotIn("⚡️ СДВГ</button>", html)

    def test_empty_list_does_not_crash(self):
        html = render_index_html([], BASE_URL)
        self.assertIn("Пока нет опубликованных статей", html)


class TestRenderSitemapXml(unittest.TestCase):
    def test_valid_xml_with_expected_urls(self):
        xml_text = render_sitemap_xml(_sample_articles(), BASE_URL)
        root = ET.fromstring(xml_text)  # raises if malformed
        locs = [el.text for el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertIn(f"{BASE_URL}index.html", locs)
        self.assertIn(f"{BASE_URL}articles/article-483.html", locs)
        self.assertIn(f"{BASE_URL}articles/article-877.html", locs)

    def test_lastmod_matches_article_date(self):
        xml_text = render_sitemap_xml(_sample_articles(), BASE_URL)
        self.assertIn("<lastmod>2026-07-15</lastmod>", xml_text)


class TestRenderRobotsTxt(unittest.TestCase):
    def test_points_at_sitemap(self):
        robots = render_robots_txt(BASE_URL)
        self.assertIn("Allow: /", robots)
        self.assertIn(f"Sitemap: {BASE_URL}sitemap.xml", robots)


class TestBuildSiteIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_writes_expected_files(self):
        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "sitemap.xml")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "robots.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, ".nojekyll")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "articles", "article-483.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "articles", "article-877.html")))

    def test_rerun_removes_stale_pages_for_dropped_articles(self):
        """Идемпотентность (ТЗ 2026-07-19): статья, выпавшая из выборки
        между запусками, не должна оставлять осиротевший HTML-файл."""
        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        build_site(_sample_articles()[:1], self.tmpdir, BASE_URL)
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "articles", "article-483.html")))
        self.assertFalse(os.path.isfile(os.path.join(self.tmpdir, "articles", "article-877.html")))

    def test_rerun_is_byte_identical(self):
        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        first = {}
        for root, _, files in os.walk(self.tmpdir):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    first[path] = f.read()

        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        for path, content in first.items():
            with open(path, "rb") as f:
                self.assertEqual(f.read(), content, f"{path} changed on identical rerun")

    def test_hidden_files_survive_clear(self):
        """clear_output_dir не должна трогать скрытые файлы/папки (.git и т.п.)."""
        os.makedirs(self.tmpdir, exist_ok=True)
        hidden_dir = os.path.join(self.tmpdir, ".git")
        os.makedirs(hidden_dir, exist_ok=True)
        marker = os.path.join(hidden_dir, "marker")
        with open(marker, "w") as f:
            f.write("keep me")

        clear_output_dir(self.tmpdir)

        self.assertTrue(os.path.isfile(marker))

    def test_unrelated_content_survives_clear_and_rebuild(self):
        """Регрессия (2026-07-19): docs/ в реальном репозитории уже
        содержал docs/architecture/ (ADR 0001 и другая документация,
        никак не связанная с сайтом) — первая версия clear_output_dir()
        чистила output_dir целиком по принципу "не скрытое — удалить" и
        снесла её при первом прогоне. build_site() обязан трогать только
        то, чем владеет сайт (articles/, index.html, sitemap.xml,
        robots.txt, .nojekyll), и ничего больше."""
        os.makedirs(self.tmpdir, exist_ok=True)
        unrelated_dir = os.path.join(self.tmpdir, "architecture")
        os.makedirs(unrelated_dir, exist_ok=True)
        unrelated_file = os.path.join(unrelated_dir, "adr-0001.md")
        with open(unrelated_file, "w", encoding="utf-8") as f:
            f.write("ADR 0001 — не трогать")
        unrelated_top_level = os.path.join(self.tmpdir, "CNAME")
        with open(unrelated_top_level, "w") as f:
            f.write("example.com")

        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        build_site(_sample_articles()[:1], self.tmpdir, BASE_URL)  # второй прогон, меньше статей

        self.assertTrue(os.path.isfile(unrelated_file))
        with open(unrelated_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ADR 0001 — не трогать")
        self.assertTrue(os.path.isfile(unrelated_top_level))

    def test_all_pages_are_parseable_html(self):
        build_site(_sample_articles(), self.tmpdir, BASE_URL)
        for root, _, files in os.walk(self.tmpdir):
            for name in files:
                if not name.endswith(".html"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    HTMLParser().feed(f.read())  # raises on structurally broken markup


if __name__ == "__main__":
    unittest.main()
