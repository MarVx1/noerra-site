import unittest

from scripts.generate_site import _evidence_badge, _row_to_article, _split_lead_from_body


class TestEvidenceBadge(unittest.TestCase):
    def test_none_when_no_passport(self):
        self.assertIsNone(_evidence_badge(None))
        self.assertIsNone(_evidence_badge(""))

    def test_capitalizes_first_letter_only(self):
        """Регрессия: .capitalize() лочит регистр всего хвоста строки, а
        _evidence_ru("moderate_high") возвращает "высокий (RCT)" — старая
        версия портила это в "высокий (rct)" (найдено на живой статье
        id=1015, 2026-07-20)."""
        self.assertEqual(_evidence_badge("moderate_high"), "🔬 Высокий (RCT)")

    def test_high_uses_microscope_emoji(self):
        self.assertEqual(_evidence_badge("high"), "🔬 Высокий (метаанализ/систематический обзор)")

    def test_limited_uses_chart_emoji(self):
        self.assertEqual(_evidence_badge("limited"), "📊 Ограниченный")

    def test_preliminary_uses_thought_emoji(self):
        self.assertEqual(_evidence_badge("preliminary"), "💭 Предварительный")

    def test_unknown_value_falls_back_gracefully(self):
        # classify_evidence_strength() всегда возвращает одно из известных
        # 6 значений, но badge не должен падать, если это когда-то не так.
        badge = _evidence_badge("something_new")
        self.assertTrue(badge.startswith("📊"))


class TestSplitLeadFromBody(unittest.TestCase):
    def test_strips_matching_first_paragraph(self):
        lead = "Есть неожиданная деталь в устройстве стресса."
        body = f"{lead}\n\nВторой абзац.\n\nТретий абзац."
        self.assertEqual(_split_lead_from_body(lead, body), "Второй абзац.\n\nТретий абзац.")

    def test_leaves_body_untouched_when_no_match(self):
        """Безопасный фолбэк: если сырой lead разошёлся с первым абзацем
        (например, simplify_text() что-то поменял) — просто не режем,
        а не отрезаем неправильный абзац."""
        lead = "Другой текст."
        body = "Первый абзац.\n\nВторой абзац."
        self.assertEqual(_split_lead_from_body(lead, body), body)

    def test_empty_lead_returns_body_unchanged(self):
        body = "Первый абзац.\n\nВторой абзац."
        self.assertEqual(_split_lead_from_body("", body), body)

    def test_lead_is_the_only_paragraph(self):
        lead = "Единственный абзац."
        self.assertEqual(_split_lead_from_body(lead, lead), "")


class TestRowToArticle(unittest.TestCase):
    def _row(self, **overrides):
        row = {
            "id": 483, "title": "Стресс: неожиданный поворот", "topic": "stress",
            "lead": "Лид-абзац.", "body": "Лид-абзац.\n\nОсновной текст.",
            "full_version": "Стресс: неожиданный поворот\n\nЛид-абзац.\n\nОсновной текст.",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "telegraph_url": "https://telegra.ph/x", "published_at": "2026-07-15 10:00:00",
            "created_at": "2026-07-14 09:00:00", "evidence_strength": "moderate_high",
        }
        row.update(overrides)
        return row

    def test_maps_core_fields(self):
        article = _row_to_article(self._row())
        self.assertEqual(article["id"], 483)
        self.assertEqual(article["topic"], "stress")
        self.assertEqual(article["topic_ru"], "Стресс")
        self.assertEqual(article["topic_emoji"], "😓")
        self.assertEqual(article["date"], "2026-07-15")
        self.assertEqual(article["evidence_badge"], "🔬 Высокий (RCT)")

    def test_lead_stripped_from_body_html(self):
        article = _row_to_article(self._row())
        self.assertEqual(article["lead_html"], "Лид-абзац.")
        self.assertEqual(article["body_html"], "Основной текст.")

    def test_missing_evidence_strength_gives_none_badge(self):
        article = _row_to_article(self._row(evidence_strength=None))
        self.assertIsNone(article["evidence_badge"])

    def test_missing_published_at_falls_back_to_created_at(self):
        article = _row_to_article(self._row(published_at=None))
        self.assertEqual(article["date"], "2026-07-14")

    def test_missing_lead_keeps_full_body(self):
        article = _row_to_article(self._row(lead=None))
        self.assertEqual(article["lead_html"], "")
        self.assertEqual(article["body_html"], "Лид-абзац.\n\nОсновной текст.")


if __name__ == "__main__":
    unittest.main()
