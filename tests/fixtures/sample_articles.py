from parsers.base import RawArticle


SAMPLE_ARTICLES = [
    RawArticle(
        title="New insights into dopamine and motivation",
        url="https://example.com/dopamine",
        abstract=(
            "A newly published study reports that stimulating dopamine circuits improves motivation. "
            "The evidence suggests a reproducible effect across two independent cohorts. "
            "The authors recommend further research into clinical translation."
        ),
        source="pubmed",
    ),
    RawArticle(
        title="A practical approach to sleep optimization",
        url="https://example.com/sleep",
        abstract=(
            "The study proposes a simple bedtime routine that supports circadian alignment. "
            "Participants reported improved sleep quality and reduced daytime fatigue. "
            "The protocol may help people with mild insomnia."
        ),
        source="arxiv",
    ),
    RawArticle(
        title="Review of recent findings in stress neuroscience",
        url="https://example.com/stress",
        abstract=(
            "This review summarizes current evidence on stress-related brain circuitry. "
            "Several recent studies converge on the role of prefrontal-amygdala pathways. "
            "The paper highlights open questions about stress resilience."
        ),
        source="cyberleninka",
    ),
]
