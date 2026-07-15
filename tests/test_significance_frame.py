import unittest

from parsers.base import RawArticle
from adaptation.editorial_engine import (
    EditorialEngine, SIGNIFICANCE_FRAME_PATTERNS, HONEST_NO_PRACTICAL_PATTERNS,
    _collect_body_blocks,
)


class TestCollectBodyBlocksSignificanceFallback(unittest.TestCase):
    """Реальный дефект (article id=483, "Стресс: неожиданный поворот"):
    базовое animal study без decomposed['practical'] раньше не получало
    вообще никакого блока значимости — _collect_body_blocks молча
    пропускала пустой practical. Теперь должен появиться fallback."""

    def test_appends_significance_frame_when_practical_empty(self):
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        blocks = _collect_body_blocks("stress", decomposed)
        self.assertTrue(blocks, "Блок значимости не добавился при пустом practical")
        self.assertIn(blocks[-1], [
            p.format(topic_prep_lower="стрессе", topic_gen_lower="стресса")
            for p in SIGNIFICANCE_FRAME_PATTERNS
        ])

    def test_uses_real_practical_value_when_present(self):
        decomposed = {"context": "", "method": "", "hook": "", "practical": "Снижение стресса помогает сну."}
        blocks = _collect_body_blocks("stress", decomposed)
        # Настоящий practical-вывод в блоке, а не рамка значимости.
        self.assertIn("Снижение стресса помогает сну.", blocks[-1])

    def test_significance_frame_distinct_from_honest_no_practical(self):
        """ТЗ: рамка значимости — не то же самое, что 'выводов нет' —
        разные банки, не задваивание одного и того же под новым именем."""
        self.assertNotEqual(set(SIGNIFICANCE_FRAME_PATTERNS), set(HONEST_NO_PRACTICAL_PATTERNS))


class TestSignificanceFrameInRealArticle(unittest.TestCase):
    def test_stress_isolation_animal_study_gets_significance_block(self):
        """Тот самый реальный случай, article id=483 (MeA Tac2-Nk3R
        signaling) — фундаментальное animal study без практического
        вывода для людей."""
        article = RawArticle(
            title="Sex-specific role of body weight in mediating stress susceptibility",
            url="https://example.com/483",
            abstract=(
                "We found that two-week social isolation during adolescence induced "
                "depressive-like behaviors in the sucrose preference test, forced "
                "swimming test and social interaction test in female but not male mice. "
                "Weight fluctuations are a hallmark of major depression."
            ),
            source="pubmed",
        )
        engine = EditorialEngine()
        passport = engine.analyze(article, "stress")
        self.assertFalse(passport["decomposed"].get("practical", "").strip())
        structure = engine.build_structure(passport)
        text = "\n\n".join(structure)
        has_significance_frame = any(
            phrase.split("{")[0] in text for phrase in SIGNIFICANCE_FRAME_PATTERNS
        )
        self.assertTrue(has_significance_frame, f"Рамка значимости не найдена в тексте:\n{text}")


if __name__ == "__main__":
    unittest.main()
