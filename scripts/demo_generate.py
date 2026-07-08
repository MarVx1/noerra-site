"""
Demo script to generate editorial outputs using EditorialPlanner and EditorialEngine.
Run:
    python scripts/demo_generate.py
"""
from parsers.base import RawArticle
from adaptation.editorial_engine import EditorialEngine
from adaptation.editorial_planner import EditorialPlanner

engine = EditorialEngine()
planner = EditorialPlanner()

# Sample articles
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

print("=== Single article editorial (Telegraph) ===")
print(engine.generate_text(engine.analyze(article1, 'dopamine'), engine.build_structure(engine.analyze(article1, 'dopamine'))))

print("\n=== Cluster telegraph ===")
print(engine.generate_cluster_text('dopamine', [article1, article2]))

print("\n=== Review ===")
print(engine.generate_review('dopamine', [article1, article2]))

print("\n=== Planner suggestion ===")
print(planner.plan_cluster('dopamine', [article1, article2]))
