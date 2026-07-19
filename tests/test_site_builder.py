import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from scripts.site_builder import (
    build_site, clear_output_dir, render_article_html, render_index_html,
    render_robots_txt, render_sitemap_xml, slug_for,
)

BASE_URL = "https://example.github.io/noerra-bot/"


def _sample_articles():
    return [
        {
            "id": 483, "title": "Стресс: неожиданный поворот", "topic": "stress",
            "topic_ru": "Стресс", "body_html": "Первый абзац.\n\n<I>Аналогия.</i>",
            "description": "Короткое описание статьи про стресс.",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "telegraph_url": "https://telegra.ph/stress-1", "date": "2026-07-15",
        },
        {
            "id": 877, "title": "Дофамин: как это работает", "topic": "dopamine",
            "topic_ru": "Дофамин", "body_html": "Текст про дофамин.",
            "description": "Короткое описание статьи про дофамин.",
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
        html = render_article_html(_sample_articles()[0], BASE_URL)
        self.assertIn("<title>Стресс: неожиданный поворот</title>", html)
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


class TestRenderIndexHtml(unittest.TestCase):
    def test_groups_by_topic_and_links_articles(self):
        html = render_index_html(_sample_articles(), BASE_URL)
        self.assertIn("Стресс", html)
        self.assertIn("Дофамин", html)
        self.assertIn('href="articles/article-483.html"', html)
        self.assertIn('href="articles/article-877.html"', html)

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
