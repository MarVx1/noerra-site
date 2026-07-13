"""Editorial Critic: scientific and style checks aligned with Noerra Manifesto."""
from typing import List, Dict, Any
import re

from adaptation.style_metrics import compute_style_metrics, MAX_SENTENCE_WORDS

# Проблемы, которые блокируют публикацию (hard).
# Остальные — soft: показываются редактору, но не блокируют.
HARD_PROBLEM_TEXTS = {
    "Main idea not detected.",
    "Sources are not provided.",
    "Low confidence in findings (recommend verification of evidence).",
    "Evidence strength is low: weak.",
    "Duplicate sentences detected in text.",
    "Analogy is missing.",
    "Practical value is false but no honest fallback phrase found in text.",
}

# Слова/фразы, которые превращают текст в "жёлтую" сенсацию — запрещены
# EDITORIAL_PLAYBOOK.md, Правило №8 ("Никакого драматизма").
HYPE_MARKERS = (
    "revolutionary", "breakthrough", "miracle", "first-ever",
    "революц", "прорыв", "сенсац",
    "учёные доказали", "ученые доказали",
    "полностью меняет", "шокирующ", "невероятн", "единственный способ",
)

# Канцелярские обороты, запрещённые EDITORIAL_ENGINE.md ("Запрещённые
# конструкции") — делают текст похожим на дипломную работу.
CANCELLERISM_MARKERS = (
    "в данной работе", "настоящее исследование", "авторы исследования",
    "в ходе исследования", "учёные обнаружили", "ученые обнаружили",
    "исследование демонстрирует", "следует отметить", "таким образом",
    "было установлено",
)


