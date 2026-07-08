"""
adaptation/editorial_planner.py — decides which story to tell and how to present it.

This module implements a lightweight EditorialPlanner that selects an angle,
recommendation for scenario, target audience and presentation hints.
"""
from typing import List
from parsers.base import RawArticle


class EditorialPlanner:
    """Simple planner that inspects articles and returns a plan for presentation."""

    def plan_for_article(self, article: RawArticle) -> dict:
        """Plan a story for a single article."""
        title = article.title or ""
        abstract = article.abstract or ""

        # simple heuristics
        is_practical = any(k in abstract.lower() for k in ("practical", "apply", "intervention", "method"))
        is_debunk = any(k in title.lower() for k in ("myth", "not", "false", "refute"))

        angle = "overview"
        if is_debunk:
            angle = "debunk"
        elif is_practical:
            angle = "practical"
        else:
            angle = "analysis"

        audience = "general"
        if "neuro" in title.lower() or "mechanism" in abstract.lower():
            audience = "informed"

        plan = {
            "angle": angle,
            "audience": audience,
            "title_hint": title,
            "lead_hint": abstract.split(".")[0] if abstract else "",
        }
        return plan

    def plan_cluster(self, topic: str, articles: List[RawArticle]) -> dict:
        """Plan a cluster story from multiple articles."""
        # basic cluster plan: angle based on diversity
        sources = set(a.source for a in articles)
        angle = "roundup"
        if len(sources) == 1:
            angle = "deep-dive"
        audience = "general"
        title_hint = f"Кластер по теме {topic}"
        return {
            "angle": angle,
            "audience": audience,
            "title_hint": title_hint,
        }
