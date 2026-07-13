import unittest
from domain.knowledge.living import (
    KnowledgeVersion, KnowledgeDiff, OpenQuestion, Myth,
    create_knowledge_version, create_knowledge_diff,
    create_open_question, create_myth,
    build_knowledge_summary, detect_open_questions, detect_myths_from_contradictions,
)
from domain.knowledge.understanding import (
    UnderstandingModel, build_understanding_model, update_understanding_model,
    extract_practical_implications,
)


class TestLivingKnowledgeDataclasses(unittest.TestCase):
    def test_create_knowledge_version(self):
        kv = create_knowledge_version("sleep", "1.0", "Initial summary.", "First version.")
        self.assertEqual(kv.topic, "sleep")
        self.assertEqual(kv.version, "1.0")
        self.assertEqual(kv.summary, "Initial summary.")

    def test_create_knowledge_diff(self):
        kd = create_knowledge_diff("sleep", "1.0", "1.1", "Old text.", "New text.", "New evidence.")
        self.assertEqual(kd.from_version, "1.0")
        self.assertEqual(kd.to_version, "1.1")
        self.assertEqual(kd.reason, "New evidence.")

    def test_create_open_question(self):
        oq = create_open_question("dopamine", "Is dopamine only about pleasure?")
        self.assertEqual(oq.topic, "dopamine")
        self.assertEqual(oq.status, "open")

    def test_create_myth(self):
        m = create_myth("dopamine", "Dopamine is the pleasure hormone.", "Dopamine is about prediction and learning.")
        self.assertEqual(m.myth_text, "Dopamine is the pleasure hormone.")
        self.assertIn("prediction", m.correction)


class TestBuildKnowledgeSummary(unittest.TestCase):
    def test_empty_claims(self):
        summary = build_knowledge_summary([], [])
        self.assertIn("No established claims", summary)

    def test_with_claims(self):
        claims = [{"topic": "sleep", "claim_text": "Sleep improves memory."}]
        consensus = [{"support_count": 3, "contradict_count": 0, "confidence": 0.8}]
        summary = build_knowledge_summary(claims, consensus)
        self.assertIn("1 scientific claims", summary)
        self.assertIn("3 supporting", summary)


class TestDetectOpenQuestions(unittest.TestCase):
    def test_contested_claims_generate_questions(self):
        claims = [{"topic": "sleep", "claim_text": "Sleep deprivation has no effect."}]
        consensus = [{"consensus_level": "contested", "support_count": 1, "contradict_count": 3, "confidence": 0.3}]
        questions = detect_open_questions(claims, consensus)
        self.assertEqual(len(questions), 1)
        self.assertIn("Sleep deprivation", questions[0].question)

    def test_supported_claims_no_questions(self):
        claims = [{"topic": "sleep", "claim_text": "Sleep improves memory."}]
        consensus = [{"consensus_level": "supported", "support_count": 5, "contradict_count": 0, "confidence": 0.8}]
        questions = detect_open_questions(claims, consensus)
        self.assertEqual(len(questions), 0)


class TestDetectMyths(unittest.TestCase):
    def test_contradictions_generate_myths(self):
        claims = [{"topic": "dopamine", "claim_text": "Dopamine is only about pleasure."}]
        consensus = [{"contradict_count": 4, "support_count": 1, "consensus_level": "contested"}]
        myths = detect_myths_from_contradictions(claims, consensus)
        self.assertEqual(len(myths), 1)
        self.assertIn("incorrect", myths[0].correction.lower())

    def test_no_contradictions_no_myths(self):
        claims = [{"topic": "dopamine", "claim_text": "Dopamine affects motivation."}]
        consensus = [{"contradict_count": 0, "support_count": 5, "consensus_level": "supported"}]
        myths = detect_myths_from_contradictions(claims, consensus)
        self.assertEqual(len(myths), 0)


class TestUnderstandingModel(unittest.TestCase):
    def test_build_model_with_data(self):
        claims = [
            {"claim_text": "Sleep improves memory.", "topic": "sleep"},
            {"claim_text": "Sleep deprivation impairs cognition.", "topic": "sleep"},
        ]
        consensus = [
            {"consensus_level": "supported", "confidence": 0.8, "summary": "support=3; contradict=0"},
            {"consensus_level": "contested", "confidence": 0.4, "summary": "support=1; contradict=2"},
        ]
        model = build_understanding_model(
            topic="sleep",
            topic_ru="Сон",
            claims=claims,
            consensus_states=consensus,
            open_questions=["Does sleep timing matter?"],
            myths=["Sleep is only rest."],
        )
        self.assertEqual(model.topic, "sleep")
        self.assertEqual(model.topic_ru, "Сон")
        self.assertEqual(len(model.key_claims), 2)
        self.assertIn("Sleep improves memory.", model.key_claims)
        self.assertEqual(model.confidence_level, "moderate")
        self.assertEqual(len(model.open_questions), 1)
        self.assertEqual(len(model.myths), 1)

    def test_build_model_empty(self):
        model = build_understanding_model(
            topic="unknown",
            topic_ru="Неизвестно",
            claims=[],
            consensus_states=[],
            open_questions=[],
            myths=[],
        )
        self.assertEqual(model.confidence_level, "insufficient_data")
        self.assertEqual(len(model.key_claims), 0)

    def test_update_model_increments_version(self):
        model = UnderstandingModel(
            topic="sleep", topic_ru="Сон", summary="Old.", key_claims=["Claim 1."],
            consensus_points=[], open_questions=[], myths=[],
            practical_implications=[], confidence_level="moderate", version="1.0",
        )
        new_claims = [{"claim_text": "New claim."}]
        new_consensus = [{"confidence": 0.9}]
        updated = update_understanding_model(model, new_claims, new_consensus)
        self.assertEqual(updated.version, "1.1")
        self.assertIn("New claim.", updated.key_claims)
        self.assertEqual(updated.confidence_level, "high")

    def test_extract_practical_implications(self):
        claims = [
            {"claim_text": "Sleep рекомендует 8 часов для здоровья.", "topic": "sleep"},
            {"claim_text": "Brain processes information.", "topic": "sleep"},
        ]
        consensus = [
            {"consensus_level": "supported", "confidence": 0.8, "claim_text": "Sleep рекомендует 8 часов для здоровья."},
            {"consensus_level": "supported", "confidence": 0.8, "claim_text": "Brain processes information."},
        ]
        implications = extract_practical_implications(claims, consensus)
        self.assertEqual(len(implications), 1)
        self.assertIn("рекоменд", implications[0].lower())


if __name__ == "__main__":
    unittest.main()