class EditorialCritic:
    """Run checks on scientific integrity, clarity, and manifesto alignment."""

    def check_scientific(self, passport: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        confidence = passport.get("confidence_score", 0)
        evidence = passport.get("evidence_strength", "")
        
        # Low confidence — hard only if evidence is "weak"
        if confidence <= 0.35 and evidence == "weak":
            issues.append("Low confidence in findings (recommend verification of evidence).")
        elif confidence <= 0.35 and evidence in {"preliminary", "limited"}:
            issues.append("Limited evidence strength: preliminary/limited — recommend verification.")
        
        if not passport.get("main_idea"):
            issues.append("Main idea not detected.")
        
        # Only flag "weak" as hard — "preliminary" and "limited" are acceptable for preprints/early research
        if evidence == "weak":
            issues.append(f"Evidence strength is low: {evidence}.")
        if not passport.get("limitations") and evidence in {"high", "moderate_high"}:
            # Only require limitations for strong evidence (where they matter most)
            issues.append("Limitations are not stated.")
        if not passport.get("sources"):
            issues.append("Sources are not provided.")
        return issues

    def check_analogy_present(self, passport: Dict[str, Any]) -> List[str]:
        """Analogy (Stage 7): без аналогии статья не должна публиковаться.

        Hard-check безопасен сразу: build_analogy() всегда возвращает
        непустую строку (есть generic fallback по сценарию), поэтому
        проверка сработает только при поломке wiring, а не из-за
        качества контента.
        """
        if not passport.get("analogy"):
            return ["Analogy is missing."]
        return []

    def check_outline_complete(self, named_blocks: Dict[str, str]) -> List[str]:
        """Article Outline (Stage 4): все обязательные блоки должны быть на месте.

        hook/reader_question/analogy уже покрыты отдельными hard-check'ами
        (main_idea, reader_question wiring, analogy) — здесь это wiring-guard
        на случай регрессии в build_named_structure(). why/caveat/what_science_found
        безусловно добавляются существующим кодом, поэтому это soft-проверка:
        падение сигнализирует о поломке, а не о качестве контента.
        """
        issues: List[str] = []
        required = ("hook", "reader_question", "what_science_found", "analogy", "why", "caveat")
        missing = [name for name in required if not named_blocks.get(name)]
        if missing:
            issues.append(f"Outline block(s) missing: {', '.join(missing)}.")
        return issues

    def check_uncertainty(self, passport: Dict[str, Any], text: str) -> List[str]:
        issues: List[str] = []
        lower = text.lower()
        uncertainty_markers = (
            "may", "might", "could", "suggests", "potentially", "likely",
            "неопредел", "возможно", "вероятно", "требует", "огранич",
        )
        has_uncertainty = any(m in lower for m in uncertainty_markers)
        if not has_uncertainty and passport.get("evidence_strength") in {"weak", "preliminary"}:
            issues.append("Uncertainty is not acknowledged despite limited evidence.")
        if any(m in lower for m in HYPE_MARKERS):
            issues.append("Sensational language detected; avoid hype.")
        return issues

    def check_style_language(self, text: str) -> List[str]:
        """Проверяет канцеляризмы, запрещённые EDITORIAL_ENGINE.md.

        Пока soft — фиксируем факт нарушения, не блокируя публикацию,
        до тех пор, пока Simplifier (Фаза 5) не начнёт реально их убирать.
        """
        issues: List[str] = []
        lower = text.lower()
        if any(m in lower for m in CANCELLERISM_MARKERS):
            issues.append("Bureaucratic/cancellerism phrasing detected.")
        return issues

    def check_clarity(self, text: str) -> List[str]:
        issues: List[str] = []
        if len(text.split()) < 50:
            issues.append("Text too short to be a standalone publication.")
        if text.count("\n\n") < 2:
            issues.append("Consider adding more paragraph breaks for readability.")
        if len(text) > 2000 and "what changed" not in text.lower() and "что изменилось" not in text.lower():
            issues.append("Long text does not explicitly explain what changed.")

        # Стилевые метрики ТЗ (12-20 слов/предложение, макс 25, абзац ≤4
        # предложений) — soft на старте (rollout burn-in), promotion в hard
        # запланирован после того, как Simplifier (Stage 6) начнёт реально
        # снижать длину предложений на практике.
        report = compute_style_metrics(text)
        if report.long_sentences:
            issues.append(f"{len(report.long_sentences)} sentence(s) exceed {MAX_SENTENCE_WORDS} words.")
        if report.long_paragraphs:
            issues.append("Paragraph(s) exceed recommended length (4 sentences).")
        return issues

    def check_rhythm(self, text: str) -> List[str]:
        """Editorial Polish (Stage 10): монотонность абзацев.

        Если 2+ абзаца подряд начинаются с одного и того же слова, текст
        читается механически/шаблонно — прямое нарушение "естественности
        языка" из ТЗ. Rule-based ограничение: ловит только буквальное
        повторение первого слова, не любую форму монотонности ритма.
        """
        issues: List[str] = []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        first_words = [p.split()[0].lower().strip(".,!?:;—-") for p in paragraphs if p.split()]
        for i in range(len(first_words) - 1):
            if first_words[i] and first_words[i] == first_words[i + 1]:
                issues.append(
                    f"Consecutive paragraphs start with the same word ({first_words[i]!r}) — monotonous rhythm."
                )
                break
        return issues

    def check_practical_honesty(self, passport: Dict[str, Any], text: str) -> List[str]:
        """Practical Value (Stage 8): защита от регрессии выдуманного совета.

        Честный fallback (editorial_engine.HONEST_NO_PRACTICAL_PATTERNS)
        рендерится только в сценарии "practical" при отсутствии реального
        маркера пользы (_build_practical_block) — для остальных сценариев
        отсутствие practical_value означает просто честное умолчание
        (блок практической пользы не добавляется вовсе, что не является
        фабрикацией). Поэтому проверка нарочно ограничена сценарием
        "practical", иначе она ложно срабатывала бы на легитимном умолчании.

        Импорт лениво внутри метода, чтобы не создавать цикл импортов между
        critic.py и editorial_engine.py.
        """
        if passport.get("scenario") != "practical" or passport.get("practical_value"):
            return []
        from adaptation.editorial_engine import HONEST_NO_PRACTICAL_PATTERNS
        if any(p in text for p in HONEST_NO_PRACTICAL_PATTERNS):
            return []
        return ["Practical value is false but no honest fallback phrase found in text."]

    def check_practical_value(self, text: str) -> List[str]:
        issues: List[str] = []
        lower = text.lower()
        practical_markers = ("practical", "recommend", "should", "may help", "важно", "рекоменд", "польз", "практич")
        if not any(m in lower for m in practical_markers):
            issues.append("Practical implications are not clear.")
        return issues

    def check_myths(self, text: str, scenario: str | None = None) -> List[str]:
        """Debunk-статьи должны явно называть развенчиваемый миф/заблуждение.

        Раньше это была мёртвая проверка: `return []` внутри `if` был
        недостижим для непустого результата, а безусловный `return []` в
        конце всегда возвращал пустой список независимо от найденных
        маркеров — метод не мог сообщить о проблеме ни при каких условиях.
        Также ограничено сценарием "debunk": вне этого сценария статья не
        обязана упоминать миф, и глобальная проверка давала бы много
        ложных срабатываний.
        """
        if scenario != "debunk":
            return []
        lower = text.lower()
        myth_markers = ("myth", "misconception", "common belief", "миф", "заблужд", "ошибочн")
        if any(m in lower for m in myth_markers):
            return []
        return ["Debunk scenario but no explicit myth/misconception phrase found."]

    def check_duplicates(self, text: str) -> List[str]:
        """Проверяет текст на повторяющиеся предложения."""
        issues: List[str] = []
        # Разбиваем на абзацы и предложения
        sentences = []
        for para in text.split("\n\n"):
            for s in re.split(r"(?<=[.!?])\s+", para.strip()):
                s = s.strip()
                if len(s) >= 20:
                    sentences.append(re.sub(r"\s+", " ", s.lower()[:120]))

        if len(sentences) < 2:
            return issues

        seen: dict[str, int] = {}
        for s in sentences:
            seen[s] = seen.get(s, 0) + 1

        duplicates = [s for s, count in seen.items() if count > 1]
        if duplicates:
            issues.append("Duplicate sentences detected in text.")
        return issues

    def check_grammar(self, text: str) -> List[str]:
        """Базовая проверка грамматики: несклонённые существительные."""
        issues: List[str] = []
        # Проверяем типичные грамматические ошибки с названиями тем
        grammar_errors = [
            ("для Дофамин", "для Дофамина"),
            ("для Сон", "для Сна"),
            ("для Стресс", "для Стресса"),
            ("для Тревожность", "для Тревожности"),
            ("для Когниция", "для Когниции"),
            ("о Дофамин ", "о Дофамине "),
            ("о Сон ", "о Сне "),
            ("о Стресс ", "о Стрессе "),
            ("на Дофамин ", "на Дофамин "),
        ]
        for bad, _good in grammar_errors:
            if bad in text:
                issues.append("Grammar error: noun not declined correctly.")
                break
        return issues

    def review(
        self,
        passport: Dict[str, Any],
        publication_text: str,
        named_blocks: Dict[str, str] | None = None,
    ) -> dict:
        scientific = self.check_scientific(passport)
        analogy = self.check_analogy_present(passport)
        uncertainty = self.check_uncertainty(passport, publication_text)
        clarity = self.check_clarity(publication_text)
        practical = self.check_practical_value(publication_text)
        practical_honesty = self.check_practical_honesty(passport, publication_text)
        myths = self.check_myths(publication_text, passport.get("scenario"))
        duplicates = self.check_duplicates(publication_text)
        grammar = self.check_grammar(publication_text)
        style_language = self.check_style_language(publication_text)
        rhythm = self.check_rhythm(publication_text)
        outline = self.check_outline_complete(named_blocks) if named_blocks is not None else []
        problems = (
            scientific + analogy + uncertainty + clarity + practical + practical_honesty
            + myths + duplicates + grammar + style_language + rhythm + outline
        )

        hard_problems = [p for p in problems if p in HARD_PROBLEM_TEXTS]
        soft_problems = [p for p in problems if p not in HARD_PROBLEM_TEXTS]

        return {
            "passed": len(hard_problems) == 0,
            "problems": problems,
            "hard_problems": hard_problems,
            "soft_problems": soft_problems,
            "scientific": scientific,
            "analogy": analogy,
            "uncertainty": uncertainty,
            "clarity": clarity,
            "practical": practical,
            "practical_honesty": practical_honesty,
            "myths": myths,
            "duplicates": duplicates,
            "grammar": grammar,
            "style_language": style_language,
            "rhythm": rhythm,
            "outline": outline,
        }
