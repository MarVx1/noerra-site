"""Editorial Critic: scientific and style checks aligned with Noerra Manifesto."""
from typing import List, Dict, Any


class EditorialCritic:
    """Run checks on scientific integrity, clarity, and manifesto alignment."""

    def check_scientific(self, passport: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        confidence = passport.get("confidence_score", 0)
        if confidence <= 0.35:
            issues.append("Low confidence in findings (recommend verification of evidence).")
        if not passport.get("main_idea"):
            issues.append("Main idea not detected.")
        evidence = passport.get("evidence_strength", "")
        # Only flag "weak" — "preliminary" and "limited" are acceptable for preprints/early research
        if evidence == "weak":
            issues.append(f"Evidence strength is low: {evidence}.")
        if not passport.get("limitations") and evidence in {"high", "moderate_high"}:
            # Only require limitations for strong evidence (where they matter most)
            issues.append("Limitations are not stated.")
        if not passport.get("sources"):
            issues.append("Sources are not provided.")
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
        hype_markers = ("revolutionary", "breakthrough", "miracle", "first-ever", "революцион", "прорыв")
        if any(m in lower for m in hype_markers):
            issues.append("Sensational language detected; avoid hype.")
        return issues

    def check_clarity(self, text: str) -> List[str]:
        issues: List[str] = []
        if len(text.split()) < 50:
            issues.append("Text too short to be a standalone publication.")
        if text.count("\n\n") < 2:
            issues.append("Consider adding more paragraph breaks for readability.")
        if len(text) > 2000 and "what changed" not in text.lower() and "что изменилось" not in text.lower():
            issues.append("Long text does not explicitly explain what changed.")
        return issues

    def check_practical_value(self, text: str) -> List[str]:
        issues: List[str] = []
        lower = text.lower()
        practical_markers = ("practical", "recommend", "should", "may help", "важно", "рекоменд", "польз")
        if not any(m in lower for m in practical_markers):
            issues.append("Practical implications are not clear.")
        return issues

    def check_myths(self, text: str) -> List[str]:
        issues: List[str] = []
        lower = text.lower()
        myth_markers = ("myth", "misconception", "common belief", "миф", "заблужд", "ошибочн")
        if any(m in lower for m in myth_markers):
            return []
        issues.append("No explicit myth/misconception addressed; consider adding clarification if relevant.")
        return []

    def review(self, passport: Dict[str, Any], publication_text: str) -> dict:
        scientific = self.check_scientific(passport)
        uncertainty = self.check_uncertainty(passport, publication_text)
        clarity = self.check_clarity(publication_text)
        practical = self.check_practical_value(publication_text)
        myths = self.check_myths(publication_text)
        problems = scientific + uncertainty + clarity + practical + myths
        return {
            "passed": len(problems) <= 1,
            "problems": problems,
            "scientific": scientific,
            "uncertainty": uncertainty,
            "clarity": clarity,
            "practical": practical,
            "myths": myths,
        }
