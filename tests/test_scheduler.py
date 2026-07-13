import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from parsers.base import RawArticle

from scheduler.scheduler import run_pipeline


class TestSchedulerPipeline(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.article = RawArticle(
            title="Dopamine Study",
            url="https://example.com/article",
            abstract="A study found a strong dopamine effect.",
            source="pubmed",
        )

    @patch("scheduler.scheduler.PubMedParser.run", return_value=[])
    @patch("scheduler.scheduler.ArxivParser.run", return_value=[])
    @patch("scheduler.scheduler.CyberLeninaParser.run", return_value=[])
    @patch("scheduler.scheduler.RSSParser.run", return_value=[])
    @patch("scheduler.scheduler.YouTubeParser.run", return_value=[])
    @patch("bot.bot.send_draft_for_editor", new_callable=AsyncMock)
    @patch("scheduler.scheduler._get_existing_urls_batch", return_value=set())
    @patch("scheduler.scheduler.save_article", return_value=1)
    @patch("scheduler.scheduler.save_summary")
    @patch("scheduler.scheduler.Pipeline")
    @patch("scheduler.scheduler.generate_post", return_value="telegram post")
    @patch("scheduler.scheduler.generate_summary", return_value="telegraph summary")
    @patch("scheduler.scheduler.classify", return_value=("dopamine", 0.9))
    @patch("scheduler.scheduler.score_article", return_value=42)
    async def test_run_pipeline_saves_new_article(
        self, score_article, classify, generate_summary, generate_post,
        pipeline_cls, save_summary, save_article, get_urls_batch, send_draft_for_editor,
        yt_run, rss_run, cyber_run, arxiv_run, pubmed_run,
    ):
        pubmed_run.return_value = [self.article]
        # Pipeline returns a publication with full_version and short_version
        # so save_summary gets the publication's text, not the mocked generate_summary
        from adaptation.publication import Publication
        pub = Publication(
            title="Test", subtitle=None, lead="lead", body="body",
            short_version="short", full_version="telegraph summary",
            sources=["pubmed"], topic="dopamine", format="analysis",
            confidence_score=0.5, audience="general",
        )
        pipeline_cls.return_value.run_for_article.return_value = {
            "draft_id": 123,
            "publication": pub,
            "review": {"passed": True, "hard_problems": [], "problems": []},
        }

        await run_pipeline()

        save_article.assert_called_once()
        # save_summary is called with publication's full_version as summary_ru
        save_summary.assert_called_once()
        call_args = save_summary.call_args
        assert call_args[0][0] == 1  # article_id
        assert "telegraph summary" in call_args[0][1] or "short" in call_args[0][1]

    @patch("scheduler.scheduler.PubMedParser.run", return_value=[])
    @patch("scheduler.scheduler.ArxivParser.run", return_value=[])
    @patch("scheduler.scheduler.CyberLeninaParser.run", return_value=[])
    @patch("scheduler.scheduler.RSSParser.run", return_value=[])
    @patch("scheduler.scheduler.YouTubeParser.run", return_value=[])
    @patch("bot.bot.send_draft_for_editor", new_callable=AsyncMock)
    @patch("scheduler.scheduler._get_existing_urls_batch", return_value={"https://example.com/article"})
    @patch("scheduler.scheduler.save_article")
    @patch("scheduler.scheduler.save_summary")
    @patch("scheduler.scheduler.Pipeline")
    @patch("scheduler.scheduler.generate_post", return_value="telegram post")
    @patch("scheduler.scheduler.generate_summary", return_value="telegraph summary")
    @patch("scheduler.scheduler.classify", return_value=("dopamine", 0.9))
    @patch("scheduler.scheduler.score_article", return_value=42)
    async def test_run_pipeline_skips_duplicate_article(
        self, score_article, classify, generate_summary, generate_post,
        pipeline_cls, save_summary, save_article, get_urls_batch, send_draft_for_editor,
        yt_run, rss_run, cyber_run, arxiv_run, pubmed_run,
    ):
        pubmed_run.return_value = [self.article]

        await run_pipeline()

        save_article.assert_not_called()
        save_summary.assert_not_called()

    @patch("scheduler.scheduler.PubMedParser.run", return_value=[])
    @patch("scheduler.scheduler.ArxivParser.run", return_value=[])
    @patch("scheduler.scheduler.CyberLeninaParser.run", return_value=[])
    @patch("scheduler.scheduler.RSSParser.run", return_value=[])
    @patch("scheduler.scheduler.YouTubeParser.run", return_value=[])
    @patch("bot.bot.send_draft_for_editor", new_callable=AsyncMock)
    @patch("scheduler.scheduler._get_existing_urls_batch", return_value=set())
    @patch("scheduler.scheduler.save_article")
    @patch("scheduler.scheduler.save_summary")
    @patch("scheduler.scheduler.Pipeline")
    @patch("scheduler.scheduler.generate_post")
    @patch("scheduler.scheduler.generate_summary")
    @patch("scheduler.scheduler.classify", return_value=("dopamine", 0.9))
    @patch("scheduler.scheduler.score_article", return_value=1)
    async def test_run_pipeline_skips_low_score_article(
        self, score_article, classify, generate_summary, generate_post,
        pipeline_cls, save_summary, save_article, get_urls_batch, send_draft_for_editor,
        yt_run, rss_run, cyber_run, arxiv_run, pubmed_run,
    ):
        pubmed_run.return_value = [self.article]

        await run_pipeline()

        # New pipeline saves low-score articles with status='low_score' for tracking
        save_article.assert_called_once_with(
            source='pubmed', title='Dopamine Study', url='https://example.com/article',
            abstract='A study found a strong dopamine effect.', external_id='',
            topic='dopamine', score=1, status='low_score',
        )
        # Pipeline is instantiated at the top of run_pipeline (before the loop)
        pipeline_cls.assert_called_once()
        # But run_for_article should NOT be called (article not processed)
        pipeline_cls.return_value.run_for_article.assert_not_called()
        # And summary/post should NOT be generated
        save_summary.assert_not_called()
        generate_summary.assert_not_called()
        generate_post.assert_not_called()
