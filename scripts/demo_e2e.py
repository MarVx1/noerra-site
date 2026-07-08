"""
E2E demo: plan -> passport -> telegraph content -> simulate create page -> telegram preview
Run:
    python scripts/demo_e2e.py
"""
import os
import sys
import hashlib
from pathlib import Path

# Ensure project root is on sys.path for local script execution
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parsers.base import RawArticle
from adaptation.pipeline import Pipeline
from adaptation.editorial import generate_telegram_text

OUTPUT_DIR = Path("scripts/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pipeline = Pipeline()

article1 = RawArticle(
    title="Dopamine and motivation",
    url="https://example.com/article",
    abstract=(
        "A new study found that dopamine affects motivated behavior. The results show that learning speed improves when reward circuits are engaged."
    ),
    source="pubmed",
)

article2 = RawArticle(
    title="Reward circuits in the brain",
    url="https://example.com/article2",
    abstract=(
        "Study shows that reward-related brain areas influence decision-making. The evidence supports stronger motivation under reinforcement."
    ),
    source="arxiv",
)

articles = [article1, article2]

def simulate_create_telegraph_page(title: str, summary: str) -> str:
    """Simulate Telegraph page creation by writing an HTML file and returning a fake URL."""
    slug = hashlib.sha1(title.encode('utf-8')).hexdigest()[:8]
    path = OUTPUT_DIR / f"telegraph_{slug}.html"
    html = f"<html><head><meta charset='utf-8'><title>{title}</title></head><body><pre>{summary}</pre></body></html>"
    path.write_text(html, encoding='utf-8')
    return f"file://{path.resolve()}"


def run_demo():
    topic = 'dopamine'

    # Run cluster demo: create drafts for each article and a cluster draft
    # Single article pipeline
    result = pipeline.run_for_article(article1, topic)
    print("PLAN:", result.get("plan"))

    # Simulate telegraph page for the cluster
    telegraph_content = pipeline.engine.generate_cluster_text(topic, articles)
    telegraph_title = f"Noerra: {pipeline.planner.plan_cluster(topic, articles).get('title_hint', topic)}"
    telegraph_url = simulate_create_telegraph_page(telegraph_title, telegraph_content)
    print("\nTelegraph page simulated:", telegraph_url)

    # Telegram preview: use publication short version
    pub = result["publication"]
    tg_post = generate_telegram_text(article1, topic, telegraph_url)
    print("\nTelegram preview:\n")
    print(tg_post)

    # Critic output
    print("\nCritic review:\n")
    print(result.get("review"))

if __name__ == '__main__':
    run_demo()
