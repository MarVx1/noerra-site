from typing import Optional

from parsers.base import RawArticle
from adaptation.editorial_engine import EditorialEngine
from adaptation.critic import EditorialCritic
from adaptation.publication import Publication
from database import db


class Pipeline:
    def __init__(self):
        self.engine = EditorialEngine()
        self.critic = EditorialCritic()

    def run_for_article(self, article: RawArticle, topic: str, article_id: Optional[int] = 0) -> dict:
        """Run full E2E pipeline for a single RawArticle.

        Returns dict with draft_id, publication and critic report.
        """
        # Analyze
        passport = self.engine.analyze(article, topic)

        # Build structure & render
        structure = self.engine.build_structure(passport)
        full_text = self.engine.generate_text(passport, structure)

        # Short version: first two paragraphs
        parts = [p for p in full_text.split('\n\n') if p.strip()]
        short = parts[0] if parts else full_text

        pub = Publication(
            title=passport.get("title", ""),
            subtitle=None,
            lead=passport.get("lead", ""),
            body="\n\n".join(parts[1:]) if len(parts) > 1 else "",
            short_version=short,
            full_version=full_text,
            sources=passport.get("sources", [article.url, article.source] if article.url else [article.source]),
            topic=passport.get("topic", topic),
            format=passport.get("suggested_format", "analysis"),
            confidence_score=passport.get("confidence_score", 0.0) or 0.0,
            audience=passport.get("audience", "general"),
        )

        # Critic review (+ Article Outline completeness check, Stage 4)
        named_blocks = self.engine.build_named_structure(passport)
        review = self.critic.review(passport, full_text, named_blocks=named_blocks)

        # Save draft to DB
        draft_id = db.save_draft(
            article_id or 0,
            pub.title,
            pub.lead,
            pub.body,
            pub.short_version,
            pub.full_version,
            ", ".join(pub.sources),
            pub.topic,
            pub.format,
            pub.confidence_score or 0.0,
            pub.audience,
        )

        return {
            "draft_id": draft_id,
            "publication": pub,
            "review": review,
            "passport": passport,
        }
