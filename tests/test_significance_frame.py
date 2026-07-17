import unittest

from parsers.base import RawArticle
from adaptation.editorial_engine import (
    EditorialEngine, SIGNIFICANCE_FRAME_PATTERNS, SIGNIFICANCE_FRAME_PATTERNS_HUMAN,
    HONEST_NO_PRACTICAL_PATTERNS, _collect_body_blocks,
)
from adaptation.text_patterns import _pick


def _all_renderings(patterns, topic):
    """_pick() применяет падеж темы и авто-фикс предлогов (с/со) —
    сравнивать нужно с этим, а не с сырым .format()."""
    return [_pick([p], topic=topic) for p in patterns]


class TestCollectBodyBlocksSignificanceFallback(unittest.TestCase):
    """Реальный дефект (article id=483, "Стресс: неожиданный поворот"):
    базовое animal study без decomposed['practical'] раньше не получало
    вообще никакого блока значимости — _collect_body_blocks молча
    пропускала пустой practical. Теперь должен появиться fallback."""

    def test_appends_significance_frame_when_practical_empty(self):
        """Без явного study_type/abstract с маркерами животных — честный
        нейтральный (human) банк, не утверждение про лабораторию."""
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        blocks = _collect_body_blocks("stress", decomposed)
        self.assertTrue(blocks, "Блок значимости не добавился при пустом practical")
        self.assertIn(blocks[-1], _all_renderings(SIGNIFICANCE_FRAME_PATTERNS_HUMAN, "stress"))

    def test_uses_lab_frame_for_animal_study_abstract(self):
        """Реальный случай (article id=483) — study_type "unknown" (сам
        классификатор не различает животных/людей), но абстракт явно
        про мышей — тут уместна рамка "лабораторное исследование"."""
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        blocks = _collect_body_blocks(
            "stress", decomposed,
            abstract="Исследование на мышах показало изменения поведения.",
        )
        self.assertIn(blocks[-1], _all_renderings(SIGNIFICANCE_FRAME_PATTERNS, "stress"))

    def test_uses_human_frame_for_classified_human_study_type(self):
        """Реальный дефект (драфт "Сон: итоги последних исследований",
        систематический обзор, доказательность "Высокий"): рамка
        значимости заявляла "это лабораторное исследование", хотя
        study_type=systematic_review — по определению исследование на
        людях (2026-07-16)."""
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        blocks = _collect_body_blocks(
            "sleep", decomposed, abstract="", study_type="systematic_review",
        )
        self.assertIn(blocks[-1], _all_renderings(SIGNIFICANCE_FRAME_PATTERNS_HUMAN, "sleep"))
        self.assertNotIn("лабораторное исследование", blocks[-1])

    def test_uses_real_practical_value_when_present(self):
        decomposed = {"context": "", "method": "", "hook": "", "practical": "Снижение стресса помогает сну."}
        blocks = _collect_body_blocks("stress", decomposed)
        # Настоящий practical-вывод в блоке, а не рамка значимости.
        self.assertIn("Снижение стресса помогает сну.", blocks[-1])

    def test_significance_frame_distinct_from_honest_no_practical(self):
        """ТЗ: рамка значимости — не то же самое, что 'выводов нет' —
        разные банки, не задваивание одного и того же под новым именем."""
        self.assertNotEqual(set(SIGNIFICANCE_FRAME_PATTERNS), set(HONEST_NO_PRACTICAL_PATTERNS))
        self.assertNotEqual(set(SIGNIFICANCE_FRAME_PATTERNS_HUMAN), set(HONEST_NO_PRACTICAL_PATTERNS))

    def test_animal_marker_wins_over_human_study_type_ordering(self):
        """Регрессия (ТЗ 2026-07-16): проверка на животных стояла ПОСЛЕ
        проверки study_type и потому была недостижима для мета-анализа/РКИ
        на грызунах — те же слова дизайна одинаково употребимы и для
        людей, и для животных. "Мы объединили данные 40 исследований на
        грызунах и мышах" при study_type="meta_analysis" раньше получало
        человеческий банк вместо лабораторного."""
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        blocks = _collect_body_blocks(
            "stress", decomposed,
            abstract="Мы объединили данные 40 исследований на грызунах и мышах.",
            study_type="meta_analysis",
        )
        self.assertIn(blocks[-1], _all_renderings(SIGNIFICANCE_FRAME_PATTERNS, "stress"))

    def test_new_animal_markers_detected(self):
        """Обезьяны/макаки/данио/in vitro — расширение списка маркеров
        (2026-07-16), "обезьян" подтверждено живым переводом (article
        id=876)."""
        decomposed = {"context": "", "method": "", "hook": "", "practical": ""}
        for abstract in (
            "Исследование на обезьянах показало изменения активности.",
            "У макак наблюдалось изменение поведения.",
            "Личинки данио были помечены флуоресцентным маркером.",
            "Клетки культивировали in vitro в течение недели.",
        ):
            with self.subTest(abstract=abstract):
                blocks = _collect_body_blocks("stress", decomposed, abstract=abstract)
                self.assertIn(blocks[-1], _all_renderings(SIGNIFICANCE_FRAME_PATTERNS, "stress"))


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
